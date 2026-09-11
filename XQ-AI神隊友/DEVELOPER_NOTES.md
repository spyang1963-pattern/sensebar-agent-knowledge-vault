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
