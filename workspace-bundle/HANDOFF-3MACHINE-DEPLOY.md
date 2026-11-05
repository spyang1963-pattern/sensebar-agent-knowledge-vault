# HANDOFF — 三機一鍵部署（PC1 / PC2 / PC3）

> 建立：2026-11-04
> 目標：三台機器都能「一鍵部署到與 notebook 一致的能力」，任務能力對齊，工作分配等三機都上線後再調。
> 相關文件：`workspace-bundle/ONBOARDING.md`（部署手冊）、`workspace-bundle/infra/PROVISIONING.md`（環境盤點）

## 0. 已確認的決策（2026-11-04）

| 項目 | 決策 |
|---|---|
| 工作區路徑 | 三機一律 `D:\AI-Agent-Workspace`（與 notebook 相同） |
| 能力 | 每台都是完整副本，任務能力與 notebook 一致（不分管制） |
| 工作分配 | 三機部署完成後再調整；調整前仍遵守「單一寫入者」 |
| 排程 | 部署階段**不自動註冊**；確認單一寫入者後才啟用 |

## 1. 本次已完成（2026-11-04）

### P0 修復：`setup_new_pc.bat`

| 問題 | 修法 |
|---|---|
| 遠端版本仍指舊路徑 `D:\!!AI agent 專案夾\...` | 統一 `PROJECT_DIR=D:\AI-Agent-Workspace`（可用環境變數覆蓋） |
| `git clone` 到子資料夾，與 `PROJECT_DIR` 不一致 | clone 直接落到 `%PROJECT_DIR%`；目錄存在但非 repo 時明確中止 |
| `!KEY!` 沒有 `setlocal enabledelayedexpansion` → 金鑰被寫成字面 `!KEY!` | 檔頭加 `setlocal enabledelayedexpansion`；寫檔改用 `>"file" echo !GROQ_KEY!` |
| 「一鍵」只裝 6 個套件，沒接 bundle | 改呼叫 `infra/update.py` + `requirements-{video,finance,stock}.txt` + `external_tools.ps1` + `health_check.py` |
| 無從驗證 | 新增 `--dry-run`（只印步驟、不寫入）；結尾自動印機器身份與待辦 |

### 其他修正

- `workspace-bundle/infra/update.py`：`pip install` timeout 120s → **900s**、`git pull` 60s → **300s**（首次安裝 whisper 常超過 2 分鐘，原本會誤判失敗）。
- 批次檔改為**純 ASCII**：中文 `.bat` 在 cp950 / 65001 主控台間會破行（實際踩到 `'tup_new_pc.bat' is not recognized`）。中文說明一律留在 md。

### 驗證

```powershell
cd D:\AI-Agent-Workspace
setup_new_pc.bat --dry-run     # 應 exit 0、列出 10 步且不變更環境
```

本機（notebook）`health_check.py --json` 實測：video 線全綠、finance 僅缺 `telegram_env`、套件缺口 0。

## 2. 待辦（依序）

### Step 2 — 統一「機器身份／角色」來源 ✅ 完成（2026-11-04）

原本三處不一致，已收斂為 **`config.py` 單一來源**：

| 項目 | 修法 |
|---|---|
| `health_check.py` 自帶機器表（只列 notebook/PC3/NAS、PC3 IP 誤填 notebook） | 移除 `MACHINES`，改讀 `config.MACHINE / MACHINE_ROLES / TAILSCALE_IPS`；報告新增 `hostname`、`machine_ip` |
| `config.py` 角色是分工制（downloader/adhoc_worker） | 改為 `worker / harvester` 的「主要職責註記」，並註明全功能；新增 `get_machine_info()` |
| `TAILSCALE_IPS` 缺 PC3 | 加 `"pc3": None`（待遷移後以 `tailscale ip -4` 補），不再沿用 notebook IP |
| `health_check.py` 設定檔路徑錯（`workspace-bundle/config/...`） | 改 `workspace-bundle/infra/config/...`＋root `notify_config.yaml`；移除永遠 ❌ 的 `.env` 檢查 |
| `task_manager_gui.py` 硬寫 pc1/pc2 IP、PC3 會 KeyError | 卡片改由 `TAILSCALE_IPS` 產生（含 pc3，IP 未設定會顯示「未設定」） |
| 文件排程時間 22:00 | 統一為實際值 **22:30**（ONBOARDING / PROVISIONING） |

驗證（notebook）：
```
machine=notebook  role=harvester  ip=100.111.44.63
config: machine.yaml ✅ / notify_config.yaml ✅
GUI get_machines(): notebook(本機) / pc1 / pc2 / pc3(未設定)
```

**刻意未改**：`MACHINE_PATHS["pc3"]` 仍指 `D:\sensebar-agent-knowledge-vault`。PC3 是現役收成機，先行改路徑會讓它拉到新 config 後找不到 output/working；改為遷移當天切換（見 Step 5）。

### Step 3 — 單一入口 `deploy.ps1` ✅ 完成（2026-11-04）

`workspace-bundle/infra/setup/deploy.ps1`

```powershell
# 先看會做什麼（不安裝、不註冊）
deploy.ps1 -Machine pc1 -DryRun

# 實際部署（呼叫 setup_new_pc.bat）
deploy.ps1 -Machine pc1

# 已裝好，只做身份 + 健檢
deploy.ps1 -SkipSetup

# 切換日：註冊 / 移除排程
deploy.ps1 -SkipSetup -RegisterTasks
deploy.ps1 -SkipSetup -UnregisterTasks
```

- **身份檢查**：讀 `config.py`（與 health_check 同一來源）。主機名未註冊（`unknown-*`）或與 `-Machine` 不符 → **中止並印出要加的 `MACHINE_ALIASES` 那行**，避免在錯的機器建任務。
- **程式碼狀態**：印分支/版本/未提交變更數，並 `git fetch` 比對 `origin`。未提交變更 >0 會警告 —— `setup_new_pc.bat` 的 `git pull --ff-only` 會被拒絕，機器會停在舊碼（PC1/PC2 很可能有這種狀況，先處理再部署）。
- **健檢摘要**：只列 ❌（任務線/能力）與 ⚠️（缺套件、未註冊排程），結尾給待補項數。
- **排程預設不註冊**；`-RegisterTasks` 才建立 4 個任務（`StartWhenAvailable` + 電池可跑 + `IgnoreNew`），`-UnregisterTasks` 供切換日舊機使用。
- 排程名稱**不帶機器後綴**（`FinanceNews_Pipeline` 等）：排程是各機本地的，同名不衝突。`health_check.py` 的排程檢查改為**分組比對**（同一件事接受多種任務名，例如金融 pipeline ＝ `FinanceNews_Pipeline` 或 `Autonomy_finance-pipeline`），因此 notebook 與 PC3 都會正確顯示 ✅（舊版只認 `Autonomy_*`，notebook 全紅）。
- `ONBOARDING.md` 已加「快速路徑」段落、修正 clone 路徑（原寫 `D:\sensebar-agent-knowledge-vault`）、排程表改為實際名稱。

驗證（notebook）：
```
deploy.ps1 -DryRun -SkipSetup  → 身份=notebook、exit 0、列出 3 ❌（telegram_env、XQ excel/snapshots）＋1 ⚠️
                                 （notebook 有 283 個未提交變更 → 程式碼狀態會顯示警告，屬正常）
deploy.ps1 -Machine pc1        → 身份不符，exit 1，提示要在 config.py 補 "laptop-vag7lbd2": "pc1"
deploy.ps1 -RegisterTasks -DryRun → 正確列出 4 個排程
health_check --json services → FinanceNews_* / ChannelWatcherDaily / XQ_Snapshot_Loop / StockMonitor_Scheduler 皆 ✅
```

### Step 4 — PC1 實機驗收 ✅ 安裝完成（2026-11-04）

**正式安裝結果（`deploy.ps1 -Machine pc1`，13:12）**：❌ 0、⚠️ 1（排程未註冊，預期）、ℹ️ 7（全為資料類）。外部工具（ffmpeg/VLC/Obsidian）與三個 bundle 套件皆安裝成功、`machine.yaml` 已自動產生、Groq/Gemini key 都在。

剩兩件事：①`workspace-bundle\infra\setup\smoke_test.py` 實跑驗證（✅ 22/22）②git 衛生（見下節，已修）。

> **資料同步已取消（2026-11-04 新方向）**：PC1/PC2 **不再複製** `finance.db`、`knowledge-base/`、`shared\watched_channels_state.json`。產出留在產出機，由 notebook 單向收割（見 Step 7）。PC1 先前那次複製屬舊方向，可清掉但不急。

> **更正（2026-11-04）**：`worker.py` **沒有 `--test` 參數**（只有 `--once` / `--retry-failed` / `--id`）。根目錄的 `test_e2e.py` **沒有進 git**（PC1 拉不到），而且它會呼叫 `harvest()`（有副作用），不適合當驗收工具。已新增 **`workspace-bundle/infra/setup/smoke_test.py`**（唯讀、可攜、結束碼＝失敗數），三機統一用它。`channel_watcher.py --once` 會寫 `shared\watched_channels_state.json`，**PC1/PC2 在 notebook 仍跑 `ChannelWatcherDaily` 期間不要執行**，否則雙寫。

1. 在 PC1 執行 `deploy.ps1 -Machine pc1 -DryRun` 先看，再 `deploy.ps1 -Machine pc1`。
   - 若 PC1 主機名尚未在 `config.py` 的 `MACHINE_ALIASES`，先在 notebook 補上並 push（PC1 才能 pull 到）。
2. `health_check.py` 四條線（finance/video/stock/xq）依該機用途全綠；XQ 線若無 XQ/Excel 可接受 ❌（人工作業）。
3. 補人工項：Gemini key（每台獨立）、Telegram（**不要**再複製 `finance.db`／`knowledge-base/`／`shared/watched_channels_state.json`，見下方新方向）。
4. 跑 `python -X utf8 workspace-bundle\infra\setup\smoke_test.py` 驗證（唯讀，結束碼＝失敗數）。
5. 通過後才複製流程到 PC2 / PC3。

#### PC1 乾跑結果（2026-11-04，`c879c1e`）

| 項目 | 結果 |
|---|---|
| 身份 | ✅ `pc1`（`DESKTOP-NDLV9LI`，worker，`100.84.223.110`） |
| 程式碼 | ✅ 與遠端一致、0 未提交變更 |
| 安裝步驟 | ✅ `setup_new_pc.bat` 乾跑通過（Git/Python/Groq key/gh/opencode 都在） |
| 健檢 | ✅ 解析成功（先前失敗原因是 `fitz` 的 deprecation warning 印到 stdout，已修） |
| 健檢 ❌ | **0 項**（分類修正後） |

PC1 缺的都是**資料類**，不是程式缺漏：

| 缺項 | 性質 | 補法 |
|---|---|---|
| `financial_news/finance.db` | 資料（57MB，含新聞去重歷史） | **PC1/PC2 不需要**（新方向）；只在 harvester（notebook）維護。PC1 已複製的那份可刪 |
| `financial_news/publisher/repo` | 另一個 repo | `git clone https://github.com/spyang1963-pattern/financial-reports.git` 到該路徑 |
| `~/.telegram_env` | 共用憑證 | 手動放（notebook 目前也沒有） |
| `stock-monitor/output/cache` | **執行時自動建立**，不必處理 | — |
| XQ 三項 | 只有 XQ 主機（PC3）才會有 | 略過 |
| `workspace-bundle/infra/config/machine.yaml` | 由 `update.py` 從 `defaults.yaml` 自動產生 | 正式跑 `deploy.ps1` 時自動出現 |

> 健檢分類規則（`health_check.py` 的 `LINE_NOT_CAPABILITY`）：能力類缺 → ❌；資料／憑證／該機專屬 → ℹ️（不計入待補）。這樣新機不會因為「還沒同步資料」被誤判成安裝失敗。

#### PC1 驗收（2026-11-04）✅ 22/22

**2026-11-05 複驗 ✅ 23/23**：拉到 `a83ff7d` 後跑 `deploy.ps1 -Machine pc1 -SkipSetup`，補建 `shared\tasks`、`shared\errors`、`shared\pc1\{status,results}`；smoke test 23 項全綠（新增的 `shared\tasks` 那項 ✅）。

`deploy.ps1 -Machine pc1 -SkipSetup` → `smoke_test.py` 全綠：身份 `pc1/worker`、六個路徑、五個核心模組、`ffmpeg`/`ffprobe`/VLC、Groq+Gemini key、`finance.db` 51580 筆。

`working/`、`output/` 一開始報 ❌ 是**空目錄不進 git** 的正常現象，已由 `deploy.ps1` 第 3 步冪等建立（`working`/`output`/`videos`）。

#### PC2 驗收（2026-11-05）⚠️ 21/22 → 已修

`deploy.ps1 -Machine pc2` 一次成功：身份 `pc2/worker`（`DESKTOP-NL6VA8T`、`100.113.234.81`）、ffmpeg 9.0.2／VLC 3.0.24／Obsidian 1.15.0／gh 2.103.3 全裝好、`machine.yaml` 自動產生、`❌ 0 ⚠️ 1`（排程未註冊）。

**唯一紅燈：`shared\` 目錄不存在**。原因與影響：

- `shared/*` 在 `.gitignore`（執行期狀態不進 git），新機 clone 後自然沒有這個目錄。
- `ipc.py` 的 `TaskQueue.get_assigned_tasks()` 在 `shared\tasks` 不存在時**靜默回傳空清單** → worker 不會報錯，只會永遠領不到任務（最惡劣的失敗模式：看起來正常但什麼都不做）。
- PC1 沒踩到，只因為它的 `shared\` 是舊工作區時代就存在的。

**修法**：`deploy.ps1` 的 `Ensure-RuntimeDirs` 改為同時建立 `shared\tasks`、`shared\errors`、`shared\<machine>\status`、`shared\<machine>\results`；`smoke_test.py` 新增一項 `shared\tasks 目錄` 檢查（22 → 23 項）。新機若沒跑最新版 `deploy.ps1`，手動補（`<machine>` 用 `config.MACHINE`，**不是** hostname）：

```powershell
powershell -ExecutionPolicy Bypass -File workspace-bundle\infra\setup\deploy.ps1 -SkipSetup
# 或手動（pc2 為例）
New-Item -ItemType Directory -Force -Path shared\tasks, shared\errors, shared\pc2\status, shared\pc2\results | Out-Null
```

#### Git 衛生：執行期狀態不該進 git（2026-11-04）

PC1 驗收後出現「24 個未提交變更」，實際成分：

| 類型 | 檔案 | 處理 |
|---|---|---|
| 真的被改的 tracked 檔 | `shared/watched_channels_state.json`（17+/21-） | **untrack + gitignore** |
| 無內容差異（只有換行屬性） | `knowledge-base/kb_query.py`、`split_transcript.py` | 保留 tracked，必要時 `git checkout --` |
| 大量未追蹤的 KB 資料 | `knowledge-base/**`（21 項） | **gitignore** |

**這不是換行問題**（`core.autocrlf=true`，`git diff --stat` 只有 1 個檔案有內容差異）。

`.gitignore` 新增兩條：

```
shared/*           # IPC 通道與執行期狀態（heartbeat、tasks、results、掃描游標）
knowledge-base/*   # 資料不是程式碼；已追蹤的 4 檔不受影響
```

`shared/watched_channels_state.json` 已 `git rm --cached`（**檔案留在磁碟**）。理由是：它是**執行期狀態**，單一寫作者應該是 notebook；被 git 追蹤只會讓 PC1/PC2 的 `git pull --ff-only` 週期性被拒。

**PC1/PC2 更新時會少掉這個檔案**（upstream 把它刪了），這是預期行為：
- 若該機根本沒跑頻道掃描 → 不需要它，略過即可。
- 若要保留 → 先 `Copy-Item shared\watched_channels_state.json` 到暫存，pull 後再複製回去（但之後它仍會與 notebook 分歧，因為它已不受 git 管理）。

⚠️ **PC3 注意**：PC3 的 `self_heal` 會自動 `git pull`，同一個 commit 會讓 PC3 的 `shared/watched_channels_state.json` **被刪除**。PC3 目前沒跑頻道監控，風險低；遷移日若需要，從 notebook 用 SMB 複製一份過去即可。

### Step 5 — PC3 遷移（最後做）

#### PC3 現況（2026-11-04 盤點，勿憑印象）

| 項目 | 現況 |
|---|---|
| 工作目錄 | `D:\sensebar-agent-knowledge-vault`（獨立 clone，含舊資料） |
| 金融報告 | 由 **autonomy mission** 執行，不是 `FinanceNews_*` 任務：`workspace-bundle\infra\autonomy\missions\finance-{pipeline,morning,evening}.json` → `workdir=D:\sensebar-agent-knowledge-vault\financial_news`、指令 `pipeline.py --report --deep --slot ...` |
| 頻道監控 | 只跑在 **notebook**（`ChannelWatcherDaily` 就緒）；PC3 的 `channel-watcher.json` mission 未在跑（2026-11-04 使用者確認） |
| 自動更新 | `self_heal.py` 每 ~6 小時（或 05:45 視窗）在此 clone 內 `git pull --ff-only`，**但受 `autonomy_config.json` 的 `repos[].hosts` 比對限制** |
| notebook 端 | `FinanceNews_Pipeline / MorningReport / EveningReport` 皆「已停用」（已交接）；`ChannelWatcherDaily` 仍啟用 |
| 運作驗證（2026-11-04） | 每日報告最新產出 **12:20**、XQ 盤中儀表正常 → PC3 現役運作正常，**遷移前不要動它** |

#### 本次改動對 PC3 的影響：**無功能影響**

| 改動 | PC3 會不會用到 | 結論 |
|---|---|---|
| `MACHINE_PATHS["pc3"]` | autonomy/finance 不讀 `config.py`；`worker.py`/`scheduler.py` 才用 | **刻意未改**，仍指舊路徑 |
| `MACHINE_ROLES["pc3"]` | 只有 `worker.py` 寫 log 用；值仍是 `harvester` | 無變化 |
| `TAILSCALE_IPS["pc3"]=None` | 只有 `task_manager_gui.py`/`health_check.py`/`_test_worker_mgr.py` 讀；報告流程不讀 | 無影響（GUI 顯示「未設定」） |
| `health_check.py` | PC3 報告任務不呼叫 | 無影響；且已改成「同組任一任務名即可」，PC3 的 `Autonomy_*` 也判 ✅ |
| `deploy.ps1` / `setup_new_pc.bat` / `update.py` | 只有人手动執行 | 無影響 |

驗證方式（靜態）：`financial_news\*.py` 沒有任何 `import config`；`autonomy\*.py` 只 import `common`，不讀 `config`。PC3 只在 `self_heal` 觸發 `git pull` 時才會拿到新 `config.py`，而新 `config.py` 對它沒有行為差異。

**補充（2026-11-04）**：`channel_watcher.py` 從 config 只取 `log / PROJECT_ROOT / SHARED_ROOT / 狀態檔函式`，這些都沒動；且它以 `PROJECT_ROOT` 組路徑，不是 `MACHINE_PATHS`，所以 PC3 若有跑頻道監控也不受影響（目前確認只在 notebook 跑）。

#### 待確認（會影響 PC3 是否自動更新／看門狗）

**主機名拼法不一致**：

| 位置 | 值 |
|---|---|
| `config.py` `MACHINE_ALIASES` | `desktop-mfkvcso`（m-f-k-**v-c**-s-o） |
| `autonomy_config.json` 與 4 個 mission 的 `hosts` | `desktop-mfkcvso`（m-f-k-**c-v**-s-o，5 個檔案一致） |

`matches_host()` 是字串比對（`h in hostname`）。兩種可能：

1. 真主機名是 `desktop-mfkcvso` → **`config.py` 的 key 是錯的**，PC3 目前被判定成 `unknown-desktop-mfkcvso`（`get_machine_paths()` 會退回 notebook 路徑），但報告照跑（不讀 config）。
2. 真主機名是 `desktop-mfkvcso` → **autonomy 那 5 處是錯的**，`self_heal` 的 git pull 與看門狗在 PC3 上等於停用（任務仍會被 Task Scheduler 觸發，但不會自動補跑/告警）。

**請在 PC3 執行以下三行並回報**，再決定改哪一邊（一次改對，別兩邊都塞）：

> **2026-11-04 決策：延到遷移日再做，不必特地跑。** PC3 目前報告與 XQ 都正常，且報告/XQ/頻道監控都不讀 `config.py`，拼字不影響現役運作。三行都是唯讀，遷移當天一次做完即可（主機名要在 `config.py` 登記正確，`deploy.ps1` 的身份檢查才過得了）。

```powershell
hostname
git -C D:\sensebar-agent-knowledge-vault rev-parse --short HEAD
schtasks /Query /FO CSV | findstr /I "Autonomy"
```

#### 遷移日步驟

1. 先停 PC3 排程（`Autonomy_*`；單一寫入者），確認 notebook 的 `ChannelWatcherDaily` 由誰接手。
2. 把資料複製到 `D:\AI-Agent-Workspace`：`financial_news\finance.db`、`output/`、`working/`、`D:\YouTube_Videos`、`shared\watched_channels_state.json`。
3. 改 `config.py` 三處：
   - `MACHINE_PATHS["pc3"]` → 與 pc1/pc2 相同的 `D:\AI-Agent-Workspace\...`
   - `TAILSCALE_IPS["pc3"]` → `tailscale ip -4` 的實際值
   - 主機名拼法（依上面三行的結果修正，`config.py` 或 autonomy 兩者擇一）
4. 改 `autonomy_config.json` 與 `missions\*.json` 的 `workdir`/`log` → 新路徑（**PC3 的報告任務靠這些硬寫路徑**，不改就還是跑舊目錄）。
5. 在 PC3 跑 `deploy.ps1 -Machine pc3 -DryRun` → 再正式跑；`health_check.py` 應顯示 `pc3` + 正確 IP。
6. 重建排程（`deploy.ps1 -SkipSetup -RegisterTasks` 或沿用 `Autonomy_*`），觀察一天；舊目錄保留一週再刪。

### Step 6 — 三機上線後再調整工作分配

- 依 `PROVISIONING.md`「單一寫入者」原則重新分配排程。
- 切換順序：同步 state → 停舊機排程 → 建新機排程 → 觀察一天。
- 開放問題：notebook 的 `videos` 是 `D:\!!!!!理周學院老師`，PC1/PC2 是 `D:\AI-Agent-Workspace\videos`。建議各機保留既有教材庫（只同步任務所需），不強制搬移。

### Step 7 — 單向收割架構（PC 產出 → notebook 收）｜待決策、未實作（2026-11-04 提出）

**方向改變**：三機不再「互相同步整份資料」，改成**單向收割**。

- **PC1/PC2 不必從 notebook 拿 `finance.db`、`knowledge-base/`**（省下 60MB + 124MB 的複製與後續同步負擔）。
- **產出物反向流回 notebook**：逐字稿 `.md`／`.srt`、課程筆記、摘要報告、直播報告 → 收割到 notebook 的 `knowledge-base/`，notebook 是 KB 的唯一正本。
- **影音不搬**：影片留在產出機的 `D:\YouTube_Videos`，KB 條目只寫「位置指標」，notebook 端點連結就能播放（SMB/UNC）。

**可行的部分**：KB 條目本來就是純文字，收割只需複製 `.md`/`.srt`/`.docx`（單支幾百 KB～幾 MB）；影片用 UNC 路徑即可線上播放，不必佔 notebook 空間。

**要改的地方**

1. KB 條目的影片路徑改成**雙欄**：`本機影片`（產出機 `D:\YouTube_Videos\...`）＋ `網路影片`（`\\100.84.223.110\YouTube_Videos\...`）。notebook 點「網路影片」；產出機點「本機影片」。目前條目只寫本機路徑，直接拿到 notebook 會點不到。
2. `\\<PC>\...` 要能連 → **反向 SMB 權限**：PC1/PC2 需開 `AI-Agent-Workspace`（或至少 `YouTube_Videos`、KB 目錄）分享並給 notebook 讀取權。今天在 notebook 上遇到的「分享 Everyone Full 但 NTFS 沒有 Everyone → 錯誤 5」會一模一樣發生在 PC 端（見第 5 節第 10 條）。
3. 收割方向建議 **notebook 主動 pull**（單一讀者、權限只需唯讀），排程例如每日一次；PC 端不需要寫入 notebook。
4. 去重仍用 `video_id`（`channel_watcher.kb_video_index()` 已具備），收割前比對，避免同支重複進 KB。

**已知障礙／待決**

| 問題 | 說明 |
|---|---|
| `shared/` 不能不同步 | 任務派工（`task_status.json`、`shared/tasks/*.json`）與 heartbeat 都在 `shared/`，PC 若不與 notebook 共用，跨機派工就斷。**收割架構只適用 KB 與 finance.db，`shared/` 仍需共用（或有替代的派工通道）** |
| PC 離線＝影片斷鏈 | 指標路徑失效。KB 條目需標「離線」或保留 thumbnail/摘要；或日後把冷片搬 NAS |
| `finance.db` 不同步 | PC1/PC2 不跑金融線（PC3 跑），所以現階段沒差；但若日後把金融線分到 PC1/PC2，空 DB 會失去去重與歷史 |
| PC 端儲存壓力 | 影片只進不出會長大，需保留策略（例如 30 天後搬 NAS 或刪） |
| 現況（2026-11-04） | notebook 端已對 `financial_news\`、`shared\`、`knowledge-base\` 加 `Everyone:(OI)(CI)(RX)`；這是「notebook → PC」方向，與收割需要的「PC → notebook」方向相反，屆時要在 PC 端做一次 |

**結論**：方向可行，且比雙向同步乾淨；但 `shared/` 派工通道與「PC 端分享權限」兩件事要先解，才會真的省事。此輪不動手。

### Step 8 — 舊工作區清理（PC1/PC2）｜腳本已備，待執行

PC1 在本次部署前已有兩次早期測試留下的工作區（PC2 可能也有）：

| 路徑 | 日期 |
|---|---|
| `D:\!!AI agent 專案夾\三師爸的 AI agent 學習 AI agent` | 2026-09-11 |
| `D:\sensebar-agent-knowledge-vault` | 2026-09-20 |

> 注意：`sensebar-agent-knowledge-vault` 在 **PC3 是現役目錄**，在 PC1/PC2 只是舊測試殘留，別搞混。

**先盤點、再決定**（腳本唯讀，不刪不改任何東西）：

```powershell
powershell -ExecutionPolicy Bypass -File workspace-bundle\infra\setup\audit_old_workspace.ps1
```

它會逐一路徑列出：大小／檔案數、Git 遠端與分支、**未推送 commit 數**、未提交變更數、`finance.db`、`knowledge-base` 的 `.md` 數與大小、`shared\watched_channels_state.json`、`output`／`working`／`videos` 容量、以及**是否有排程任務仍指向該路徑**。

**判斷原則**

| 情況 | 處理 |
|---|---|
| 未推送 commit > 0 | 先 `git push`（或確認是測試垃圾），否則刪了就救不回 |
| 有排程指向它 | 先停用／改路徑，否則排程天天失敗 |
| `finance.db` 或 KB 比新工作區新／更完整 | 先複製需要的部分再刪 |
| 以上都沒有 | 整包壓縮留一份到 NAS／外接，再刪資料夾 |

**注意**：舊目錄若沒有 `.git`（例如 `D:\!!AI agent 專案夾\...` 在 notebook 上就是純資料夾、315MB／1330 檔），就沒有 commit 可救，只需確認裡面沒有獨有的 KB／影片。

#### PC1 盤點結果（2026-11-04 18:10）

| 項目 | `D:\!!AI agent 專案夾\三師爸的 AI agent 學習 AI agent` | `D:\sensebar-agent-knowledge-vault` |
|---|---|---|
| 大小／檔案 | 316 MB／347 | 75 MB／441 |
| 最後寫入 | 2026-07-16 | 2026-09-20 |
| Git | master @ `99d919a` | master @ `923d732` |
| 未推送 commit | **0** | **0** |
| 未提交變更 | **3 個檔案** | 0 |
| `finance.db` | 無 | 無 |
| KB | 26 個 `.md`／3 MB | 1 個 `.md`／0 MB |
| 監控狀態 | 無 | 有（2026-09-20，已過期） |
| `working/` | **306 MB／28 檔（佔绝大部分）** | — |
| 排程指向 | 無 | 無 |

**結論**：兩份都可安全封存後刪除。
- `sensebar-agent-knowledge-vault`：git 完全乾淨、無本地 commit → 遠端可完整重建，**直接刪**。
- `!!AI agent 專案夾\...`：有 3 個未提交變更，但整包只有 316 MB → **先壓縮留存再刪**（zip 內含 `.git`，可還原）。
- 兩份的 `shared` 監控狀態都是舊的（7 月／9 月），現行正本在 notebook（`2026-11-03`），不需保留。
- `working/` 306 MB 是舊處理暫存（影片／中間檔），沒有保留價值。

#### PC2 盤點結果（2026-11-05 11:22）✅ 已清理

| 路徑 | 大小／檔案 | Git | 未推送 | 排程指向 | 處理 |
|---|---|---|---|---|---|
| `D:\AI Agent` | 0 MB／**0 檔** | 無 | — | 無 | 空殼，直接刪 |
| `C:\AI agent 工作區` | 0 MB／**2 檔**（`free-quota.py`／`.cmd`，2026-11-02） | 無 | — | 無 | 2 檔先備份到 `D:\_archive\quota-probe-2026-11-02\`，再刪 |
| `D:\sensebar-agent-knowledge-vault` | 76 MB／446 檔 | master @ `97890ee` | **0**（`origin/master..HEAD`=0、`HEAD..origin`=131） | 無 | **不壓縮**，直接刪 |

**為何這次不用壓縮**（與 PC1 不同）：`git status --porcelain --ignored` 完全空白——連未追蹤、被忽略的檔案都沒有，工作區與 `97890ee` 完全一致，GitHub 可完整重建。PC1 那次要壓縮是因為 `!!AI agent 專案夾\...` 有 3 個未提交變更＋306 MB `working\`。

**踩坑（已修，`52a61ec`）**：`powershell -File ... -Path "a","b","c"` **不會**拆成陣列，整個 token 會是一個字串，腳本因此把所有路徑都判成「不存在」。已改為綁定後自行以逗號／分號分割，並強制 `exit 0`（git 的 stderr 會讓 `-File` 回傳 1，看起來像失敗）。

驗證：`Test-Path` 三條全部 `False`；D 槽 226 GB 已用／1.77 TB 可用。

### Step 9 — OC 額度小窗（`oc_widget`）推廣到三機｜已可攜

`oc_widget.py` + `oc_usage.py` + `oc_widget.bat` 已納入 git（原本只在 notebook、且 `sys.path` 寫死 `D:\AI-Agent-Workspace`）。

**可攜化修正**：`sys.path` 改由 `Path(__file__).resolve().parent` 決定；`oc_widget.bat` 重寫為**純 ASCII**（原本含中文註解，在 cp950/UTF-8 之間會把 `cd /d` 併進 `rem` 行而失效）。

**每台裝法（含 PC3，在任何目錄都能跑）**：

```powershell
cd D:\AI-Agent-Workspace
pythonw oc_widget.py          # 背景常駐（建議）
# 或雙擊 oc_widget.bat
python oc_widget.py --check    # 只印一次數字
```

開機自動啟動（可選）：`shell:startup` 放 `oc_widget.bat` 的捷徑。

**先決條件**：該機要有 opencode 並登入過（`%LOCALAPPDATA%\opencode\auth.json` 才有 `opencode-go` key）。
- 有 key → 顯示 Go（5h／週／月，**官方精確值、帳號級**）
- 沒 key → 顯示「Go —」，免費數字仍可算（讀本機 `opencode.db`）

**重要語意**：「免費」的計數是**讀本機 DB 估算**（本機免費池日累計，08:55 換日），所以每台只看到自己那台的用量；三台加起來才是帳號真實用量。**它不是「200/5h」配額，也沒有分母**——伺服器端是動態上限、帳號／IP 共用（實測撞牆點 1／206／337 次，未撞牆日可達 443／725 次）。Go 是官方 API，三台看到同一個數字。


## 3. 人工不可自動化（每台都一樣）

| 項目 | 位置 |
|---|---|
| Gemini key（每台獨立） | `%USERPROFILE%\.gemini_api_key` |
| Groq key（共用） | `%USERPROFILE%\.groq_api_key` |
| Telegram 告警（共用） | `%USERPROFILE%\.telegram_env` |
| 資料同步 | **不再複製**（PC1/PC2）：產出留本機，由 notebook 單向收割（Step 7）；`finance.db`／`knowledge-base/` 只留在 harvester |
| GitHub 認證 | 首次 push 輸入帳號 + Token |
| 排程切換 | 確認單一寫入者後才啟用 |

## 4. NAS（DS718+）角色建議 — 待決策

**建議定位：備援儲存 + 交換區，不當執行機。**

| 用途 | 建議 | 理由 |
|---|---|---|
| Hyper Backup 目的地 | ★ 首選 | 三機的 `knowledge-base/`、`finance.db`、`shared/` 每日備份；SHR-1 可容單碟故障 |
| 三機大檔交換區 | ★ 推薦 | `\\NAS\exchange\` 放影片/模型/暫存，避免大檔進 git；定期清理 |
| 離線安裝來源（wheelhouse） | ★ 推薦 | `pip download` 的 wheels 放 NAS，新機無網路也能裝 |
| 日誌/報告彙整 | 可選 | 各機上傳 `logs/`、`task_status.json`，NAS 做每日彙總（Python 3.8 限制） |
| 中央 SQLite | ✗ 不建議 | SQLite 走 SMB 有鎖定/毀損風險；DB 留在現役 harvester，NAS 只收備份 |
| 當 worker / git working copy | ✗ 不建議 | Python 3.8、無 GPU、套件裝不動；共用 working copy 會檔案鎖衝突 |

待決事項：
1. 兩顆硬碟容量與 RAID 模式（建議 SHR-1）。
2. 共用資料夾命名與配額（`backup/`、`exchange/`、`archive/`）。
3. 備份排程由哪台機器發起（建議由現役 harvester 統一推）。
4. 是否啟用 Snapshot Replication（Btrfs）防勒索。

## 5. 踩過的坑（本次新增）

1. **中文 `.bat` 編碼**：UTF-8 或 CP950 都會因主控台 codepage 不同而破行；批次檔一律 ASCII，中文放 md。
2. **`echo` 文字含 `()` 會提前關閉 `if (...)` 區塊**：區塊內訊息不要用括號。
3. **`set /p` 取值需 `enabledelayedexpansion`**：否則金鑰寫入字面 `!KEY!`。
4. **`pip install` 首次可能 >2 分鐘**：update.py timeout 已調到 900s。
5. **PATH 需重開終端**：winget 裝完同一視窗仍找不到指令。
6. **GUI 長駐程序**：改完 `task_manager_gui.py` 必須關閉重開，否則仍是舊碼。
7. **PowerShell 傳參給原生程式會吃掉雙引號**：`python -c 'sys.path.insert(0, r"$Root")'` 到 python 手上變成 `rD:\...`。改用環境變數傳值，或 python 端用單引號。
8. **含中文的 `.ps1` 要存 UTF-8 with BOM**：PS 5.1 對無 BOM 的檔案會以 ANSI 解讀，中文全亂。`deploy.ps1` 已加 BOM。
9. **套件會在 import 時印 warning 到 stdout，把 JSON 弄壞**（2026-11-04 在 PC1 實踩）：`PyMuPDF` 的 `fitz` 會印 `warning: The 'fitz' API is deprecated...`，`health_check.py --json` 的輸出前面多這一行，`ConvertFrom-Json` 直接拋「無效的 JSON 基本型別: warning」。修法：`deploy.ps1` 只取第一個 `{` 到最後一個 `}` 的區段，並用 `2>$null` 抑制 stderr；多餘輸出會印成「（健檢附帶輸出，已忽略：…）」方便追查。**不要改回 `$raw | ConvertFrom-Json`**。
10. **SMB「分享 Full 但複製被拒（錯誤 5）」＝ NTFS 沒有 Everyone**（2026-11-04 實踩）：notebook 的 `AI-Agent-Workspace` 分享是 `Everyone: Full`，但 NTFS ACL 只有 `Authenticated Users(M)` / `Users(RX)`。PC1 用本機帳號（`user`）連過來時是匿名身分，兩個群組都不屬於它 → 分享層放行、檔案層 Access Denied。修法（唯讀，不動寫入）：
    ```powershell
    foreach ($p in @("financial_news","shared","knowledge-base")) {
        icacls "D:\AI-Agent-Workspace\$p" /grant "*S-1-1-0:(OI)(CI)(RX)" /T /C /Q
    }
    ```
    用 SID `S-1-1-0` 而非 `Everyone` 字串，避免多語系／本機化名稱問題。正式解法是 `net use \\host\share /user:<host>\<account> *` 走帳號驗證，不必開 Everyone。

## 6. 快速指令

```powershell
# 部署（新機）— 建議走 deploy.ps1（含身份檢查 + 健檢摘要）
cd D:\AI-Agent-Workspace
powershell -ExecutionPolicy Bypass -File workspace-bundle\infra\setup\deploy.ps1 -Machine pc1 -DryRun
powershell -ExecutionPolicy Bypass -File workspace-bundle\infra\setup\deploy.ps1 -Machine pc1

# 只跑安裝（不驗身份）
setup_new_pc.bat --dry-run      # 先看會做什麼
setup_new_pc.bat                # 實際安裝

# 切換日排程
powershell -ExecutionPolicy Bypass -File workspace-bundle\infra\setup\deploy.ps1 -SkipSetup -RegisterTasks
powershell -ExecutionPolicy Bypass -File workspace-bundle\infra\setup\deploy.ps1 -SkipSetup -UnregisterTasks

# 舊工作區盤點（唯讀；刪任何東西之前先跑）
powershell -ExecutionPolicy Bypass -File workspace-bundle\infra\setup\audit_old_workspace.ps1

# 額度小窗（零 token）
pythonw oc_widget.py            # 常駐；或雙擊 oc_widget.bat
python oc_widget.py --check     # 只印一次

# 健檢
python -X utf8 workspace-bundle\infra\health_check.py
python -X utf8 workspace-bundle\infra\health_check.py --json

# 機器身份
python -X utf8 -c "import config; print(config.MACHINE, config.get_machine_role())"
```

## 7. 尚未處理的小事（下次順手做）

1. `sync_shared.ps1`（未納入 git）內仍硬寫 PC1/PC2/notebook 的 Tailscale IP，且假設分享名稱為 `AI-Agent-Workspace`；改 IP 時要一起改。若要收斂，改成讀 `config.TAILSCALE_IPS`。
2. `health_check.py` 的 `AI-Agent-Sync` 任務在 notebook 上不存在（sync 只在需要推送的機器上跑），新機健檢會顯示 ⚠️ 屬正常。
3. notebook 的 `MACHINE_PATHS["notebook"]["videos"]` 指 `D:\!!!!!理周學院老師`，PC1/PC2 指 `D:\AI-Agent-Workspace\videos`；分配工作時再決定是否統一。
