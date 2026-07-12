#!/usr/bin/env python3
"""批次處理所有沒有字幕的影片"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
RAW_DIR = ROOT / "raw"
PIPELINE = ROOT / "run_pipeline.py"

# 需要處理的影片（排除 18,20,22 即 OpenCode_EP02, EP03, EP01）
VIDEOS = [
    "EP01_用Agent學習Agent",
    "EP02_學習Agent基本觀念",
    "EP03_Agent四隻手腳",
    "EP04_MCP連接器",
    "AI_Agents教學簡報HTML",
    "AI_Agents自動化影片Hyperframes",
    "AI_Agent教學應用台語",
    "AntiGravity_EP02_極速處理檔案",
    "AntiGravity_EP03_自動化備課",
    "AntiGravity_EP04_Gems升級Skill",
    "AntiGravity_EP05_教學網頁5階段",
    "AntiGravity_EP06_GoogleClassroom",
    "AntiGravity_EP07_Padlet課程牆",
    "AntiGravity_EP08_Agent代理複製聲音",
    "Claude_EP05_GitHub倉庫",
    "GoogleAntiGravity2實測",
    "GPTcodex_EP05_Codex隱藏功能",
    "OpenCode_EP04_Agent大軍",
    "OpenCode_EP05_BigPickle",
]


def find_video(slug: str) -> Path | None:
    """找到影片檔"""
    folder = RAW_DIR / slug
    if not folder.exists():
        return None
    for ext in ["*.mp4", "*.avi", "*.mov", "*.mkv"]:
        videos = list(folder.rglob(ext))
        if videos:
            return videos[0]
    return None


def main():
    print(f"準備處理 {len(VIDEOS)} 個影片\n")

    success = 0
    fail = 0

    for i, slug in enumerate(VIDEOS, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(VIDEOS)}] {slug}")
        print(f"{'='*60}")

        video = find_video(slug)
        if not video:
            print(f"[SKIP] 找不到影片")
            fail += 1
            continue

        print(f"影片：{video}")

        cmd = [
            sys.executable,
            str(PIPELINE),
            str(video),
            "--skip-cover",  # 跳過封面，加速處理
        ]

        try:
            r = subprocess.run(cmd, timeout=1800, cwd=str(ROOT))
            if r.returncode == 0:
                print(f"[OK] {slug} 完成")
                success += 1
            else:
                print(f"[FAIL] {slug} 失敗")
                fail += 1
        except subprocess.TimeoutExpired:
            print(f"[TIMEOUT] {slug} 超時")
            fail += 1
        except Exception as e:
            print(f"[ERROR] {e}")
            fail += 1

    print(f"\n{'='*60}")
    print(f"=== 完成 ===")
    print(f"成功: {success}")
    print(f"失敗: {fail}")


if __name__ == "__main__":
    main()
