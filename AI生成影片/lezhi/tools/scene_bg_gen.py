"""scene_bg_gen.py - 用 Pollinations（免費）生「線稿風空景」背景

生成給 scene_dialog.py 用的 AI 背景（空景客廳，無人物）。畫風配合程式角色
（乾淨線條＋平塗）。Pollinations 免費層解析度上限約 576×1024（要求更高也只回這個）。

用法：
  python lezhi/tools/scene_bg_gen.py --out working/ai_bg --scene "cafe" --seed 11
"""
from __future__ import annotations

import argparse
import time
import urllib.parse
import urllib.request
from pathlib import Path

STYLE = ("2D flat vector cartoon illustration, simple flat solid colors, NO shading, NO gradients, "
         "NO realistic texture, bold clean black outlines, children's book cartoon style, "
         "simple minimal flat cartoon")

NEG = "realistic, photorealistic, 3D render, shadows, gradients, detailed texture, depth, cinematic"

# 場景關鍵詞（客廳 / 咖啡廳 / 工地 / 廚房…）
SCENES = {
    "living": "empty living room, two sofas facing each other across a coffee table, a window and a round wall clock on the wall, NO people, empty room",
    "cafe": "empty cafe interior, a small round table and two chairs, a counter and a menu board, a window, NO people, empty cafe",
    "kitchen": "empty kitchen interior, cabinets and a counter, a window, a stove, NO people, empty kitchen",
    "site": "empty construction site interior, a ladder and tools, brick wall, a caution sign, NO people, empty room",
}


def gen(outdir: Path, scene: str, seed: int, idx: str):
    desc = SCENES.get(scene, SCENES["living"])
    full = f"{desc}, {STYLE}, avoid {NEG}"
    enc = urllib.parse.quote(full)
    url = f"https://image.pollinations.ai/prompt/{enc}?width=1080&height=1920&model=flux&nologo=true&seed={seed}"
    for attempt, wait in enumerate([0, 8, 15, 25]):
        if wait:
            time.sleep(wait)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "lezhi-bg/1.0"})
            data = urllib.request.urlopen(req, timeout=240).read()
            if len(data) > 8000:
                p = outdir / f"{idx}.png"
                p.write_bytes(data)
                return len(data)
        except Exception as e:
            print(f"  {idx} try {attempt}: {str(e)[:50]}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="生場景式對話劇的 AI 背景")
    ap.add_argument("--out", default="working/ai_bg")
    ap.add_argument("--scene", default="living", choices=list(SCENES))
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--tag", default="bg")
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    idx = f"{args.tag}_{args.scene}"
    print(f"gen {idx} ...")
    size = gen(outdir, args.scene, args.seed, idx)
    print(f"  -> {size} bytes")
    print("done ->", outdir)


if __name__ == "__main__":
    main()
