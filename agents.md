# AI Agent 影片自動化生產線

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

```powershell
# 建立排程任務（每天 10:00 執行）
$taskName = "SensebarAutoUpdate"
$action = New-ScheduledTaskAction -Execute "D:\!!AI agent 專案夾\三師爸的 AI agent 學習 AI agent\auto_update.bat"
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

### 自動排程（已設定）

Windows 排程任務 `SensebarAutoUpdate`：
- **執行時間**：每天早上 10:00
- **執行內容**：自動檢查 @sensebar 頻道新影片
- **處理邏輯**：
  1. 嘗試下載 YouTube 字幕（免費、秒完）
  2. 無字幕時下載音訊（比影片小 10 倍）
  3. 用 Groq Whisper 辨識字幕
  4. 自動清理暫存檔
  5. 同步到 knowledge-base/youtube-clips
- **日誌位置**：logs/update_YYYYMMDD_HHMMSS.txt
- **通知方式**：桌面彈出視窗

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
