# AGENTS.md — stock-monitor（台股融資券分析看板）

> 本檔是**給任何 AI agent 的強制操作手冊**。在此目錄工作的 agent 必須遵守下列規則。
> 知識以「檔案」為準，不依賴模型記憶。若完成任務後本檔所述與實際不符，請立即更新本檔。

## 專案簡介
台股融資券（融資/融券/維持率/三大法人）自動化分析系統。
- 每日 21:30 由 `message_scheduler.py` 觸發 `run_stock_analysis.py`，產出 HTML 看板並部署到 GitHub Pages。
- 看板 URL：`https://spyang1963-pattern.github.io/sensebar-agent-knowledge-vault/`
- 部署方式：`run_stock_analysis.py` 內含 push（`deploy_github.py`），GitHub Pages 約 45~55 秒生效。
- 專案路徑：`D:\AI-Agent-Workspace\stock-monitor`

## 強制工作流程（不可跳過）

### 1. 重產看板（每次改程式後必做）
```powershell
cd "D:\AI-Agent-Workspace\stock-monitor"
python run_stock_analysis.py --no-notify
```
- 需跑完整步流程，約 2~5 分鐘。中途可能被 TWSE API 限流，可重試。
- `--no-notify` 表示不要發 LINE/Email（手動測試時務必加，避免重複通知）。

### 2. 驗證 JS 語法（改到 generate_dashboard.py 後必做）
```powershell
python "C:\Users\hpspy\AppData\Local\Temp\opencode\js_check.py" "D:\AI-Agent-Workspace\stock-monitor\output\dashboard\dashboard_YYYY-MM-DD.html"
```
- node 不在 PATH，不能用 node 驗證。
- **注意**：`C:\Users\hpspy\AppData\Local\Temp\opencode\js_check.py` 是暫存區檔、可能已被清理而**不存在**（2026-09-13 驗證時已消失）。找不到時用等價檢查：`html.parser` 解析整份 HTML + 對 `<script>` 內容做括號平衡檢查。

### 3. 驗證部署結果（必做，防止「部署成功但資料是舊的」）
產生後**必須確認線上資料日期與內容正確**，再回報完成：
```powershell
Start-Sleep -Seconds 55
# 然後抓取線上 index.html，確認：
#  - 最新 K線日期 = 最新交易日
#  - 警示股數目/看板資料日期符合當日
#  - 本次修改的關鍵字存在（例如新的函數名/class 名）
```
- 曾發生：重產成功但 `STOCK_DAY_ALL` 只回前一天股價，腳本靜默回退，導致「8/10 看板跟 8/7 一樣」。**必須驗證資料日期後才能說「完成」**。
- **GitHub Pages 快取陷阱**：`index.html` 會被 CDN 快取，使用者點純網址會看到舊版。**通知訊息裡的看板 URL 務必帶版本參數**（如 `?d=20260811`，新參數＝新快取鍵）強制取新資料。相關程式碼：`message_scheduler.py`（`dashboard_url`）與 `run_stock_analysis.py` Step 10。

## 已知陷阱（務必閱讀）

1. **`STOCK_DAY_ALL` OpenAPI 只回「最新一個交易日」**，不看傳入日期參數，且比 margin API 慢更新（約凌晨過後才更新前一天）。
   - 時間點不對時 `fetch_stock_prices()` 會回空 → 自動回退到前一個有效股價 → 看板資料日期變舊。
   - 改法可考慮改用 `MI_INDEX`（支援歷史日期）取代。
2. **`src/advanced_data.py` CSV 讀檔**：部分 CSV 曾含損毀字元或髒資料。
   - 讀檔務必用 `encoding="utf-8-sig", errors="replace"`（**所有**讀取點都要，含 `_write_inst`/`_write_market`/`_append_margin` 內部讀舊檔的迴圈——曾因漏加導致回補時 UnicodeDecodeError 崩潰）。
   - `int()` 轉換務必 try/except 跳過髒資料（例：`'1646792026-06-09'`）。
   - 曾因此崩潰，導致 21:30 通知只發「無資料」備用訊息。
3. **`refresh()` 回補判定與法人資料缺失**：
   - `HistoryData.refresh()` 以 `market_daily.csv` 的日期判斷「已回補」。**若某日 T86 法人 API 當時失敗（限流），market 有該日但 `institutional_history.csv` 缺 → 永遠不會回補法人**。曾發生 8/11~8/21 法人序列整段缺失。
   - 已修：`refresh()` 另檢查 `_read_inst_coverage()`（各日列數 < 500 視為缺失，一併回補）。
   - 驗證方式：`python -c "import csv;from collections import Counter;rows=list(csv.DictReader(open(r'output/cache/institutional_history.csv',encoding='utf-8-sig',errors='replace')));c=Counter(r['date'] for r in rows);[print(d,c[d]) for d in sorted(c)[-10:]]"`
3. **`src/advanced_data.py` 個股 K線（`get_kline`/`_fetch_kline`）**：
   - **`STOCK_DAY` 的 `date` 參數必須用「西元 8 位數」（`YYYYMM01`，例：`20260801`）**。用民國格式（`115/08/01`）會回 HTML 錯誤頁 → JSON 解析失敗 → 個股 K線永遠抓不到，只能靠 Yahoo 補（Yahoo 會慢一天），造成「大盤 8/11、個股 8/10」。
   - **快取更新條件**：`get_kline` 只在「快取最後日期 ≥ 今天」時才直接用快取；否則重抓並與舊快取合併（勿覆蓋更早歷史）。曾用 `now-3天` cutoff，導致快取卡 3 天不更新。
   - 大盤綜合 K線（combo）用 Yahoo 指數、個股 K線用 TWSE `STOCK_DAY`，兩源更新時差會造成日期不一致。
4. **`src/generate_dashboard.py`**：
   - HTML 由 Python f-string 產生，JS 內嵌；`{`、`}` 一律雙寫 `{{` `}}`；regex 量詞要寫 `{{4,6}}`。
   - 行 ~1369 的 `SyntaxWarning: invalid escape sequence '\s'`（JS regex `split(/\s+/)`）**是無害的，勿「修」**。
   - `loadLiveStock()` 做兩階段繪圖：先畫 K線（立即回饋），再補融資/法人資料（20-30 秒）。點擊後無反應請先檢查此函數。
   - 即時查詢的摘要卡（`stock-info-cards`）顯示融資/法人最新值與資料天數，是使用者確認「有撈到資料」的依據。
5. **TDCC 集保每週資料**：快取在 `output/cache/tdcc_shareholding.json`，每週六更新，僅當週資料（無法取歷史週）。下次跑時當 prev 比對。API：`https://openapi.tdcc.com.tw/v1/opendata/1-5`（`證券代號`含尾端空白、`持股分級 15`=千張以上）。
6. **排程器**：`message_scheduler.py` 是常駐迴圈（30 秒輪詢），非 Windows 排程。改程式後**需重啟排程器**才生效（`python message_scheduler.py` 或 `啟動排程執行器.bat`）。log 在 `logs/scheduler.log`。
7. **通知去重**：`sent_log.json` 以「日」去重；手動測試通知務必 `--no-notify`。
8. **config.yaml 狀態層級（重要陷阱）**：訊息有兩層狀態，會互相干擾：
   - **訊息本體 `status`**（`stock_alert` 等）：`message_scheduler.py` 的 `should_send_now()` 要求 `status == "運作中"` 才會觸發。**設成「已停止」＝整則訊息完全不執行（連產出看板/更新網站都不做）**。曾發生：使用者只停發 Email/Line（把 `recipients` 的 status 設「暫停」），但訊息本體 status 也被設「已停止」→ 網站 2 天沒更新。
   - **接收者 `recipients[].status`**：「暫停」＝不發送該通道（LINE/Email），但訊息仍會執行、看板仍會更新。
   - 使用者想「停發通知但繼續更新網站」：只能改 `recipients` 為「暫停」，**訊息本體維持「運作中」**。
   - 確認狀態：`python -c "import yaml,json;c=yaml.safe_load(open('config.yaml',encoding='utf-8'));[print(m['id'],m['status']) for m in c['messages']]"`
9. **排程器無痕死亡**：`message_scheduler.py` 若被關閉/崩潰，log 停在最後一行，無任何錯誤。檢查方式：`Get-CimInstance Win32_Process -Filter "Name='python.exe'"` 找 `message_scheduler`；lock 檔 `scheduler.lock` 若殘留舊 PID 需手動刪除。排程器須用 watchdog（`scheduler_watchdog.py`）或手動啟動維持運行。
10. **`load_cache()` 預設只回最近 7 天**（`src/margin_cache.py`：`load_cache(max_days=7)`）。用 `--date` 重產**較舊日期**時，目標日的前一日比對資料會被擠出 7 天窗口 → `prev_date` 找不到 → `margin_change` 全 0（警示股誤歸零）、`est_maintenance_rate` 全變 100%（融資斷頭潮誤觸發）。**已在 `run_stock_analysis.py` 兩處改用 `load_cache(max_days=70)`**，勿改回。曾發生：批次重產 8/11~8/13 時警示股從 13/11/25 檔全部變 0。
11. **`generate()` 每次都會把產出覆寫成 `index.html`**（`src/generate_dashboard.py`）。用 `--date` 重產舊日期時，**線上首頁(index)會倒退成舊看板**。批次重產務必**由舊到新**、最後重產最新交易日；或重產完把最新看板複製為 `docs/index.html` 再 deploy。曾發生：重產 8 月看板後，GitHub Pages 首頁(index)從 9/11 倒退成 8/21。
12. **GitHub Pages CDN 快取延遲極常見**：剛 push 後立刻抓線上 URL 常拿到舊內容（幾十 KB 至幾分鐘）。驗證線上狀態必須**帶 cache-buster**（`?cb=<timestamp>`，例：`index.html?cb=1699999999`）強制取新；否則會誤判「部署失敗」。已確認 push 後約 45~55 秒生效。

## 檔案地圖
| 檔案 | 用途 |
|------|------|
| `run_stock_analysis.py` | 主流程入口（Step 1~11：資料→分析→看板→部署） |
| `src/twse_fetcher.py` | TWSE API 抓取（margin/股價/法人），`fetch_stock_prices` 用 STOCK_DAY_ALL |
| `src/advanced_data.py` | 大盤序列/維持率估算/TDCC 千張/圖表 payload（`build_chart_payload`） |
| `src/generate_dashboard.py` | 產生 HTML 看板（JS 內嵌 f-string，約 1600 行）。含「一鍵複製」`_build_bulk_copy_buttons()`（把三大觸發/警示篩選/法人排行/四象限的股號+股名一次複製，提供直行 A/B 欄往下與橫列 A/B、D/E 併欄兩種 TSV 排版） |
| `src/margin_cache.py` | 融資歷史 CSV 快取 |
| `message_scheduler.py` | 21:30 排程器 + 通知發送 |
| `config.yaml` | 排程/通知/門檻設定 |
| `deploy_github.py` | 複製到 docs/ 並 git push |
| `output/cache/` | 歷史資料快取（margin_history.csv / institutional_history.csv / tdcc_shareholding.json） |
| `output/dashboard/dashboard_YYYY-MM-DD.html` | 產出的看板檔案 |

## 全域規範
- 所有文件/回覆使用繁體中文；程式碼註解使用英文。
- commit message 用英文，格式 `type: description`（feat/fix/docs/style/refactor/test/chore）。
- 測試指令：`python -m py_compile src\<file>.py` 先做語法檢查。
