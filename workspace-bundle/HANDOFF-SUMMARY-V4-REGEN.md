# HANDOFF｜摘要 prompt v4 全庫重生（2026-11-07 更新：f6eaddc）

## 背景（為什麼要做）
摘要 prompt 原本寫死「投資／交易課程」＋個股小節，遇到哲學／一般課程只會吐一個「關鍵結論」。
實測：全庫 131 篇摘要有 122 篇 < 600 字元（中位數 313，最短 226）。

`make_course_note.py` 已改為 **v4 內容自適應**（`SUMMARY_PROMPT_VER="v4"`）：
- A 投資／交易 → 大盤與行情觀點／個股與族群／操作策略與條件／關鍵數據與指標／關鍵結論
- B 其他主題 → 核心觀點／概念與定義／案例與例證／方法與步驟／關鍵結論（要求 5～8 條具體重點）
- 摘要檔頭自 v4 起多一行 **`> 摘要版本：v4`**（重跑判斷用）

## 進度（2026-11-07 13:47）
| 機器 | 摘要總數 | 已標 v4 | 未標記 | 說明 |
|---|---|---|---|---|
| notebook | 131 | 44 | 87 | 44 支已 `--stamp-only` 補標記；87 篇仍待重生 |
| PC1 | 106 | 32 | **74** | 32 篇剛重生（已帶標記）；74 篇內容是 v4 但缺標記 |

> **陷阱（已修，`f6eaddc`）**：原本用「摘要內 `整理日期` = 今天就跳過」判斷，會誤擋「當天凌晨用舊 prompt
> 產出的短摘要」。現在改看 `> 摘要版本：v4` 標記；沒有標記時，同日且 ≥700 字元才視為新版。
> 另新增 `--if-shorter-than N`，可只挑偏薄的補。
>
> **第二個陷阱（`--stamp-only`，2026-11-07）**：版本標記是後加的，PC1 有 74 篇、notebook 有 44 篇
> 「內容已是 v4 但沒有標記」。若直接 `--all`，這 118 篇會被當成舊版重跑（白燒 118 次 Gemini）。
> 解法：`regen_summaries.py --all --stamp-only` 只補一行、不動內容、不呼叫 API。
> 判斷用 **B 組小節 ≥2 個**（v3 從未產出這些標題）；**不看 A 組**，因為 v3 對非投資內容也會硬套
> 「大盤／個股」（那 3 篇正是要重生的）。

## 分工
```
PC1  regen_summaries.py --all --if-shorter-than 600  →  fix_youtube_links  →  publish_outbox
                                                    ↓（shared\pc1\outbox）
notebook  harvest_pc.py --replace " 摘要.md" " 摘要.docx"  →  fix_youtube_links
          →  regen_summaries.py --all --if-shorter-than 600   （補 PC1 沒有的 notebook 獨有條目）
```

## PC1 端（貼給 PC1 agent 的原文）
見對話中的 N1～N5。重點：
1. `git pull --ff-only`（要 >= `a5f8647` 之後含 `--stamp-only` 的版本）
2. `regen_summaries.py --all --stamp-only --dry-run` → **期望 74 支**（只補標記，不呼叫 Gemini）
3. 同上不加 `--dry-run`
4. `publish_outbox.py`（標記改了 md/docx → 會重打包那 74 包）

## notebook 端（收割，需帶 --replace）
```powershell
python -X utf8 harvest_pc.py --machine pc1 --dry-run --replace " 摘要.md" --replace " 摘要.docx"
python -X utf8 harvest_pc.py --machine pc1 --replace " 摘要.md" --replace " 摘要.docx"
python -X utf8 fix_youtube_links.py --apply
python -X utf8 regen_summaries.py --all --if-shorter-than 600 --dry-run   # 看還剩幾支
python -X utf8 regen_summaries.py --all --if-shorter-than 600             # 補剩下的
python -X utf8 fix_youtube_links.py --apply
```

**沒有 `--replace` 會白跑**：`harvest_pc.py` 的預設是「同家族同名不同內容 → 保留 notebook 正本」，
所以 PC1 重生好的摘要會被丟掉、只記 `skipped_same`。`--replace` 覆蓋前會把舊檔備份到
`knowledge-base\_harvest_overwritten\<machine>\<tid>\<時間>\`。

**「不縮水」保護（預設開，`f6eaddc`）**：新檔比本機小就不覆蓋，訊息 `⚠ 保留本機較完整版本`。
用意是防止「PC 端還是舊短版就打包」把 notebook 的長摘要蓋回去。真要硬蓋才加 `--replace-force`。

## 驗收（尾巴，別忘）
```powershell
python -X utf8 -c "import pathlib,statistics,re; kb=pathlib.Path('knowledge-base/youtube-clips'); s=[len(p.read_text(encoding='utf-8-sig')) for p in kb.glob('* 摘要.md')]; print('篇數',len(s),'| <600',sum(1 for x in s if x<600),'| 中位數',int(statistics.median(s)))"
```
- 期望：`篇數 131｜<600 0~5｜中位數 1000+`
- 連結：`python -X utf8 fix_youtube_links.py`（不加 `--apply`）應回報「0 變更」
- `knowledge-base\_harvest_conflicts` 應為空；`_harvest_overwritten` 會有舊摘要備份（正常，可留可刪）

## 已知注意
- `regen_summaries.py` **不吃** `.note_quota.json`（明確指定＝已決定要做）；channel_watcher／backfill 才計配額。
- 選取規則：①有 `> 摘要版本：v4` → 跳過；②無標記但同日且 ≥700 字元 → 跳過；③`--if-shorter-than N` 已達標 → 跳過；④`--force` 全做。
- PC1 只有 106 支逐字稿、notebook 131 → 約 25 支 notebook 獨有，PC1 的 `--all` 覆蓋不到，要 notebook 自己 `--if-shorter-than 600` 補。
- 若 Gemini 503：`_retry_llm` 內層 6 輪＋外層 3 輪會撐很久；真的失敗會印 `[失敗]` 並繼續下一支，重跑即可（已完成的會跳過）。
