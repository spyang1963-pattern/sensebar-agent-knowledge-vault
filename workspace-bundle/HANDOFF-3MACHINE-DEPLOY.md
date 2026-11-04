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

### Step 4 — PC1 實機驗收（未開始）

1. 在 PC1 執行 `deploy.ps1 -Machine pc1 -DryRun` 先看，再 `deploy.ps1 -Machine pc1`。
   - 若 PC1 主機名尚未在 `config.py` 的 `MACHINE_ALIASES`，先在 notebook 補上並 push（PC1 才能 pull 到）。
2. `health_check.py` 四條線（finance/video/stock/xq）依該機用途全綠；XQ 線若無 XQ/Excel 可接受 ❌（人工作業）。
3. 補人工項：Gemini key（每台獨立）、Telegram、資料同步（`finance.db`、`knowledge-base/`、`shared/watched_channels_state.json`）。
4. 跑一次 `python channel_watcher.py --once` 的縮小版或 `worker.py --test` 驗證。
5. 通過後才複製流程到 PC2 / PC3。

### Step 5 — PC3 遷移（最後做）

#### PC3 現況（2026-11-04 盤點，勿憑印象）

| 項目 | 現況 |
|---|---|
| 工作目錄 | `D:\sensebar-agent-knowledge-vault`（獨立 clone，含舊資料） |
| 金融報告 | 由 **autonomy mission** 執行，不是 `FinanceNews_*` 任務：`workspace-bundle\infra\autonomy\missions\finance-{pipeline,morning,evening}.json` → `workdir=D:\sensebar-agent-knowledge-vault\financial_news`、指令 `pipeline.py --report --deep --slot ...` |
| 頻道監控 | 同層 `channel-watcher.json`（workdir=舊根目錄）；notebook 的 `ChannelWatcherDaily` 目前仍「就緒」，PC3 那份是否也在跑待確認 |
| 自動更新 | `self_heal.py` 每 ~6 小時（或 05:45 視窗）在此 clone 內 `git pull --ff-only`，**但受 `autonomy_config.json` 的 `repos[].hosts` 比對限制** |
| notebook 端 | `FinanceNews_Pipeline / MorningReport / EveningReport` 皆「已停用」（已交接）；`ChannelWatcherDaily` 仍啟用 |

#### 本次改動對 PC3 的影響：**無功能影響**

| 改動 | PC3 會不會用到 | 結論 |
|---|---|---|
| `MACHINE_PATHS["pc3"]` | autonomy/finance 不讀 `config.py`；`worker.py`/`scheduler.py` 才用 | **刻意未改**，仍指舊路徑 |
| `MACHINE_ROLES["pc3"]` | 只有 `worker.py` 寫 log 用；值仍是 `harvester` | 無變化 |
| `TAILSCALE_IPS["pc3"]=None` | 只有 `task_manager_gui.py`/`health_check.py`/`_test_worker_mgr.py` 讀；報告流程不讀 | 無影響（GUI 顯示「未設定」） |
| `health_check.py` | PC3 報告任務不呼叫 | 無影響；且已改成「同組任一任務名即可」，PC3 的 `Autonomy_*` 也判 ✅ |
| `deploy.ps1` / `setup_new_pc.bat` / `update.py` | 只有人手动執行 | 無影響 |

驗證方式（靜態）：`financial_news\*.py` 沒有任何 `import config`；`autonomy\*.py` 只 import `common`，不讀 `config`。PC3 只在 `self_heal` 觸發 `git pull` 時才會拿到新 `config.py`，而新 `config.py` 對它沒有行為差異。

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

## 3. 人工不可自動化（每台都一樣）

| 項目 | 位置 |
|---|---|
| Gemini key（每台獨立） | `%USERPROFILE%\.gemini_api_key` |
| Groq key（共用） | `%USERPROFILE%\.groq_api_key` |
| Telegram 告警（共用） | `%USERPROFILE%\.telegram_env` |
| 資料同步 | `finance.db`、`knowledge-base/`、`shared/watched_channels_state.json`（**必須最新**） |
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
