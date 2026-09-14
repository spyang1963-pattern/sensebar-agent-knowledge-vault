# 台股融資券分析看板 - 工作記錄

## 完成日期：2026-07-15

---

## 已完成項目

### 1. 資料抓取模組 (`src/twse_fetcher.py`)
- **TWSE MI_MARGN API**：直接抓融資融券餘額（1055檔個股）
- **TWSE OpenAPI**：個股收盤價
- **Yahoo Finance**：加權指數 + 歷史走勢
- **重要發現**：TWSE MI_MARGN API 會忽略 date 參數，只回傳最新一天的資料

### 2. 本地 CSV 快取 (`src/margin_cache.py`)
- 每天抓完資料存入 `output/cache/margin_history.csv`
- 隔天自動跟前一天比對計算融資增減
- 解決了「無法抓取歷史融資資料」的問題

### 3. 分析引擎 (`src/analyzer.py`)
- 合併融資券 + 股價資料
- 計算：融資增減、融資使用率、估計維持率、3日累計漲跌
- 三大觸發條件：
  - 融資斷頭潮（3日累計跌>10% + 融資大減 + 維持率<135%）
  - 恐慌停損（今日跌>4% + 融資大減 + 維持率>145%）
  - 主力換手（今日漲 + 融資大減）

### 4. 看板生成器 (`src/generate_dashboard.py`)
- 暗色主題 HTML 看板
- 7 個大盤指標卡片
- 三大觸發條件表格
- 個股篩選表格
- Chart.js 圖表（產業分布甜甜圈 + 加權指數走勢線）
- 歷史目錄頁（history.html）

### 5. 主流程 (`run_stock_analysis.py`)
- 11 個步驟自動執行
- Step 4：存入 CSV 快取
- Step 11：自動推送到 GitHub Pages

### 6. 部署 (`deploy_github.py`)
- 自動複製 dashboard 到 `docs/`
- 自動 git add → commit → push
- GitHub Pages 網址：`https://spyang1963-pattern.github.io/sensebar-agent-knowledge-vault/`

### 7. 排程
- Windows 排程任務 `StockAnalysis`
- 每天 18:00 執行 `run_stock_analysis.py`

---

## 潛在問題與注意事項

### 1. 融資增減第一天為 0
- **原因**：CSV 快取沒有昨天的資料
- **解決**：跑 2-3 天後就有歷史資料，警示會開始出現
- **正常行為**，不需要擔心

### 2. TWSE API 回傳同樣資料
- **現象**：無論傳哪個日期，都回傳今天（115年07月15日）的資料
- **原因**：證交所伺服器端快取
- **影響**：無法抓取歷史融資資料
- **解決**：用本地 CSV 快取比對（已實作）

### 3. FinMind 免費版限制
- **問題**：免費版必須逐股查詢（需要 `data_id`）
- **影響**：無法一次抓全部股票
- **解決**：改用 TWSE 直接 API（已實作）

### 4. 股價資料延遲
- **現象**：18:00 跑的時候，今日股價可能還沒公佈
- **解決**：自動嘗試抓前一個交易日的股價
- **影響**：股價可能不是最新的

### 5. GitHub Pages 部署
- **需求**：需要手動推送到 GitHub
- **已解決**：`deploy_github.py` 自動處理
- **注意**：排程跑完會自動推送，但需要 git 有設定好 SSH key 或 token

### 6. LINE/Email 通知尚未設定
- **原因**：用戶手機尚未取得
- **LINE**：需要建立 LINE Official Account + Messaging API
- **Email**：需要 Gmail App Password
- **設定檔**：`config.yaml` 裡的 `line` 和 `email` 區塊

---

## 檔案結構

```
stock-monitor/
├── run_stock_analysis.py      ← 主流程（每天 18:00 執行）
├── deploy_github.py           ← 推送到 GitHub Pages
├── config.yaml                ← 設定檔（閾值、觸發條件、通知）
├── requirements.txt           ← Python 依賴
├── setup.bat                  ← 新 PC 一鍵安裝
├── src/
│   ├── twse_fetcher.py        ← 資料抓取
│   ├── analyzer.py            ← 分析引擎
│   ├── generate_dashboard.py  ← 看板生成器
│   ├── margin_cache.py        ← CSV 快取管理
│   └── notifier.py            ← LINE/Email 通知（待設定）
├── output/
│   ├── cache/
│   │   └── margin_history.csv ← 融資歷史快取
│   └── dashboard/
│       ├── index.html         ← 最新看板
│       ├── history.html       ← 歷史目錄
│       └── dashboard_YYYY-MM-DD.html ← 歷史備份
└── docs/                      ← GitHub Pages 用
    ├── index.html
    ├── history.html
    └── dashboard_YYYY-MM-DD.html
```

---

## 要繼續做的事

### 1. LINE 通知（等手機拿到後）
- 建立 LINE Official Account
- 開啟 Messaging API
- 取得 Channel Access Token
- 在 `config.yaml` 設定 token

### 2. Email 通知（等手機拿到後）
- 開啟 Gmail 兩步驟驗證
- 建立 App Password
- 在 `config.yaml` 設定帳號和密碼

### 3. 可能的優化
- 加入更多技術指標
- 加入個股歷史走勢圖
- 匯出 CSV 報表
- 加入更多產業分類
