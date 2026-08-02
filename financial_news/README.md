# 金融情報系統（Financial News System）

即時收集央行/金管會/證交所/地緣政治新聞，以 Gemini 免費版分析，產出
台股、美股、全球宏觀的影響報告、走勢預期與標的/警示建議。

## 系統架構

```
資訊源（全免費）                    收集層                分析層             輸出層
Google News RSS ──┐
Fed/央行/財經RSS ──┼─► news_collector ─► SQLite ─► noise_filter ─► Gemini ─► report_generator
Yahoo行情(免費API) ┘     (每30分鐘)      事件庫     (濾雜訊)      (分類/預測)   (每日報告)
                                                          │
                                              dashboard_web（即時/分析/歷史）
                                              notifier（LINE 已通 / Telegram 待設）
```

## 使用方式

```powershell
cd D:\AI-Agent-Workspace\financial_news

# 手動跑完整流程（收集→過濾→分析→報告）
python pipeline.py --full --batch 8

# 只收集
python pipeline.py --collect

# 分析（Gemini 免費版）
python pipeline.py --analyze --batch 8

# 產生每日報告（寫入 knowledge-base\金融\每日報告\）
python pipeline.py --report

# 市場行情快照（台股/美股/匯率/油金）
python market_data.py --collect
python market_data.py --latest

# 儀表板（背景執行）
start_dashboard.bat
# 瀏覽器開 http://127.0.0.1:5050

# 通知
python notifier.py --digest        # 發送摘要（LINE）
python notifier.py --test-tg       # 測試 Telegram（需先設 token，見 TELEGRAM_SETUP.md）
```

## 排程（已註冊 Windows 工作排程器）

| 任務 | 頻率 | 內容 |
|------|------|------|
| FinanceNews_Pipeline | 每 30 分鐘 | 收集 + 過濾 + 分析 |
| FinanceNews_DailyReport | 每日 18:30 | 產生每日報告 |
| FinanceNews_Dashboard | 登入時 | 自動啟動儀表板 |

## 資料庫結構（finance.db）

- `events`：新聞事件（來源、標題、時間、摘要、分類、重要性、情緒、標的、影響說明）
- `market_snapshots`：行情快照（歷史紀錄可回比）
- `analysis_runs`：分析執行紀錄

## 追蹤歷史

- 每日報告：`knowledge-base\金融\每日報告\YYYY-MM-DD.md`（Obsidian 可讀）
- 事件趨勢：儀表板「歷史」頁顯示最近 7 天事件數量
- 行情快照：`market_data.py --latest` 可看最新，DB 內可回比

## 檔案

| 檔案 | 功能 |
|------|------|
| news_collector.py | RSS/新聞收集 |
| noise_filter.py | 關鍵字濾雜訊 |
| analysis_engine.py | Gemini 分析（分類/情緒/標的/影響/展望） |
| report_generator.py | 每日報告 → KB |
| market_data.py | Yahoo 行情快照 |
| dashboard_web.py | 本機 Flask 儀表板 |
| notifier.py | LINE/Telegram 推播 |
| pipeline.py | 全流程執行器 |
| db.py | SQLite 資料層 |

## 備註

- Gemini 免費版每日有額度，批次用 `--batch 8` 較穩；額度用完會自動停，
  隔日或切 model 再跑（`GEMINI_MODEL=gemini-2.5-flash-lite`）。
- 報告含免責聲明：AI 生成僅供參考，不構成投資建議。
