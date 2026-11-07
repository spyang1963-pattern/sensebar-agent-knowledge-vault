# HANDOFF｜摘要 prompt v4 全庫重生（2026-11-07）

## 背景（為什麼要做）
摘要 prompt 原本寫死「投資／交易課程」＋個股小節，遇到哲學／一般課程只會吐一個「關鍵結論」。
實測：全庫 131 篇摘要有 122 篇 < 600 字元（中位數 313，最短 226）。

`make_course_note.py` 已改為 **v4 內容自適應**（`SUMMARY_PROMPT_VER="v4"`）：
- A 投資／交易 → 大盤與行情觀點／個股與族群／操作策略與條件／關鍵數據與指標／關鍵結論
- B 其他主題 → 核心觀點／概念與定義／案例與例證／方法與步驟／關鍵結論（要求 5～8 條具體重點）

notebook 已重生 **44 支**（2026-11-07 本批哲學清單）：中位數 **308 → 1214 字元（4.0x）**、0 失敗、5.3 分鐘。
**剩下 87 篇舊摘要仍偏薄**，交付 PC1 重生。

## 分工
```
PC1  regen_summaries.py --all  →  fix_youtube_links  →  publish_outbox
                                                   ↓（shared\pc1\outbox）
notebook  harvest_pc.py --replace " 摘要.md" " 摘要.docx"  →  fix_youtube_links
          →  regen_summaries.py --all（只補 PC1 沒有的條目；今天已重生的會自動跳過）
```

## PC1 端（貼給 PC1 agent 的原文）
見對話中的 K1～K5。重點：
1. `git pull --ff-only`（要 >= `6105e34`，含 v4 prompt 與 `regen_summaries.py`）
2. `regen_summaries.py --all --max 3` 先試 3 支
3. `regen_summaries.py --all`（PC1 端 105～106 篇，約 6～10 分鐘）
4. `fix_youtube_links.py --apply`（新摘要沒有 `> 原始影片：[YouTube](...)`）
5. **等 150 秒**再 `publish_outbox.py`（打包有「靜止 120 秒」保護，剛寫完會被跳過）

## notebook 端（收割，需帶 --replace）
```powershell
python -X utf8 harvest_pc.py --machine pc1 --dry-run --replace " 摘要.md" --replace " 摘要.docx"
python -X utf8 harvest_pc.py --machine pc1 --replace " 摘要.md" --replace " 摘要.docx"
python -X utf8 fix_youtube_links.py --apply
python -X utf8 regen_summaries.py --all --dry-run    # 看還有幾支沒被 PC1 覆蓋到
python -X utf8 regen_summaries.py --all              # 只做剩下那幾支（今天已重生的自動跳過）
python -X utf8 fix_youtube_links.py --apply
```

**沒有 `--replace` 會白跑**：`harvest_pc.py` 的預設是「同家族同名不同內容 → 保留 notebook 正本」，
所以 PC1 重生好的摘要會被丟掉、只記 `skipped_same`。`--replace` 覆蓋前會把舊檔備份到
`knowledge-base\_harvest_overwritten\<machine>\<tid>\<時間>\`。

## 驗收（尾巴，別忘）
```powershell
python -X utf8 -c "import pathlib,statistics,re; kb=pathlib.Path('knowledge-base/youtube-clips'); s=[len(p.read_text(encoding='utf-8-sig')) for p in kb.glob('* 摘要.md')]; print('篇數',len(s),'| <600',sum(1 for x in s if x<600),'| 中位數',int(statistics.median(s)))"
```
- 期望：`篇數 131｜<600 0~5｜中位數 1000+`
- 連結：`python -X utf8 fix_youtube_links.py` （不加 --apply）應回報「0 變更」
- `knowledge-base\_harvest_conflicts` 應為空；`_harvest_overwritten` 會有舊摘要備份（正常，可留可刪）

## 已知注意
- `regen_summaries.py` **不吃** `.note_quota.json`（明確指定＝已決定要做）；channel_watcher／backfill 才計配額。
- `--all` 預設跳過「今天已重生」的（看摘要內的 `整理日期`），避免手滑重複燒 Gemini；要重做加 `--force`。
- 兩台機器同一天各跑一次 Gemini 是預期行為（PC1 為主、notebook 補 PC1 沒有的條目）。
- 若 Gemini 503：`_retry_llm` 內層 6 輪＋外層 3 輪會撐很久；真的失敗會印 `[失敗]` 並繼續下一支，重跑即可（已完成的會跳過）。
