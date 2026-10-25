"""scene_bg_gen.py - 用 Pollinations（免費）生「線稿風空景」背景

生成給 scene_dialog.py 用的 AI 背景。成功就「編號保存」不覆蓋（例如 kitchen_1.png、kitchen_2.png…）。

姿勢分類（對應 window_server 的 SCENE_POSE）：
  sit（都坐）      ：living、cafe
  sitstand（一站一坐）：kitchen、park、cafe_outdoor、office
  stand（都站）     ：site、sidewalk、park_gate、bus_stop、pavilion

用法：
  python lezhi/tools/scene_bg_gen.py --scene kitchen --out working/ai_bg3
  python lezhi/tools/scene_bg_gen.py --scene pavilion --out working/ai_bg3 --seed 123
"""
from __future__ import annotations

import argparse
import time
import urllib.parse
import urllib.request
from pathlib import Path

STYLE = ("2D flat vector cartoon illustration, simple flat solid colors, NO shading, NO gradients, "
         "NO realistic texture, NO dark shadow, uniform light floor color, bold clean black outlines, "
         "children's book cartoon style, eye-level camera angle, only a small sliver of ceiling visible "
         "at the very top, floor occupying the lower half, simple minimal flat cartoon")

NEG = "realistic, photorealistic, 3D render, shadows, gradients, detailed texture, depth, cinematic, dark floor"

# 場景關鍵詞（每個 sit / sitstand 場景都要有「可坐的椅子/長椅」，否則角色會懸空）
SCENES = {
    "living": "empty living room, two sofas facing each other across a coffee table, a window and a round wall clock on the wall, NO people, empty room",
    "cafe": "empty cafe interior, two chairs facing each other across a small round table, a counter and a menu board, a window, NO people, empty cafe",
    "kitchen": "empty kitchen interior, cabinets and a counter, a window, a stove, NO people, NO chairs, empty kitchen",
    "park": "empty park with a wooden bench and green trees, a path, blue sky, NO people, NO chairs",
    "cafe_outdoor": "outdoor cafe terrace with a small round table and a chair, a sun umbrella, NO people",
    "office": "empty office with a desk, a chair and a computer monitor, a window, NO people",
    "site": "empty construction site interior, a ladder and tools, brick wall, a caution sign, NO people, NO chairs",
    "sidewalk": "city sidewalk with a street and buildings in the background, a street lamp, NO people",
    "park_gate": "park entrance gate with a path and trees, a sign, NO people",
    "bus_stop": "bus stop shelter with a bench on a street, a road sign, NO people",
    "pavilion": "garden pavilion gazebo with a bench in a park, trees and flowers, NO people",
}


def next_num(outdir: Path, scene: str) -> int:
    nums = []
    for f in outdir.glob(f"{scene}_*.png"):
        try:
            nums.append(int(f.stem.rsplit("_", 1)[-1]))
        except Exception:
            pass
    return (max(nums) + 1) if nums else 1


def gen(outdir: Path, scene: str, seed: int) -> Path | None:
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
                n = next_num(outdir, scene)
                p = outdir / f"{scene}_{n}.png"
                p.write_bytes(data)
                return p
        except Exception as e:
            print(f"  try {attempt}: {str(e)[:60]}")
    return None


def main():
    ap = argparse.ArgumentParser(description="生場景式對話劇的 AI 背景（編號保存）")
    ap.add_argument("--out", default="working/ai_bg3")
    ap.add_argument("--scene", default="living", choices=list(SCENES))
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--list", action="store_true", help="列出可用場景")
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.list:
        print("可用場景（姿勢分類）：")
        print("  sit：", "、".join(k for k in SCENES if k in ("living", "cafe")))
        print("  sitstand：", "、".join(k for k in SCENES if k in ("kitchen", "park", "cafe_outdoor", "office")))
        print("  stand：", "、".join(k for k in SCENES if k in ("site", "sidewalk", "park_gate", "bus_stop", "pavilion")))
        return

    seed = args.seed if args.seed is not None else int(time.time()) % 100000
    print(f"gen {args.scene} ...")
    p = gen(outdir, args.scene, seed)
    if p:
        print(f"  -> {p.name} ({p.stat().st_size} bytes)")
    else:
        print("  -> 失敗")
    print("done ->", outdir)


if __name__ == "__main__":
    main()
