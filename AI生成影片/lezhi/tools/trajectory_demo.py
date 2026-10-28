"""trajectory_demo.py - 自動移動軌跡 demo（單角色連續動作）

示範 char_trajectory.compile_path（路徑點＋段動作 → 自動過渡）＋char_modes 渲染：
  站（起點）→ 走路進場 → 坐下（盤腿＋揮手）→ 站起 → 跑步退後

輸出到 working/trajectory_demo/：關鍵影格 PNG + demo.mp4。

用法：
  python lezhi/tools/trajectory_demo.py
  python lezhi/tools/trajectory_demo.py --bg working/ai_bg3/park_1.png
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEZHI = PROJECT_ROOT / "lezhi"
WORKING = PROJECT_ROOT / "working"
sys.path.insert(0, str(LEZHI / "tools"))

import char_modes as cm          # noqa: E402
import char_trajectory as ct     # noqa: E402

_mode = cm.get(cm.DEFAULT)


def draw_frame(bg, who, x, y, r, t, mode, wave, facing, pose):
    img = Image.open(bg).convert("RGB")
    d = ImageDraw.Draw(img)
    dir = -1 if facing == "left" else 1
    if mode == "sit":
        _mode.draw_char_seated(d, who, x, y, r, dir, "flat", "normal", "closed",
                               facing=facing, wave=wave, t=t)
    else:
        _mode.draw_char_standing(d, who, x, y, r, dir, t, wave, "flat", "normal", "closed",
                                 facing=facing, pose_override=pose)
    return img


def encode(frames, out, fps):
    W, H = frames[0].size
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "20", "-pix_fmt", "yuv420p", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for f in frames:
        p.stdin.write(f.tobytes())
    p.stdin.close()
    p.wait()


def demo_path(y):
    """示範路徑：站起點 → 走路 → 坐(揮手) → 跑步退後。"""
    waypoints = [
        {"x": 60, "y": y, "pose": "stand", "hold": 0.3},
        {"x": 380, "y": y, "pose": "sit", "wave": True, "hold": 0.8},
        {"x": 60, "y": y, "pose": "stand", "hold": 0.2},
    ]
    segments = [
        {"motion": "walk", "dur": 2.0, "steps_per_sec": 2.0, "amp": 1.0, "facing": "auto"},
        {"motion": "run", "dur": 1.6, "steps_per_sec": 3.0, "amp": 1.0, "facing": "auto"},
    ]
    return ct.compile_path(waypoints, segments)


def main():
    ap = argparse.ArgumentParser(description="自動移動軌跡 demo")
    ap.add_argument("--bg", default=str(WORKING / "ai_bg3" / "park_1.png"))
    ap.add_argument("--out", default=str(WORKING / "trajectory_demo"))
    ap.add_argument("--who", default="ren")
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--r", type=int, default=55)
    ap.add_argument("--y", type=float, default=760.0)
    args = ap.parse_args()

    bg = Path(args.bg)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fps = args.fps
    r = args.r

    tr = demo_path(args.y)
    total = tr.duration()
    nframes = int(round(total * fps))

    frames = []
    for fi in range(nframes):
        t = fi / fps
        pose, x, y, mode, wave, facing = tr.sample(t)
        frames.append(draw_frame(bg, args.who, x, y, r, t, mode, wave, facing, pose))

    for label, t in [("walk", 0.75), ("sit", 2.8), ("retreat", 4.5)]:
        pose, x, y, mode, wave, facing = tr.sample(t)
        draw_frame(bg, args.who, x, y, r, t, mode, wave, facing, pose).save(out / f"frame_{label}.png")

    clip = out / "demo.mp4"
    encode(frames, clip, fps)
    print(f"done -> {clip}（{total:.1f}s, {nframes} frames @ {fps}fps）")


if __name__ == "__main__":
    main()
