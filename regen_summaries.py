# -*- coding: utf-8 -*-
"""重生摘要（指定範圍）— 用目前 make_course_note 的 prompt 重做既有的「{stem} 摘要.md/.docx」。

為什麼要有這支：
- 摘要 prompt 改版（`SUMMARY_PROMPT_VER`）後，只重生「你指定」的那批，不必整庫重跑。
- 明確指定＝使用者已決定要做，所以**不吃** `.note_quota.json` 每日 20 筆
  （與 `worker.py` 的 note/summary 任務同一原則；channel_watcher／backfill 才計配額）。
- 產物直接覆寫 KB 內的「{stem} 摘要.md/.docx」；檔名與 H1 都沿用原本的 stem，不會產生重複條目。

用法：
  python -X utf8 regen_summaries.py --ledger-date 2026-11-07 --dry-run
  python -X utf8 regen_summaries.py --ledger-date 2026-11-07
  python -X utf8 regen_summaries.py --video-id d_zRI9C58TQ,lYaZYnsIF9k
  python -X utf8 regen_summaries.py --stem "2025-05-11_社会撕扯感" --dry-run

判讀：每支會印 `[n/N] 完成 stem（字元數）`；失敗會印 `[失敗] stem: 原因` 並繼續下一支。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
KB_ROOT = PROJECT_ROOT / "knowledge-base"
LEDGER = PROJECT_ROOT / "working" / "harvest_ledger.json"
LOG_DIR = PROJECT_ROOT / "logs"

SUFFIXES = (
    " 摘要.md", " 摘要.docx",
    " 課程筆記.md", " 課程筆記.docx",
    ".link.txt", ".srt", ".md", ".docx", ".txt",
)


def log(msg: str) -> None:
    print(msg, flush=True)


def stem_from_path(dest: str) -> str:
    name = Path(dest).name
    for suf in SUFFIXES:
        if name.endswith(suf):
            return name[: -len(suf)]
    return Path(name).stem


def stems_from_ledger(date_prefix: str) -> list[str]:
    if not LEDGER.exists():
        raise SystemExit(f"找不到帳本：{LEDGER}")
    data = json.loads(LEDGER.read_text(encoding="utf-8-sig"))
    out: list[str] = []
    seen = set()
    for _key, rec in data.items():
        if not str(rec.get("harvested_at", "")).startswith(date_prefix):
            continue
        dest = rec.get("dest") or ""
        if not dest:
            continue
        stem = stem_from_path(dest)
        if stem and stem not in seen:
            seen.add(stem)
            out.append(stem)
    return out


def stems_from_video_ids(ids: list[str], kb_dir: Path) -> list[str]:
    """用 video_id 找回 stem：掃 .link.txt（最快）與逐字稿前 60 行。"""
    want = [x.strip() for x in ids if x.strip()]
    found: dict[str, str] = {}
    for link in kb_dir.glob("*.link.txt"):
        txt = link.read_text(encoding="utf-8-sig", errors="ignore")
        for vid in want:
            if vid in txt and vid not in found:
                found[vid] = link.name[: -len(".link.txt")]
    for md in kb_dir.glob("*.md"):
        if md.stem.endswith(("課程筆記", "摘要")):
            continue
        head = "\n".join(md.read_text(encoding="utf-8-sig", errors="ignore").splitlines()[:60])
        for vid in want:
            if vid in head and vid not in found:
                found[vid] = md.stem
    missing = [v for v in want if v not in found]
    if missing:
        log(f"[警告] 這些 video_id 在 {kb_dir.name} 找不到對應條目：{', '.join(missing)}")
    return [found[v] for v in want if v in found]


def main() -> int:
    ap = argparse.ArgumentParser(description="重生指定範圍的摘要（不吃每日配額）")
    ap.add_argument("--kb-subdir", default="youtube-clips", help="KB 子目錄（預設 youtube-clips）")
    ap.add_argument("--kb", help="直接指定 KB 目錄（覆寫 --kb-subdir）")
    ap.add_argument("--ledger-date", help="用 harvest 帳本：重生該日收割的條目（YYYY-MM-DD）")
    ap.add_argument("--video-id", help="逗號分隔的 video_id（例：d_zRI9C58TQ,lYaZYnsIF9k）")
    ap.add_argument("--stem", action="append", default=[], help="直接指定條目 stem（可重複）")
    ap.add_argument("--all", action="store_true", help="整個 KB 子目錄全部重生（131 支約 15~20 分鐘）")
    ap.add_argument("--max", type=int, default=0, help="最多做幾支（0=全部，用來試跑）")
    ap.add_argument("--dry-run", action="store_true", help="只列出會處理的條目，不呼叫 Gemini、不寫檔")
    ap.add_argument("--force", action="store_true", help="連「今天已重生過」的也重做（預設跳過，避免重複燒額度）")
    args = ap.parse_args()

    kb_dir = Path(args.kb) if args.kb else (KB_ROOT / args.kb_subdir)
    if not kb_dir.is_dir():
        raise SystemExit(f"KB 目錄不存在：{kb_dir}")

    stems: list[str] = list(args.stem)
    if args.all:
        stems += [p.stem for p in sorted(kb_dir.glob("*.md"))
                  if not p.stem.endswith(("課程筆記", "摘要"))]
    if args.ledger_date:
        stems += stems_from_ledger(args.ledger_date)
    if args.video_id:
        stems += stems_from_video_ids(re.split(r"[,\s]+", args.video_id), kb_dir)

    # 去重、保序
    seen = set()
    stems = [s for s in stems if s and not (s in seen or seen.add(s))]
    if not stems:
        raise SystemExit("沒有指定任何條目（用 --ledger-date／--video-id／--stem）")

    todo = []
    skipped_today = 0
    today_mark = f"整理日期：{datetime.now().strftime('%Y-%m-%d')}"
    for stem in stems:
        src = kb_dir / f"{stem}.md"
        if not src.is_file():
            log(f"[跳過] 找不到逐字稿：{src.name}")
            continue
        old = kb_dir / f"{stem} 摘要.md"
        old_len = 0
        if old.is_file():
            try:
                old_txt = old.read_text(encoding="utf-8-sig", errors="ignore")
                old_len = len(old_txt)
                if not args.force and today_mark in old_txt:
                    skipped_today += 1
                    continue
            except Exception:
                old_len = 0
        todo.append((stem, src, old_len))

    if args.max:
        todo = todo[: args.max]

    log(f"目標 {len(todo)} 支｜KB：{kb_dir}"
        + (f"｜今天已重生略過 {skipped_today}" if skipped_today else ""))
    if args.dry_run:
        for stem, _src, old_len in todo:
            log(f"  [DRY] {stem}（現有摘要 {old_len} 字元）")
        return 0

    from make_course_note import generate_summary

    ok = fail = 0
    t0 = time.time()
    LOG_DIR.mkdir(exist_ok=True)
    for i, (stem, src, old_len) in enumerate(todo, 1):
        log(f"\n[{i}/{len(todo)}] {stem}（現有 {old_len} 字元）")
        try:
            md_out, docx_out = generate_summary(
                stem, [str(src)], kb_dir, progress=lambda m: log(f"    {m}")
            )
            new_len = len(Path(md_out).read_text(encoding="utf-8-sig", errors="ignore"))
            log(f"  ✓ 完成 {Path(md_out).name}（{old_len} → {new_len} 字元）")
            ok += 1
        except Exception as e:
            log(f"  [失敗] {stem}：{e}")
            fail += 1

    mins = (time.time() - t0) / 60
    log(f"\n執行完畢：成功 {ok}／失敗 {fail}｜耗時 {mins:.1f} 分鐘")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
