# 🎯 胚騰 AI 台股融資券分析系統

一個自動化的台股融資券分析系統，每日自動分析三大法人買賣超、融資斷頭潮、恐慌停損、主力換手等指標，並透過 LINE/Email 即時通知。

## ✨ 功能特色

### 📊 每日分析（18:00 自動執行）
- **三大法人買賣超**：外陸資、投信、自營商淨買超排行
- **融資斷頭潮**：3日累計跌>10% + 維持率<135%
- **恐慌停損**：今日跌>4% + 融資大減
- **主力換手**：今日漲 + 融資減 = 籌碼好轉
- **精美元分析看板**：自動產生 HTML 看板

### ⚡ 即時監控（盤中每 5 分鐘）
- **個股即時警報**：自選股股價異常變動立即通知
- **進階警報條件**：
  - 股價漲跌幅超過門檻
  - 成交量異常放大
  - 長上/下影線（反轉訊號）
  - 跳空缺口偵測

### 📱 多管道通知
- **LINE 即時推播**：手機立即收到
- **Email 詳細報告**：完整分析表格
- **歷史警報紀錄**：所有警報可回顧

### 🖥️ 管理介面
- **自選股管理**：GUI 介面輕鬆管理自選股
- **通知管理**：管理訊息、收件者、排程
- **排程監控**：即時查看系統運作狀態

## 🚀 安裝步驟

### 環境需求
- Windows 10/11
- Python 3.9 或更高版本
- 網路連線

### 安裝流程

#### 1. 安裝 Python
到官網下載安裝：https://www.python.org/downloads/
- 安裝時勾選「Add Python to PATH」

#### 2. 解壓縮安裝包
將 `stock-monitor.zip` 解壓縮到你想放的位置，例如：
```
D:\stock-monitor
```

#### 3. 安裝套件
打開命令提示字元（CMD），執行：
```bash
cd D:\stock-monitor
pip install -r requirements.txt
```

#### 4. 設定 LINE Token
1. 到 [LINE Developers](https://developers.line.biz/) 建立一個 Messaging API Channel
2. 取得 Channel Access Token
3. 編輯 `config.yaml`，將 token 填入：
```yaml
channels:
  line:
    channel_access_token: "你的TOKEN"
```

#### 5. 取得你的 LINE User ID
1. 在 LINE 新增好友：@117tehfu（胚騰官方帳號）
2. 傳送任意訊息
3. 到 [LINE Developers](https://developers.line.biz/) 查看你的 User ID
4. 填入 `config.yaml`：
```yaml
messages:
  - recipients:
      - channel: line
        target: "你的User_ID"
```

#### 6. 測試執行
```bash
python run_stock_analysis.py
```

#### 7. 設定自動排程
執行 `setup_scheduler.bat` 自動設定 Windows 排程器。

## 📁 檔案結構

```
stock-monitor/
├── config.yaml              # 設定檔（重要！）
├── run_stock_analysis.py    # 每日分析主程式
├── run_realtime_monitor.py  # 即時監控主程式
├── notification_manager.py  # 通知管理 GUI
├── watchlist_manager.py     # 自選股管理 GUI
├── scheduler_monitor.py     # 排程監控 GUI
├── src/
│   ├── twse_fetcher.py      # TWSE 資料抓取
│   ├── analyzer.py          # 分析引擎
│   ├── institutional_fetcher.py  # 三大法人資料
│   ├── stock_monitor.py     # 即時監控模組
│   ├── stock_chart.py       # 歷史走勢圖
│   ├── alert_history.py     # 警報歷史紀錄
│   ├── generate_dashboard.py # 看板生成器
│   ├── margin_cache.py      # 快取管理
│   └── notifier.py          # 通知模組
├── data/                    # 資料目錄
├── output/                  # 輸出目錄
├── logs/                    # 日誌目錄
└── requirements.txt         # 套件清單
```

## ⚙️ 設定說明

### config.yaml 主要設定

```yaml
# 分析設定
analysis:
  thresholds:
    margin_decrease_pct: -5.0    # 融資減少百分比
    price_drop_pct: -2.0         # 股價跌幅

# 三大法人觸發條件
analysis:
  triggers:
    margin_call:
      cumulative_drop_pct: -10.0  # 3日累計跌幅
      max_maintenance_rate: 135.0 # 維持率
    panic_sell:
      daily_drop_pct: -4.0        # 單日跌幅
    institutional_buy:
      daily_rise_pct: 2.0         # 單日漲幅

# 即時監控
realtime_monitor:
  enabled: true
  monitor_hours:
    start: "09:00"
    end: "13:30"
  watchlist:
    - code: "2330"
      name: "台積電"
      thresholds:
        price_drop_pct: -3.0
```

## 🔧 常見問題

### Q: 看不到資料？
A: TWSE 資料通常在 18:00-20:00 之間更新，系統會自動重試。

### Q: LINE 沒收到通知？
A: 檢查 `config.yaml` 中的 token 和 user_id 是否正確。

### Q: 如何新增自選股？
A: 執行 `watchlist_manager.py`，用 GUI 介面管理。

### Q: 歷史資料在哪裡？
A: `data/` 目錄下有 `margin_history.csv` 和 `alert_history.json`。

## 📞 聯絡方式

- 作者：胚騰 AI Agent
- GitHub：https://github.com/spyang1963-pattern

## 📜 授權條款

MIT License - 自由使用、修改、散布。

---

**享受 AI 自動化分析的樂趣！** 🚀
