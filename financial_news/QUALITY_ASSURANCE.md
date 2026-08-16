# 金融新聞情報系統 · 品質保證工程設計

> 版本：v1.0　日期：2026-08-10
> 目標：確保所蒐集資訊的正確性（Accuracy）、可靠性（Reliability）、時效性（Timeliness），並讓品質可量化、可稽核、可追溯。

---

## 0. 背景：為何需要品質保證

2026-08-10 品質稽核發現以下實質缺陷，若不解決，系統的後續推論（分析、預測、報告）均建立在不可靠的資料之上：

| # | 缺陷 | 實證 |
|---|------|------|
| Q1 | 最重要新聞被誤殺 | 「台股收盤漲702點 收復季線44331點」「45000點得而復失」等今日關鍵收盤新聞全被 `is_noise=1` |
| Q2 | 完全沒有去重 | `is_duplicate` 全部為 0；同新聞出現 12 次（PChome 公告）、5 次（Wall Street Today） |
| Q3 | 來源嚴重偏斜 | 已分析 9,252 筆中「油價」類查詢佔 ~1,860 筆，資料集由查詢詞主導而非真實市場重要性 |
| Q4 | 交叉驗證覆蓋不足 | severity≥2 共 5,581 筆，僅 1,066 筆有第二模型複核（17%） |
| Q5 | 無關新聞混入報告 | bbc "Could your tattoo stop you from getting a job?" 因 `ALWAYS_KEEP_SOURCES` 強制保留 |
| Q6 | 嚴重度浮濫 | severity=3（重大）達 1,064 筆，重大事件應稀有，評分標準不穩定 |

---

## 1. 總體架構：四層品質保證

```
┌─────────────────────────────────────────────────────────┐
│  第 0 層  來源治理 (Source Governance)                    │
│  可信度分數・每來源限量・時效門檻・白名單分級・品質計分卡      │
├─────────────────────────────────────────────────────────┤
│  第 1 層  收集去重 (Collection & Dedup)                   │
│  標題正規化・內容哈希・近重複合併・同新聞保留最高可信來源      │
├─────────────────────────────────────────────────────────┤
│  第 2 層  過濾 (Filtering)                               │
│  規則分數 + 模型分類雙通道・關鍵新聞保護・誤殺回收機制        │
├─────────────────────────────────────────────────────────┤
│  第 3 層  分析驗證 (Analysis & Verification)              │
│  重要事件 100% 雙模型驗證・置信度分數・驗證覆蓋率稽核         │
└─────────────────────────────────────────────────────────┘
```

每層皆有可量化 KPI，報告檔頭附「品質儀表板」供使用者一眼稽核。

---

## 2. 第 0 層：來源治理

### 2.1 來源可信度分級

每個來源（feed/查詢）設定 `trust` 等級，影響去重時的保留優先權與分析權重：

| 等級 | 分數 | 範例 | 說明 |
|------|------|------|------|
| A（權威） | 1.0 | 央行官網（fed/ecb）、證交所、金管會 | 第一手公告，不可由其他來源取代 |
| B（主流） | 0.8 | CNBC、Reuters、BBC、經濟日報、工商時報、Yahoo | 知名財經媒體，標題可靠 |
| C（一般） | 0.6 | MarketWatch、NYT、LINE TODAY、民視 | 具一定可信度 |
| D（可疑） | 0.3 | 內容農場、理財部落格、觀點文章 | 標題常聳動，僅作補充 |

- **去重衝突時**：同一新聞多來源出現 → 保留 trust 最高者；同 trust 保留 published 最早者。
- **分析權重**：severity 相同時，trust 高的來源優先列入「重大事件」區塊。

### 2.2 每來源每輪限量（配額）

- 每個查詢/feed 每輪收集 **上限 30 筆**，避免單一查詢（如「油價」1,145 筆）壟斷資料集。
- 每輪收集總量上限：Google News 查詢整體 ≤ 400 筆、直接 feed ≤ 200 筆。
- 新增事件若超過配額，只保留 published 最新者（時效優先）。

### 2.3 時效門檻

- **收集端**：RSS entry 的 `published` 距今超過 **48 小時** 且非權威來源（A/B 級）→ 跳過不收集。
- **分析端**：`published` 距今超過 **72 小時** → 不再納入「新增事件」區塊，僅留在「全部事件」。
- **報告端**：市場快照逾 24 小時 → 標示 `⚠️`（已實作）。

### 2.4 白名單分級（取代 ALWAYS_KEEP_SOURCES）

原 `ALWAYS_KEEP_SOURCES` 一律保留 → 改為「保留下限」：

| 來源 | 行為 |
|------|------|
| A/B 級權威與主流來源 | 不需過規則分數，**直接保留**（但 2.2 限量仍適用） |
| C/D 級來源 | 必須過規則分數（threshold=2） |
| 任何來源 | 若內容命中「關鍵新聞保護」規則（§4.1）→ 強制保留 |

這樣 bbc 的 tattoo 文章會被保留（A 級）…**不**，bbcbusiness 屬 B 級。改進：B 級也過一道「主題有效性」粗篩（規則分數 ≥ -1，即扣除明顯負面關鍵字後不為負）。tattoo 新聞觸發 NEGATIVE 或無任何 POSITIVE → 排除。

---

## 3. 第 1 層：收集去重

### 3.1 標題正規化

```
normalize(title):
  - 轉小寫
  - 去全形/半形空白、多餘空白
  - 去除結尾的「來源名」字尾（如 " - 經濟日報"、" | UDN"、"- Yahoo新聞"）
  - 去除標點符號差異（，,。.；;）與「【】」括號內容（公告前綴如【公告】、【快訊】）
  - 去「？?!！」結尾
```

### 3.2 內容哈希

- `dedup_key = sha1(normalize(title)[:100])`
- 資料表新增 `dedup_key TEXT` 欄位（可為 NULL 表示未去重）。
- **同 dedup_key 合併**：保留 trust 最高 + published 最早者為主記錄，其餘標 `is_duplicate=1`。

### 3.3 近重複（fuzzy）合併

- 標準化後 Title 的 **Difflib ratio ≥ 0.85** 視為同一新聞。
- 僅在每輪新收集批次內進行（不與全歷史比對，避免 O(n²)）。
- 合併規則同上（保留最高 trust、最早 published）。

### 3.4 去重執行時機

- `collect_all()` 結束後、`filter` 之前，執行 `dedup_pending()`。
- 產出品質指標：去重率 = 被合併數 / 總收集數。

---

## 4. 第 2 層：過濾

### 4.1 關鍵新聞保護（防誤殺）

即使規則分數不足，命中以下任一條件即**強制保留**：

```
# 台股 / 市場指數
"台股 收盤" | "收盤" + 指數數字 | "加權指數" | "大漲|大跌|飆漲|崩跌" + 點數
# 央行 / 政策
"央行" | "中央銀行" | "Fed|FOMC|Federal Reserve" | "升息|降息"
# 監管
"金管會" | "證交所" | "證監會" | "SEC"
# 地緣政治
"戰爭|開戰|襲擊|空襲|入侵" | "制裁" + 國家
# 財報/重大公司
"營收" + "新高|創高|破紀錄" | "財報" + "超預期|暴雷"
```

以「台股收盤漲702點」為例：命中 `台股 收盤` → 保留。此規則直接解決 Q1。

### 4.2 雙通道過濾

1. **通道一（規則）**：現有 `score_event()`（保留，threshold=2）。
2. **通道二（模型）**：規則得分在邊界（0~2）的事件，交由 Gemini 以低額度快速分類（financial 相關？）。
3. **決策**：任一通道判定「保留」→ 保留；都判定噪音 → `is_noise=1`。
4. 邊界事件存 `pending_review`，供人工或後續模型批次複核。

### 4.3 誤殺回收機制

- `is_noise=1` 的事件在 **24 小時內** 若被新的同標題/近重複新聞再次收集到 → 自動取消噪音標記（`is_noise=0`），並重新分析。
- 提供 `noise_filter.py --recover` 指令：重新檢視最近 48h 噪音事件，命中「關鍵新聞保護」規則者回收。
- 此機制處理「先被誤殺、後因查詢擴大而再現」的新聞。

---

## 5. 第 3 層：分析驗證

### 5.1 重要事件 100% 交叉驗證

- 現有 `verify_important()` 已實作，但覆蓋率僅 17%（原因：歷史事件在驗證功能上線前已分析）。
- **改進**：
  - `verify_important` 改為批次呼叫（一次送多筆），避免逐筆 round-trip，提高產量。
  - 增加**歷史補驗**：對 `severity>=2 且 verification IS NULL` 的事件，排程每次補驗 N 筆（如 20/輪），逐步提升覆蓋率。
  - 新增環境變數 `VERIFY_COVERAGE_TARGET`（預設 0.95）與稽核腳本。

### 5.2 置信度分數（Confidence）

- 分析結果新增 `confidence` 欄位（0~1）：
  - 雙模型一致（verified）：`confidence = 0.9`
  - 雙模型衝突（conflict）：`confidence = 0.4`（報告標註「判斷分歧」）
  - 單模型未驗證：`confidence = 0.6`
- 報告中 confidence < 0.6 的重大事件標 `⚠️ 未經複核`。

### 5.3 品質儀表板（報告檔頭）

每日報告開頭新增：

```
> **品質儀表板**：事件 80 筆 | 去重 12% | 來源 23 | 關鍵事件保護 5 | 驗證覆蓋 95% | 資料新鮮度 ≤5min
```

指標定義：
- `去重率` = 當輪合併數 / 收集總數
- `驗證覆蓋率` = 已驗證(severity≥2) / 總(severity≥2)
- `資料新鮮度` = 報告產出時間 − 最新事件 published 時間

### 5.4 稽核指令

```bash
python quality_audit.py            # 全量品質稽核（§0 之 Q1-Q6 指標）
python quality_audit.py --recent 24h   # 最近 24h 品質稽核
```

---

## 6. 資料庫 Schema 變更

```sql
ALTER TABLE events ADD COLUMN dedup_key TEXT;
ALTER TABLE events ADD COLUMN trust REAL DEFAULT 0.8;
ALTER TABLE events ADD COLUMN confidence REAL DEFAULT 0.6;
ALTER TABLE events ADD COLUMN dedup_group TEXT;   -- 同一新聞群組主記錄 id
CREATE INDEX idx_events_dedup_key ON events(dedup_key);
```

既有資料遷移：`dedup_key` 由現有 events 回填（一輪批次）；`trust` 依來源對照表回填。

---

## 7. 實作順序（對應本次任務清單）

1. **設計文檔**（本文檔）✅
2. **修復誤殺** ✅
   - `noise_filter.py`：新增 `KEY_NEWS_PATTERNS`（台股收盤/加權指數/央行/Fed/金管會/地緣政治/財報重大）、`KEEP_ON_SIGHT`（fed/ecb）、`is_key_news()`、`--recover` 回收指令、白名單改最小相關性篩檢
   - 已回收誤殺：今日 41 筆 + 歷史 14 筆 + 追蹤 8 筆
3. **去重機制** ✅
   - `dedup.py`（新檔）：`normalize_title()`（去來源字尾/公告前綴/標點）、`dedup_key`（sha1）、`trust_for_source()`（fed/ecb=1.0、主流=0.8、google-news=0.6）、`dedup_pass()`（保留最高 trust + 已分析 + 最早者）、`compute_trust()` 校正
   - `db.py`：新增 `dedup_key/dedup_group/trust/confidence` 欄位 + `mark_dedup()/set_confidence()/set_trust()`
   - `pipeline.py run_collect()`：收集後自動跑 trust 校正 + dedup
4. **來源治理** ✅
   - `news_collector.py`：`MAX_PER_FEED=30`、`MAX_GOOGLE_TOTAL=400`、`MAX_DIRECT_TOTAL=200`、`MAX_AGE_HOURS=48`（時效門檻）、`_too_old()`、fed/ecb 豁免 age gate
5. **驗證覆蓋** ✅
   - `analysis_engine.py`：`_confidence_for()`（verified=0.9/conflict=0.4/unverified=0.6）、`_verify_one_groq()` 429 退避、`backfill_verification()` 歷史補驗 + rate-limit 快速中止、`--backfill-verify` CLI、analyze 後寫入 confidence
   - `pipeline.py run_full()`：每輪補驗 20 筆
   - `quality_audit.py`（新檔）：誠實計算「真實驗證覆蓋率」（僅 verified+conflict 計入）
   - `report_generator.py`：報告檔頭「品質儀表板」即時顯示
6. **完整 pipeline 重跑** ✅（見 §8 現況）

---

## 8. 驗收標準（KPI）

| 指標 | 修正前 | 現況（2026-08-10 實測） | 目標 |
|------|--------|----------------------|------|
| 今日關鍵新聞誤殺數 | 30+ 筆 | 0（已回收 41+14+8 筆） | 0 |
| 去重率 | 0% | 12.2%（1,678 筆） | ≥ 20%（每輪） |
| 單一查詢佔比（油價） | 20% | 7.5%（max source） | ≤ 10% |
| 重要事件真實驗證覆蓋率 | 17%* | 18.1%（944/5,214，其餘為 Groq 429 rate-limited） | ≥ 95% |
| 資料新鮮度 | 修正前 +8h | ≤ 8 分鐘 | ≤ 15 分鐘 |
| 無關新聞混入報告 | 有 | 已設 KEEP_ON_SIGHT 分級 + 最小相關性篩檢 | 0 |

\* 原 17% 為「有驗證紀錄（含 unverified）」；真實驗證（第二模型有產出）僅 18.1%。差距主因是
Groq 免費額度 429 rate limit，屬外部資源限制，`backfill_verification` 每輪自動補驗、額度恢復即提升。

### 8.1 品質儀表板範例（報告檔頭）

```
> 品質儀表板: 資料新鮮度 ≤8min | 去重率 12.2% | 最大來源佔 7.5% | 驗證覆蓋 18.1%
```

### 8.2 稽核指令

```bash
python quality_audit.py              # 全量稽核（含儀表板）
python quality_audit.py --recent 24  # 最近 24h 稽核
python noise_filter.py --recover --apply   # 誤殺回收
python analysis_engine.py --backfill-verify 20  # 歷史補驗 20 筆
python dedup.py --stats              # 去重統計
```

---

## 9. 限制與誠實聲明

- **資料來源本質**：Google News RSS 對部分查詢仍有滯後（「中央銀行 利率」263h），此為來源限制，靠時效門檻（§2.3）與直接 feed 稀釋。
- **自動化無法取代人類判斷**：severity/outlook 為模型主觀輸出，品質儀表板僅確保「過程可稽核」，不保證「結論正確」。
- **需要週期性人工抽檢**：建議每週人工檢視 10 則隨機重大事件，回饋校正 prompt。
