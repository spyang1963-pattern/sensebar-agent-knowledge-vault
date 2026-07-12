---
name: cover-image
description: AI 封面圖生成。當使用者要求「畫封面」「生封面圖」「做 YouTube 縮圖」「畫一張圖」時使用此技能。使用免費 Pollinations.AI 生成圖片，無需 API Key。也可選擇使用 OpenAI gpt-image-2（付費）。
---

# cover-image：AI 封面圖生成

## 何時觸發
使用者要求：
- 畫封面、生封面圖、做 YouTube 縮圖
- 畫一張圖、生一張圖

## 前置需求

### 免費方案（Pollinations.AI，預設）
- **不需要 API Key**，不需要註冊，直接使用
- 已安裝 Python 3.10+

### 付費方案（OpenAI gpt-image-2，可選）
- OpenAI API Key：`$env:OPENAI_API_KEY` 或 `%USERPROFILE%\.openai.env`
- 已安裝 `openai` Python 套件：`pip install openai`

## 使用方式

### 方案一：免費 Pollinations.AI（推薦）

```powershell
# 手繪風格封面（預設 1280x720，YouTube 橫版）
python ".opencode\skills\cover-image\draw_free.py" "doodle style, AI tutorial thumbnail, colorful, cartoon" --name cover

# 指定尺寸
python ".opencode\skills\cover-image\draw_free.py" "科技教學封面" --width 1280 --height 720 --name cover

# 固定種子（可重複生成相同圖片）
python ".opencode\skills\cover-image\draw_free.py" "doodle coding" --seed 42 --name cover
```

#### 參數
| 參數 | 說明 |
|------|------|
| `prompt`（必填）| 自然語言描述（英文效果最佳）|
| `--width` | 圖片寬度，預設 1280 |
| `--height` | 圖片高度，預設 720 |
| `--name` | 輸出檔名前綴，預設 cover |
| `--outdir` | 輸出目錄 |
| `--model` | `flux`（預設，品質高）/ `turbo`（速度快）|
| `--seed` | 隨機種子（相同種子+prompt 會產生相同圖片）|

### 方案二：付費 OpenAI（可選）

```powershell
python ".opencode\skills\cover-image\draw.py" "要畫的內容" --name cover
```

| 參數 | 說明 |
|------|------|
| `prompt`（必填）| 自然語言描述 |
| `--size` | `1024x1024`（方）/ `1536x1024`（橫，預設）/ `1024x1536`（直）|
| `--quality` | `low`（預設，約 NT$0.3）/ `medium` / `high` |
| `--name` | 輸出檔名前綴 |
| `--outdir` | 輸出目錄 |
| `--edit` | 人物形象照路徑，可結合人物 |

## 封面設計指引

**預設風格：手繪插畫風（Doodle Style）**，搭配「景象+圖標」組合（不含人物）。

Prompt 撰寫要點：
1. 加入 `doodle style, hand-drawn, cartoon, colorful` 等風格關鍵字
2. 用英文撰寫 prompt 效果最佳
3. 描述具體景象 + 圖標（如：電腦、書本、程式碼、齒輪）
4. 不要描述人物/角色
5. 背景用鮮明配色（如：深藍底 + 亮色幾何圖案）

### 風格參考
- 詳見 `assets/style/cover-style.md`

### Quality 判斷（OpenAI 方案）
- **low**（預設）：99% 情境夠用，速度最快
- **medium**：low 明顯不夠時
- **high**：僅限實體印刷品

## 錯誤處理

### Pollinations.AI
- 生成失敗 → 檢查網路連線，或換個 prompt 再試
- 圖片不理想 → 調整 prompt 描述，或加 `--seed` 固定結果

### OpenAI
- `403 Organization must be verified` → 去 platform.openai.com 做 Individual 驗證
- `401 Invalid API key` → 檢查 API Key 設定
- `429 Rate limit` → 額度用完，去 Billing 儲值

## 個人化
- 封面風格：參照 `assets/style/cover-style.md`
- 人物形象照：`assets/persona/` 目錄下的去背 PNG（僅 OpenAI 方案支援）
