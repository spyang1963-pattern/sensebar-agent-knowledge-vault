---
name: draw-free
description: 免費 AI 生圖。零 API Key、零 GPU，用 Pollinations.ai 免費 API 生成圖片。當使用者要「生圖」「畫圖」「生成圖片」「做封面」「做海報」「產生視覺素材」時載入。
---

# draw-free — 免費 AI 生圖

## 用途

用 Pollinations.ai 免費 API 生成圖片，不需要 API Key、不需要 GPU。

## 前置安裝（第一次使用才需要）

```bash
pip install pillow
```

## 使用方式

### 基本生圖

```bash
python draw_free.py "一隻可愛的水豚在讀書"
```

### 加文字疊加（對話框 + 中文標題）

```bash
# 1. 先生底圖
python draw_free.py "可愛的水豚插畫" --name capybara

# 2. 疊上對話框文字
python overlay-text.py generated/capybara_*.png --text "壓力？那能吃嗎？" --subtitle "— 卡皮巴拉的人生哲學"
```

## 參數

### draw_free.py

| 參數 | 預設 | 說明 |
|------|------|------|
| `prompt`（必填） | — | 要畫什麼 |
| `--size` | `1024x1024` | `WIDTHxHEIGHT` |
| `--model` | 自動（最快） | `flux`/`turbo`/`nanobanana`/`seedream` |
| `--seed` | 隨機 | 相同 seed = 相同圖 |
| `--n` | `1` | 1–8 張 |
| `--name` | `image` | 檔名前綴 |
| `--outdir` | `./generated/` | 輸出目錄 |

### overlay-text.py

| 參數 | 預設 | 說明 |
|------|------|------|
| `image`（必填） | — | 來源圖片路徑 |
| `--text`（必填） | — | 主文字 |
| `--subtitle` | 無 | 副標題 |
| `--output` | `<檔名>_overlay.png` | 輸出路徑 |
| `--font-size` | `42` | 主文字大小 |
| `--sub-font-size` | `22` | 副標題大小 |

## 模型選擇

| 模型 | 特色 | 適合 |
|------|------|------|
| （不指定） | **最快，1-3 秒** | 絕大多數情況 |
| `flux` | 高品質通用 | 需要特定風格時 |
| `turbo` | 快速 5-10 秒 | 預覽、迭代 |
| `nanobanana` | 攝影寫實 | 寫實風格 |
| `seedream` | 東方美學 | 亞洲風格 |

> ⚠️ **不指定模型最快，快 15-40 倍。** 除非你真的要某個特定模型，否則不要帶 `--model`。

## 限制

- **匿名層限制**：同一個 IP 同時只准 1 個請求
- **圖中文字**：中文不要指望，英文也不可靠。用 `overlay-text.py` 後製疊加
- **需要網路連線**

## 授權

MIT License — 自由使用、修改、散布。
