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

# 「同一天產生、但沒有版本標記」時，用來判斷它是否已是新版（v4）產出的字元門檻。
# v4 實測最短 819 字元；被誤擋的 v3 短版都 < 600。
SAME_DAY_MIN = 700


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


def looks_like_current(txt: str) -> bool:
    """沒有版本標記時，用內容特徵判斷它是否已是 v4 產出（避免白白重生）。

    只認 B 組小節（核心觀點／概念與定義／案例與例證／方法與步驟）：v3 從未產出過這些標題，
    出現 2 個以上就幾乎確定是 v4。**不看 A 組**——v3 的 A 組小節（大盤／個股…）在
    「非投資內容」也可能被硬套出來，那正是要被重生的對象，不能因此誤判成新版。
    """
    b = sum(1 for h in ("### 核心觀點", "### 概念與定義", "### 案例與例證", "### 方法與步驟")
            if h in txt)
    return b >= 2


def stamp_version(txt: str, ver: str) -> str:
    """在摘要檔頭插入 `> 摘要版本：x`（只加一行，不動內容）。"""
    line = f"> 摘要版本：{ver}"
    lines = txt.splitlines()
    if line in lines:
        return txt
    for i, ln in enumerate(lines):
        if ln.startswith("> 整理日期："):
            lines.insert(i + 1, line)
            return "\n".join(lines) + ("\n" if txt.endswith("\n") else "")
    # 找不到整理日期 → 插在第一個空行之後（H1 之後）
    for i, ln in enumerate(lines):
        if not ln.strip():
            lines.insert(i + 1, line)
            return "\n".join(lines) + ("\n" if txt.endswith("\n") else "")
    return txt + "\n" + line + "\n"


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
    ap.add_argument("--force", action="store_true", help="連「已是目前版本／今天已重生」的也重做（預設跳過，避免重複燒額度）")
    ap.add_argument("--if-shorter-than", type=int, default=0, metavar="N",
                    help="只重生現有摘要短於 N 字元的條目（缺摘要也算）。例：--if-shorter-than 600")
    ap.add_argument("--stamp-only", action="store_true",
                    help="只補 `> 摘要版本：x` 一行（不呼叫 Gemini、不改內容）。"
                         "用於「內容已是新版、但檔案是在加版本標記之前產生的」")
    ap.add_argument("--stamp-all", action="store_true",
                    help="搭配 --stamp-only：不看內容特徵，全部缺少標記的都補（已知整批都是新版時用）")
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
    skipped_same_ver = skipped_today = 0
    today_mark = f"整理日期：{datetime.now().strftime('%Y-%m-%d')}"
    try:
        from make_course_note import SUMMARY_PROMPT_VER as cur_ver
    except Exception:
        cur_ver = ""
    ver_mark = f"> 摘要版本：{cur_ver}" if cur_ver else ""
    min_len = args.if_shorter_than

    if args.stamp_only:
        if not cur_ver:
            raise SystemExit("讀不到 make_course_note.SUMMARY_PROMPT_VER，無法補標記")
        from make_course_note import build_docx

        stamped = already = skipped_old = 0
        for stem in stems:
            md = kb_dir / f"{stem} 摘要.md"
            if not md.is_file():
                continue
            txt = md.read_text(encoding="utf-8-sig", errors="ignore")
            if ver_mark in txt:
                already += 1
                continue
            if not (args.stamp_all or looks_like_current(txt)):
                skipped_old += 1
                log(f"  [略過] {stem}（看起來不是目前版本，留給實際重生）")
                continue
            if args.dry_run:
                log(f"  [DRY] 補標記 {stem}（{len(txt)} 字元）")
                stamped += 1
                continue
            new_txt = stamp_version(txt, cur_ver)
            md.write_text(new_txt, encoding="utf-8")
            try:
                build_docx(new_txt, md.with_suffix(".docx"))
            except Exception as e:
                log(f"  [警告] {stem}：docx 重建失敗（{e}），md 已補標記")
            stamped += 1
        log(f"補標記完成：{stamped} 檔｜已有標記 {already}｜看起來是舊版略過 {skipped_old}"
            + ("｜[DRY] 未寫檔" if args.dry_run else ""))
        return 0

    for stem in stems:
        src = kb_dir / f"{stem}.md"
        if not src.is_file():
            log(f"[跳過] 找不到逐字稿：{src.name}")
            continue
        old = kb_dir / f"{stem} 摘要.md"
        old_len = 0
        old_txt = ""
        if old.is_file():
            try:
                old_txt = old.read_text(encoding="utf-8-sig", errors="ignore")
                old_len = len(old_txt)
            except Exception:
                old_txt, old_len = "", 0

        if not args.force and old_txt:
            # 1) 已是目前 prompt 版本 → 跳過（最可靠；v4 起摘要會寫 `> 摘要版本：v4`）
            if ver_mark and ver_mark in old_txt:
                skipped_same_ver += 1
                continue
            # 2) 舊檔沒有版本標記（v4 上線前產生的）：
            #    同一天產生且長度已達新版水準 → 視為已是新版，不再重做
            #    （v4 實測最短 819 字元；被誤擋的 v3 短版都 <600）
            if today_mark in old_txt and old_len >= SAME_DAY_MIN:
                skipped_today += 1
                continue
            # 3) --if-shorter-than：只挑「明顯偏薄」的，已夠長的就跳過
            if min_len and old_len >= min_len:
                continue

        todo.append((stem, src, old_len))

    if args.max:
        todo = todo[: args.max]

    notes = []
    if skipped_same_ver:
        notes.append(f"已是 {cur_ver or '目前版本'} 略過 {skipped_same_ver}")
    if skipped_today:
        notes.append(f"今日已重生略過 {skipped_today}")
    if args.force:
        notes.append("--force 全部重做")
    log(f"目標 {len(todo)} 支｜KB：{kb_dir}" + ("｜" + "｜".join(notes) if notes else ""))
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
            try:
                import video_links
                video_links.normalize_file(md_out, quiet=True)
            except Exception as e:
                log(f"    [警告] 影片位置標記失敗（稍後可重跑 video_links.py）：{e}")
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
