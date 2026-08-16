# financial_news AGENTS.md

## 專案概覽
金融新聞自動化：每 30 分鐘收集新聞 → 過濾 → AI 分析 → 每日/晚間報告 → GitHub Pages。

## 排程任務（Windows Task Scheduler）
| 任務 | 頻率 | 參數 |
|---|---|---|
| FinanceNews_Pipeline | 每 30 分鐘 | `pipeline.py --full --batch 150 --time-budget 480` |
| FinanceNews_MorningReport | 每日 07:00 | `pipeline.py --report --deep --slot morning` |
| FinanceNews_EveningReport | 每日 19:00 | `pipeline.py --report --deep --slot evening` |
| FinanceNews_Dashboard | 登入時 | `start_dashboard.bat` |

## ⚠️ 電腦關機/睡眠中斷報告陷阱（2026-08-14 實際發生）
- 現象：早上 7:00 深度報告沒產出、沒上網站；`FinanceNews_MorningReport` `LastTaskResult=3221225786`（0xC000013A=STATUS_CONTROL_C_EXIT，進程被強制終止）；深度報告缺 `2026-08-14 早上`；repo/site/deep 停在 8/13-pm。
- 根因：非程式 bug。電腦在 07:00 任務執行期間關機/重啟（system log 顯示 07:49 一連串 McAfee 服務啟動＝開機），Task Scheduler 終止執行中的進程。StartWhenAvailable 只救「錯過觸發」的任務（07:49 開機後 pipeline 補跑 07:57），救不了「已啟動執行中被殺」的任務（MorningReport LastRun 仍顯示 07:00，不會補跑）。
- 診斷流程：
  1. `Get-ScheduledTaskInfo FinanceNews_MorningReport`：看 LastTaskResult（非 0 = 失敗；0xC000013A = 被終止）。
  2. 查 system log 開機證據：`wevtutil qe System /q:*[System[(EventID=1)]] /c:20 /rd:true /f:text`，看 07:00 後是否有 McAfee Service Controller 服務啟動批次（＝開機）。
  3. 對照 `logs\pipeline.log` 時間線：06:45 analyze → 07:57 collect 中間 70 分鐘空白 = 關機期間錯過的輪次。
- 補救：手動重跑同排程指令 `python pipeline.py --report --deep --slot morning`（會重新產深度報告並 build+push）。**跑之前先確認沒有 pipeline 進程在跑**（`Get-Process python`），避免同時 build+push 衝突。補跑後驗證：repo `deep\2026-08-14-am.html` 存在、index「最新深度」指向它、線上 `https://spyang1963-pattern.github.io/financial-reports/deep/2026-08-14-am.html` 可開且報告時間正確。

## 已知陷阱
### 重複排程 RepetitionDuration 到期停止（2026-08-12 實際發生）
- 現象：pipeline 停止收集，每日報告「沒動態更新」、資料慢一天。
- 根因：`FinanceNews_Pipeline` 的重複觸發帶 `Duration=P9DT2H40M, StopAtDurationEnd=True`，自 8/2 22:24 起算，8/12 01:04 到期後不再觸發；Morning/EveningReport 是 Daily 觸發不受影響，所以報告照跑但內容是舊資料。
- 修正：`Set-ScheduledTask` 更新 Trigger 為 `-RepetitionDuration (New-TimeSpan -Days 3650)`。
- 驗證：
  - `Get-ScheduledTaskInfo FinanceNews_Pipeline`：`LastTaskResult` 須為 0。
  - `logs\pipeline.log` 出現 `collect:` 新紀錄。
  - DB：`SELECT MAX(fetched_at) FROM events` 應接近現在。
- 註：`setup_finance_schtask.ps1` 與 `fix_finance_tasks.ps1` 都是 3650 天設定，但現役排程曾被其他工具以 9 天 Duration 覆寫——**任何手動改排程前先查 Triggers.Repetition.Duration**。

## 分析額度現況
- `logs\pipeline.log` 中 `analyze: ... quota_hit=True` 幾乎每次出現：Gemini 免費版額度耗盡，分析批次自動停止（`analysis_engine.py` 設計如此）。現役排程 `--batch 150` 大於 README 建議的 `--batch 8`。
- 收集（collect）不受影響，只有 AI 分析標籤會落後。

## 報告動態更新陷阱（2026-08-13 修正）
- 現象：報告停在 13:13 不更新，但 collect 持續在跑、DB 持續新增事件。
- 根因：`run_full()` 原本 `if not quota_hit: run_report()`——quota_hit=True（Gemini 額度不足）時整輪跳過報告。而每輪 analyze 其實仍有 24~150 筆成功寫入 DB（quota_hit 只是提前停止），這些分析結果因此看不見。
- 修正：改為 `if analyzed > 0: run_report(deep=False)`——只要有新分析就重產報告（每 30 分鐘滾動更新）。報告 cutoff 機制（previous file mtime）會自動涵蓋上次產出後的新事件。
- 額外陷阱：`pipeline.py` 需 `import sqlite3`（topic dedup 用 `conn.row_factory = sqlite3.Row`），漏掉會出現 `WARNING topic dedup failed: name 'sqlite3' is not defined` 但流程繼續。

## 報告產出位置
- 每日報告：`..\knowledge-base\每日報告\YYYY-MM-DD.md`
- 深度報告：`..\knowledge-base\深度報告\深度報告 YYYY-MM-DD 版.doc`
- 發布：`publisher\repo\` → GitHub Pages

## 過濾門檻（2026-08-13 調整）
- `noise_filter.py` 新增「重要公司白名單」：`IMPORTANT_COMPANIES`（台股權值+電子供應鏈+美股大型+AI 鏈）。純個股事件（財報/營收/EPS/評級/併購/裁員…）若未提及白名單公司、且無宏觀語境（`MACRO_PROTECT_PATTERNS`：央行/通膨/指數/地緣/大盤等），直接判 noise。
- 回測（8/10 後 2806 筆歷史已分析事件）：濾掉 4.6% 小公司個股新聞，誤殺率 0.18%（僅小型股財報，皆可接受）。

## 主題級去重（2026-08-13 加入）
- `dedup.py::topic_dedup_pass()`：同一事件被多源重複報導（如 CPI 3.4% 當日 14 筆）合併壓縮。每主題保留信任度最高+已分析+最早的前 2 筆，其餘標 `is_duplicate=1`（`db.mark_dedup`）。
- 合併條件（保守，防誤吞不同事件）：48h 視窗內、≥2 個共同「強錨詞」（`STRONG_TOPIC_KW`：cpi/油價/央行/戰爭/輝達等）、至少 1 個共同數值、且區域無衝突（美中新聞不互併）。
- 已接入 `pipeline.py::run_full()`（filter 之後、analyze 之前），排程 `--full` 自動執行；可手動 `python dedup.py --topic`（套用）/ `--topic-dry`（預覽）。
- `db.unanalyzed()` 已排除 `is_duplicate=1`，被標記者不會再耗分析額度、不出現在報告。
- 2026-08-13 首輪套用：12 buckets、18 筆合併（全為同主題重複，無誤合併）。
- 2026-08-13 16:36 排程輪驗證：`topic dedup: 17 buckets, 6 merged`（修復 `import sqlite3` 後每輪正常執行）。

## 行事曆保留已過期事項（2026-08-13 變更）
- `publisher\market_calendar.py::build_calendar()`：原本 `date_ < today` 直接丟棄過期事件（完成的事項隔天就消失）。改為 `date_ < today - 30天` 才丟棄 → **已完成事項保留約一個月**。
- 月曆網格改為「上個月 + 本月 + 未來 2 個月」共 4 張表（保證過去 30 天的事件都在網格內）；`upcoming` 加 `done` 旗標。
- `calendar.html`：已完成事件顯示「已完成」+ 網格內淡化刪除線（`.evdot.done`）；「未來 7 天」提醒過濾 `days_left >= 0` 排除已過期者。
- 驗證：`python -c "from publisher import market_calendar; ..."` 看 `months` 與 `done` 旗標。

## 即時時鐘市場標籤（2026-08-13 變更）
- `publisher\template.html` 與 `calendar.html` 的即時時鐘區塊（header `#clock` + 行事曆大時鐘卡片）市場徽章調整：
  - 台北：**加權指數**（原「台股」更名）09:00-13:30、**台指期日盤** 08:45-13:45、**台指期夜盤** 15:00-次日05:00（週一至五）
  - 紐約：**美股** 09:30-16:00 ET、**美股夜盤**（盤後）16:00-20:00 ET
- JS 新增 `nightOpen()` 處理台指期夜盤跨日（15:00-24:00 週一至五 + 00:00-05:00 週二至六）；`marketOpen()` 維持同日時段。
- 注意：兩檔案都要同步修改（template.html 是各報告頁 header，calendar.html 是行事曆頁）。

## ⚠️ publisher push 事故陷阱（2026-08-13 實際發生）
- 現象：誤推後 GitHub Pages 只剩 calendar.html，daily/deep/index 全部消失（commit 顯示 22 檔 delete）。
- 根因：`build.py::push()` 會先 `rmtree(site)`（`build()` 開頭）＋刪除 repo 根所有舊檔，再從 site 搬內容。若 site 殘缺（例如某輪 build 因異常在重建中途中斷、site 只剩部分檔案），push 會把「殘缺狀態」當成最新推上去，線上檔案被刪光。
- 修正：`python -m publisher.build --no-push` 重建完整 site → **先驗證 `site\daily`、`site\deep` 檔案數正常**（daily 12、deep 9）→ 再 `build.push()`。
- 教訓：**任何手動 push 前，先確認 site/ 目錄完整性**；懷疑 site 殘缺時先完整重建再推。pipeline 內的正常 build+push 每次都是完整重建（build() 全量），不會有殘缺問題；只有人工部分渲染（如只改 calendar.html）時才可能踩到。

## ⚠️ 「最新深度」誤指早上報告陷阱（2026-08-13 修正）
- 現象：使用者反映「下午 7:00 深度分析沒發布」，但其實 `deep/2026-08-13-pm.html` 早在 19:00 就 push 上線（commit 70cb6a3）。真相是網站「最新深度」導覽與 index 的深度區塊指向 `2026-08-13-am.html`（早上）。
- 根因：`build.py::collect_reports()` 的 `items.sort(key=lambda x: (x["day"], x["slot"]), reverse=True)` 用中文 slot 排序——「早上」(U+65E9) 的 Unicode 大於「傍晚」(U+508D)，reverse 後**早上反而排前面**，`latest_deep = next(...)` 取到早上報告。
- 修正：sort key 改用 slot 數值 rank：`{"": 0, "早上": 0, "傍晚": 1}.get(x["slot"], 0)`，傍晚排前面。
- 教訓：① 中文當排序 key 依賴 Unicode 順序極易出錯，需用數值 rank。② `deep_day_slug` 用 `sorted(slug)[-1]` 依賴字串 'pm'>'am' 恰巧正確，勿改成中文比較。③ 判定「報告有沒有發布」以 repo 根 deep/ 檔案與 git log 為準，不要只看導覽連結。④ 回報「沒發布」前先 fetch 線上 URL 本身（如直接開 deep/2026-08-13-pm.html），確認檔案存在與內容日期。
