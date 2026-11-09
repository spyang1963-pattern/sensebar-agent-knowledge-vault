# 新機一鍵部署（現行版，2026-11-08）

> 適用：PC1／PC2／PC3（產出機）與 notebook（收割＋正本）。
> 這份是「**現在真的要做的清單**」；`ONBOARDING.md` 是 2026-08 的舊手冊（金融線為主，部分已過時），
> 兩者衝突時以本檔與 `NAS-WHITEPAPER.md` 為準。
>
> 一句話：**程式與工具可以一鍵，金鑰／NAS 憑證／Tailscale 登入／排程切換一定要人工。**

---

## 0. 先分清楚這台機器是什麼角色

| 角色 | 機器 | 必需 | 不需要 |
|---|---|---|---|
| 產出機 | pc1 / pc2 / pc3 | 跑 pipeline、產生 KB 條目、22:50 打包到 NAS（或本機 outbox） | 23:10 收割、01:30 備份 |
| 收割機 | notebook | 23:10 從 NAS 收割、01:30 備份到 NAS、`knowledge-base\` 是**唯一正本** | 大量轉錄（可用但非必要） |

`config.py` 會用主機名判斷角色（`MACHINE_ALIASES`）。**新主機名一定要先加進去**，否則
`deploy.ps1` 會直接中止（這是刻意的，避免在錯的機器建排程）。

---

## 1. 一鍵流程（照順序做，約 20 分鐘）

```powershell
# 1) 取得程式碼（三機統一 D:\AI-Agent-Workspace）
git clone https://github.com/spyang1963-pattern/sensebar-agent-knowledge-vault.git D:\AI-Agent-Workspace

# 2) 先看會做什麼（不寫入）
powershell -ExecutionPolicy Bypass -File D:\AI-Agent-Workspace\workspace-bundle\infra\setup\deploy.ps1 -Machine pc2 -DryRun

# 3) 實際部署
powershell -ExecutionPolicy Bypass -File D:\AI-Agent-Workspace\workspace-bundle\infra\setup\deploy.ps1 -Machine pc2

# 4) 關掉終端、重開（PATH 生效），然後驗收
python -X utf8 D:\AI-Agent-Workspace\workspace-bundle\infra\setup\smoke_test.py

# 5) 只有切換日才註冊排程（見 §4）
powershell -ExecutionPolicy Bypass -File D:\AI-Agent-Workspace\workspace-bundle\infra\setup\deploy.ps1 -SkipSetup -RegisterTasks
```

---

## 2. 自動化涵蓋到哪裡（現況）

| 項目 | 自動？ | 由誰做 | 備註 |
|---|---|---|---|
| Git | ✅ | `setup_new_pc.bat` | 沒裝就 winget 安裝；有 repo 就 `git pull --ff-only` |
| Python 3.12 | ✅ | `setup_new_pc.bat` | 沒裝就 winget 安裝 |
| Python 套件 | ✅ | `infra\update.py`＋`requirements-{base,video,finance,stock}.txt` | base 已含 yt-dlp／python-docx／paramiko／google-genai |
| ffmpeg／ffprobe | ✅ | `external_tools.ps1` | 燒字幕、合併音訊必需 |
| VLC | ✅ | `external_tools.ps1` | **必須預設路徑**（`run_pipeline.py` 寫死） |
| Tesseract | ✅ | `external_tools.ps1` | 文件圖片 OCR 備援 |
| **Deno（JS runtime）** | ✅（2026-11-08 補） | `external_tools.ps1` | 缺它 yt-dlp 抓得到 metadata 但**下載影片一律 403** |
| **Tailscale** | ✅（2026-11-08 補） | `external_tools.ps1` | 不同網段時靠它連 NAS；登入仍要人工 |
| 執行期目錄 | ✅ | `deploy.ps1` | `working`／`output`／`videos`／`logs`／`raw`／`shorts`／`shared\tasks`／`shared\<machine>\{status,results}` |
| 機器身份 | ✅（檢查） | `deploy.ps1` | 讀 `config.py`；不符直接中止 |
| 排程（outbox／收割／備份） | ✅（2026-11-08 補） | `deploy.ps1 -RegisterTasks` | 依機器自動篩選，不會把收割排到產出機 |
| 健檢 | ✅ | `infra\health_check.py` | 金融／影音／股票／XQ 四線能力 |
| **部署後自我檢查** | ✅（2026-11-08 補 NAS 項） | `infra\setup\smoke_test.py` | 唯讀；含 deno、NAS 可達性、憑證、排程 |
| Groq key | 半自動 | `setup_new_pc.bat` | 可互動輸入；也可手動放 `~\.groq_api_key` |
| **Gemini key** | ❌ | 人工 | `~\.gemini_api_key`，**每台獨立** |
| **Telegram** | ❌ | 人工 | `~\.telegram_env` |
| **NAS 帳號憑證** | ❌ | 人工 | `cmdkey /add:<NAS> /user:producer`（產出機）或 `harvest`（notebook） |
| **Tailscale 登入** | ❌ | 人工 | `tailscale up` 後在瀏覽器授權（一次性） |
| **排程切換** | 半自動 | 人工決定時機 | 同一任務全時間只能一台跑 |

---

## 3. 人工必做的 4 件事（腳本不會替你做）

### 3.1 金鑰

| Key | 位置 | 策略 |
|---|---|---|
| Gemini | `%USERPROFILE%\.gemini_api_key` | **每台獨立**（免費層各自 500/日，共用會互搶） |
| Groq | `%USERPROFILE%\.groq_api_key` | 共用（轉錄／vision） |
| Telegram | `%USERPROFILE%\.telegram_env` | 共用（告警） |
| YouTube cookies（選用） | `<repo>\cookies.txt` | 只在需要會員／年齡限制影片時；**等同帳密，勿 commit** |

### 3.2 NAS 憑證（產出機＝`producer`；notebook＝`harvest`）

先確認 NAS 走哪條路（兩條都測，哪條通就用哪條）：

```powershell
Test-NetConnection 192.168.1.121  -Port 445 -InformationLevel Quiet   # 同一內網
Test-NetConnection 100.65.113.20  -Port 445 -InformationLevel Quiet   # Tailscale
```

存憑證（密碼來自 notebook 的 `%USERPROFILE%\.nas_accounts.json`；**不要貼進對話**）：

```powershell
$nas = "192.168.1.121"        # 或 100.65.113.20
$s = Read-Host -AsSecureString "貼上 NAS 密碼"
$p = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
       [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
cmdkey /add:$nas /user:producer /pass:$p      # notebook 改成 /user:harvest
$p = $null; $s = $null
cmdkey /list:$nas
```

驗證（產出機要「讀得到、寫得進自己那格、寫不進 backup」）：

```powershell
Restart-Service LanmanWorkstation -Force
Test-Path \\<nas>\exchange
Set-Content \\<nas>\exchange\<machine>\outbox\_probe.txt "ok"
Remove-Item  \\<nas>\exchange\<machine>\outbox\_probe.txt -Force
try { Set-Content \\<nas>\backup\_x.txt "x" -ErrorAction Stop; "NG" } catch { "OK: backup 被拒" }
```

### 3.3 Tailscale 登入

```powershell
tailscale up            # 印出網址，到瀏覽器用「同一個帳號」授權
tailscale ip -4         # 記下這台的 100.x
```

授權後把 IP 寫進 `config.py` 的 `TAILSCALE_IPS`（PC3 目前是 `None`），commit + push。

### 3.4 排程切換（單一寫入者）

同一任務全時間只能一台跑。切換時：**舊機停用 → 新機註冊 → 觀察一天 → 舊機刪除**。

---

## 4. 排程清單（2026-11-08 現行）

| 任務 | 時間 | 機器 | 指令 | 用途 |
|---|---|---|---|---|
| `PublishOutboxDaily` | 22:50 | pc1/pc2/pc3 | `publish_daily.bat` | 打包 → NAS `exchange\<machine>\outbox`（自動偵測機器；LAN 不通改用 tailnet；兩條都不通才 fallback 本機） |
| `HarvestPCDaily` | 23:10 | **notebook** | `harvest_daily.bat` | 收割 NAS（pc1；pc2/pc3 未上 NAS 前仍走各機）→ `knowledge-base\` |
| `NasBackupDaily` | 01:30 | **notebook** | `backup_daily.bat` | KB／finance.db／shared → NAS `backup\` |
| `ChannelWatcherDaily` | 22:30 | 一台 | `channel_watcher.py --once` | 頻道掃描（單一寫入者） |
| `FinanceNews_*` | 每 30 分／07:00／19:00 | 一台 | `pipeline.py …` | 金融線（單一寫入者） |

`deploy.ps1 -RegisterTasks` 會**依機器自動篩選**：outbox 只裝在 pc1/2/3，收割與備份只裝在 notebook。

---

## 5. 驗收（三關，全部要綠）

```powershell
# 1) 唯讀自我檢查（身份、工具、金鑰、NAS、排程）
python -X utf8 workspace-bundle\infra\setup\smoke_test.py

# 2) 打包演練（不寫檔）
python -X utf8 publish_outbox.py --dry-run

# 3) 真的推一次（產出機）
python -X utf8 publish_outbox.py --outbox "\\<nas>\exchange\<machine>\outbox" --ledger working\_outbox_published_nas.json
```

> `<nas>` 先試 `192.168.1.121`（同內網），不通就改 `100.65.113.20`（Tailscale）。
> `publish_daily.bat` 會自己判斷（機器名從 `config.py` 取，不用為每台改檔）。

期望：`smoke_test` 0 項失敗；dry-run 列出包數；真實推送 `失敗 0`，NAS 上
`Get-ChildItem \\<nas>\exchange\<machine>\outbox -Directory` 數量與本機一致。

notebook 另外驗：

```powershell
python -X utf8 harvest_pc.py --machine pc1 --dry-run      # 應全 skipped_same
```

---

## 6. 踩過的坑（新機一定會遇到，先看這段）

1. **deno 不是選配**：缺它時 yt-dlp 抓 metadata／列格式都正常，**只有真正下載影片會 403**，
   任務 14 秒就失敗。PC1 曾因此 66 支全滅。`smoke_test` 會把它列為 ❌。
2. **`.bat` 在 `chcp 65001` 之前不要放中文**：UTF-8 位元組可能含 `&`／`|`，cmd 會當指令分隔
   （實測噴 `'se' 不是內部或外部命令`）。本專案的 `.bat` 一律 ASCII 註解。
3. **SMB 對同一台主機只保留一個 session**：換帳號測試前先 `Restart-Service LanmanWorkstation`，
   否則會沿用舊身份，看起來像「權限設錯」。
4. **`cmdkey` 是「認主機名」的**：`\\datanas\…` 不通是正常的；請用 IP。
   Tailscale 的 FQDN 要先為那個名稱另存一筆 `cmdkey` 才會通。
5. **git 工作區很髒時 `git pull --ff-only` 會失敗**：部署前先看 `git status`，
   不要把別台帶來的未提交變更硬蓋掉。
6. **`shared\tasks` 不存在時 worker 會「靜默領不到任務」**：`deploy.ps1` 會建立，別手動刪。
7. **同機只能有一個 worker**：`worker.py` 會寫 `working\_worker_<machine>.lock`；
   同時跑兩個會重複領同一筆任務。
8. **NAS 上的 Tailscale 升級會覆蓋 privilege**（見 `NAS-WHITEPAPER.md` §5.2），
   升級後若 `tailscale0` 不見，先查 `/var/packages/Tailscale/conf/privilege`。
9. **`.ps1` 含中文一定要存成「UTF-8 with BOM」**：PowerShell 5.1 對沒有 BOM 的 `.ps1`
   會用 ANSI（cp950）解讀，中文註解可能被拆成引號／逗號而**語法錯誤**（實測
   `external_tools.ps1` 就是這樣壞掉的）。`.bat` 相反：**不要 BOM、不要中文**。
10. **`setup.bat` 是舊版**（只裝 auto-editor／groq／ffmpeg／VLC），不要拿它當新機安裝；
    一律用 `deploy.ps1`。
11. **Tesseract 裝了但不在 PATH**（PC2 實踩）：winget 版不會自己加 PATH，
    `pytesseract` 會直接 `TesseractNotFoundError`。`external_tools.ps1` 現在會自動把
    `C:\Program Files\Tesseract-OCR` 加進使用者 PATH；加完要開新終端。
12. **Obsidian 的實際路徑是 `%LOCALAPPDATA%\Programs\Obsidian\Obsidian.exe`**（不是
    `%LOCALAPPDATA%\Obsidian\`）。要讓 `.obsidian\` 出現，用 Obsidian 開一次
    `D:\AI-Agent-Workspace` 當 vault 即可（設定會存在 repo 內、可同步）。
13. **改了 repo 一定要 `git push`**：其他機器只拉得到 origin。PC2 曾因此拿到舊版
    `external_tools.ps1`（沒有 Deno）而卡住。**檢查法**：`git status -sb` 若顯示
    `ahead N` 就是還有 N 個 commit 沒推。
    **還有一個陷阱**：`AGENTS.md` 在 git 裡登記的是小寫 **`agents.md`**，而 git 的
    pathspec 分大小寫（Windows 檔案系統不分）→ `git add AGENTS.md` 會**靜默什麼都不做**，
    改完的文件就永遠沒進 commit。查法：`git ls-files -v | findstr /i agents`。

14. **把「狀態回報」貼給另一台 agent 時，前面一定要加一句**
    「以下是狀態回報，不是任務；不要執行任何動作」。否則 agent 可能把回報裡的
    「要不要開始領任務？」「先手動跑一支測試影片」當成指令去做（2026-11-09 實際發生過一次，
    幸好當下沒有任何動作）。
15. **任務管理 GUI「點了沒反應」幾乎都是 pythonw 靜默死亡**（2026-11-09 PC2 實踩）：
    `pythonw.exe` 沒有主控台，啟動期任何例外都不會顯示，程式直接消失。最經典的觸發點是
    **雙擊 `.pyw`**——舊的 `task_manager_gui.pyw` 是 2026-07 的副本，第 13 行是沒有防護的
    `sys.stdout.reconfigure(...)`，而 pythonw 下 `sys.stdout` 是 `None` → 一啟動就
    `AttributeError`（已實測：同一份檔用 `python.exe` 開得起來，用 `pythonw.exe` 退出碼 1、
    沒有視窗、沒有訊息）。另一個靜默死法是舊的單一實例鎖：`%TEMP%\task_manager_gui.lock`
    裡的 PID 被別的程式重用，GUI 就 `sys.exit(0)`。
    **現在的防護**：`.pyw` 改成薄殼（實作只有 `task_manager_gui.py` 一份）、單一實例改用
    具名 mutex（不會有殘留鎖）、任何啟動例外都跳 MessageBox + 寫
    `working\task_manager_gui_error.log`。**開 GUI 請用 `launch_gui.bat`**（已進 repo，
    `pythonw` → `pyw` → `python` 依序嘗試）。排錯第一步永遠是**在有主控台的視窗跑**
    `python -X utf8 task_manager_gui.py`，錯誤就會直接印在畫面上。
16. **`管理介面.bat`／`.vbs`／`.lnk` 沒有進 git**（是舊的個人捷徑，`.lnk` 還寫死
    `C:\Users\hpspy\...\pythonw.exe`）。所以 PC2／PC3 上不會有這些檔，雙擊 `.py`／`.pyw`
    會走到檔案關聯，行為各機不同。跨機一律用 repo 內的 `launch_gui.bat`。

---

## 7. 目前的缺口（2026-11-08 盤點）

| 缺口 | 影響 | 狀態 |
|---|---|---|
| `external_tools.ps1` 原本沒有 deno／Tailscale | 新機會重演「下載 403」與「連不到 NAS」 | ✅ 已補 |
| `deploy.ps1` 原本沒有 outbox／收割／備份排程 | 新機裝好也不會自動發佈／收割 | ✅ 已補（依機器篩選） |
| `smoke_test.py` 原本不檢查 NAS／憑證／排程 | 裝完看起來全綠，實際上線才發現連不到 NAS | ✅ 已補 |
| `ONBOARDING.md` 第 3／5／8 步是 2026-08 舊流程 | 會叫人用 AnyDesk 複製 KB、漏掉 deno 與新排程 | ⚠ 已在本檔標示；ONBOARDING 僅保留金融線細節 |
| PC2 ready（2026-11-09 00:1x） | 環境、Deno、Tesseract PATH、Tailscale、NAS `producer` 憑證與寫入權限全部驗證通過；**刻意未註冊排程**（尚無產出） | ✅ 完成 |
| PC3 尚未存 NAS 憑證與 Tailscale 登入 | 每晚 `offline`／無法發佈 | ⏳ 待做（每台一次，見 §3） |
| PC3 尚未遷到 `D:\AI-Agent-Workspace`、`TAILSCALE_IPS["pc3"]=None` | 無法納入自動流程 | ⏳ 待做 |
