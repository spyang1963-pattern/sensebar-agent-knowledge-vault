#!/usr/bin/env python3
"""
從 Clipping 目錄的 .md 逐字稿建立 SRT 字幕檔。
使用估計時間碼（每秒約 4 個中文字）。
"""

import os
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent
CLIPPING_DIR = BASE / "Clipping"
KB_DIR = BASE / "knowledge-base" / "youtube-clips"

CHARS_PER_SEC = 4  # 每秒約 4 個中文字
MAX_CHARS_PER_SUB = 30  # 每段字幕最多字數
PAUSE_BETWEEN_SUBS = 0.3  # 段落間停頓秒數


def format_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def split_text_to_subs(text: str) -> list[str]:
    """將文字拆成適合字幕的段落"""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    subs = []
    for line in lines:
        if len(line) <= MAX_CHARS_PER_SUB:
            subs.append(line)
        else:
            # 按逗號或句號分割長句
            parts = re.split(r'([，、。！？])', line)
            current = ""
            for p in parts:
                if len(current) + len(p) <= MAX_CHARS_PER_SUB:
                    current += p
                else:
                    if current:
                        subs.append(current)
                    current = p
            if current:
                subs.append(current)
    return subs


def md_to_srt(md_path: Path) -> str | None:
    """將 .md 逐字稿轉換為 SRT 格式"""
    text = md_path.read_text(encoding="utf-8", errors="replace")

    # 找到 --- 分隔線後的逐字稿內容
    parts = text.split("---", 1)
    if len(parts) < 2:
        return None
    transcript = parts[1].strip()
    if not transcript:
        return None

    subs = split_text_to_subs(transcript)
    if not subs:
        return None

    srt_lines = []
    current_time = 0.0

    for i, sub_text in enumerate(subs, 1):
        duration = len(sub_text) / CHARS_PER_SEC
        start = format_time(current_time)
        end = format_time(current_time + duration)
        srt_lines.append(f"{i}")
        srt_lines.append(f"{start} --> {end}")
        srt_lines.append(sub_text)
        srt_lines.append("")
        current_time += duration + PAUSE_BETWEEN_SUBS

    return "\n".join(srt_lines)


def extract_youtube_id(text: str) -> str | None:
    m = re.search(r'youtube\.com/watch\?v=([A-Za-z0-9_-]{11})', text)
    return m.group(1) if m else None


def main():
    KB_DIR.mkdir(parents=True, exist_ok=True)

    md_files = list(CLIPPING_DIR.rglob("*.md"))
    print(f"找到 {len(md_files)} 個 clipping 檔案\n")

    success = 0
    skip = 0
    fail = 0

    for md in sorted(md_files):
        rel = md.relative_to(CLIPPING_DIR)
        text = md.read_text(encoding="utf-8", errors="replace")
        vid = extract_youtube_id(text)
        if not vid:
            print(f"[SKIP] {rel.name} - 無 YouTube URL")
            skip += 1
            continue

        # 檢查是否已有 SRT
        existing = list(KB_DIR.glob(f"{vid}.srt"))
        if existing:
            print(f"[SKIP] {rel.name} - 已有 SRT")
            skip += 1
            continue

        srt_content = md_to_srt(md)
        if not srt_content:
            print(f"[FAIL] {rel.name} - 無逐字稿內容")
            fail += 1
            continue

        # 建立子目錄
        category = rel.parent.name if rel.parent != Path(".") else "misc"
        cat_dir = KB_DIR / category
        cat_dir.mkdir(parents=True, exist_ok=True)

        srt_path = cat_dir / f"{vid}.srt"
        srt_path.write_text(srt_content, encoding="utf-8")

        # 同時複製一份到根目錄方便查找
        srt_root = KB_DIR / f"{vid}.srt"
        srt_root.write_text(srt_content, encoding="utf-8")

        print(f"[OK] {rel.name} -> {srt_path.relative_to(BASE)}")
        success += 1

    print(f"\n=== 完成 ===")
    print(f"成功: {success}")
    print(f"跳過: {skip}")
    print(f"失敗: {fail}")


if __name__ == "__main__":
    main()
