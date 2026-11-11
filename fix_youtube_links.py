#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_youtube_links.py — 把 KB 條目裡的 YouTube 連結改成可點格式。

規則（AGENTS.md「重要規則 3」）：
    ✅ [YouTube](https://www.youtube.com/watch?v=VIDEO_ID)
    ❌ https://www.youtube.com/watch?v=VIDEO_ID（純文字）

做兩件事（都是純文字、不連網、可重跑）：
1. 逐字稿：`YouTube 連結：https://...` → `YouTube 連結：[YouTube](https://...)`
2. 摘要／課程筆記：完全沒有連結時，在 H1 標題後補一行 `> 原始影片：[YouTube](...)`
   （video_id 由同 stem 的 `.link.txt` 或逐字稿內文取得）

用法
----
    python -X utf8 fix_youtube_links.py --dry-run          # 只列會改哪些檔（預設）
    python -X utf8 fix_youtube_links.py --apply            # 實際寫入
    python -X utf8 fix_youtube_links.py --apply --subdir 人工智慧/AI\\ agent-三師爸/直播

結束碼 = 0（沒有失敗）；找不到 video_id 的檔案會列出來，不會亂猜。
"""
import argparse
import io
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config

PROJECT_ROOT = Path(config.PROJECT_ROOT)
KB_ROOT = PROJECT_ROOT / "knowledge-base"

VID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")
BARE_URL_RE = re.compile(
    r"(?<!\]\()https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?v=|shorts/|live/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})")
MD_LINK_RE = re.compile(r"\[YouTube\]\(https?://[^)]+\)")

SUFFIXES = (" 摘要", " 課程筆記")

# 內部作業目錄不處理（與 fix_video_links.py 排除集一致；
# _harvest_overwritten 是收割覆蓋備份，補連結只會污染備份）
EXCLUDE_DIRS = {"_harvest_conflicts", "_harvest_overwritten", "_video_links",
                "_archive_no_transcript", "_harvest_align_test"}


def log(msg):
    print(msg, flush=True)


def read(path):
    return io.open(path, encoding="utf-8", errors="replace").read()


def video_id_of(stem_dir, stem):
    """優先用 `.link.txt`（channel_watcher 產生，內容就是 URL），其次逐字稿前 60 行。"""
    link = stem_dir / f"{stem}.link.txt"
    if link.exists():
        m = VID_RE.search(read(link))
        if m:
            return m.group(1)
    md = stem_dir / f"{stem}.md"
    if md.exists():
        head = "\n".join(read(md).splitlines()[:60])
        m = VID_RE.search(head)
        if m:
            return m.group(1)
    return ""


def fix_transcript(path, vid):
    """回傳 (新內容 or None, 說明)。"""
    text = read(path)
    if MD_LINK_RE.search(text):
        return None, "已有可點連結（跳過）"
    if vid:
        new, n = BARE_URL_RE.subn(
            lambda m: f"[YouTube](https://www.youtube.com/watch?v={m.group(1)})", text)
        if n:
            return new, f"連結改為可點（{n} 處）"
        return None, "內文沒有裸連結（跳過）"
    if BARE_URL_RE.search(text):
        return None, "⚠ 有裸連結但抓不到 video_id"
    return None, "沒有連結（跳過）"


def fix_product(path, vid):
    """摘要／筆記：沒有連結就補在 H1 後面。"""
    if not vid:
        return None, "⚠ 找不到 video_id"
    text = read(path)
    if MD_LINK_RE.search(text):
        return None, "已有可點連結（跳過）"
    lines = text.splitlines(keepends=True)
    url = f"https://www.youtube.com/watch?v={vid}"
    insert_at = 0
    for i, line in enumerate(lines[:15]):
        if line.startswith("# "):
            insert_at = i + 1
            break
    block = f"\n> 原始影片：[YouTube]({url})\n"
    # 標題後若緊接既有引言區塊，讓新行併進同一區塊（不要多一個空行）
    tail = "".join(lines[insert_at:insert_at + 2])
    if tail.startswith("\n> "):
        block = f"\n> 原始影片：[YouTube]({url})"
    new = "".join(lines[:insert_at]) + block + "".join(lines[insert_at:])
    return new, "補上原始影片連結"


def iter_md(kb, subdirs):
    """yield KB 內（或指定子目錄內）所有待檢 md，遞迴、排除內部作業目錄。

    2026-11-11 修正：原本預設只掃 knowledge-base/youtube-clips 且 glob 不遞迴，
    導致 20VTA／三師爸／XQ 等其他資料夾的摘要／課程筆記從未被補過
    「原始影片」連結行（使用者回報：有網址但點不動）。預設改為全 KB 遞迴。
    """
    roots = [kb / s for s in subdirs] if subdirs else [kb]
    for root in roots:
        if not root.is_dir():
            log(f"⚠ 目錄不存在：{root}")
            continue
        for path in sorted(root.rglob("*.md")):
            try:
                rel = path.relative_to(kb)
            except ValueError:
                rel = path
            if any(part in EXCLUDE_DIRS for part in rel.parts):
                continue
            yield path


def main():
    ap = argparse.ArgumentParser(description="把 KB 的 YouTube 連結改成 [YouTube](...) 可點格式")
    ap.add_argument("--apply", action="store_true", help="實際寫入（預設只預覽）")
    ap.add_argument("--dry-run", action="store_true", help="只預覽（預設行為，保留此旗標方便沿用）")
    ap.add_argument("--kb", help="覆寫 KB 根（測試用）")
    ap.add_argument("--subdir", action="append", help="只處理指定子目錄（可重複；預設＝全 KB 遞迴）")
    args = ap.parse_args()

    kb = Path(args.kb) if args.kb else KB_ROOT
    changed, skipped, warned = [], [], []

    for path in iter_md(kb, args.subdir):
        stem = path.stem
        is_product = stem.endswith(SUFFIXES)
        base_stem = next((stem[: -len(s)] for s in SUFFIXES if stem.endswith(s)), stem)

        if is_product:
            vid = video_id_of(path.parent, base_stem)
            new, note = fix_product(path, vid)
        else:
            vid = video_id_of(path.parent, stem)
            new, note = fix_transcript(path, vid)

        if new is None:
            (warned if note.startswith("⚠") else skipped).append((path.name, note))
            continue
        changed.append((path, note))
        if args.apply:
            tmp = path.with_suffix(path.suffix + ".tmp")
            with io.open(tmp, "w", encoding="utf-8", newline="") as f:
                f.write(new)
            tmp.replace(path)

    mode = "已寫入" if args.apply else "將修改"
    log(f"{mode} {len(changed)} 檔｜跳過 {len(skipped)}｜需人工 {len(warned)}")
    for p, note in changed[:15]:
        log(f"  {p.name[:70]} ← {note}")
    if len(changed) > 15:
        log(f"  …另有 {len(changed) - 15} 檔")
    for p, note in warned[:20]:
        log(f"  ⚠ {p[:70]}：{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
