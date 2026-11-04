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

### Step 3 — 單一入口 `deploy.ps1`（未開始）

`workspace-bundle/infra/setup/deploy.ps1 -Machine pc1|pc2|pc3 [-RegisterTasks]`
- 包裝 `setup_new_pc.bat`，加上：機器身份檢查（未註冊即提示）、健檢摘要（只看 ❌）、可選排程註冊。
- 排程預設**不註冊**，需明確加 `-RegisterTasks`。

### Step 4 — PC1 實機驗收（未開始）

1. 在 PC1 執行 `setup_new_pc.bat`（非 dry-run）。
2. `health_check.py` 四條線（finance/video/stock/xq）依該機用途全綠；XQ 線若無 XQ/Excel 可接受 ❌（人工作業）。
3. 補人工項：Gemini key（每台獨立）、Telegram、資料同步（`finance.db`、`knowledge-base/`、`shared/watched_channels_state.json`）。
4. 跑一次 `python channel_watcher.py --once` 的縮小版或 `worker.py --test` 驗證。
5. 通過後才複製流程到 PC2 / PC3。

### Step 5 — PC3 遷移（最後做）

PC3 仍跑在 `D:\sensebar-agent-knowledge-vault`，先不動以免中斷現役收成。遷移日執行：

1. 先停 PC3 排程（單一寫入者）。
2. 把資料複製到 `D:\AI-Agent-Workspace`：`output/`、`working/`、`D:\YouTube_Videos` 影片庫。
3. 改 `config.py` 兩處：
   - `MACHINE_PATHS["pc3"]` → 與 pc1/pc2 相同的 `D:\AI-Agent-Workspace\...`
   - `TAILSCALE_IPS["pc3"]` → `tailscale ip -4` 取得的實際值
4. 在 PC3 跑 `setup_new_pc.bat` → `health_check.py` 驗收（應顯示 pc3 + 正確 IP）。
5. 重建排程，觀察一天；舊目錄保留一週再刪。

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

## 6. 快速指令

```powershell
# 部署（新機）
cd D:\AI-Agent-Workspace
setup_new_pc.bat --dry-run      # 先看會做什麼
setup_new_pc.bat                # 實際安裝

# 健檢
python -X utf8 workspace-bundle\infra\health_check.py
python -X utf8 workspace-bundle\infra\health_check.py --json

# 機器身份
python -X utf8 -c "import config; print(config.MACHINE, config.get_machine_role())"
```
