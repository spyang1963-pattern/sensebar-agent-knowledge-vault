# 機器佈署／接手手冊（Onboarding & Takeover Runbook）

> 目標：任何新機器或接手機（PC1/PC2/新電腦）能在最短時間內，達成與現役機一致的完整能力。
> 原則：能腳本化的全部腳本化；只有「金鑰、資料同步、GitHub 認證」三項必須人工。
> 本手冊由 2026-08 PC3 實際佈署過程固化而來。
>
> ⚠ **2026-11-08 更新**：NAS 上線後，資料流已改為「PC → NAS → notebook」，
> 且多出 outbox／收割／備份三個排程。**新機請先看 `DEPLOY-NEW-PC.md`**（現行清單）；
> 本檔保留金融線細節，第 5／8 步的資料同步方式已被取代。

## 快速路徑（建議：三機一鍵）

新機（PC1 / PC2 / PC3）不必逐步照做，直接：

```powershell
# 1. 取得程式碼到統一工作區（三機一律 D:\AI-Agent-Workspace）
git clone https://github.com/spyang1963-pattern/sensebar-agent-knowledge-vault.git D:\AI-Agent-Workspace

# 2. 先看會做什麼（不寫入）
powershell -ExecutionPolicy Bypass -File D:\AI-Agent-Workspace\workspace-bundle\infra\setup\deploy.ps1 -Machine pc1 -DryRun

# 3. 實際部署（Git/Python/外部工具/套件/健檢/NAS 可達性）
powershell -ExecutionPolicy Bypass -File D:\AI-Agent-Workspace\workspace-bundle\infra\setup\deploy.ps1 -Machine pc1

# 4. 重開終端後驗收（唯讀；應 0 項失敗）
python -X utf8 D:\AI-Agent-Workspace\workspace-bundle\infra\setup\smoke_test.py

# 5. 人工：設 NAS 憑證（producer／harvest）＋ Tailscale 登入（見 DEPLOY-NEW-PC.md §3）

# 6. 切換日才註冊排程（單一寫入者；會依機器自動篩選）
powershell -ExecutionPolicy Bypass -File D:\AI-Agent-Workspace\workspace-bundle\infra\setup\deploy.ps1 -SkipSetup -RegisterTasks
```

`deploy.ps1` 會先比對 `config.py` 的機器身份，不符合就中止（避免在錯的機器建任務）；接著呼叫 `setup_new_pc.bat`，最後印出只含 ❌ / ⚠️ 的健檢摘要。以下第 1～8 步是它背後的細節，需要手動排查時再看。

## 架構角色

| 角色 | 職責 | 機器 |
|---|---|---|
| 產出機（producer） | 跑 pipeline、產生 KB 條目、22:50 打包到 NAS `exchange\<machine>\outbox` | PC1 / PC2 / PC3 |
| 收割／正本（harvester） | 23:10 收割、01:30 備份到 NAS、`knowledge-base\` 唯一正本 | notebook |
| NAS（DS718+） | **交換區＋備份**，不是執行機；SQLite／`shared\tasks` 不上 NAS | DATANAS（192.168.1.121 / 100.65.113.20） |

> **2026-11-04 決策**：PC1 / PC2 / PC3 / Notebook **能力完全一致**（皆為完整副本，可獨立承接 finance / video / stock / XQ）。`MACHINE_ROLES` 只是主要職責註記，不代表能力限制。三機工作區一律 `D:\AI-Agent-Workspace`（PC3 待遷移）。
> **2026-11-08 更正**：舊表把 NAS 寫成「collector／角色待定」已作廢；NAS 只做交換與備份。

單一寫入者原則：同一種排程任務全時間只能有一台機器在跑，切換時先停舊再啟新。

## 第 1 步：取得程式碼

```powershell
git clone https://github.com/spyang1963-pattern/sensebar-agent-knowledge-vault.git D:\AI-Agent-Workspace
```
（已 clone 過則 `git pull`。之後所有路徑以 `<REPO>` 代表 repo 根目錄；三機統一為 `D:\AI-Agent-Workspace`）

## 第 2 步：Python 套件安裝（依任務線）

```powershell
$env:WORKSPACE_ROOT = "<REPO>"
python <REPO>\workspace-bundle\infra\update.py
```
（安裝 requirements-base.txt：requests/PyYAML/feedparser/watchdog/paramiko/groq/pymupdf/python-pptx/python-docx/pillow/openpyxl/markitdown/reportlab/matplotlib/qrcode/youtube-transcript-api/yt-dlp＋跨線共用 google-genai/markdown/pandas/bs4/psutil/flask）

**再依你要跑的任務線裝專屬檔**（`workspace-bundle\infra\requirements-<線>.txt`）：

| 任務線 | 專屬檔 | 內容 | 裝法 |
|---|---|---|---|
| Finance | `requirements-finance.txt` | pywin32（deep_report 用 win32com） | `python -m pip install -r <REPO>\workspace-bundle\infra\requirements-finance.txt` |
| Video（三機） | `requirements-video.txt` | openai-whisper／auto-editor／openai／python-dotenv／pytesseract | 同上，換檔名 |
| Stock | `requirements-stock.txt` | 無額外（base 已含 pandas/bs4） | 略，直接 `-r stock-monitor\requirements.txt` |
| XQ 儀表板 | 無專屬 | 依賴 finance 環境＋google-genai（base 已含） | 不需另裝 |

一次裝多條線可逐條 `pip install -r`。**裝完必須重開終端**讓 PATH 生效（多 Python 假象陷阱）。

## 第 3 步：外部工具一鍵安裝

```powershell
powershell -ExecutionPolicy Bypass -File <REPO>\workspace-bundle\infra\setup\external_tools.ps1
```
安裝 ffmpeg、VLC、Obsidian、Tesseract、**Deno**、**Tailscale**。**裝完必須重開終端**讓 PATH 生效。

> Deno 不是選配：缺它 yt-dlp 抓得到 metadata，但**下載影片一律 403**（2026-11-06 PC1 66 支全滅）。
> Tailscale 裝完仍要人工 `tailscale up` 並在瀏覽器授權。

## 第 4 步：API Keys（人工，位置固定）

| Key | 位置 | 策略 |
|---|---|---|
| Gemini | `C:\Users\<user>\.gemini_api_key` | **每台獨立**（Google AI Studio 另建專案，各自 500 次/天/模型額度池，避免互搶） |
| Groq | `C:\Users\<user>\.groq_api_key` | 共用（轉錄/verify/vision 用量低） |
| Telegram（告警） | `C:\Users\<user>\.telegram_env`（`TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`） | 共用 |
| OpenRouter（選用） | `C:\Users\<user>\.openrouter_api_key` | 共用；finance analyze 第三 provider，沒 key 自動跳過 |

## 第 5 步：資料同步（2026-11-08 起改走 NAS，不再用 AnyDesk 複製）

| 資料 | 來源 | 說明 |
|---|---|---|
| 程式與 KB | `git clone` / `git pull` | KB 已在 repo 內；**新機不必從別台複製** |
| 金融 DB | 各機自己的 `financial_news\finance.db` | 不跨機同步；notebook 的版本每日 01:30 備份到 NAS |
| KB 正本 | notebook `knowledge-base\` | PC 的產出經 NAS 收割進正本；NAS `backup\` 只是備份 |
| 頻道狀態檔 | `shared\watched_channels_state.json` | 只有**跑 channel_watcher 的那台**需要最新版 |

> 舊做法（AnyDesk 手動複製 KB／DB／state）已作廢：現在是「PC 產出 → NAS 交換 → notebook 收割」單向流。

## 第 6 步：註冊機器身份

`<REPO>\config.py`：
- `MACHINE_ALIASES` 加 `"hostname小寫": "pcN"`
- `MACHINE_PATHS` 加該機路徑
- `MACHINE_ROLES` 加主要角色註記（全功能；角色不限制能力）

改完 commit + push（所有機器同步這份設定）。驗證：
```powershell
python -X utf8 -c "import sys; sys.path.insert(0, r'<REPO>'); import config; print(config.MACHINE, config.get_machine_role())"
```

## 第 7 步：環境健檢

```powershell
python <REPO>\workspace-bundle\infra\health_check.py
```
輸出含基礎層套件、設定檔、排程任務、視覺/生圖/KB 能力，以及 **四條任務線能力**（finance / video / stock / xq）——每線列出 `finance.db`、`~/.telegram_env`、whisper、tesseract、Excel 進程、snapshots 新鮮度等關鍵項，❌ 的項就是要補的。可 `--json` 輸出供腳本讀。

## 第 7.5 步：XQ 線人工前置（無法腳本，機器上手後做一次）
1. 安裝並登入 **XQ 看盤軟體**；開權限報價表（`輸出欄位 → DDE` 貼進 Excel，不用存檔）
2. 確認 **Excel 開著**＋PC 不待機；健檢中 `excel_running` 應為 ✅

## 第 8 步：排程（切換日才啟用！）

| 任務名稱 | 觸發 | 指令 | 裝在哪 |
|---|---|---|---|
| FinanceNews_Pipeline | 每 30 分 | `python pipeline.py --full --batch 150 --time-budget 480` | 一台 |
| FinanceNews_MorningReport | 每天 07:00 | `python pipeline.py --report --deep --slot morning` | 一台 |
| FinanceNews_EveningReport | 每天 19:00 | `python pipeline.py --report --deep --slot evening` | 一台 |
| ChannelWatcherDaily | 每天 22:30 | `python channel_watcher.py --once` | 一台 |
| **PublishOutboxDaily** | **每天 22:50** | `publish_daily.bat` | **pc1/pc2/pc3** |
| **HarvestPCDaily** | **每天 23:10** | `harvest_daily.bat` | **notebook** |
| **NasBackupDaily** | **每天 01:30** | `backup_daily.bat` | **notebook** |

> 任務名稱不帶機器後綴：排程是各機本地的，同名不衝突，且 `health_check.py` 以這些名稱判讀。
> **2026-11-08 起 `deploy.ps1 -RegisterTasks` 會依機器自動篩選**（outbox 只裝產出機、收割／備份只裝 notebook），不會把收割排到 PC。
> 用 `deploy.ps1 -RegisterTasks` 建立（會自動設定「充電/電池都可跑、錯過補跑、不重複啟動」）。
> 切換日舊機移除：`deploy.ps1 -UnregisterTasks`。

**切換日順序**：
1. 同步最新 watched_channels_state.json → 新機
2. 舊機：停用上述同名任務
3. 新機：建立並啟用任務
4. 若涉及報告發佈：先確認新機 `publisher\repo\` 的 remote 指向 `financial-reports.git`（誤指主 repo 會污染程式庫；不確定就刪掉 `publisher\repo\` 讓 build.py 重建）
5. 觀察一天確認正常後，舊機任務可刪除

## 已知陷阱（踩過的坑）

1. **多 Python／舊 shell PATH 假象**：套件裝了但 import 失敗 → 重開終端再驗證
2. **watched_channels_state.json 過期** → 歷史影片全被重下載重轉錄，燒 Groq 額度
3. **publisher repo remote 指錯** → push 會污染主 vault repo
4. **run_pipeline.py 寫死 VLC 路徑** `C:\Program Files\VideoLAN\VLC\vlc.exe` → VLC 必裝預設路徑
5. **Gemini 免費層額度**：每專案每日 500 次/模型，台灣時間約 15:00 重置；分析積壓事件會快速燒完
6. **NAS Python 3.8** 裝不了 google-genai → 只能純收集
7. **deno 缺了 yt-dlp 會 403**：metadata 正常、下載全死（PC1 66 支全滅）；`smoke_test` 會列 ❌
8. **`.bat` 在 `chcp 65001` 之前不要放中文**：UTF-8 位元組可能含 `&`／`|`，cmd 會當指令分隔（實噴 `'se' 不是命令`）
9. **`cmdkey` 是認「主機名」的**：`\\datanas\…` 不通是正常的，請用 IP；FQDN 要另外存一筆
10. **`.ps1` 含中文要存 UTF-8 with BOM**（PowerShell 5.1 會用 ANSI 讀沒 BOM 的檔 → 語法錯誤）；`.bat` 則相反（不要 BOM、不要中文）
