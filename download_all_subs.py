#!/usr/bin/env python3
"""從 Clipping 目錄的所有 .md 檔案中提取 YouTube URL，下載字幕到 knowledge-base。"""

import os
import re
import subprocess
import sys
import json
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent
CLIPPING_DIR = BASE / "Clipping"
KB_DIR = BASE / "knowledge-base"
WORKING_DIR = BASE / "working"

def extract_youtube_id(url: str) -> str | None:
    m = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})', url)
    return m.group(1) if m else None

def scan_clippings():
    """回傳 {video_id: [(md_path, title), ...]}"""
    videos = defaultdict(list)
    for md in CLIPPING_DIR.rglob("*.md"):
        text = md.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            m = re.search(r'(https?://(?:www\.)?youtube\.com/watch\?v=[A-Za-z0-9_-]+|https?://youtu\.be/[A-Za-z0-9_-]+)', line)
            if m:
                vid = extract_youtube_id(m.group(0))
                if vid:
                    title = md.stem
                    videos[vid].append((md, title))
                break
    return videos

def check_existing_srt(video_id: str) -> bool:
    """檢查是否已有字幕"""
    for sub_dir in [KB_DIR, WORKING_DIR]:
        for srt in sub_dir.rglob(f"*{video_id}*.srt"):
            return True
    return False

def download_subtitle(video_id: str, title: str, out_dir: Path) -> bool:
    """用 yt-dlp 下載字幕"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(out_dir / f"{video_id}_%(lang)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--write-auto-sub",
        "--write-sub",
        "--sub-lang", "zh-Hant,zh-TW,zh,zh-Hans,en",
        "--sub-format", "srt",
        "--skip-download",
        "-o", out_template,
        "--no-overwrites",
        "--ignore-errors",
        url
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result.returncode == 0

def find_downloaded_srt(video_id: str, out_dir: Path) -> Path | None:
    """找到下載的 SRT"""
    for srt in out_dir.glob(f"{video_id}_*.srt"):
        return srt
    return None

def organize_srt(srt_path: Path, video_id: str, titles: list) -> bool:
    """將 SRT 放到 knowledge-base 對應目錄"""
    kb_sub = KB_DIR / "youtube-subs"
    kb_sub.mkdir(parents=True, exist_ok=True)

    target = kb_sub / f"{video_id}.srt"
    if target.exists():
        print(f"  [SKIP] 已存在: {target.name}")
        return True

    import shutil
    shutil.copy2(srt_path, target)
    print(f"  [OK] {target.name}")

    # 寫入對應的 md 資訊
    info_path = kb_sub / f"{video_id}_info.md"
    lines = [f"# {video_id}\n"]
    lines.append(f"\n## 影片連結\nhttps://www.youtube.com/watch?v={video_id}\n")
    lines.append(f"\n## 關聯 Clipping\n")
    for md_path, t in titles:
        lines.append(f"- [{t}]({md_path.relative_to(BASE)})\n")
    info_path.write_text("".join(lines), encoding="utf-8")
    return True

def main():
    print("=== 掃描 Clipping 目錄 ===")
    videos = scan_clippings()
    print(f"找到 {len(videos)} 個不重複的 YouTube 影片\n")

    need_download = []
    has_sub = 0
    for vid, titles in sorted(videos.items()):
        if check_existing_srt(vid):
            has_sub += 1
            continue
        need_download.append((vid, titles))

    print(f"已有字幕: {has_sub}")
    print(f"需要下載: {len(need_download)}\n")

    if not need_download:
        print("所有影片都已有字幕！")
        return

    temp_dir = WORKING_DIR / "yt-subs-temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    success = 0
    fail = 0
    skip = 0

    for i, (vid, titles) in enumerate(need_download, 1):
        title_short = titles[0][1][:60]
        print(f"[{i}/{len(need_download)}] {title_short}...")
        print(f"  Video ID: {vid}")

        try:
            ok = download_subtitle(vid, titles[0][1], temp_dir)
            srt = find_downloaded_srt(vid, temp_dir) if ok else None

            if srt:
                organize_srt(srt, vid, titles)
                success += 1
            else:
                print(f"  [WARN] 無可用字幕")
                skip += 1
        except subprocess.TimeoutExpired:
            print(f"  [ERROR] 超時")
            fail += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            fail += 1

    print(f"\n=== 完成 ===")
    print(f"成功: {success}")
    print(f"無字幕: {skip}")
    print(f"失敗: {fail}")

if __name__ == "__main__":
    main()
