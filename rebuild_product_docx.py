#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rebuild_product_docx.py — 從既有產品 md 重建 docx（md 的 [文字](url) → docx 真超連結）。

背景（2026-11-11）：`make_course_note.build_docx` 在 2026-11-11 前不支援超連結，
舊產品 docx 內的 YouTube 連結是純文字、點不動（md 有行、docx 跟不上的缺口）。
本工具掃 KB 的「 摘要.md／課程筆記.md」，從對應 md 重建同名 docx。

- 樣板＝worker 同款林教授樣板；該檔不存在時退回 python-docx 預設格式
  （與 worker 在無樣板機器的行為一致，產出機 KB 從零開始時就是這樣）。
- 只重建「已有 docx」的產品，不會無中生有。
- 重建後自我驗證：md 有「> 原始影片：[YouTube](」的產品，docx 必須有
  指向 youtube.com 的 w:hyperlink；缺的會列成 ✗（結尾統計應為 0）。
- 冪等可重跑；純本機動作，不連網、不花 Gemini／Groq 額度。

用法：
    python -X utf8 rebuild_product_docx.py --dry-run              # 只列會重建哪些
    python -X utf8 rebuild_product_docx.py                       # 實際重建＋自我驗證
    python -X utf8 rebuild_product_docx.py --subdir "20VTA 頻道"  # 限縮子目錄（可重複）
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from make_course_note import build_docx  # noqa: E402

KB = ROOT / "knowledge-base"

# 內部作業目錄不處理（與 fix_youtube_links.py / fix_video_links.py 排除集一致）
EXCLUDE_DIRS = {"_harvest_conflicts", "_harvest_overwritten", "_video_links",
                "_archive_no_transcript", "_harvest_align_test"}

SUFFIXES = (" 摘要.md", " 課程筆記.md")

# 與 worker.DEFAULT_NOTE_TEMPLATE 同路徑（不 import worker——模組層級會建 TaskQueue）
DEFAULT_TEMPLATE = KB / "金融交易" / "理周學院" / "林教授" / "_preview_林教授 量價時間角度的三道菜 課程筆記.docx"


def iter_products(kb: Path, subdirs):
    roots = [kb / s for s in subdirs] if subdirs else [kb]
    for root in roots:
        if not root.is_dir():
            print(f"⚠ 目錄不存在：{root}")
            continue
        for p in sorted(root.rglob("*.md")):
            try:
                rel = p.relative_to(kb)
            except ValueError:
                rel = p
            if any(part in EXCLUDE_DIRS for part in rel.parts):
                continue
            if not any(p.name.endswith(s) for s in SUFFIXES):
                continue
            docx = p.with_suffix(".docx")
            if not docx.exists():
                continue
            yield p, docx


def docx_youtube_link_count(path: Path) -> int:
    """數 docx 內指向 youtube.com 的真超連結數（驗收用）。"""
    from docx import Document
    from docx.oxml.ns import qn
    doc = Document(str(path))
    n = 0
    for para in doc.paragraphs:
        for hl in para._p.findall(qn("w:hyperlink")):
            rid = hl.get(qn("r:id"))
            if rid in doc.part.rels and "youtube.com" in doc.part.rels[rid].target_ref:
                n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description="從產品 md 重建 docx（補真超連結）")
    ap.add_argument("--dry-run", action="store_true", help="只列出會重建哪些，不寫檔")
    ap.add_argument("--subdir", action="append", default=[],
                    help="只處理 KB 內指定子目錄（可重複；預設全 KB）")
    ap.add_argument("--template", type=Path, default=None,
                    help="docx 樣板（預設＝worker 同款；不存在自動退回預設格式）")
    args = ap.parse_args()

    template = args.template or DEFAULT_TEMPLATE
    template = Path(template) if Path(template).exists() else None
    if template is None:
        print("（找不到樣板，用 python-docx 預設格式——與 worker 無樣板機器的行為一致）")

    rows = list(iter_products(KB, args.subdir))
    if args.dry_run:
        for md, _ in rows:
            print(f"  [DRY] {md.relative_to(KB)}")
        print(f"將重建 {len(rows)} 個 docx（不寫檔）")
        return 0

    t0 = time.time()
    done = failed = no_link = 0
    bad = []
    for md, docx in rows:
        rel = md.relative_to(KB)
        try:
            md_text = md.read_text(encoding="utf-8", errors="replace")
            build_docx(md_text, docx, template=template)
            done += 1
            # 自我驗證：md 有原始影片行 → docx 必須有 youtube 超連結
            if "> 原始影片：[YouTube](" in md_text:
                if docx_youtube_link_count(docx) < 1:
                    bad.append(str(rel))
        except Exception as e:
            failed += 1
            print(f"  ✗ {rel}：{e}")
        if "> 原始影片：[YouTube](" not in md_text:
            no_link += 1
    print(f"重建 {done}｜失敗 {failed}｜樣板 {'有' if template else '無（預設格式）'}｜"
          f"md無原始影片行（來源無URL，正常）{no_link}｜耗時 {time.time() - t0:.0f}s")
    if bad:
        print(f"✗ {len(bad)} 個 docx 重建後仍缺 YouTube 超連結（不應發生）：")
        for b in bad[:15]:
            print(f"    {b}")
        return 1
    print("自我驗證：md 有原始影片行的產品，docx 全部含 YouTube 超連結 [OK]")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
