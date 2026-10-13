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

### 直播報告（20VTA）

- 產生器：`make_live_report.py`（逐字稿 md → Gemini 摘要 → python-docx 產 Word）
- 輸出：`knowledge-base\20VTA 頻道\直播\直播報告\*.docx`
- 格式參考：`【波段王子 廖崧沂】命中大盤轉折 42006！...doc`
  （一、影片資訊；二、摘要；三、主要重點與操作策略（大盤/技術/操作系統/個股/建議）；四、重點與提醒事項；五、結語）
- `channel_watcher.py` 在處理 20VTA 直播（`kb_dir.name=="直播"`）完成後自動呼叫 `make_live_report.make_report(md_path)`。
- 補做缺報告：`python make_live_report.py --all`（已存在 .doc/.docx 會 SKIP）。
- 日期來源：`.link.txt` 的 video_id → yt-dlp `extract_flat` 取 upload_date。

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
- 收成報告：`harvest_report.py` 產「任務總覽＋失敗清單＋KB 待補課程筆記清單」（排除 `知識庫\金融交易` 老師語料；`--kb-only` 只看待補；輸出 `working\harvest_report_YYYY-MM-DD.md`）。
- **陷阱（2026-10-12 實踩）：Gemini 續傳快取 `_parts_{title}` 原寫在 out_dir（＝KB 目錄）→ 汙染知識庫。修正：一律放 `working\_note_parts\`（`course\`＝make_course_note、`dir\`＝make_dir_notes），**任何快取都不可寫進 out_dir/KB**。既有 117 個已移至 `working\_note_parts_backup\`（保留相對路徑）。

### 實例：選擇權實驗室--外資期貨成本的計算方法.docx
- 1246 張 JPEG、228MB、1239 張唯一（去重效益小）。
- 舊流程 KB md（60KB）只留段落文字，圖全成空白行。
- 新流程 30 張樣本 → 23.5K 字（`working\_samples\..._sample30.md`），品質良好（籌碼表/K線/履約價表數字完整）。
- 全檔外推約 1MB md、約 75 分 API，受 500/日限制跨約 3 天；**待其他 PC 備便後再交付執行**。
