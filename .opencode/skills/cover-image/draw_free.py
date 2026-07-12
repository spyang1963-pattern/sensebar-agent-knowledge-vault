#!/usr/bin/env python3
"""免費封面圖生成（Pollinations.AI）— 無需 API Key。

用法：
  python draw_free.py "手繪風格的 AI 教學封面"
  python draw_free.py "科技教學" --width 1280 --height 720 --name cover
"""
import argparse
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime


def main():
    ap = argparse.ArgumentParser(description="免費封面圖生成（Pollinations.AI，無需 API Key）")
    ap.add_argument("prompt", nargs="+", help="要畫的內容描述")
    ap.add_argument("--width", type=int, default=1280, help="圖片寬度，預設 1280")
    ap.add_argument("--height", type=int, default=720, help="圖片高度，預設 720")
    ap.add_argument("--name", default="cover", help="檔名前綴")
    ap.add_argument("--outdir", default=".", help="輸出目錄")
    ap.add_argument("--model", default="flux", help="模型：flux（預設）/ turbo")
    ap.add_argument("--seed", type=int, default=None, help="隨機種子（固定種子可重複生成）")
    args = ap.parse_args()

    prompt = " ".join(args.prompt)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={args.width}&height={args.height}&model={args.model}"
    if args.seed is not None:
        url += f"&seed={args.seed}"

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = outdir / f"{args.name}_{stamp}.png"

    print(f"[INFO] 正在生成圖片...")
    print(f"[INFO] Prompt: {prompt}")
    print(f"[INFO] 尺寸: {args.width}x{args.height}")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cover-image-free/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        out_path.write_bytes(data)
        size_kb = len(data) / 1024
        print(f"[OK] 輸出 {out_path}（{size_kb:.0f} KB）")
    except Exception as e:
        print(f"[ERR] 生成失敗：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
