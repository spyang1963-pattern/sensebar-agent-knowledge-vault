# PC1 自主工作包（交給 PC1 上的 agent 讀）

> 建立：2026-11-06　對象：**在 PC1 上跑的 coding agent**
> 你不需要問人，照這份做完 A、B 兩階段；C 階段有一步要管理員權限，做不到就回報。
> 全程用繁體中文回報。指令一律 `python -X utf8 ...`（Windows 主控台 cp950 會讓中文輸出變亂碼）。

---

## 0. 你是誰、在哪裡

| 項目 | 值 |
|---|---|
| 機器代號 | `pc1`（`config.MACHINE`，**不是** hostname） |
| hostname | `DESKTOP-NDLV9LI` |
| Tailscale IP | `100.84.223.110` |
| 工作區 | `D:\AI-Agent-Workspace`（三機統一，別用舊的 `D:\sensebar-agent-knowledge-vault`） |
| 自己的知識庫 | `D:\AI-Agent-Workspace\knowledge-base`（**本機實體目錄**，不是網路磁碟） |
| 影片 | `D:\YouTube_Videos`、`D:\AI-Agent-Workspace\videos` |
| 角色 | `worker`（收任務、跑產線、產出逐字稿／筆記／摘要） |
| 另一台 | `notebook` = `100.111.44.63`，KB 的**唯一正本**、收割者 |

**先讀這三份**（順序不要顛倒）：

1. `AGENTS.md`（根目錄）— 全部踩過的坑與規則
2. `workspace-bundle/HANDOFF-3MACHINE-DEPLOY.md` — 三機部署事實、PC1 已驗收項目
3. `workspace-bundle/STEP7-HARVEST-DESIGN.md` — 收割架構（你要配合的規格）

---

## 1. 現況（notebook 端看到的，2026-11-06）

1. **你的 KB 是本機的**：`D:\AI-Agent-Workspace\knowledge-base`。三機**不互相同步** KB，
   notebook 才是正本；你的產出要「收割」回去，不是複製整份 KB。
2. **`shared\` 目前沒有互通**：notebook 的 `shared\tasks`（1809 筆）裡沒有任何
   `assigned_to=pc1` 的任務，代表你的任務是在自己本機跑的，成果沒有回到 notebook。
3. **收割機制剛備好**（2026-11-06）：
   - PC1 端：`publish_outbox.py`（把完成的 KB 產出打包到 `shared\pc1\outbox\<tid>\`）
   - notebook 端：`harvest_pc.py`（UNC 主動 pull，含去重／衝突／帳本）
4. 你不需要、也不應該寫入 notebook 的 KB。方向永遠是 **notebook 來讀你**。

---

## 2. 階段 A：連結你自己的知識庫（先做，零風險）

### A1. 確認 KB 裡真的有你產出的東西

```powershell
cd D:\AI-Agent-Workspace
python -X utf8 -c "import pathlib; kb=pathlib.Path('knowledge-base'); print('md', len(list(kb.rglob('*.md'))), 'srt', len(list(kb.rglob('*.srt'))), 'docx', len(list(kb.rglob('*.docx'))))"
```

- 數字 > 0 → 你的產線確實有寫進本機 KB，往 A2。
- 數字是 0 或很小 → 先確認任務是真的有完成（`shared\tasks\task_*.json` 的 `status`），
  不要急著重跑（重跑會重送 Whisper／Gemini，浪費額度）。

### A2. 用 KB 查詢工具驗證「讀得到」

```powershell
python -X utf8 knowledge-base\kb_query.py --list
python -X utf8 knowledge-base\kb_query.py "關鍵字" --srt "output\<課程>\字幕.srt" --video "output\<課程>\剪輯後.mp4"
```

驗收：`--list` 列得出主題、關鍵字查詢有結果。

### A3. 不要做的事

- ❌ 不要從 notebook 複製整份 `knowledge-base\`（124MB 且每天長大，只會兩邊分歧）
- ❌ 不要 `git add knowledge-base\`（KB 已在 `.gitignore`，資料不是程式碼）
- ❌ 不要刪任何 KB 條目來「重新整理」

---

## 3. 階段 B：連結 Obsidian（建議：vault 指本機 KB，不要指 SMB）

### B1. 做法（推薦，最快也最穩）

1. 開 Obsidian → **Open folder as vault** → 選 `D:\AI-Agent-Workspace\knowledge-base`
2. 命名為 `AI-Agent-KB (PC1)`

**為什麼不要直接把 vault 指到 `\\100.111.44.63\...`（notebook）**

| 問題 | 後果 |
|---|---|
| Obsidian 會索引＋監看整個 vault | SMB 上每個檔案操作都要走網路，開 vault 會卡數十秒 |
| 斷網／notebook 休眠 | vault 變成空殼，Obsidian 可能把索引狀態寫壞 |
| 兩個 Obsidian 同時寫同一份 md | 檔案鎖衝突、內容互蓋（notebook 是正本，不能冒這個險） |

→ **SMB 只用來「看」，不要當 vault。** 要看 notebook 的資料，用檔案總管開 UNC 路徑即可。

### B2. 如果你也需要 Clipping

Obsidian 一個視窗只開一個 vault。用**第二個 vault**（`Open another vault`）指到
`D:\AI-Agent-Workspace\Clipping`，不要用 junction／symlink 把 Clipping 塞進 KB
（Obsidian 對 Windows junction 的支援不穩定，且會讓 KB 目錄多出非 KB 檔案）。

### B3. 建議設定（避免 Obsidian 拖慢產線）

- Settings → Files & Links → **Excluded files** 加入：`working/`、`output/`、`logs/`、`.git/`
  （若 vault 只指 KB 就不需要，但留着沒壞處）
- 不用裝任何社群外掛就能讀 `.md`；`.srt` 想預覽再加外掛
- ❌ 不要讓 Obsidian 去「同步」這個 vault（沒有 Obsidian Sync，也不需要）

### B4. 驗收

1. Obsidian 左側看得到 `youtube-clips` 等子資料夾與 `.md` 條目
2. 點開任一逐字稿，內文正常、沒有亂碼
3. 搜尋一個你確定在內文出現的詞，找得到

回報：vault 路徑、看到的 `.md` 數量、搜尋測試結果。

---

## 4. 階段 C：收割回 notebook（PC1 只做兩件事）

> 架構：PC1 把文字產出**複製**到本機 `shared\pc1\outbox\`，最後寫 `manifest.json`；
> notebook 用 `harvest_pc.py` 透過 UNC **主動 pull**。PC1 不需要寫入 notebook。

### C0. 先更新程式碼

```powershell
cd D:\AI-Agent-Workspace
git status --porcelain          # 有未提交變更先看是什麼，不要亂 reset
git pull --ff-only              # 取得 publish_outbox.py（2026-11-06 新增）
```

### C1. 打包到 outbox

```powershell
python -X utf8 publish_outbox.py --dry-run    # 先看會打包幾包
python -X utf8 publish_outbox.py              # 實際打包
```

特性（讀過再執行，才不會誤會）：

- **複製不搬**：本機 KB 條目原封不動
- **manifest.json 最後寫**：先寫 `.tmp` 再 rename，收割器看到 manifest 才算完整
- **冪等**：帳本 `working\_outbox_published.json` 記大小＋mtime，沒變就跳過
- **同支影片只打包一次**：`youtube`／`note`／`summary` 三個任務指向同一個 stem，只取第一包
- 打包失敗會列出來（常見：找不到 KB 條目、任務沒有產出）→ 照訊息查，不要硬改 KB

驗收：

```powershell
python -X utf8 -c "import pathlib,json; o=pathlib.Path('shared/pc1/outbox'); d=[p for p in o.iterdir() if (p/'manifest.json').exists()]; print('完整包', len(d)); print([p.name for p in d][:10])"
```

- 「完整包」數量應接近你 KB 裡的「影片條目數」（逐字稿為單位，不是檔案數）
- 隨便開一個 `manifest.json`，確認 `schema=1`、`video_id`、`kb_subdir`、`files` 都有值

### C2. 開唯讀 SMB 分享（需要「系統管理員」PowerShell）

```powershell
New-SmbShare -Name "AI-Agent-Workspace" -Path "D:\AI-Agent-Workspace" -ReadAccess "Everyone"
New-SmbShare -Name "YouTube_Videos"     -Path "D:\YouTube_Videos"     -ReadAccess "Everyone"

# NTFS 也要給，否則會出現「分享 Everyone 但複製被拒（錯誤 5）」
icacls "D:\AI-Agent-Workspace" /grant "*S-1-1-0:(OI)(CI)(RX)" /T /C /Q
icacls "D:\YouTube_Videos"     /grant "*S-1-1-0:(OI)(CI)(RX)" /T /C /Q
```

- 用 SID `S-1-1-0` 而不是 `Everyone` 字串（多語系／本機化名稱問題）
- **只給 RX（讀取＋執行），不要給 W（寫入）**：notebook 不需要寫你
- 若沒有管理員權限 → **停下來回報**，不要改用「複製到 notebook」的替代方案

驗收（在 PC1 自己這台先確認分享存在）：

```powershell
Get-SmbShare -Name "AI-Agent-Workspace" | Select-Object Name,Path
Test-Path "\\localhost\AI-Agent-Workspace\shared\pc1\outbox"
```

最終驗收由 notebook 執行（你只要回報「已開分享」）：

```powershell
Test-Path "\\100.84.223.110\AI-Agent-Workspace\shared\pc1\outbox"
```

### C3. 之後：每日一次打包（等 notebook 那邊收割排程上線再開）

```powershell
# 手動：
python -X utf8 publish_outbox.py
# 排程（例：每天 22:50，收割器 23:10 來收）：
schtasks /Create /TN "PublishOutboxDaily" /TR "cmd /c cd /d D:\AI-Agent-Workspace && python -X utf8 publish_outbox.py" /SC DAILY /ST 22:50 /F
```

先在收割器上線前**不要**建排程，避免每天重寫 outbox。

### C4. 派工（`shared\`）— 先不要動

跨機派工需要 `shared\` 共用，但現況你本機的 `shared` 是獨立副本。
**這一步等 notebook 決定「共用 shared」或「改成資料庫」後再處理**，現在動它會讓
`task_status.json` 與 `shared\tasks` 互相覆蓋（AGENTS.md 有兩次實踩）。

---

## 5. 禁止事項（做錯會傷到正本或浪費額度）

| ❌ 不要 | 原因 |
|---|---|
| 跑 `channel_watcher.py --once` | 會寫 `shared\watched_channels_state.json`，與 notebook 雙寫，造成重複下載 |
| 寫入／覆蓋 notebook 的 `knowledge-base\` | 正本只有 notebook 能寫；你只提供 outbox |
| `git add knowledge-base\` 或 `shared\` | 兩者都在 `.gitignore`，是執行期資料 |
| 手改 `.srt` 檔名 | 只改 `.md` 檔名，`.srt` 靠 `.link.txt` 的 video_id 配對 |
| 重跑「已完成」的任務 | worker 多半 skip-if-exists，重跑會重送 Whisper／Gemini（免費額度一天約 330 次） |
| 用 `Set-Content -Encoding UTF8` 寫 JSON | PowerShell 5.1 會加 BOM，`json.loads` 直接爆（請用程式寫或 `[System.IO.File]::WriteAllText` + UTF8Encoding($false)） |
| 刪 `working\_note_parts\` 以外的快取 | 筆記／摘要快取刪了就會重花 Gemini 額度 |
| 用 junction／symlink 把多個目錄拼成一個 Obsidian vault | Obsidian 不穩定，且刪檔會直接刪到正本 |

---

## 6. 回報格式（做完直接貼這段，不要寫長篇心得）

```
【PC1 回報】
A. KB        ：md __ / srt __ / docx __；kb_query --list 主題數 __；關鍵字測試 __（成功/失敗）
B. Obsidian  ：vault = ______________；看到的 .md 數 __；搜尋測試 __（成功/失敗）
C.1 outbox   ：dry-run 預計 __ 包；實際 __ 包；失敗 __ 筆（錯誤訊息：______）
C.2 分享     ：已開（是/否）；Get-SmbShare 顯示 ______；本機 Test-Path ______
其他阻礙     ：______
```

有錯誤就把**原始指令輸出**一起貼（不要只寫「失敗了」）。

---

## 7. 快速自我檢查（有問題先跑這支）

```powershell
cd D:\AI-Agent-Workspace
python -X utf8 -c "import config,sys; print('machine', config.MACHINE, 'role', config.get_machine_role(), 'ip', config.TAILSCALE_IPS.get(config.MACHINE))"
python -X utf8 workspace-bundle\infra\setup\smoke_test.py    # 唯讀，結束碼＝失敗數
deno --version                                              # YouTube 下載需要；沒有就先裝
```

- `smoke_test.py` 有紅字 → 先修環境，不要開始跑任務
- 缺 `deno` → `winget install --id DenoLand.Deno -e --accept-source-agreements --accept-package-agreements`
  （缺它會讓 yt-dlp 全部 403，且**只有真正下載時才會炸**，metadata 測試看不出來）

---

## 8. 這次不要做的事（範圍控制）

- 不改 `worker.py`／`channel_watcher.py` 的排程邏輯
- 不動 `finance.db`、`XQ`、`stock-monitor`（那些不是這次目標）
- 不做「把 notebook KB 複製過來」或「雙向同步」
- 不建立任何 Windows 排程（除了 C3 明列的那個，且要等指示）

有疑問先停在原地、回報，不要自行擴大範圍。
