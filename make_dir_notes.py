# -*- coding: utf-8 -*-
"""Directory-walk wrapper for make_course_note.py.

Collects all *.md under --dir, dedupes by basename (keeps shallowest path),
sorts by path, then produces one course note (md + docx) in --out.

Usage:
  python make_dir_notes.py --title "海龍王 教學文 2018-8月-1" --dir <folder> --out <dir> --template <docx>
"""
import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_course_note as mcn


def _shallow(p):
    return p.relative_to(p.anchor).as_posix().count("/")


def _date_range(stem: str) -> str | None:
    """從教學文檔名解析日期範圍（首日 ~ 尾日，跨日合輯檔顯示範圍）。

    支援：
      * 一般檔：  2018-10-01------...
      * 合輯長檔：2018-12  06___12-28(有字幕)、2019-03  04___03-18(有字幕)、
                  2018-07-30___2018-08-15(有字幕)
    """
    m = re.search(r"(\d{4})-(\d{2})\s*-?\s*(\d{2})", stem)
    if not m:
        return None
    first = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    tail = stem.split("___", 1)[1] if "___" in stem else None
    if tail:
        m2 = re.search(r"(\d{4}-\d{2}-\d{2}|\d{2}-\d{2})", tail)
        if m2:
            second = m2.group(1)
            if len(second) == 5:  # MM-DD → 補年份
                second = f"{m.group(1)}-{second}"
            return f"{first} ~ {second}"
    return first


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("."))
    ap.add_argument("--template", type=Path, default=None)
    ap.add_argument("--date-heading", action="store_true",
                    help="章節標題加上教學日期（從檔名解析，支援跨日合輯範圍）")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", args.title)

    # collect + dedupe by basename keeping shallowest
    seen = {}
    for dp, _dn, fn in os.walk(args.dir):
        for f in sorted(fn):
            if not f.lower().endswith(".md"):
                continue
            p = Path(dp) / f
            if "錄製_" in f:
                continue
            d = _shallow(p)
            if f not in seen or d < seen[f][1]:
                seen[f] = (p, d)
    md_sources = [v[0] for v in sorted(seen.values(), key=lambda x: x[1])]
    if not md_sources:
        print("no md found"); return

    for i, p in enumerate(md_sources):
        print(f"[src {i+1}/{len(md_sources)}] {p}")
    print(f"--- total {len(md_sources)} files ---")

    api_key = mcn.load_gemini_key()
    parts_dir = mcn.ROOT / "working" / "_note_parts" / "dir" / safe_title
    parts_dir.mkdir(parents=True, exist_ok=True)

    chapters = []
    for i, mdp in enumerate(md_sources):
        p = Path(mdp)
        base = p.parent.name or p.stem
        date_tag = "　【" + _date_range(p.stem) + "】" if (args.date_heading and _date_range(p.stem)) else ""
        part = parts_dir / f"{i:02d}-{p.stem[:24]}.md"
        if part.exists():
            data = part.read_text(encoding="utf-8").split("\n", 1)
            note = data[1] if len(data) > 1 else data[0]
            chapters.append((base, note, date_tag))
            print(f"[{i+1}/{len(md_sources)}] 載入暫存 → {base}{date_tag}")
            continue
        print(f"[{i+1}/{len(md_sources)}] 整理 → {base}{date_tag} ...")
        raw = p.read_text(encoding="utf-8", errors="replace")
        body = mcn.strip_meta(raw)
        note = mcn.gemini_note(body, api_key)
        part.write_text(base + "\n" + note, encoding="utf-8")
        chapters.append((base, note, date_tag))
        print(f"        . 完成（{len(note):,} 字元）")

    lines = [f"# {args.title}", ""]
    lines.append("> 課程筆記（整理自課堂逐字稿，依時間順序）。")
    lines.append(f"> 整理日期：{datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")
    for base, md, date_tag in chapters:
        hdr = "## " + base.strip() if not base.startswith("##") else base
        hdr = hdr + date_tag
        lines.append(hdr)
        lines.append("")
        lines.append(md.strip())
        lines.append("")

    md_text = "\n".join(lines)
    md_out = args.out / f"{safe_title} 課程筆記.md"
    md_out.write_text(md_text, encoding="utf-8")
    print(f"[OK] {md_out}")

    docx_out = md_out.with_suffix(".docx")
    mcn.build_docx(md_text, docx_out, template=args.template)
    print(f"[OK] {docx_out}")


if __name__ == "__main__":
    main()