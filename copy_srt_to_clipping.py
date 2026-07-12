#!/usr/bin/env python3
"""把 SRT 檔案複製到 Clipping 目錄下對應的位置，讓 Obsidian 能看到。"""

import shutil
from pathlib import Path

BASE = Path(__file__).parent
KB_DIR = BASE / "knowledge-base" / "youtube-clips"
CLIPPING_DIR = BASE / "Clipping"


def main():
    srt_files = list(KB_DIR.glob("*.srt"))
    print(f"找到 {len(srt_files)} 個 SRT 檔案\n")

    copied = 0
    for srt in srt_files:
        vid_id = srt.stem  # 例如 luRFvHW0SF8

        # 找對應的 .md 檔案
        for md in CLIPPING_DIR.rglob("*.md"):
            content = md.read_text(encoding="utf-8", errors="replace")
            if vid_id in content:
                # 複製到 .md 同目錄
                target = md.parent / f"{vid_id}.srt"
                if not target.exists():
                    shutil.copy2(srt, target)
                    print(f"[OK] {md.parent.name}/{vid_id}.srt")
                    copied += 1
                break

    print(f"\n複製了 {copied} 個 SRT 檔案到 Clipping 目錄")


if __name__ == "__main__":
    main()
