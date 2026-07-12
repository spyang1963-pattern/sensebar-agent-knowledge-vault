#!/usr/bin/env python3
"""整理 Clipping 目錄：把 .srt 檔案重新命名為跟 .md 檔案對應的名稱。"""

import re
from pathlib import Path

BASE = Path(__file__).parent
CLIPPING_DIR = BASE / "Clipping"


def extract_youtube_id(text: str) -> str | None:
    m = re.search(r'youtube\.com/watch\?v=([A-Za-z0-9_-]{11})', text)
    return m.group(1) if m else None


def main():
    # 建立 {video_id: md_path} 對應
    vid_to_md = {}
    for md in CLIPPING_DIR.rglob("*.md"):
        text = md.read_text(encoding="utf-8", errors="replace")
        vid = extract_youtube_id(text)
        if vid:
            vid_to_md[vid] = md

    # 找出所有 .srt 檔案
    srt_files = list(CLIPPING_DIR.glob("*.srt"))
    print(f"找到 {len(srt_files)} 個 .srt 檔案")
    print(f"找到 {len(vid_to_md)} 個 .md 檔案有 YouTube URL\n")

    renamed = 0
    skipped = 0

    for srt in srt_files:
        vid = srt.stem  # 例如 luRFvHW0SF8

        if vid in vid_to_md:
            md_path = vid_to_md[vid]
            new_name = md_path.with_suffix(".srt").name

            if srt.name == new_name:
                print(f"[SKIP] {srt.name} 已經是正確名稱")
                skipped += 1
                continue

            new_path = srt.parent / new_name

            # 如果目標已存在，先刪除
            if new_path.exists() and new_path != srt:
                new_path.unlink()

            srt.rename(new_path)
            print(f"[OK] {srt.name} -> {new_name}")
            renamed += 1
        else:
            print(f"[SKIP] {srt.name} 找不到對應的 .md")
            skipped += 1

    print(f"\n重新命名: {renamed}")
    print(f"跳過: {skipped}")


if __name__ == "__main__":
    main()
