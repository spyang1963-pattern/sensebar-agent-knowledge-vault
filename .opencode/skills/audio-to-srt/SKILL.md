---
name: audio-to-srt
description: 音訊/影片檔自動生成乾淨 SRT 字幕檔。當使用者要「把音訊轉字幕」「做 SRT」「語音轉文字 + 時間碼」「影片上字幕」時使用此技能。預設走 Groq Whisper-large-v3-turbo（雲端、word-level 時間碼），備援本地 Whisper medium。
---

# audio-to-srt：音訊 → 乾淨 SRT

## 何時觸發
使用者提供音訊/影片檔並要求：
- 轉字幕、生成 SRT、上字幕
- 語音轉文字且要有時間碼
- 字幕清洗、修錯字、潤斷句

## 兩條路線

| 路線 | 模型 | 時間碼粒度 | 速度 | 隱私 | 適用 |
|------|------|------------|------|------|------|
| **A. Groq（預設）** | whisper-large-v3-turbo | **word-level** | 快 | 上雲 | 一般情境 |
| B. 本地 Whisper | medium | segment-level | 慢 | 完全本地 | 敏感內容 |

## 核心原則

1. **時間碼神聖不可侵犯**：清字過程 SRT 時間碼行完全不可改動
2. **段落邊界不可動**：不得合併/拆分/新增/刪除段落
3. **只改文字，不改語意**：修錯字、加標點、順語感

## 路線 A：Groq 流程（預設）

### Step 1：環境檢查
```powershell
# Groq API Key
$env:GROQ_API_KEY                          # 環境變數
Get-Content "$env:USERPROFILE\.groq_api_key"  # 或本地 key 檔
```

### Step 2：Groq STT
```powershell
python ".opencode\skills\audio-to-srt\scripts\transcribe_groq.py" `
  "working\<影片代號>\<影片代號>.cut.wav" `
  --out "working\<影片代號>\_subtitles\<影片代號>.groq.json"
```

### Step 3：重新斷句
```powershell
python ".opencode\skills\audio-to-srt\scripts\resegment.py" `
  "working\<影片代號>\_subtitles\<影片代號>.groq.json" `
  --audio "working\<影片代號>\<影片代號>.cut.wav" `
  --out "working\<影片代號>\_subtitles\<影片代號>.raw.srt"
```

### Step 4：詞彙修正
```powershell
python ".opencode\skills\audio-to-srt\scripts\apply_vocab.py" `
  "working\<影片代號>\_subtitles\<影片代號>.raw.srt" `
  --out "working\<影片代號>\_subtitles\<影片代號>.vocab.srt"
```

### Step 5：AI 清字
讀取 `.vocab.srt`，依 `references/cleanup_rules.md` 逐段清理。
只改文字行，時間碼行完全不動。

### Step 6：驗證
```powershell
python ".opencode\skills\audio-to-srt\scripts\validate_srt.py" `
  --raw "working\<影片代號>\_subtitles\<影片代號>.vocab.srt" `
  --clean "working\<影片代號>\_subtitles\<影片代號>.clean.srt"
```

### Step 7：產純文字稿
```powershell
python ".opencode\skills\audio-to-srt\scripts\srt_to_txt.py" `
  "working\<影片代號>\_subtitles\<影片代號>.clean.srt" `
  --out "working\<影片代號>\<影片代號>.txt"
```

## 路線 B：本地 Whisper（備援）
```powershell
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -X utf8 -m whisper "輸入檔.wav" `
  --model medium --language zh --output_format srt `
  --output_dir "working\<影片代號>\_subtitles"
```

## 檔案結構
```
skills/audio-to-srt/
├── SKILL.md
├── scripts/
│   ├── transcribe_groq.py
│   ├── resegment.py
│   ├── apply_vocab.py
│   ├── srt_to_txt.py
│   └── validate_srt.py
└── references/
    ├── cleanup_rules.md
    └── vocabulary.md
```
