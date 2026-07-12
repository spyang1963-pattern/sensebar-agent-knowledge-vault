#!/usr/bin/env python3
"""下載沒有字幕的影片（用 yt-dlp）"""

import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
RAW_DIR = BASE / "raw"

VIDEOS = [
    ("gm1ln1Z0hHo", "EP02_學習Agent基本觀念"),
    ("yShlwYrZxzg", "EP03_Agent四隻手腳"),
    ("eV0BTIIwpuk", "AI_Agents教學簡報HTML"),
    ("EH8QG6S4mJY", "AI_Agents自動化影片Hyperframes"),
    ("4agikgWGpPw", "EP04_MCP連接器"),
    ("11ROttp_5zk", "AI_Agent教學應用台語"),
    ("8QzfB8_LcH0", "EP01_用Agent學習Agent"),
    ("agQOf09rXlk", "AntiGravity_EP02_極速處理檔案"),
    ("wH2tXQY5MOU", "AntiGravity_EP03_自動化備課"),
    ("NpBfe9LfEUA", "AntiGravity_EP04_Gems升級Skill"),
    ("8INcIHIYnMA", "AntiGravity_EP05_教學網頁5階段"),
    ("QOsWBcs1RAQ", "AntiGravity_EP06_GoogleClassroom"),
    ("pI2nitfc8Tg", "AntiGravity_EP07_Padlet課程牆"),
    ("5jj4W5XU3nw", "AntiGravity_EP08_Agent代理複製聲音"),
    ("EKJ832yOLLw", "Claude_EP05_GitHub倉庫"),
    ("hBEXshEnWRY", "GoogleAntiGravity2實測"),
    ("alb9Bq2PhOk", "GPTcodex_EP05_Codex隱藏功能"),
    ("tiWSQNaunwg", "OpenCode_EP02_最強AI Agents"),
    ("kOZUNSvyrgU", "OpenCode_EP04_Agent大軍"),
    ("VccxnWOeDDo", "OpenCode_EP03_OpencodeGo"),
    ("cXp0Cj3u7jE", "OpenCode_EP05_BigPickle"),
    ("lB7Pl8Dl_Rw", "OpenCode_EP01_用一句話學AI Agent"),
]


def download_video(vid: str, name: str) -> bool:
    out_dir = RAW_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(out_dir / "原始.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f", "worst[ext=mp4]/worst",
        "--no-check-certificates",
        "--geo-bypass",
        "-o", out_template,
        f"https://www.youtube.com/watch?v={vid}",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return result.returncode == 0


def main():
    print(f"準備下載 {len(VIDEOS)} 個影片\n")

    success = 0
    fail = 0

    for i, (vid, name) in enumerate(VIDEOS, 1):
        print(f"[{i}/{len(VIDEOS)}] {name} ({vid})")
        try:
            ok = download_video(vid, name)
            if ok:
                print(f"  [OK] 下載成功\n")
                success += 1
            else:
                print(f"  [FAIL] 下載失敗\n")
                fail += 1
        except subprocess.TimeoutExpired:
            print(f"  [TIMEOUT] 超時\n")
            fail += 1
        except Exception as e:
            print(f"  [ERROR] {e}\n")
            fail += 1

    print(f"\n=== 完成 ===")
    print(f"成功: {success}")
    print(f"失敗: {fail}")


if __name__ == "__main__":
    main()
