---
name: video-pipeline
description: YouTube 教學影片自動化生產線。當使用者要求「處理影片」「剪影片」「自動剪輯」「跑完整流程」「影片轉字幕」「產封面」「寫 metadata」「一次搞定上架」時使用此技能。從原始影片到 YouTube 上架包（剪輯 + 字幕 + 封面 + 描述 + SEO）全自動完成。
---

# video-pipeline：YouTube 影片自動化生產線

## 先讀

- `assets/style/cover-style.md`（封面風格指南）

## 流程概覽

```
raw/<影片代號>/原始.mp4
    │
    ├─ Step 1: smart-cut       → 去靜音（auto-editor）
    ├─ Step 2: audio-to-srt    → SRT + 純文字（Groq Whisper）
    ├─ Step 3: 產 10 個標題    → 等使用者挑
    │
    └─ 使用者挑完 ──→ output/<YouTube 標題>/
                          ├── <標題>.mp4
                          ├── <標題>.srt
                          ├── <標題>.txt
                          ├── cover.png         ← AI 生圖
                          └── metadata.md       ← 描述 / 社群 / SEO
```

## Step 1：收件與環境檢查

1. 確認 `raw/` 目錄下有新影片（mp4/mov/mkv/webm）
2. 建立 `working/<影片代號>/` 工作目錄
3. 環境檢查：
   - `ffmpeg -version`（必裝）
   - `python -m auto_editor --version`（smart-cut 必要）
   - `python -c "import groq"`（audio-to-srt 必要）
   - Groq API Key：檢查 `%USERPROFILE%\.groq_api_key` 或 `$env:GROQ_API_KEY`
   - OpenAI API Key（封面生成用）：檢查 `$env:OPENAI_API_KEY` 或 `%USERPROFILE%\.openai.env`

若缺工具，提示使用者安裝：
```powershell
pip install auto-editor groq openai
winget install Gyan.FFmpeg
```

## Step 2：剪口播（smart-cut）

讀取 `smart-cut` 技能，執行：
```powershell
python ".opencode\skills\smart-cut\scripts\smart_cut.py" `
  "raw\<影片代號>\原始.mp4" `
  --out "working\<影片代號>\<影片代號>.cut.mp4" `
  --threshold 0.05 `
  --margin "0.2s"
```

- `--threshold`：音量門檻（0.04=寬鬆，0.06=嚴格，0.08=極嚴）
- `--margin`：每段語音前後保留緩衝（格式 `前,後`）

輸出：`working/<影片代號>/<影片代號>.cut.mp4`

## Step 3：轉字幕（audio-to-srt）

讀取 `audio-to-srt` 技能，流程：

### 3a. 抽音訊
```powershell
ffmpeg -y -i "working\<影片代號>\<影片代號>.cut.mp4" `
  -vn -ar 16000 -ac 1 -c:a pcm_s16le `
  "working\<影片代號>\<影片代號>.cut.wav"
```

### 3b. Groq STT
```powershell
python ".opencode\skills\audio-to-srt\scripts\transcribe_groq.py" `
  "working\<影片代號>\<影片代號>.cut.wav" `
  --out "working\<影片代號>\_subtitles\<影片代號>.groq.json"
```

### 3c. 重新斷句
```powershell
python ".opencode\skills\audio-to-srt\scripts\resegment.py" `
  "working\<影片代號>\_subtitles\<影片代號>.groq.json" `
  --audio "working\<影片代號>\<影片代號>.cut.wav" `
  --out "working\<影片代號>\_subtitles\<影片代號>.raw.srt"
```

### 3d. 詞彙修正
```powershell
python ".opencode\skills\audio-to-srt\scripts\apply_vocab.py" `
  "working\<影片代號>\_subtitles\<影片代號>.raw.srt" `
  --out "working\<影片代號>\_subtitles\<影片代號>.vocab.srt"
```

### 3e. AI 清字
讀取 `.vocab.srt`，依 `references/cleanup_rules.md` 逐段清理錯字、標點、贅詞。
**核心原則**：時間碼行完全不可改動，只改文字行。

### 3f. 驗證
```powershell
python ".opencode\skills\audio-to-srt\scripts\validate_srt.py" `
  --raw "working\<影片代號>\_subtitles\<影片代號>.vocab.srt" `
  --clean "working\<影片代號>\_subtitles\<影片代號>.clean.srt"
```

### 3g. 產純文字稿
```powershell
python ".opencode\skills\audio-to-srt\scripts\srt_to_txt.py" `
  "working\<影片代號>\_subtitles\<影片代號>.clean.srt" `
  --out "working\<影片代號>\<影片代號>.txt"
```

### 3h. 交付
- 複製 `.clean.srt` → `<影片代號>.srt`
- 保留 `_subtitles/` 中間檔供稽核

## Step 4：產標題並暫停

讀取清字後的 `.txt`，產生 10 個 YouTube 標題候選，涵蓋：
- 痛點解決型
- 教學 know-how 型
- 對比反問型
- 具體案例型
- 懶人包型

寫入 `working/<影片代號>/titles.md`，停下等使用者選編號。

## Step 5：建立輸出資料夾

- 清洗標題中的 Windows 不合法字元：`？！：／＼?!:/\\<>|"*`
- 建立 `output/<清洗後標題>/`
- 將 Step 2~3 的產物複製進來：
  - `<標題>.mp4`（from working cut）
  - `<標題>.srt`
  - `<標題>.txt`

## Step 6：產封面

讀取 `cover-image` 技能，使用 AI 生圖：
- 需要 OpenAI API Key（或使用本地 Stable Diffusion）
- 參考 `assets/style/cover-style.md` 風格指南（手繪插畫風）
- 不使用人物形象照，以景象 + 圖標為主角

## Step 7：寫 metadata

`metadata.md` 必含：
1. **YouTube 描述**（含章節時間碼）
2. **Facebook / Instagram / Threads 社群貼文**
3. **SEO 主關鍵字、次關鍵字、長尾關鍵字**
4. **YouTube 標籤欄位**（半形逗號分隔，可直接複製貼上）
5. **上架前 checklist**

## Step 8：打包與檢查

輸出資料夾應包含：
```
output/<標題>/
├── <標題>.mp4      ← 剪好的影片
├── <標題>.srt      ← SRT 字幕
├── <標題>.txt      ← 純文字稿
├── cover.png       ← YouTube 封面
└── metadata.md     ← 描述 + 社群 + SEO
```

## 使用者操作

1. 把影片放進 `raw/<隨意取個影片代號>/`
2. 跟 opencode 說：「使用 video-pipeline 處理 `<影片代號>`」
3. AI 跑 Step 1~4，在 Step 4 暫停等你挑標題
4. 挑完後 AI 繼續產封面與文案
5. 完成品在 `output/<標題>/`

## 踩坑

- **先剪後轉字幕**：對「剪好的影片」轉字幕，時間碼才會對齊
- **VFR（可變幀率）**：螢幕錄影常見，smart_cut.py 內建 VFR→CFR 自動轉換
- **Groq 25MB 上限**：大檔自動 ffmpeg 降取樣，使用者無感
- **中文檔名**：Groq 上傳可能編碼壞掉，腳本已處理
- **Windows 路徑**：含中文或 `[Claude]` 的路徑用引號與 `-LiteralPath`

## 個人化清單（首次使用必改）

| 項目 | 位置 | 說明 |
|------|------|------|
| 封面風格 | `assets/style/cover-style.md` | 已設為手繪插畫風，可自行調整 |
| 字幕詞彙表 | `audio-to-srt/references/vocabulary.md` | 加你自己的專有名詞 |
| 詞彙替換表 | `audio-to-srt/scripts/apply_vocab.py` | 加「Whisper 常聽錯 → 正確」對照 |
