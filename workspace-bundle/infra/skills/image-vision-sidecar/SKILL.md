---
name: image-vision-sidecar
description: 讓純文字模型（DeepSeek、GLM 等無視覺模型）間接讀圖。用 Groq 免費 Vision API 把 PNG/JPG/PDF/PPTX/DOCX 轉成繁體中文 Markdown 描述。當使用者要「讀圖片」「分析這張圖」「看這份 PDF 的圖」「讀簡報的圖」「這份文件有圖我看不到」「描述圖片內容」「抽取圖中文字」「OCR」且**目前使用的模型不支援視覺輸入**時載入。若目前模型本身支援視覺（如 Claude、GPT、Gemini、Luna 等），直接由主模型讀圖即可，**不要**載入本技能。
---

# Image Vision Sidecar — 讓純文字模型讀圖

## ⚠️ 何時用、何時不用

| 情況 | 做法 |
|------|------|
| 主模型**支援視覺**（Claude、GPT-5.6 Luna、Gemini、Kimi 等多模態模型） | **不要用本技能**，直接把圖片/PDF 餵給主模型讀，又快又準 |
| 主模型**不支援視覺**（DeepSeek V4 Flash、GLM-5.2 等純文字模型） | 用本技能間接讀圖：抽圖 → Groq Vision 描述 → 交給主模型 |
| 不確定主模型有沒有視覺 | 先直接餵圖測試；被拒絕（如「this model does not support image/pdf input」）再用本技能 |

> 判斷依據：**以「目前對話中實際使用的模型」為準**，不是以工具清單為準。

## 用途

當目前使用的模型不支援視覺輸入（如 DeepSeek V4 Flash、GLM-5.2 等純文字模型），
但使用者需要理解圖片、PDF、簡報或 Word 文件中的圖形內容時，用這個工具
「間接看圖」：把檔案中的圖片抽出來 → 送給 Groq 免費 Vision API → 取得繁體
中文描述 → 把描述交給主模型繼續處理。

## 前置安裝（第一次使用才需要）

### 1. 安裝 Python 套件

```bash
pip install -r requirements.txt
```

### 2. 申請 Groq API key（免費）

1. 到 <https://console.groq.com/> 註冊帳號（免費）
2. 進入 **API Keys** 頁面 → **Create API Key** → 複製
3. 儲存 key（二選一）：
   - 環境變數：`set GROQ_API_KEY=<你的key>`（Windows）
   - 或存成檔案：`echo <你的key> > ~/.groq_api_key`

## 使用方式

### 基本用法

```bash
python vision.py <檔案路徑>
```

### 模式

| 模式 | 指令 | 用途 |
|------|------|------|
| describe（預設） | `python vision.py <檔案>` | 詳細描述圖片內容（物件、文字、顏色、版面） |
| ocr | `python vision.py <檔案> --mode ocr` | 只抽圖中文字，表格轉成 Markdown |

### 參數

```bash
python vision.py <檔案> [--mode describe|ocr] [--output <路徑>] [--model <模型>]
```

- `--output`：指定輸出檔路徑（預設在檔案同目錄產生 `<檔名>.vision.md`）
- `--model`：指定 Vision 模型（預設自動從 Groq 現有模型中選用）

## 支援格式

| 格式 | 處理方式 |
|------|---------|
| PNG / JPG / JPEG / WEBP / BMP / GIF | 直接送圖 |
| PDF | 每頁轉成 150dpi PNG 逐頁描述 |
| PPTX | 抽出每頁投影片中的圖片 |
| DOCX | 抽出內嵌圖片 |

## 注意事項

- **免費額度**：Groq 免費方案有速率限制，大量圖片可能觸發限流。
- **模型可用性**：Groq 的模型會下架或新增，vision.py 每次執行會自動檢查。
- **隱私**：檔案內容會上傳到 Groq（美國伺服器），敏感資料請先脫敏。
