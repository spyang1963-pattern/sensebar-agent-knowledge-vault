#!/usr/bin/env python3
"""同步 Clipping 目錄：重新配對 .md/.srt 並同步到 knowledge-base。"""

import re
import shutil
from pathlib import Path

BASE = Path(__file__).parent
CLIPPING = BASE / "Clipping"
KB = BASE / "knowledge-base" / "youtube-clips"

YOUTUBE_RE = re.compile(r"youtube\.com/watch\?v=([A-Za-z0-9_-]{11})")


def extract_youtube_id_from_md(text: str) -> str | None:
    m = YOUTUBE_RE.search(text)
    return m.group(1) if m else None


def extract_youtube_id_from_srt(text: str) -> str | None:
    m = YOUTUBE_RE.search(text)
    return m.group(1) if m else None


def main():
    # 1. 建立 VID -> md 對應
    vid_to_md = {}
    for md in CLIPPING.glob("*.md"):
        text = md.read_text(encoding="utf-8", errors="replace")
        vid = extract_youtube_id_from_md(text)
        if vid:
            vid_to_md[vid] = md

    # 2. 建立 VID -> srt 對應（從 SRT 內容找 VID）
    vid_to_srt = {}
    for srt in CLIPPING.glob("*.srt"):
        text = srt.read_text(encoding="utf-8", errors="replace")
        vid = extract_youtube_id_from_srt(text)
        if vid:
            vid_to_srt[vid] = srt
        elif srt.stem.isascii() and len(srt.stem) == 11:
            # 舊格式：檔名就是 VID
            vid_to_srt[srt.stem] = srt

    # 3. 用 VID 重新配對
    renamed = 0
    for vid, md in vid_to_md.items():
        correct_srt = md.with_suffix(".srt")
        if correct_srt.exists():
            continue

        if vid in vid_to_srt:
            old_srt = vid_to_srt[vid]
            if old_srt != correct_srt:
                old_srt.rename(correct_srt)
                print(f"[RENAME] {old_srt.name} -> {correct_srt.name}")
                renamed += 1

    # 4. 同步到 knowledge-base
    KB.mkdir(parents=True, exist_ok=True)
    for f in KB.glob("*.srt"):
        f.unlink()

    copied = 0
    for srt in CLIPPING.glob("*.srt"):
        shutil.copy2(srt, KB / srt.name)
        copied += 1

    # 5. 報告未配對
    unpaired = [m for m in CLIPPING.glob("*.md") if not m.with_suffix(".srt").exists()]

    print(f"\n配對修正: {renamed}")
    print(f"同步到 knowledge-base: {copied} 個 SRT")
    if unpaired:
        print(f"未配對 .md: {len(unpaired)}")
        for m in unpaired:
            print(f"  {m.name}")


if __name__ == "__main__":
    main()
