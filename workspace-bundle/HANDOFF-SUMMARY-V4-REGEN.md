# HANDOFF｜摘要 prompt v4 全庫重生（2026-11-07 ✅ 完成）

## 結果（收尾狀態）
| 指標 | 之前 | 之後 |
|---|---|---|
| 摘要篇數 | 131 | 131 |
| 有 `> 摘要版本：v4` | 0 | **131（100%）** |
| < 600 字元 | 122 | **4**（皆為 1 分鐘 Shorts，426～549 字） |
| 中位數字元 | 313 | **1200** |
| 小節標題重複 | 有 | **0 篇** |
| 缺 `> 原始影片：[YouTube](...)` | 87 | **0** |
| `_harvest_conflicts` | 0 | 0 |

家族完整性：`逐字稿 131｜筆記 131｜摘要 131｜srt 214｜docx 262`，缺件 0。

## 背景（為什麼要改）
摘要 prompt 原本寫死「投資／交易課程」＋個股小節，遇到哲學／一般課程只會吐一個「關鍵結論」。
`make_course_note.py` 已改為 **v4 內容自適應**（`SUMMARY_PROMPT_VER="v4"`）：
- A 投資／交易 → 大盤與行情觀點／個股與族群／操作策略與條件／關鍵數據與指標／關鍵結論
- B 其他主題 → 核心觀點／概念與定義／案例與例證／方法與步驟／關鍵結論（要求 5～8 條具體重點）
- 摘要檔頭自 v4 起多一行 **`> 摘要版本：v4`**（重跑與否的判斷依據）

## 三段實跑（合計 Gemini 約 180 次）
1. notebook 本批 44 支：**308 → 1214** 字元、5.3 分鐘
2. PC1：全庫 74 支（5.8 分）→ 補 32 支（2.2 分）→ 1 支誤分類重生（637 → 1388）
3. notebook 獨有 29 支：**384 → 1272** 字元、2.9 分鐘

## 三個踩過的坑（都已修，勿改回）
1. **「同日跳過」誤擋**（`f6eaddc`）：原本用 `整理日期` = 今天就跳過，會把「當天凌晨用舊 prompt
   產出的短摘要」誤判成已完成（PC1 中了 32 篇）。改看 `> 摘要版本：v4`；無標記時才用
   「同日且 ≥700 字元」當備援。
2. **版本標記是後加的**（`0a30d8f`）：118 篇（PC1 74 + notebook 44）內容是 v4 但沒標記，
   直接 `--all` 會白燒 118 次 Gemini。解法 `--stamp-only`：只插一行、不呼叫 API、同步重建 docx。
   判斷只認 **B 組小節 ≥2 個**，**不看 A 組**（v3 對非投資內容也硬套大盤／個股，那正是要重生的）。
3. **收割會把新版換成舊版**（`f6eaddc`）：`harvest_pc.py` 預設「同名不同內容 → 保留 notebook 正本」，
   沒有 `--replace` 就會白跑；加了 `--replace` 後又可能被「產出機還是舊短版」蓋回去，
   所以再加**「不縮水」保護**（新檔較小就保留本機，訊息 `⚠ 保留本機較完整版本`）。

## 需要時怎麼重跑
```powershell
# 只補「缺少 v4 標記」的（不呼叫 Gemini）
python -X utf8 regen_summaries.py --all --stamp-only --dry-run

# 只重生偏薄的
python -X utf8 regen_summaries.py --all --if-shorter-than 600 --dry-run

# 指定範圍
python -X utf8 regen_summaries.py --video-id nZDI_VzSEeg
python -X utf8 regen_summaries.py --ledger-date 2026-11-07

# 重生後一定要補連結（新寫的摘要沒有那一行）
python -X utf8 fix_youtube_links.py --apply
```

## 收割（PC 產出 → notebook 正本）
```powershell
python -X utf8 harvest_pc.py --machine pc1 --dry-run --replace " 摘要.md" --replace " 摘要.docx"
python -X utf8 harvest_pc.py --machine pc1 --replace " 摘要.md" --replace " 摘要.docx"
python -X utf8 fix_youtube_links.py --apply
```
覆蓋前舊檔備份在 `knowledge-base\_harvest_overwritten\<machine>\<tid>\<時間>\`（本輪 160 檔）。

## 已知限制
- **v4 誤分類率約 1/106**：純方法論內容（例：「問題意識的五個構件」）可能被判成 A 投資類，
  只吐 2 節且偏短。重生一次通常修好；未來若常發生再升 v5（會讓所有標記失效，屬大事）。
- PC1 有 4 篇沒有對應 outbox 包（本機手動／外來條目：`哲学入门 001-01`、`如何建立 YouTube 頻道`、
  `YouTube 頻道創建教學 2026`、`新頻道盈利第一關`）→ 由 notebook 自己重生，不走收割。
- `regen_summaries.py` **不吃** `.note_quota.json`（明確指定＝已決定要做）；channel_watcher／backfill 才計配額。
- 4 篇 <600 是內容本質（Shorts），不要再重生去湊字數。
