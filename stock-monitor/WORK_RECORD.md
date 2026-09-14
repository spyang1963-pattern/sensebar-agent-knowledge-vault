# 胚騰 AI Agent - 工作紀錄與帳密備份

> ⚠️ 此檔案包含敏感資訊，請妥善保管，勿外流！

---

## 📋 今日工作摘要 (2026-07-21 更新)

### 完成項目
1. **股票監控系統建置**
   - 專案位置：`D:\_AI Agent\stock-monitor\`
   - 資料來源：台灣證券交易所 (TWSE) 融資融券 API
   - 功能：每日抓取融資券數據、篩選警示股、生成圖表

2. **GitHub Pages 部署**
   - 網址：https://spyang1963-pattern.github.io/sensebar-agent-knowledge-vault/
   - 自動部署腳本：`deploy_github.py`
   - 內容：HTML 看板 + 歷史紀錄頁面

3. **LINE 通知設定**
   - 官方帳號名稱：胚騰
   - 通知功能：警示股推送、每日摘要
   - **已修正**：連結改為完整 GitHub Pages 網址

4. **Email 通知設定**
   - Gmail SMTP 發送
   - 每日寄送分析報告
   - **已修正**：連結改為完整 GitHub Pages 網址

5. **排程系統（已穩定）**
   - 排程執行器：`message_scheduler.py`（背景運行，每 30 秒檢查）
   - 監控 GUI：`scheduler_monitor.py`
   - Windows 排程工作：`StockAnalysis` (每日 18:00), `TWSE_DataMonitor` (18:00-21:00)
   - **已修正**：cp950 崩潰、去重洪流、Email 漏發

6. **Dashboard 更新**
   - Footer 改為「© 2026 胚騰 AI Agent」
   - 暗色主題、7 個指標卡片、三大觸發條件

7. **⭐ 即時監控機制**
   - 監控腳本：`data_monitor.py`
   - 啟動腳本：`start_monitor.bat`
   - 功能：每15分鐘檢查 TWSE 資料更新
   - 觸發條件：發現新資料立即執行分析並通知
   - 排程設定：`TWSE_DataMonitor` (交易日 18:00-21:00 每15分鐘)

8. **⭐⭐ 通知管理系統 GUI**
   - 檔案：`notification_manager.py`
   - 啟動：`啟動通知管理.bat` 或 `python notification_manager.py`
   - 功能：圖形化介面管理所有通知訊息

#### 通知管理系統功能
| 頁籤 | 功能 |
|------|------|
| 總覽 | 所有訊息一覽表、使用者總覽、搜尋功能 |
| 編輯 | 選擇訊息編輯、接收者管理、排程設定 |
| 設定 | LINE/Email 管道設定 |

#### 訊息狀態系統
| 狀態 | 說明 |
|------|------|
| 編輯中 | 新建或修改中 |
| 待命 | 設定完成，等待啟動 |
| 運作中 | 已啟動，依排程發送 |
| 已停止 | 已停止發送 |

#### 接收者狀態系統
| 狀態 | 說明 |
|------|------|
| 運作中 | 正常接收訊息 |
| 暫停 | 暫時不發送 |
| 錯誤 | 發送失敗 |

#### config.yaml 新結構
```yaml
channels:        # 通知管道設定
messages:        # 訊息清單（每則獨立管理）
  - name: 訊息名稱
    status: 編輯中/待命/運作中/已停止
    recipients:
      - name: 姓名
        channel: line/email
        target: ID/Email
        status: 運作中/暫停/錯誤
    schedule:
      start: immediately/日期時間
      repeat: once/hourly/daily/weekly/monthly
      time: HH:MM
      end: never/日期時間
analysis:        # 股票分析設定
```

---

## 🔐 帳號密碼備份

### LINE 官方帳號
| 項目 | 內容 |
|------|------|
| 帳號名稱 | 胚騰 |
| Basic ID | `@117tehfu` |
| User ID (你的) | `U22237069d5d57cdb8ea50c4c762e36df` |
| Channel Access Token | 已設定於 config.yaml |

### Gmail (用於 Email 通知)
| 項目 | 內容 |
|------|------|
| Email | `spyang1963@gmail.com` |
| App Password | `qodk pthc zklc lwrb` |
| SMTP Server | `smtp.gmail.com` |
| SMTP Port | `587` |

### GitHub
| 項目 | 內容 |
|------|------|
| 帳號 | `spyang1963-pattern` |
| Repo 名稱 | `sensebar-agent-knowledge-vault` |
| GitHub Pages URL | https://spyang1963-pattern.github.io/sensebar-agent-knowledge-vault/ |

---

## 📁 專案結構

```
D:\_AI Agent\
├── stock-monitor\              # 股票監控系統主目錄
│   ├── config.yaml             # 設定檔（閾值、通知設定）
│   ├── run_stock_analysis.py   # 主執行腳本
│   ├── message_scheduler.py    # 排程執行器（背景自動發送）
│   ├── scheduler_monitor.py    # 排程監控 GUI
│   ├── notification_manager.py # 通知管理系統 GUI
│   ├── test_scheduler.py       # 排程邏輯診斷
│   ├── sent_log.json           # 已發送紀錄（去重用）
│   ├── requirements.txt        # Python 套件
│   ├── setup.bat               # 安裝腳本
│   ├── logs\
│   │   └── scheduler.log       # 排程執行日誌
│   ├── src\
│   │   ├── twse_fetcher.py     # TWSE 資料抓取
│   │   ├── analyzer.py         # 分析邏輯
│   │   ├── generate_dashboard.py # Dashboard 生成
│   │   ├── notifier.py         # LINE/Email 通知
│   │   └── margin_cache.py     # 融資資料快取
│   └── output\
│       ├── dashboard\          # 生成的 HTML 檔案
│       └── cache\              # 資料快取
├── docs\                       # GitHub Pages 內容
│   ├── index.html              # 主頁面
│   └── history.html            # 歷史紀錄頁面
└── WORK_LOG.md                 # 工作紀錄
```

---

## 🔧 重要設定檔位置

| 檔案 | 說明 |
|------|------|
| `D:\_AI Agent\stock-monitor\config.yaml` | 所有設定（閾值、通知開關、LINE Token、Email） |
| `D:\_AI Agent\stock-monitor\run_stock_analysis.py` | 主程式入口 |
| `D:\_AI Agent\stock-monitor\deploy_github.py` | 自動部署腳本 |
| `D:\_AI Agent\docs\` | GitHub Pages 內容目錄 |

---

## 🚀 常用操作

### 啟動通知管理系統
```bash
cd D:\_AI Agent\stock-monitor
python notification_manager.py
# 或直接雙擊 啟動通知管理.bat
```

### 啟動排程執行器（背景運行）
```powershell
cd D:\_AI Agent\stock-monitor
Start-Process -FilePath python -ArgumentList message_scheduler.py -WindowStyle Hidden
```

### 停止排程執行器
```powershell
Get-Process python* | Where-Object {$_.MainWindowTitle -eq ''} | Stop-Process -Force
# 或使用 SchedulerMonitor GUI 停止
```

### 查看排程日誌
```powershell
Get-Content D:\_AI Agent\stock-monitor\logs\scheduler.log -Tail 50
```

### 手動執行分析
```bash
cd D:\_AI Agent\stock-monitor
python run_stock_analysis.py
```

### 手動檢查資料更新（單次）
```bash
cd D:\_AI Agent\stock-monitor
python data_monitor.py
```

### 啟動即時監控（持續運行）
```bash
cd D:\_AI Agent\stock-monitor
python data_monitor.py --daemon 15
# 或直接執行 start_monitor.bat
```

### 手動部署到 GitHub Pages
```bash
cd D:\_AI Agent
python stock-monitor/deploy_github.py
```

### 查看排程工作
```powershell
Get-ScheduledTask -TaskName "StockAnalysis"
Get-ScheduledTask -TaskName "TWSE_DataMonitor"
```

### 修改設定
編輯 `D:\_AI Agent\stock-monitor\config.yaml`

---

## ⚠️ 注意事項

1. **LINE Channel Access Token** 有時效性，需定期更新
2. **Gmail App Password** 如果安全性設定變更需重新產生
3. **TWSE API** 融資融券資料有 1-3 天延遲，這是證交所正常作業流程
4. **GitHub Pages** 部署後可能需等 1-2 分鐘才會更新
5. **監控機制**：系統會每15分鐘檢查 TWSE，發現新資料立即通知
6. 排程時間：`StockAnalysis` 每日 18:00 執行，`TWSE_DataMonitor` 18:00-21:00 每15分鐘監控

---

## 📝 今日學到的重點

1. TWSE MI_MARGN API 融資融券資料有 1-3 天延遲，這是證交所正常作業流程
2. GitHub Pages 部署後可能有瀏覽器快取，需 `Ctrl+F5` 強制更新
3. GitHub 有 secret scanning 機制，會偵測並阻擋含有 API key 的 push
4. **建立即時監控機制**：每15分鐘檢查 TWSE，發現新資料立即觸發分析並通知
5. 使用 `subprocess.run()` 執行外部腳本，可擷取輸出並處理錯誤
6. **Windows subprocess + 中文**：`text=True` 用 cp950 編碼，必須改用 `encoding="utf-8", errors="replace"`
7. **去重週期必須匹配 repeat 類型**：daily 訊息用「當日」去重，不能用「分鐘」
8. **排程器一定要寫 log 檔案**：stdout 輸出在背景運行時會消失
9. **股票分析的 Email 要在特殊處理函數裡發送**：不能只依賴一般訊息處理流程

---

## 🔄 監控機制說明

### 架構
```
data_monitor.py (每15分鐘)
    ↓
檢查 TWSE API 最新日期
    ↓
比對本地快取 (monitor_status.json)
    ↓
有新資料? → 是 → 執行 run_stock_analysis.py → 發送 LINE + Email
           → 否 → 等待下次檢查
```

### 狀態檔
- 位置：`output/monitor_status.json`
- 內容：記錄上次已知日期、最後檢查時間

### 排程
- `TWSE_DataMonitor`：交易日 18:00-21:00，每15分鐘執行一次
- 總共 13 個觸發點（18:00, 18:15, 18:30, ... 21:00）

---

*最後更新：2026-07-21 (排程器穩定化完成)*
*記錄者：胚騰 AI Agent*

---

## 📝 今日工作重點 (2026-07-21)

### 新增檔案
- `notification_manager.py` - 通知管理系統 GUI 主程式
- `啟動通知管理.bat` - 批次啟動腳本
- `message_scheduler.py` - 排程執行器（背景自動發送）
- `scheduler_monitor.py` - 排程監控 GUI
- `test_scheduler.py` - 排程邏輯診斷腳本
- `logs/scheduler.log` -排程執行日誌

### 重要修改
- `config.yaml` - 重新設計結構，以訊息為主體
- `src/notifier.py` - 支援新格式 (name + user_id/email)
- `message_scheduler.py` - 修復三個重大 bug

### 設計決策
1. **訊息為主體** - 每則訊息獨立管理接收者與排程
2. **狀態管理** - 訊息有編輯中/待命/運作中/已停止
3. **接收者狀態** - 每個接收者可獨立暫停/恢復
4. **頁籤式介面** - 總覽+編輯+設定，操作直覺

### 待辦事項
- [ ] 整合 data_monitor.py 與新的 config 結構
- [ ] 接收者錯誤處理（發送失敗自動標記）

---

## 🐛 2026-07-21 排程器重大 Bug 修復

### Bug 1：cp950 編碼崩潰（Stock Analysis 從未觸發）
- **症狀**：`台股融資券分析` 排程時間到了卻從不發送
- **原因**：`execute_stock_analysis()` 使用 `subprocess.run(..., text=True)`，Windows 預設用 cp950 編碼解碼，遇到 TWSE 中文輸出就 `UnicodeDecodeError` 崩潰
- **修正**：改用 `encoding="utf-8", errors="replace"` + `-u` unbuffered 參數
- **關鍵教訓**：Windows PowerShell 環境下 subprocess 的 text mode 用系統編碼，不是 UTF-8

### Bug 2：分析成功後沒發通知
- **症狀**：`execute_stock_analysis()` 成功後只 return True，沒有組裝+發送 LINE/Email
- **原因**：`send_stock_analysis_message()` 成功分支只做 `return True`，沒有呼叫 `send_line_message()`
- **修正**：成功後從 stdout 提取警示股數，組裝通知並同時發送 LINE + Email
- **同時修正**：Email 也加入發送邏輯（原本只發 LINE）

### Bug 3：LINE 洪流（每分鐘重複發送）
- **症狀**： Scheduler 啟動後，每分鐘收到一則相同訊息
- **原因**：deduplication 用「分鐘」等級 (`%Y-%m-%d %H:%M`)，但 `daily` 訊息應該每天只發一次
- **修正**：改為「當日」等級 (`%Y-%m-%d`) 去重，`hourly` 用 `%Y-%m-%d %H`
- **關鍵教訓**：去重週期必須匹配 repeat 類型

### Bug 4：完全沒有 logging
- **症狀**：Scheduler 崩潰時找不到原因，stdout 輸出消失
- **修正**：加入 `logging` 模組，所有輸出同步寫入 `logs/scheduler.log`

### 經驗總結
| 場景 | 錯誤做法 | 正確做法 |
|------|----------|----------|
| subprocess 輸出含中文 | `text=True` | `encoding="utf-8", errors="replace"` |
| 重複發送防止 | 用分鐘等級 | 匹配 repeat 類型（daily=當日） |
| 排程器除錯 | 只靠 print | 寫入 log 檔案 |
| Email 發送 | 只在一般訊息處理 | 股票分析也要處理 Email |

### 驗證結果
- Scheduler PID 3868 穩定運行
- `logs/scheduler.log` 正常記錄所有觸發
- LINE + Email 都成功發送
- 去重生效，每則訊息每天只發一次
