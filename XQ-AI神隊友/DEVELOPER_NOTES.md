# XQ-AI神隊友 — 開發者思維交接筆記（DEVELOPER NOTES）

> 本檔給「接手者」看：說明這套 HTML 看板是**怎麼想出來的**、關鍵決策與為何這樣做。
> 這裡寫「為什麼」（思維），不是「怎麼跑」（那在 CLAUDE.md 與各腳本檔頭）。

最後更新：2026-09-08（追加 rank 新版、15 分排程、視覺配色原則）

---

## 一、事情的緣起

原本這三樣報告（族群資金排行／齊漲分歧診斷／盤中觀察三段）只輸出**純文字 .md**，
使用者覺得「不好讀、抓不到重點」。想要的是一個**一眼看到關鍵、跳出純文字框框**的呈現。

結論：改成**互動式 HTML 看板**，並上 GitHub Pages（手機能看）。不是改資料、不是加預測，
只是**把同一批資料用更聰明的方式呈現**。

重要界線（鐵則，全程沒破）：只看盤中快照、不預測、不給買賣建議、數值照抄腳本輸出。

---

## 二、借了「知識庫」的易讀手法（寫作框架）

參考 `D:\AI-Agent-Workspace\knowledge-base\金融\深度報告\` 的寫法，把「易讀骨架」移植進來：
1. **一句話結論**：標題下第一行，先講最重要的一件事。
2. **欄位口語翻譯**：技術欄位（內外盤比／乖離／換手）首次出現時，hover 顯示一句人話。
3. **「這代表什麼」**：矛盾、反差不只列「誰漲誰跌」，還點出數據合起來的含義。
4. **該盯的變數**：結尾列出 2-3 個接下來值得追蹤的客觀訊號（不帶方向）。

這些都寫進 `CLAUDE.md` 的「文體通用規則」了。

---

## 三、核心：三層詮釋（這是整件事的靈魂）

使用者問：「資金排名的資料有涵義嗎？各筆／整體／趨勢的意義？」於是設計了三層：

### ① 各筆意義（單一檔/族群，用快照既有欄位算）
把 raw 欄位交叉判讀成「這代表什麼」：
- 重磅量（佔前50名≥5%）+ 收黑 → 偏出貨（南亞科111億 -0.31%）
- 重磅量 + 收紅 → 真金白銀在接（承接型量）
- 內外盤比 <40 → 賣方掛單厚，上檔壓力；>60 → 買方厚，下檔有撐
- 乖離 ≤ -2.5 → 開高走低、動能弱
- 換手≥10 → 爆量對戰；低換手卻鎖漲 → 籌碼極輕
- 委買委賣嚴重失衡 → 掛單極端

實作在 `render_html.py` 的 `interpret_stock()`。

### ② 整體結構診斷（整張盤涵義）
`diagnose_structure()` 自動算：
- **資金集中度**：前50名成交值 ÷ 全表。⚠️ 目前快照只含報價表那 100 檔，非全市場，
  所以集中度偏高（96%）是「報價表內」的相對值，不是全市場，參考就好，別過度解讀。
- **主軸訊號**：最大資金族群的量 vs 方向（載板205億卻收黑→主軸退潮，最重要）。
- **上下游結構**：用族群名關鍵字做粗略分層（材料/基板/板廠/設備/顆粒…），
  多層同時有錢＝題材型整鏈；只有單層＝個股消息。
- **小盤輪動**：量較小但全紅的族群→高低切換手。
- **漲跌家數**：全表紅綠家數對比。

### ③ 趨勢意義（與前一份快照比）—— 尚未有資料，架構已就位
`load_previous()` + `compare_rank()` 自動找「前一份同 kind 快照」比對。
**前提是要累積到至少 2 份同 kind 快照**。目前每種只有今天一份，所以顯示「尚無前份可比較」。

**這就是為什麼要設「每 30 分快照」排程**→ 到收盤前會累積約 9 份，今晚③就有真實資料。

---

## 四、架構決策（為何這樣設計）

| 決策 | 理由 |
|---|---|
| 用 **Python** 寫 `render_html.py` | 處理數字/字串/歷史最穩，且與另兩專案（financial_news、stock-monitor）一致 |
| 直接**讀 snapshots\ CSV**，不解析 analyze_*.ps1 的文字輸出 | CSV 是乾淨結構化資料，解析文字易碎；且 CSV 有時間戳，天然可做歷史 |
| CSV 當**歷史庫**（不另建 DB） | 最輕量、零依賴、符合現有快照機制；掃 `snapshots\rank_*.csv` 就有一串歷史 |
| 產出**單一自足 HTML**（內嵌 CSS/JS，無外部依賴）| 好部署到 GitHub Pages，手機開也正常，不需伺服器 |
| 判定門檻對齊 `analyze_breadth.ps1` | 保證 HTML 與文字報告「同口徑」、跨日可比 |

### 檔案地圖（本次新增）
- `routines/render_html.py` — HTML 產生器（核心，含三層詮釋）
- `xq_snapshot_loop.bat` — 被 Windows 排程呼叫，依序抓 rank/breadth/notes 快照
- `setup_xq_snapshot_task.ps1` — 建立/重設 Windows 排程（可重跑）
- `routines/outputs/{kind}_{stamp}.html` — 產出看板
- `DEVELOPER_NOTES.md` — 本檔

### 視覺設計原則（2026-09-08 定案）
- **配色語意單一化**：「紅＝看多/上漲/資金流入」，「綠＝看空/下跌/流出」，「黃＝中性/警惕」。
  CSS 變數 `--up` 紅、`--down` 綠；class `.key-red/.key-green/.key-yellow`。
  **寫判讀文案（one_line_*／斷句／pill／箭頭）時一個字都不能馬虎**，曾把「收黑」標成紅色。
- **展開/收起機制**：`toggleRest(btn)` 讀 `data-wrap`（包住的容器 id）、`data-expand/data-collapse`（按鈕文字），
  `.rest-row`（表格列）／`.rest-inline`（div）預設隱藏、`.rest-open` 顯示。
  **單檔頁用 `JS`、dashboard 用 `DASH_JS`，兩份都要有 toggleRest**。
- **資金位移 verdict（進貨/出貨判讀）**：只看成交值增減太單薄，與股價方向合看才有意義：
  進貨(量增價漲)/疑似出貨(量增價跌)/惜售(量縮價漲)/退潮(量縮價跌)，pill 上色。

---

## 四之一、盤後綜合分析（dashboard 第四 tab）— 格式定案（2026-09-11）

> 這塊的樣式全在 `render_html.py` 的 `_pm_*` 函式＋CSS（`.pm-*`）。**不要憑記憶改**，重弄前先讀這段與 `_pm_forecast_section`／`_pm_render_md`／`_pm_hl_line` 實作。
> 報告格式由 `postmarket_report.py` 的 SYSTEM_PROMPT 定義（管 Gemini 產出 md），渲染管樣式，兩者都要動才一致。

### ✅ 定稿範本版本（2026-09-12 使用者確認「這個版本定稿，記下來為範本」）
- **定稿 commits（由舊到新，全部已 push 並部署 PC3＋線上）**：`437b367`（標題 startswith＋薑黃標號 pm-idx/尾註 pm-note/judge 薑黃）→ `1b8afb3`（現價錨定/價位品質）→ `eb4ef8b`（缺方向補中性 flat pill＋CSS）→ `dd2a6b2`（**方向=中性也有 pill**）→ `6dd58ce`（排名標籤 `N.` 取代 `N#`）。
- **🔖 回滾保險 tag：`pm-v2-final`**（2026-09-12 建立，已 push 遠端）。指向定稿後最新 commit（dashboard 快照 commit），**此 tag 之後被開新分支做新功能，tag 永遠不移動**。還原方式：`git checkout pm-v2-final -- routines/render_html.py routines/postmarket_prep.py routines/postmarket_report.py publisher/deploy.py`（只還原程式檔）；整個回定稿：`git reset --hard pm-v2-final`。**改壞程式時，第一件事就是查 `git log --oneline --all` 找這個 tag**。
- **線上驗證基線**：pmdata 4 份（09/10 morning 8 卡 / 09/10 evening 14 卡 / 09/11 morning 12 卡 / 09/11 evening 12 卡），每檔有薑黃標號、每檔有方向 pill（中性＝灰 flat）、價位可疑才出現 pm-pxwarn。
- **將來任何輸出跑掉**，以此為修正基準：重產後逐卡核對「有無薑黃標號（pm-idx）、有無方向 pill（含中性 flat）、有無不該出現的 pm-pxwarn、排名標籤是否 `N.`、股名紅綠對不對」。
- **前鼎教訓（2026-09-12，兩次）**：
  ① 第一次誤判「缺方向欄」補了 fallback，才發現 md 原文是 `方向：中性`——中性分支原本 cls="" 讓 `if cls` 不畫 pill。
  ② **任何方向（含中性）都要有 pill**：`_pm_dir_label` 對空字串與「中性」都回 （"中性","flat",""）。`.pill.flat` 樣式＝`--flat` 灰。

### 版面定案（使用者逐輪確認過的「定版」）
- **預測榜卡片（`.pm-stock`）**：每檔一行內含——**薑黃標號** `.pm-idx`（`background:#4a3a10;color:#e0b34d`，卡片順序 1,2,3…）＋股名 `<b data-code data-name>`（依方向 `key-red`紅／`key-green`綠）＋方向 pill（`.pill.up/.pill.down/.pill.flat`，缺方向時是中性 flat）＋「強度：X」`.pm-str`。
- **詳細行 `.pm-detail`**：`<span class="pm-k">`（藍底標籤，`background:#243156;color:#bcd2ff`）＋「：」＋ `_pm_hl_line` 高亮內容。
- **次標籤 `.pm-sub`**（價值點的「大家怎麼想／數據怎麼說」等）＝淡藍底（同 `.pm-k`）；**「我的判斷／我的判斷與理由」＝ `.pm-sub.pm-judge` 薑黃**（`background:#4a3a10;color:#e0b34d`），比淡藍高一層、是這塊的視覺主角。先前用海棠紅 `_PM_SUB_MAGENTA` 已廢棄。
- **標題尾註 `.pm-note`**：預測榜標題會帶小字（如「（含 5 檔中小型股）」），薑黃小字顯示在標題旁，**不要**把它當成整段標題的一部分去做比對。
- **一鍵複製按鈕**：卡片標題右側 `copyStocks`，輸出 **TSV**（`code\tname` 換行）方便貼 Excel。
- **排名標籤一律 `N.`**：盤面任何「第 N 名」的股票清單（頭號矛盾 `.contra-card .t`、齊漲分歧逐檔清單等）一律顯示 `1. 台積電` 格式（`{r['Rk']}.`），**不可用 `#`**（`6dd58ce`）。

### 關鍵陷阱（本次實踩，務必遵守）
1. **標題比對用 `title.startswith("明日個股預測榜")`，不可 `==`**：Gemini 不時在標題加尾註（如「（含 5 檔中小型股）」），`==` 失配會讓整段預測榜**滑落 generic section**（整列海棠紅、方向只剩文字、無 pill 卡片）＝使用者看到的「權值股偏紅」。
2. **price 速查表要餵進 input**：`postmarket_prep.py` 會讀最新 `breadth_*.csv` 的 `Close` 建「現價速查表（成交值前 80）」放 input 開頭，個股訊號行附現價。**沒有現價，Gemini 就會靠訓練記憶硬編支撐/壓力**（例：聯一光現價 166 卻寫「支撐 42/壓力 48」）。
3. **prompt 鐵律**：SYSTEM_PROMPT 明定「支撐必須 < 現價 < 壓力、與現價合理距離（±3%~15%）、查無現價寫『無現價資料，不估價位』、嚴禁編價」。
4. **渲染驗證層**：`_pm_check_price` 用最新 breadth 快照現價比對 md 的「支撐 X / 壓力 Y」，方向反了或偏差 ≥50% → 插 `.pm-pxwarn`（橙色警示）。**跨日渲染**（報告日 vs 快照日不同）且個股大漲大跌時可能誤標，門檻 ±50% 已是緩衝。
5. **詳細行解析**：`- 標籤：內容` 用 `re.match(r"^([^：]+)：\s*(.*)$", raw, re.S)` 拆；**關鍵價位在 `cur is not None` 後才 `_pm_check_price(code, ...)`**（code 來自該檔股票變數）。
6. **每一檔都要有方向 pill**：`_pm_dir_label` 對空字串（漏寫方向欄）**和「中性」**都回傳（"中性","flat",""），不可讓 cls 空（`if cls` 會省略 pill）。`.pill.flat` 用 `--flat` 灰。**前鼎案例**＝Gemini 寫的是「方向：中性」，原本中性分支 cls="" → 無 pill；別誤判成「缺欄位」。
7. 歷史報告以 `pmdata` JSON 內嵌進 dashboard；渲染時 embed 的 HTML 在 ``<script type="application/json" id="pmdata">``，`</` 要 `.replace("</","<\\/")` 防被 `</script>` 截斷（既有規則，沿用）。

### 檔案分工（改這塊要知道）
- `postmarket_prep.py`：彙整五路資料 → `routines\postmarket\input_{date}_{slot}.md`；現價速查表、資料時效註記都在這。
- `postmarket_report.py`：SYSTEM_PROMPT（含預測榜 12~15 檔、至少 4~5 檔中小、關鍵價位鐵律、催化劑）＋呼叫 Gemini → `routines\outputs\postmarket\postmarket_{date}_{slot}.md`。
- `render_html.py`：`_pm_render_md` 逐一 render pmdata；`_pm_forecast_section` 處理預測榜卡片；CSS `.pm-*` 在同檔。
- 排程：`XQ_Postmarket_Evening`（22:00）／`XQ_Postmarket_Morning`（06:30）；跑 `xq_postmarket_loop.bat <slot>`（prep→report→render→deploy 串好）。

### ⭐ 新功能需求（2026-09-12 使用者提出，接手 session 照此實作）

#### 需求一：儀表板「一鍵輸出全部表 → 貼 Excel」
- **目標**：dashboard 四個頁籤（資金排行／齊漲分歧／盤中三段／盤後綜合分析）每一張資料卡，**按一次鍵**就把「目前頁籤全部表」或「全部頁籤所有表」彙整成一整份，直接複製、貼到 Excel，不用一卡一張慢慢複製。
- **現況**：每卡各自有 `copyStocks` 按鈕（`DASH_JS` 內，約 `render_html.py` L1601），只複製**單卡**（抓 `.card` 內 `[data-code]`→`code\tname`；無 `[data-code]` 則抓 `table` 全文）。
- **做法（建議）**：
  1. `DASH_HEAD`（L1492 的 header 區）tabbar 下方加一排按鈕：「📋 輸出本頁全部表」「📋 輸出全部頁籤」。
  2. `DASH_JS` 新增 `copyAll(scope)`：`scope='page'` 只走 `.tabpage.active`；`scope='all'` 走全部 `.tabpage`（每頁前綴頁籤名）。對每個 `.card`，**前綴一行「【卡片標題】」**（取 `card.querySelector('h2').textContent`），再輸出複製內容（沿用 copyStocks 的 `[data-code]`→TSV 或 table 全文）；卡片間空一行。tab 分隔＝Excel 分欄、換行＝分列，貼上即「多張小表依序往下排」。
  3. 成功提示沿用 `copyStocks` 的 `copied` 樣式＋「已複製 N 張表」。
- **驗證**：`python -X utf8 render_html.py --dashboard` 重產，開 HTML 確認按鈕與 `copyAll` 存在；瀏覽器手測複製→貼 Excel 看分欄分列正確。
- **注意**：`copyStocks` 有兩份等義實作（`JS` L775 與 `DASH_JS` L1601），各自獨立頁面，`copyAll` 只需加在 `DASH_JS`（盤中儀表板用）；若要單頁版也要就同步加 `JS`。
- **⚠️ JS 內嵌 Python 陷阱（2026-09-12 實踩）**：DASH_JS 是 Python 三引號字串，寫 JS 字串常數 `'\n'` 會被 Python **展開成真實換行字元塞進 JS**＝JS SyntaxError→整個 script 崩→時間軸/報告/按鈕全失效。**內嵌 JS 的換行一律寫 `'\\n'`、Tab 寫 `'\\t'`**（成對雙反斜線）。事後可用產出 HTML 的 `blocks.join` 行＋`repr()` 檢查是否為逃脫序列。

#### 需求二：盤後預測榜「出榜依據＋可靠度＋大中小型涵蓋＋資金板塊權重」
- **目標**：明日個股預測榜每檔都要——
  1. **出榜依據**：條列「為何選上」的具體數據（引用 input 的資金位移增減/法人買賣超張數/融資券變化/千張大戶增減等實數），不可只寫「法人看好」空話。
  2. **可靠度評級**：每檔標示「高/中/低」＋一句話理由（如「資金位移＋法人連買同步，可靠度高；僅單一指標者中/低」）。
  3. **大中小型標示**：每檔註明「大型/中型/小型」，整體要涵蓋三類，維持至少 4~5 檔中小型。
  4. **資金板塊權重**：明訂資金明顯流入板塊（XQ 盤中資金位移增加但股價未充分反映者）的檔次應佔榜單**最高比重（至少一半）**——這是本儀表板的核心資訊，出榜必須以其為主。
- **現況**：`postmarket_report.py` SYSTEM_PROMPT 已有排序條件（資金位移優先→法人→融資券→催化劑→平衡族群）與「至少 4~5 檔中小型」，但輸出欄位只有操盤邏輯/關鍵價位/催化劑；**沒有「依據」「可靠度」「規模分類」欄位，資金權重未量化**。
- **資料已全在 input**（`postmarket_prep.py` 組裝）：`## 0 現價速查表 / 1 XQ盤中資金 / 2 融資券 / 3 三大法人 / 4 千張大戶 / 5 美股 / 6 行事曆 / 7 金融報告`。渲染有現價速查表錨定＋pm-pxwarn 驗證層。
- **待與使用者確認**：
  - 「融資券分析中的**三大觸發**」→ 專案目前無此子功能，需定義（XQ 融資券頁分類？）。
  - 「**法人買賣超 / 個股篩選 / 四象限**」→ 法人買賣超在 input $$3；個股篩選＝預測榜本身；**四象限**僅盤中 `compare_rank()` verdict（資金量×漲跌四象限），input 中無，若要納入出榜依據需先擴充 prep。
  - 出榜簡報是否需要「可靠度」統一圖例（例：高＝綠勾/中＝黃/低＝灰）？渲染層配合（新 pill class）。
- **改動範圍（三層）**：`postmarket_report.py`（SYSTEM_PROMPT 增欄位格式＋鐵律）→ `render_html.py`（`_pm_*` 解析新欄位＋可靠度 pill CSS）→ 可能 `postmarket_prep.py`（四象限/融資券摘要）→ 多輪驗證 Gemini 輸出格式（固定欄位、避免跑版）。
- **建議由付費模型 DeepSeek-V4-Pro/GLM-5.1 開新 session 承接**：三層協動＋反覆驗證，big-pickle 免費層（200/5h）會很快燒完；定稿 tag `pm-v2-final` 已 push 遠端，改壞隨時還原（見回滾保險）。

---

## 五、排程（Windows Task Scheduler）

- 任務名：**XQ_Snapshot_Loop**（系統管理員握有的舊任務，StartBoundary=09:25，待管理員停用）
  與 **XQ_Snapshot_Loop2**（一般權限建立，**09:15 起**，目前的主力任務）
- 時段：週一~五 **09:15 起，每 15 分一次，持續到 13:30**（Plan：09:15 第 1 份 → 09:30/09:45/…/13:30）
- 動作：`cmd /c xq_snapshot_loop.bat`（→ 依序跑三種 snapshot.ps1，以 -STA 掛 Excel）
- 為什麼能多跑不爆：`snapshot.ps1` 內建**盤中時段守門**（09:15–13:30，時段外回 SKIP）＋
  **stale 去重**（資料沒變不重存），所以就算兩支排程交錯觸發，也只多跑一次、無害。

**⚠️ 09:25 殘留教訓（2026-09-11 紀錄）**：
- `setup_xq_snapshot_task.ps1` 從頭就寫 `-At 09:15`，但 PC3 實際任務是 **09:25**（09/08「改 15 分」重註冊時，實際 StartBoundary 被設成 09:25，與文件不符，文件一路沿用錯誤）。
- 09/10 停用舊 Loop2 時只停任務、沒把主力任務起跑改回 09:15 → 09/11 第一輪變成 09:25。
- **教訓：停用雙排程後，務必確認主力任務的 StartBoundary 是文件寫的時刻；文件與實際不符時更新文件，不要沿用舊紀錄。**
- 現況：舊 `XQ_Snapshot_Loop`（管理員所有，09:25）無法由一般權限停用 → 用 `setup_xq_snapshot_task.ps1` 建了 `XQ_Snapshot_Loop2`（09:15）。兩支並跑靠 stale 去重無害；**勿刪新任務**。管理員停用舊的後，主力就是 Loop2。

**⚠️ 排程要生效的前提（很重要）**：
1. **Excel 開著**，裡面有 XQ 用 DDE 貼過來的報價表（快照靠 COM 讀它）。
2. **電腦不能睡眠**。
3. 三者缺任一 → 該輪會 SKIP / stale，資料不累積，③趨勢就沒料。

### 想改排程
重跑 `setup_xq_snapshot_task.ps1` 即可（-Force 覆蓋，一般權限建立的是 `XQ_Snapshot_Loop2`）。
想改頻率/時段，改該檔裡的 `-At 09:15`、`-RepetitionInterval`、`-RepetitionDuration`。

⚠️ **頻率調密（30→15）的代價**：同日輪數約加倍（約 27 輪/天），dashboard 內嵌歷史 JSON 明顯變大。
   若嫌大：調小 `HIST_DAYS`、或「歷史輪只存精簡 fragment」的現有設計已是省空間方案。

---

## 六、還沒做（待辦）

- [x] **作法二、作法三套同一 HTML 框架** — 2026-09-08 完成：
      `build_breadth/render_breadth`（齊漲/齊跌/分歧/獨走＋個股訊號最反直覺）、
      `build_notes/render_notes`（全樣本 vs 前份、三段自動文、翻紅翻黑、大幅位移）。
      判定口徑對齊 `analyze_breadth.ps1`／`analyze_notes.ps1` 常量。
- [x] 「該盯的變數」排進 HTML — 三 kind 共用 `_render_watch()`。
- [x] 驗證 ③ 資金位移真的能算出 — 2026-09-08 實測成功（台積電 +46億 等，見 SESSION_20260908.md）。
- [x] **單一儀表板 xq_dashboard.html** — 2026-09-08 完成：
     三 tab（rank/breadth/notes）＋時間軸切歷史（保留最近 5 交易日）；最新輪顯示完整全文、
     歷史輪顯示精簡 fragment（`frag_rank/frag_breadth/frag_notes`）；同輪快照以「分鐘」合併。
     陷阱：內嵌 JSON 必須 `.replace("</","<\\/")` 否則被完整 HTML 自己的 `</script>` 截斷。
     `xq_snapshot_loop.bat` 每輪尾連跑 `python render_html.py --dashboard` 自動重產。
- [x] **rank 頁新版（展開＋資金位移 verdict＋紅多綠空配色）** — 2026-09-08 完成：
     族群資金表/逐檔解讀預設 5 項＋展開/收回按鈕；`compare_rank()` 四象限 verdict
     （進貨/疑似出貨/惜售/退潮）；全判讀文案配色修正（收黑/退潮/流出＝綠）。已實測 1525 快照。
- [x] **排程改每 15 分** — 2026-09-08 完成（`setup_xq_snapshot_task.ps1` 重註冊 `PT15M`，Result 驗證）。
- [x] **GitHub Pages** — 2026-09-08 完成：新 repo `spyang1963-pattern/xq-dashboard`（master/根目錄/legacy），
      上線 `https://spyang1963-pattern.github.io/xq-dashboard/`。`publisher/deploy.py` 自動發佈，
      已掛進 `xq_snapshot_loop.bat` 每輪推送（仿 financial_news→financial-reports 模式）。
      ⚠️ 歷史 JSON 會隨輪次（15 分頻率約 27 輪/天）長大，目前 130KB 尚可；嫌大時調 `HIST_DAYS`。

---

## 七、額度／模型提醒（重要）

- 本專案預設用 **big-pickle（免費）**。免費層有硬上限 **200 次/5h（滾動）**，
  且是**共用池**（跟其它免費模型一起算）。
- 切付費模型（如 deepseek-v4-flash）前**必看**：`python C:\Users\hpspy\.config\opencode\scripts\check_go_usage.py`。
- ⚠️ 陷阱：`deepseek-v4-flash-free`（免費）和 `deepseek-v4-flash`（付費）名稱極像，
  要切切務必選 `opencode-go/deepseek-v4-flash`（付費），選錯 free 版會爆共用免費池。
- 本作業（把 rank 框架複製到 breadth/notes）是**機械性延續**，big-pickle 就夠，不需切付費。
