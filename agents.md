# AI Agent 影片自動化生產線

## OpenCode 額度（成本敏感，別亂跑）

**成本原則**：每次「跑腳本查額度」＝ 1 次模型請求 + 數百 token 進上下文，是回覆附一行字的
數十倍成本。所以**不要每個回合都跑**。

- **零成本（推薦）**：`oc_widget.py` 常駐小窗（`pythonw oc_widget.py` 或 `oc_widget.bat`），
  每 60 秒自己抓數字，不經過模型、不佔配額、不花錢。
- **對話中查**：使用者打 `/usage`（`.opencode/commands/usage.md`，1 次請求）。
- **何時主動跑**：長任務開工時、回合數已多（≈50+）時、或使用者問到額度時，才跑
  `python oc_usage.py`，並在回覆最後附一行：
  `額度：免費 UTC日 337 次（上限動態）｜Go 月 100% ⛔→11/10`。
- 免費模型撞牆訊號 `Free usage limit reached`。
- **免費池不是「200 次／5 小時」（2026-11-04 更正，別再照舊講）**：自 2026-10-23 起
  Zen 免費額度是「每個 IP × 每個「免費池日」（**本機 08:55 換日**）」的**動態** bucket，
  上限不公告，帳號／網路共用，UI 與 API 都查不到剩餘量。
  **顯示的 153/200（76%）只是本機把「最近 5h 的請求數」
  硬套 200 的估算，跟伺服器實際額度無關**——2026-11-04 就是顯示 76% 卻在本池日
  第 337 次請求被拒（21:31:52）。
  實務規則：**免費池只做短、可丟棄的事**；顯示日累計 ≥150 就當「隨時會斷」，
  長任務（轉錄、整批修檔、多工具 agent）一律先切 `opencode-go/*`。
- **2026-11-05 實測校準（本機 opencode.db ＋ opencode.log，勿再猜）**：
  - **換日時間是 08:55（本機）**，不是 00:00Z/08:00：11-04 21:43 被拒 → 隔日 09:47 才恢復；
    11-02 17:09 被拒 → 當日 23:29 恢復（6.3h）、11-03 02:00 被拒 → 09:11 恢復（7.2h），
    恢復點不固定在整點 → 伺服器是滾動式補回，客戶端顯示的「reset at 08:55」只是估算。
  - **337 不是配額**：本機撞牆點分別是 1 次、206 次、337 次（同日兩次撞牆 21:31/21:43 都是 337）；
    沒撞牆的日子可跑到 443、725 次（10-18／10-11）。可見上限與**帳號/IP 的其它消耗**共用，
    單機 DB 只能算「自己用了幾次」，算不出剩餘。
  - 撞牆訊息有兩種：`You've used today's free messages. They reset at HH:MM`（真額度）與
    `AI_APICallError: Free usage limit reached`（含暫時性；11-03 09:23 被拒、09:25 重試即成功）。
  - TUI（`oc_widget.py`）因此只顯示「日累計 + 5h 參考 + 上次撞牆當時累計」，**不顯示 /200 或 /337**；
    `oc_usage.py --reset-at 08:55` 可調換日時間。
- 免費數字是本機估算（DB assistant steps ≈ 請求數）；**Go 是官方精確值**：
  `GET https://opencode.ai/inference/go/v1/usage`（Bearer = auth.json 的 opencode-go key，
  純 HTTP、零 token），回 `rolling/weekly/monthly {percent,status,resetsAt}`。
  monthly `status=rate-limited` 代表該期已滿（2026-11-04 實測：標記 rate-limited 後
  Go 請求仍可成功，屬超額／計費狀態，不是硬擋；但別依賴）。

## 快速開始（新 PC 安裝）

1. 複製整個專案目錄到新 PC
2. 執行 `setup.bat`（Windows）安裝所有依賴
3. 到 https://console.groq.com 建立 API Key
4. 執行 `python run_pipeline.py raw/課程/原始.mp4`

## 目錄結構

```
專案根目錄/
├── run_pipeline.py              ← 一鍵執行完整流程
├── setup.bat                    ← 新 PC 一鍵安裝
├── opencode.json                ← opencode 設定
├── AGENTS.md                    ← 本說明文件
├── .opencode/skills/            ← 技能模組
│   ├── smart-cut/               ← 智能剪輯
│   ├── audio-to-srt/            ← 語音轉字幕
│   └── cover-image/             ← 封面生成
├── knowledge-base/              ← 知識庫
│   ├── kb_query.py              ← 查詢工具
│   └── traditional-kline/       ← 主題資料
├── raw/                         ← 原始影片（放入此處）
├── working/                     ← 暫存工作檔
└── output/                      ← 最終輸出
```

## 使用方式

### 一鍵跑完整流程
```powershell
python run_pipeline.py raw/課程代號/原始.mp4
```

### 查詢知識庫
```powershell
# 關鍵字搜尋
python knowledge-base/kb_query.py "紅黑紅" --srt "output/課程/字幕.srt" --video "output/課程/剪輯後.mp4"

# 列出所有主題
python knowledge-base/kb_query.py --list

# 看特定主題
python knowledge-base/kb_query.py --topic 03

# 開啟影片跳轉
python knowledge-base/kb_query.py "紅黑紅" --srt "字幕.srt" --video "影片.mp4" --open
```

### 手動跑各步驟
```powershell
# Step 1: 去靜音
python .opencode/skills/smart-cut/scripts/smart_cut.py raw/課程/原始.mp4 --out working/課程/trimmed.mp4

# Step 2: 語音轉字幕
python .opencode/skills/audio-to-srt/scripts/transcribe_groq.py working/課程/trimmed.mp4 --out working/課程/raw.json

# Step 3: 重新分段
python .opencode/skills/audio-to-srt/scripts/resegment.py working/課程/raw.json --out working/課程/reseg.srt --audio working/課程/trimmed.mp4

# Step 4: 術語校正
python .opencode/skills/audio-to-srt/scripts/apply_vocab.py working/課程/reseg.srt --out working/課程/corrected.srt

# Step 5: 驗證
python .opencode/skills/audio-to-srt/scripts/validate_srt.py --raw working/課程/reseg.srt --clean working/課程/corrected.srt

# Step 6: 產生純文字
python .opencode/skills/audio-to-srt/scripts/srt_to_txt.py working/課程/corrected.srt --out working/課程/clean.txt

# Step 7: 產生封面
python .opencode/skills/cover-image/draw_free.py "doodle style, stock market" --name cover --outdir output/課程
```

## 前置需求

- Python 3.10+
- ffmpeg（在 PATH 中）
- auto-editor（pip install auto-editor）
- groq（pip install groq）
- Groq API Key（免費：https://console.groq.com）
- VLC（可選，用於影片播放跳轉）

## API Key 設定

```powershell
# 方法一：環境變數
$env:GROQ_API_KEY = "你的key"

# 方法二：檔案（推薦）
Set-Content "$env:USERPROFILE\.groq_api_key" "你的key"
```

## 封面生成

使用免費 Pollinations.AI，不需要 API Key。
如需使用付費 OpenAI 版本，設定：
```powershell
$env:OPENAI_API_KEY = "你的key"
```

## 注意事項

- 影片名稱建議用英文或編號，避免中文路徑問題
- 預設封面風格為簡潔版（手繪K線筆記本）
- 知識庫查詢支援 12 個主題（傳統K線型態）
- 每部影片約需 5-10 分鐘處理時間

## 自動更新 @sensebar 知識庫

### 自動化流程

```
新影片發布 → 偵測新影片 → 下載字幕 → 同步到知識庫
                    ↓（無字幕時）
              下載音訊 → Whisper 辨識 → 同步到知識庫
```

### 安裝步驟（新 PC）

```powershell
# 1. 安裝 Python 套件
pip install yt-dlp groq plyer

# 2. 設定 Groq API Key（免費）
Set-Content "$env:USERPROFILE\.groq_api_key" "你的key"

# 3. 測試
python auto_update.py
```

### 設定 Windows 排程任務

> **注意（2026-11-03）**：以下 `SensebarAutoUpdate` 建立指令僅為歷史紀錄，**不要在新 PC 執行**。頻道掃描統一由 `ChannelWatcherDaily`（每天 22:30，`channel_watcher.py --once`）負責，@sensebar 與 20VTA 共用同一次掃描。

```powershell
# 【歷史紀錄，勿執行】舊的 10:00 任務
$taskName = "SensebarAutoUpdate"
$action = New-ScheduledTaskAction -Execute "D:\AI-Agent-Workspace\auto_update.bat"
$trigger = New-ScheduledTaskTrigger -Daily -At "10:00AM"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -AllowStartIfOnBatteries

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "每天自動檢查 @sensebar 新影片並更新知識庫" -Force
```

### 手動執行

```powershell
# 立即檢查更新
python auto_update.py

# 或執行批次檔
auto_update.bat
```

### 設定檔 config.yaml

```yaml
channel:
  url: "https://www.youtube.com/@sensebar"
  keywords:
    - "claude"
    - "codex"
    - "antigravity"
    - "opencode"
    - "agent"
    - "googlea"

output:
  subtitle_langs:
    - "zh-Hant"
    - "zh-TW"
    - "zh"
    - "zh-Hans"
    - "en"
```

### watched_channels（channel_watcher 監控清單）

```yaml
watched_channels:
  - name: "三師爸"
    channel_url: "https://www.youtube.com/@sensebar"   # 目前「不會被掃描」，僅供紀錄
    note: true                                          # 預設收成後產課程筆記
    subtitle_langs: ["zh-Hant", "zh-TW", "zh", "en"]
    playlists:
      - id: "PLkNQUBglz8..."                            # 播放清單：只用 id
        kb_dir: "人工智慧/AI agent-三師爸/AI Agent 基本功"
      - url: "https://www.youtube.com/@sensebar/streams" # 直播：必填，漏了就不會掃直播
        kb_dir: "人工智慧/AI agent-三師爸/直播"
        max_initial: 4        # 首次掃描處理支數（= 要補的支數 + 1~2 緩衝）
        burn_subs: true       # 有字幕也下載影片並燒字幕
        format: "720"         # 影片下載解析度預設（1080／720）；只影響要燒字幕的下載
```

**必知**：`channel_url` 目前**沒有任何作用**，真正被掃的只有 `playlists`（`id` 或 `url` 皆可）。`kb_dir.name == "直播"` 的來源會**自動**呼叫直播報告產生器；`format` 只供燒字幕下載用（預設 1080p H.264，`YT_DL_FORMAT_720` 為 720p）。

### 自動排程（現況：2026-11-03 修正）

**頻道掃描只有一個排程：`ChannelWatcherDaily`，每天 22:30 執行 `channel_watcher.py --once`，一次掃完 `watched_channels` 內所有頻道（@sensebar＋20VTA），每頻道每日僅掃一次。**

- **固定 22:30**，不改成其他時間；排程設定（2026-11-03）：
  - `StartWhenAvailable = true` → 22:30 若關機／休眠而錯過，開機後**補跑一次**
  - `DisallowStartIfOnBatteries = false`、`StopIfGoingOnBatteries = false` → 未插電也會在 22:30 正常跑，跑到一半拔電也不會被中止
  - `MultipleInstancesPolicy = IgnoreNew` → 補跑與固定掃描不會同時開兩份
  - 補跑與固定掃描合計仍以「一天一次」為原則；若補跑已跑完，當晚 22:30 仍照常掃（新片通常還沒有）

- 舊的 `SensebarAutoUpdate`（每天 10:00 執行 `auto_update.bat`）已 **Disable**，不要再啟用，否則 @sensebar 會變成一天掃兩次（10:00 與 22:30）。
- `auto_update.py` / `auto_update.bat` 仍保留供**手動**補片使用（`auto_update.bat` 已支援 `--no-pause`，排程呼叫時不會卡在 pause）。
- 手動補片後若 Clipping 有新增，記得跑 `python sync_clipping.py`。
- 舊說明（勿再照抄建立 10:00 排程）：原本的 `SensebarAutoUpdate` 會下載 YouTube 字幕／Whisper 辨識後同步到 `knowledge-base/youtube-clips`，日誌在 `logs/update_YYYYMMDD_HHMMSS.txt`，通知為桌面彈出視窗。

### 重要規則

1. **改完檔名要跑 sync**
   ```powershell
   python sync_clipping.py
   ```
   - 自動重新配對 .md 和 .srt
   - 自動同步到 knowledge-base/youtube-clips

2. **不要手動改 SRT 檔名**
   - 只改 .md 檔名，sync 會幫你配對
   - SRT 會根據 .md 裡的 YouTube URL 自動對應

3. **YouTube 連結要可點擊**
   - 格式：`[YouTube](https://www.youtube.com/watch?v=VIDEO_ID)`
   - 不是：`https://www.youtube.com/watch?v=VIDEO_ID`
   - 不是：`<https://https://www.youtube.com/watch?v=VIDEO_ID>`

4. **新影片加字幕**
   - 自動化：跑 `python auto_update.py`（會自動處理）
   - 手動：從 raw/ 找影片用 `run_pipeline.py` 處理

## Obsidian 整理 Clipping 目錄

### 重要規則

1. **改完檔名要跑 sync**
   ```powershell
   python sync_clipping.py
   ```
   - 自動重新配對 .md 和 .srt
   - 自動同步到 knowledge-base/youtube-clips

2. **不要手動改 SRT 檔名**
   - 只改 .md 檔名，sync 會幫你配對
   - SRT 會根據 .md 裡的 YouTube URL 自動對應

3. **YouTube 連結要可點擊**
   - 格式：`[YouTube](https://www.youtube.com/watch?v=VIDEO_ID)`
   - 不是：`https://www.youtube.com/watch?v=VIDEO_ID`
   - 不是：`<https://www.youtube.com/watch?v=VIDEO_ID>`

4. **新影片加字幕**
   - 有影片檔：用 `run_pipeline.py` 處理
   - 只有逐字稿：用 `generate_srt_from_clippings.py` 產生估計時間碼 SRT
   - 沒有字幕：從 raw/ 找影片用 Whisper 辨識

### 目錄結構

```
Clipping/
├── *.md                    ← 逐字稿（含 YouTube URL + 字幕內容）
├── *.srt                   ← 對應字幕檔
└── _archive_no_transcript/ ← 無逐字稿的重複版本
```

### 常見問題

| 問題 | 解決方法 |
|------|----------|
| .md 和 .srt 配對斷掉 | 跑 `python sync_clipping.py` |
| YouTube 連結不能點 | 改成 `[YouTube](URL)` 格式 |
| 無逐字稿的檔案 | 移到 `_archive_no_transcript/` |
| knowledge-base 沒同步 | 跑 `python sync_clipping.py` |

## 任務管理 GUI：新增 YouTube 任務（2026-11-03 修正）

`task_manager_gui.py` 的「新增任務 → YouTube」現在是**展開成逐支任務**，不再在 GUI 程序內同步跑完整流程。

- 輸入單一影片／播放清單／頻道網址皆可（`channel_watcher.expand_youtube_entries()` 解析；「最多處理支數」空白＝全部）。
- 解析後先做 **video_id 精確去重**（`channel_watcher.kb_video_index()` 掃 KB ＋ 本機 pending/processing 任務），已在知識庫或已有待處理任務的支會略過並回報數量。
- 每支寫成 `type="youtube"` 任務（`task_status.json` ＋ `shared/tasks/task_{tid}.json`），由 `worker.py` 領取；`worker.process_youtube_task()` 依序處理：有官方字幕→下載字幕→KB；無字幕→下載影片＋`run_pipeline.py --skip-cut`→KB；再依旗標建立並內嵌執行 note／summary 任務。
- 任務欄位：`video_id`、`title`、`kb_subdir`（預設 `youtube-clips`）、`harvest_to_kb`、`auto_note`、`auto_summary`、`burn_subs`、`assigned_to`（pc1/pc2/notebook，未填＝任一 worker 可領）。
- **陷阱**：`kb_video_index(refresh=True)` 首次約 1 分鐘（已放背景執行，對話框會顯示「正在比對知識庫」）；GUI 是長駐程序，**改完必須關閉重開**才會載入新碼，否則按「建立」仍是舊行為（看起來像沒作用、任務清單沒訊息）。
- 舊的 `channel_watcher.process_youtube_url()` 仍保留（上限 5 支、供手動呼叫），但 GUI 已不使用。

## channel_watcher 頻道自動監控（2026-09-23 更新）

### 已知陷阱（都被踩過，務必讀）

1. **auto-editor 完成後會自動開播放器**：`smart_cut.py` 呼叫 auto-editor 處理完預設「Do not open the output file after editing」，此環境的系統預設播放器是 PotPlayer → 直播逐支處理時 PotPlayer 一個接一個跳窗（使用者印象＝「一直打轉」）。**已修**：smart_cut.py 已加 `--no-open`。改回時勿移除。
2. **state 檔舊 bug（打轉真正主因一）**：舊版 `channel_watcher.py` 的 `process_has_subs` 成功分支 `continue` 會跳過 `save_channel_state`，只有離線轉錄分支會存。結果 `shared\watched_channels_state.json` 的 `last_video_id` 停在最早 → 每次掃描把已處理的支當「新片」重新下載＋轉錄（耗時且反覆）。**已修**：for 迴圈每支處理完統一保存。勿再改用 continue 跳過保存。
3. **`--once` 超過 10 分鐘無輸出**：多半是 PowerShell 管線緩衝假象，不代表卡住。判別法：另開視窗看 `logs\channel_watcher.log` 是否持續進展；執行時建議 `python -u ... --once *> 檔` 重導輸出。
4. **執行中途被中止的後果**：state 倒退 → 下次掃描重處理已完成的支。校正法：把該頻道 `last_video_id` 設為該清單**列表第一個** `id`（即「假裝全部處理過」→ 掃描時 0 新片）。20VTA streams 列表排序非直覺（首支未必最新上傳），但以此校正仍安全。
5. **Groq chat completions 在此環境回 403/404**（models 可用但 chat 被拒，疑似 region 限制）。直播摘要改用 **Gemini**：key 在 `~/.gemini_api_key`（deep_report.py 同款讀法），模型 `gemini-3.5-flash-lite`。
6. **漏掃直播的根因：設定只寫播放清單、沒寫 `/streams`（2026-10-16 實踩）**：`scan_all_channels()` 只逐一掃 `watched_channels[].playlists`，**`channel_url` 設了卻完全沒被使用**。三師爸（`@sensebar`）原本只有 7 個課程播放清單、沒有 `/streams` → 直播**一支都沒掃過**（當時 `@sensebar/streams` 有 142 支，KB 只有 11 支對應檔）。作者的習慣是「直播後才再歸類到清單上，有時不歸類」，所以**只監控清單必然漏片**；20VTA 之所以沒漏，是因為它有 `@20VTA/streams` 這個條目。**新頻道務必確認 `playlists` 裡有 `/streams`**。注意：用 **video_id** 比對「是否已收成」會大量失準——作者歸類的是「重新上傳/另一支」的影片，ID 與直播版不同（本次 131 支 ID 看似缺漏，實際只缺 4 支），判斷要以**標題＋上片日期**核對。
7. **首次掃描上限 `max_initial` 會決定補哪幾支**：`scan_playlist` 在「無 `last_video_id`／找不到上次 ID」時只取 `entries[:max_initial]`，並把游標跳到清單最前（最新）。若把 `max_initial` 設太大，會把**已收成過的舊片**再抓一遍（本次從 6 改成 4：`/streams` 最新 4 支正是唯一缺的 4 支，第 5 支起其內容早已存在）。首次掃描值 = 「要補的支數 + 1~2 支緩衝」，不要直接給 30。

8. **日後掃描「精準去重」＝只用 video_id（2026-10-16 實作，勿改成標題比對）**：`channel_watcher.kb_video_index()` 掃 KB 建 `{video_id: 條目路徑}`，`scan_playlist(dedup=True)` 對每支新片先查；命中即在 KB 任一目錄就**略過並仍推進游標存檔**（不可用 `continue` 跳過存檔，見陷阱 2）。命中訊息記入通知明細（`⏭️ 已在知識庫，略過`）。索引在 `scan_all_channels()` 開場 `refresh=True` 重建（warm 0.7s），同批新建條目即時回寫索引（跨清單重複也擋）。**為何不用標題去重**（實測後否決）：(a) 2133 筆舊條目表頭只有 `# YouTube Metadata`，真標題只在**檔名**（含 `YYYY-MM-DD_` 前綴、`:`→`_`）；(b) 正規化標題精確比對 142 支 `/streams` 只命中 22 支，作者歸類是**改標題重新上傳**；(c) 同標題不同影片的實例一堆（例：`週三 呂佳霖盤後分析與關鍵報告` 跨 2020-04-29／05-06 是不同集）→ 標題去重會誤略過真新片。**結論：標題／模糊比對一律不做；僅 video_id 精確去重。** 舊條目（無 id、無連結）無法精準去重，改以 `max_initial` 小值（1~4）當緩衝降低風險。

9. **首播影片的日期前綴要用 `release_date`，不是 `timestamp`（2026-11-02 實踩）**：`channel_watcher.get_video_date()` 原本以 `timestamp` 優先，但**首播（premiere）影片的 `timestamp` 會停在最早排定的時間**，即使實際延期首播也不會更新。實例：`hY5G0pT5xmE` 的 `upload_date=20261026`、`timestamp=2026-10-26 21:03:48+08:00`，但 `release_date=20261102`（實際 11/2 首播，影片開頭也說「轉眼間我們就來到11月了」），結果整組產出（逐字稿／SRT／筆記／直播報告／影片檔名）前綴全錯成 `2026-10-26_`。**已修**：優先序改為 `release_date → timestamp → upload_date`，勿改回。**另一支 `S8p2zgvaS4w` 的 `release_date=20261026`（`upload_date=20261027`）維持 10-26 才是對的**，改前綴前務必先用 yt-dlp 印出三個欄位核對，不要憑檔名或標題猜。修正前綴時要**整組一起改**：KB 逐字稿 `.md`／`.srt`／`.link.txt`、` 課程筆記.md/.docx`、`直播報告\*.docx`（內文「直播時間」也要改）、`D:\YouTube_Videos\<檔名>.mp4` 與 `_字幕.mp4`、`working\_note_parts\course\<檔名>` 快取目錄；逐字稿內文的 `日期：` 與「本機影片」「燒字幕影片」路徑也要同步。

### 直播報告（各頻道通用）

- 產生器：`make_live_report.py`（逐字稿 md → Gemini 摘要 → python-docx 產 Word）
- **輸出目錄預設為「逐字稿同層的 `直播報告\`」**（2026-10-16 修正：原本 `make_report(out_dir=REPORT_DIR)` 寫死 `20VTA 頻道\直播\直播報告`，導致三師爸的 4 份直播報告被寫進 20VTA 資料夾。`--out` 預設也改 `None`）。各頻道各有自己的 `直播報告\`。
- **版型依頻道自動切換（2026-10-16）**：路徑含 `20VTA` → 沿用財經版型（講師硬寫「廖崧沂（波段王子、點靈）」、章節含大盤/技術/個股）；否則走**通用版型**，講師取 yt-dlp `uploader`（三師爸=「三師爸Sense Bar」），章節改為「三、主要重點」，並禁止套用與內容不符的財經小節。
- 格式參考（20VTA）：`【波段王子 廖崧沂】命中大盤轉折 42006！...doc`
  （一、影片資訊；二、摘要；三、主要重點與操作策略；四、重點與提醒事項；五、結語）
- `channel_watcher.py` 在 `kb_dir.name=="直播"` 完成後自動呼叫 `make_live_report.make_report(md_path)`（不指定 `out_dir` → 落在同層）。
- 補做缺報告：`python make_live_report.py --all`（已存在 .doc/.docx 會 SKIP）。
- 日期來源：`.link.txt` 的 video_id → yt-dlp `extract_flat` 取 upload_date。
- **Gemini 會偶發 503 UNAVAILABLE（高需求）**：`generate_content` 的 tenacity 重試仍可能耗盡而拋 `ServerError`，長批次請**包一層外層重試**（等待後重呼）。

## 文件內嵌圖片 OCR 工作流（E，2026-10-12）

### 目的
文件（Word）與網頁內的圖片，轉成 AI 可讀文字，隨原文「原位交錯」寫入 KB 條目 .md，補足純文字提取會遺漏的圖表/截圖知識。

### 規格（file_processors.py）
- 輸出格式：每張圖 `[圖N]` + `【描述】…【文字】…`。
- 引擎鏈：Gemini Vision（`gemini-3.5-flash-lite`）→ Groq Vision（`qwen/qwen3.6-27b`）→ Tesseract（僅文字）。
- 原位交錯：docx 依 `document.xml` 順序（DrawingML `a:blip` + 舊版 VML `v:imagedata`）；web 依 `<img>` 順序就地替換。
- 過濾：<15KB 或任一邊 <200px 視為 icon/logo 略過。
- 上限：單檔預設 30 張（`MAX_IMAGES_PER_DOC`；CLI `--max-images 0`＝無限）；每日 `MAX_VISION_PER_DAY=450`（貼近 Gemini 免費層 500/日）。
- 去重＋續傳：逐圖 md5 檢查點 `working\_img_checkpoints\{hash}.json`；重跑跳過已完成、同圖只辨識一次。
- 撞每日上限：丟 `_QuotaStop` → 任務標 `paused`、檢查點保存；隔日重跑同任務自動接續。

### 重活交付與收成（分工）
- 設計原則：**不做中央派遣**；任一 PC 一鍵部署後獨立運作。
- Notebook：建流程、下任務、收成 KB。
- PC：執行重活（docx 大量圖片 OCR），循序、寫進度（`working\_task_progress\{tid}.json`）、跨日續傳。
- 收成：PC 產出 KB 條目 .md → notebook 抽驗 → `make_course_note.generate_note` 產課程筆記 .md＋.docx → 入 KB。
- **產品任務型別（L2/L3）**：`note`＝詳細課程筆記（`{stem} 課程筆記.md`＋.docx）；`summary`＝摘要報告（`{stem} 摘要.md`＋.docx，重點整理 3–8 點＋關鍵結論，摘要優先、需要時再補詳細）。兩者皆為**獨立可下派/重派任務**（worker 型別 `summary`/`note`，`source_md`＝任一既有逐字稿 md，輸出同目錄，skip-if-exists）；來源任務可帶 `auto_note`／`auto_summary`；`channel_watcher` 支援 `summary:` 設定；GUI 新增任務選單有「產出產品」勾選（摘要報告／詳細筆記，逐字稿恆產）；`file_processors.py` CLI 支援 `--auto-summary`/`--auto-note`。產製預算（Gemini）與課程筆記共用 `.note_quota.json`＋`MAX_NOTES_PER_RUN`。快取在 `working\_note_parts\summary\`。
- **摘要品質改版 v3（2026-10-13）**：原 prompt 限「400 字以內」且多段**直接串接**，導致標題重複、過度簡化、幾乎不提個股。改為**交易導向結構化摘要**：①個股／族群**逐檔**列一行（名稱：多空方向 — 依據／理由 — 關鍵價位或條件 — 風險）；②固定小節（大盤與行情觀點／個股與族群／操作策略與條件／關鍵數據與指標／關鍵結論，無內容者略過）；③篇幅**寧詳勿略**、具體數字與價位全保留；④**嚴禁臆測股票代號**（逐字稿未明講就只寫名稱）；⑤多段／多來源新增 `gemini_summary_merge()` **合併收斂**（去重、整併個股、標題不重複）。**關鍵陷阱（2026-10-13 實踩）：合併的觸發條件原本寫成「來源數 > 1」，但 `sections` 是「每支來源」一筆——單支逐字稿即使切 3 段也只算 1 筆，導致 merge 永不執行、輸出仍是多個重複小節。已改為「逐段累計」`all_parts`（每個 chunk 一筆快取，檔名 `{VER}-{src}-{seg}.md`），`len(all_parts) > 1` 才合併。** `SUMMARY_PROMPT_VER` 置於快取檔名，改 prompt 時遞增即自動讓舊快取失效。
- 收成報告：`harvest_report.py` 產「任務總覽＋失敗清單＋KB 待補課程筆記清單」（排除 `知識庫\金融交易` 老師語料；`--kb-only` 只看待補；輸出 `working\harvest_report_YYYY-MM-DD.md`）。
- 批量回補：`backfill_products.py` 掃 KB 待補逐字稿（排除 `金融交易` 語料）產摘要/筆記，**可複選**（`--summary`/`--note`，預設兩者）、`--subtree` 限子目錄、`--dry-run` 預覽；與 channel_watcher 共用 `.note_quota.json` 每日 20 筆配額，達上限即停、隔日重跑續補，skip-if-exists。**`--dry-run` 絕不扣配額**（陷阱：`produce()` 曾把 `quota_take()` 放在 `dry_run` 判斷之前，預覽一次偷扣 12 筆配額，2026-10-13 修正）。**每次配額消耗記錄於 `knowledge-base\.note_quota_log.tsv`（時間／累計／來源），供查核「配額何時、被誰用掉」**（backfill 與 channel_watcher 共用）。**陷阱（2026-10-13 實踩）：JSON 設定檔（如 `.note_quota.json`）絕不可用 PowerShell `Set-Content -Encoding UTF8` 產生——PS 5.1 會加 UTF-8 BOM，`json.loads` 遇 BOM 抛錯→被 try/except 吞掉→配額恆讀 0 且 `quota_take()` 不再累加。改法：①程式讀取一律 `encoding="utf-8-sig"` 容錯；②手動改檔用 `[System.IO.File]::WriteAllText(path, text, (New-Object System.Text.UTF8Encoding($false)))` 寫無 BOM，或交給程式寫（`write_text(..., encoding="utf-8")`）。**GUI 亦有「◈ 產品回補」對話視窗（任務頁按鈕）：選範圍（全部知識庫／任一子目錄）→ 列出待補清單（含缺摘要/缺筆記標記）→ 勾選產品（摘要報告／詳細筆記，複選）→ 「回補選取（可多選）」或「批量回補全部」（背景執行、日誌區即時顯示、當日配額用完即停）。**長時任務 UI 必備回饋**：按下立即 disable 執行鈕＋日誌「▶ 開始」＋狀態列「執行中…（x/N）」＋逐項「⏳／✓」，完成才 re-enable；避免使用者因無回饋而連點重複下命令（重複下命令的代價：重複扣 Gemini 配額）。**`generate_note`/`generate_summary` 為分段呼叫 Gemini，單筆需數分鐘**，故回饋（進行中狀態）是必要而非加分。**課程筆記（L2）與摘要不同**：其 prompt 本就要求「寧可詳盡、不要精簡」且不限字數，故無摘要那種過度簡化的問題；但筆記同樣是「多 chunk 直接串接、無合併步驟」，長逐字稿在不同 chunk 交界處**可能出現重複標題或主題微幅重疊**（內容不漏，僅結構重複）——若日後要求更高，可為筆記加類似的合併/接續步驟。**陷阱（2026-10-13 實踩）：GUI 是長駐程序，改完 `task_manager_gui.py` 後既有視窗仍跑舊碼，必須關閉重開才會載入新功能（當時舊視窗無回饋，使用者以為沒產出，其實成品數分鐘後才落地）。** 另 `backfill_products.py` 支援單檔回補：`--file <相對路徑子字串>`。
- **陷阱（2026-10-12 實踩）：Gemini 續傳快取 `_parts_{title}` 原寫在 out_dir（＝KB 目錄）→ 汙染知識庫。修正：一律放 `working\_note_parts\`（`course\`＝make_course_note、`dir\`＝make_dir_notes），**任何快取都不可寫進 out_dir/KB**。既有 117 個已移至 `working\_note_parts_backup\`（保留相對路徑）。

### 實例：選擇權實驗室--外資期貨成本的計算方法.docx
- 1246 張 JPEG、228MB、1239 張唯一（去重效益小）。
- 舊流程 KB md（60KB）只留段落文字，圖全成空白行。
- 新流程 30 張樣本 → 23.5K 字（`working\_samples\..._sample30.md`），品質良好（籌碼表/K線/履約價表數字完整）。
- 全檔外推約 1MB md、約 75 分 API，受 500/日限制跨約 3 天；**待其他 PC 備便後再交付執行**。

## 音訊快取與轉錄品質防護（2026-11-02 事故）

### 事故
任務 1913 對 380.7MB 舊／不完整檔案壓出 13.3MB 的靜音 mp3（`mean_volume -91 dB`），任務 1918 因檔名相同直接重用該快取，導致 110 分鐘的股市課程被 Whisper 轉成日文與 AI 工具幻覺，KB 逐字稿、課程筆記、摘要與燒錄字幕全部錯誤。

### 已修（勿改回）
1. `worker.compress_video` 加入快取驗證：sidecar（`{stem}.mp3.json`）來源 size 不符、來源比快取新、檔案 <64KB、平均音量 < -60 dB、長度差 >2%，任一項即重建；先寫 `.part.mp3` 再 `os.replace`，避免中斷留下半成品。
2. `run_pipeline.py` 轉錄前 `guard_audio()`（靜音直接中止）、轉錄後 `guard_transcript()`（日文假名 >2% 或「ご視聴ありがとうございました」≥3 次即判定失敗，不寫入 KB）。
3. `transcribe_groq.py` 預設 prompt 改為中性（不再硬塞 AI 工具名詞，避免股市內容被帶偏）。
4. `run_pipeline.py --skip-cut` 不再把音訊複製成「剪輯後.mp4」，改輸出「音訊.mp3」；worker 會清除舊的誤命名檔。

### 重做流程（本次 1913–1919）
原始影片 → Groq `large-v3-turbo`（金融 prompt、`--chunk-min 12`）→ `resegment.py` → `apply_vocab.py` → `validate_srt.py` → `srt_to_txt.py` → 重建 KB 逐字稿 md → 刪除舊筆記／摘要 `.md`/`.docx` 與 `working/_note_parts/{course,summary}/<title>` 快取 → 重產 → 覆寫 output 字幕 → 重燒 `..._字幕.mp4`。

### 切記
重產筆記／摘要前必須刪除同名 `.md`/`.docx` 與 `_note_parts` 快取，否則 worker 會 skip-if-exists，看起來「跑成功」但其實還是舊內容。

## run_pipeline 收尾崩潰與重試重複轉錄（2026-11-04）

> 完整處理記錄（時間軸、額度分析、驗收清單）：
> `docs/incidents/2026-11-04_任務1921-1923_處理記錄.md`

### 事故
任務 1921／1923（同一支 XQ 直播）全部步驟都成功、output 也已有 `字幕.srt`／`音訊.mp3`／`metadata.md`，
卻在最後一行 `print(f"  影片：{final_video.name}")` 拋 `UnboundLocalError: final_video`，
worker 判定 pipeline 失敗 → 自動重試 3 次（每次重跑轉錄）→ 永久失敗，且沒收成 KB／沒產筆記摘要。

### 原因
`run_pipeline.py` 的 Step 8 分兩種輸出：音訊（worker `--skip-cut`，`src_video` 是 mp3 → `音訊.mp3`）與影片（`剪輯後.mp4`）。
音訊分支只設 `final_audio`，但結尾固定印 `final_video.name` → 只有 worker 的音訊路徑會炸，手動跑影片路徑不會。

### 已修（勿改回）
1. Step 8 統一設 `final_media`（音訊或影片）＋`media_label`，結尾與 `kb_query` 提示都改用 `final_media`。
2. 新增 `run_pipeline.py --resume`：`corrected.srt` 比來源音訊新時，跳過 Step 2–4（不重複送 Whisper），
   仍跑 Step 5 驗證、Step 6 純文字、封面與輸出。`worker.run_pipeline()` 一律加 `--resume`，
   失敗重試／重排任務不會再把 2 小時音訊重轉一次（來源重新壓縮後 mtime 較新 → 自動失效重跑）。
3. GUI「新增任務 → 影片」遇到同路徑 **failed** 任務時，改問「直接把該任務重排（沿用既有字幕）嗎？」，
   不再默默建立重複任務（本次 1921/1923 就是失敗後重建產生的；1918/1919 也是同樣的重複對）。
   **GUI 是長駐程序，改完要關閉重開。**

