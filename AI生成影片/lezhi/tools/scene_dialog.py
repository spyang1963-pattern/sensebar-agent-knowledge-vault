"""scene_dialog.py - 場景式對話劇（融合版，定案）

AI 生背景（空間感）＋ 程式畫怪奇角色（特點）＋ 程式合成/動態：
  - 角色：盤腿坐側身，阿忍（大眼鏡＋黑髮）、小樂（紅帽＋棕髮）
  - 表情：眨眼＋說話張嘴＋喜怒哀樂（側臉單眼）
  - 真實對嘴：TTS 音量包絡驅動嘴型三階（closed/half/open）
  - 進場：走路→揮手→盤腿坐下
  - 字幕：程式畫（固定置底、含說話者名字）

完整開發紀錄見：AI生成影片/場景對話劇開發紀錄.md

用法：
  python lezhi/tools/scene_dialog.py --bg working/ai_bg3/hi_a.png --out working/scene_demo
"""
from __future__ import annotations

import argparse
import asyncio
import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[2]   # ...\AI生成影片
WORKSPACE = PROJECT_ROOT.parent                      # ...\AI-Agent-Workspace
LEZHI = PROJECT_ROOT / "lezhi"
sys.path.insert(0, str(WORKSPACE))                    # make_short.py
sys.path.insert(0, str(LEZHI / "tools"))              # make_dialog / make_comic

import make_dialog as md  # noqa: E402
import make_short as ms   # noqa: E402
import make_comic as mc   # noqa: E402

INK = (21, 26, 27)
SKIN = (247, 219, 196)
REN = {"hair": (38, 42, 45), "top": (117, 137, 133), "pants": (58, 62, 68), "glasses": True, "cap": False}
LE = {"hair": (94, 66, 51), "top": (224, 158, 106), "pants": (70, 82, 96), "glasses": False, "cap": True}
NAME = {"ren": "阿忍", "le": "小樂"}

FONT = r"C:\Windows\Fonts\msjh.ttc"
FONTB = r"C:\Windows\Fonts\msjhbd.ttc"


def draw_head(d, who, sx, sy, r, dir, brow, eye, mouth):
    """頭＋髮（chord 只蓋頭頂 1/5）＋側臉五官（單眼/鼻/嘴）。"""
    c = REN if who == "ren" else LE
    d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=SKIN, outline=INK, width=5)
    d.chord([sx - r - 2, sy - r - 2, sx + r + 2, sy + r + 2], 217, 323, fill=c["hair"], outline=INK, width=5)
    if c["cap"]:
        d.rounded_rectangle([sx - int(r * 0.85), sy - r + 2, sx + int(r * 0.5), sy - r + int(r * 0.42)],
                            radius=10, fill=(196, 92, 82), outline=INK, width=4)
    eye_x = sx + dir * int(r * 0.42)
    ey = sy + int(r * 0.12)
    if eye == "blink":
        d.line([(eye_x - int(r * 0.26), ey), (eye_x + int(r * 0.26), ey)], fill=INK, width=5)
    elif eye == "wide":
        d.ellipse([eye_x - int(r * 0.28), ey - int(r * 0.24), eye_x + int(r * 0.28), ey + int(r * 0.24)],
                  fill=(255, 255, 255), outline=INK, width=4)
        d.ellipse([eye_x - int(r * 0.1), ey - int(r * 0.08), eye_x + int(r * 0.1), ey + int(r * 0.12)], fill=INK)
    else:
        d.ellipse([eye_x - int(r * 0.17), ey - int(r * 0.17), eye_x + int(r * 0.17), ey + int(r * 0.17)], fill=INK)
    by = ey - int(r * 0.42)
    if brow == "up":
        d.line([(eye_x - int(r * 0.26), by - int(r * 0.1)), (eye_x + int(r * 0.26), by - int(r * 0.32))], fill=INK, width=5)
    elif brow == "in":
        d.line([(eye_x - int(r * 0.26), by - int(r * 0.32)), (eye_x + int(r * 0.26), by - int(r * 0.1))], fill=INK, width=5)
    else:
        d.line([(eye_x - int(r * 0.26), by), (eye_x + int(r * 0.26), by)], fill=INK, width=5)
    d.ellipse([sx + dir * int(r * 0.72) - int(r * 0.13), sy + int(r * 0.12) - int(r * 0.13),
               sx + dir * int(r * 0.72) + int(r * 0.13), sy + int(r * 0.12) + int(r * 0.13)],
              fill=SKIN, outline=INK, width=4)
    my = sy + int(r * 0.5)
    mx = sx + dir * int(r * 0.4)
    if mouth == "open":
        d.ellipse([mx - int(r * 0.14), my - int(r * 0.06), mx + int(r * 0.18), my + int(r * 0.26)],
                  fill=(122, 60, 60), outline=INK, width=4)
    elif mouth == "half":
        d.ellipse([mx - int(r * 0.1), my - int(r * 0.03), mx + int(r * 0.14), my + int(r * 0.14)],
                  fill=(122, 60, 60), outline=INK, width=4)
    else:
        d.line([(sx + dir * int(r * 0.24), my), (sx + dir * int(r * 0.62), my)], fill=INK, width=5)
    if c["glasses"]:
        d.ellipse([eye_x - int(r * 0.34), ey - int(r * 0.44), eye_x + int(r * 0.34), ey + int(r * 0.2)],
                  outline=INK, width=4)
        d.line([(eye_x - int(r * 0.34), ey - int(r * 0.12)), (sx - dir * int(r * 0.45), ey - int(r * 0.12))],
               fill=INK, width=4)


def draw_char_seated(d, who, sx, sy, r, dir, brow, eye, mouth):
    """盤腿坐側身（下半身單一形狀，無交接線）。"""
    c = REN if who == "ren" else LE
    hip_back = sx - dir * int(r * 0.9)
    hip_front = sx + dir * int(r * 1.6)
    hx0, hx1 = min(hip_back, hip_front), max(hip_back, hip_front)
    d.rounded_rectangle([hx0, sy + int(r * 2.2), hx1, sy + int(r * 3.3)], radius=int(r * 0.55),
                        fill=c["pants"], outline=INK, width=4)
    foot_x = sx + dir * int(r * 1.4)
    d.ellipse([foot_x - int(r * 0.3), sy + int(r * 2.6), foot_x + int(r * 0.3), sy + int(r * 3.4)],
              fill=(40, 40, 44), outline=INK, width=3)
    d.rounded_rectangle([sx - int(r * 0.75), sy + int(r * 0.7), sx + int(r * 0.75), sy + int(r * 2.6)],
                        radius=int(r * 0.5), fill=c["top"], outline=INK, width=4)
    d.line([(sx, sy + int(r * 1.1)), (sx + dir * int(r * 0.6), sy + int(r * 2.7))], fill=c["top"], width=int(r * 0.4))
    draw_head(d, who, sx, sy, r, dir, brow, eye, mouth)


def draw_char_standing(d, who, sx, sy, r, dir, t, wave):
    """站姿（走路／揮手），一隻外側手臂有描邊＋手。"""
    c = REN if who == "ren" else LE
    for lx in (sx - int(r * 0.38), sx + int(r * 0.38)):
        d.line([(lx, sy + int(r * 2.5)), (lx, sy + int(r * 4.6))], fill=c["pants"], width=int(r * 0.5))
        d.ellipse([lx - int(r * 0.3), sy + int(r * 4.5), lx + int(r * 0.3), sy + int(r * 4.7)],
                  fill=(40, 40, 44), outline=INK, width=3)
    d.rounded_rectangle([sx - int(r * 0.7), sy + int(r * 0.7), sx + int(r * 0.7), sy + int(r * 2.7)],
                        radius=int(r * 0.5), fill=c["top"], outline=INK, width=4)
    shx = sx + dir * int(r * 0.3)
    shy = sy + int(r * 1.0)
    if wave:
        wa = math.sin(t * 8) * 16
        hx = shx + dir * int(r * 0.4) + wa
        hy = shy - int(r * 2.4)
    else:
        hx = shx + dir * int(r * 0.2)
        hy = shy + int(r * 1.3)
    d.line([(shx, shy), (hx, hy)], fill=INK, width=int(r * 0.42) + 4)
    d.line([(shx, shy), (hx, hy)], fill=c["top"], width=int(r * 0.42))
    d.ellipse([hx - int(r * 0.2), hy - int(r * 0.2), hx + int(r * 0.2), hy + int(r * 0.2)],
              fill=SKIN, outline=INK, width=3)
    draw_head(d, who, sx, sy, r, dir, "flat", "normal", "closed")


def draw_subtitle(d, who, text, W, H):
    """程式畫字幕：固定置底、白字黑底、含說話者名字、位置一致。"""
    font = ImageFont.truetype(FONTB, 30)
    label = f"{NAME[who]}：{text}"
    maxw = W - 40
    lines, cur = [], ""
    for ch in label:
        if d.textlength(cur + ch, font=font) <= maxw:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    lh = 52
    bar_top = H - 40 - len(lines) * lh - 14
    d.rectangle([0, bar_top, W, H], fill=(0, 0, 0))
    y = bar_top + 8
    for ln in lines:
        tw = d.textlength(ln, font=font)
        d.text(((W - tw) / 2, y), ln, font=font, fill=(255, 255, 255))
        y += lh


def mouth_from_energy(e):
    if e < 0.15:
        return "closed"
    if e < 0.5:
        return "half"
    return "open"


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


def render_entrance(out, bg, fps):
    """進場：阿忍走路→揮手→坐下。回傳 (clip, dur)。"""
    clip = out / "entrance.mp4"
    dur = 3.8
    n = int(dur * fps)
    frames = []
    for fi in range(n):
        t = fi / fps
        img = Image.open(bg).convert("RGB")
        d = ImageDraw.Draw(img)
        draw_char_seated(d, "le", 150, 470, 55, 1, "flat", "normal", "closed")
        if t < 2.0:
            prog = t / 2.0
            x = int(620 - prog * (620 - 435))
            draw_char_standing(d, "ren", x, 470, 55, -1, t, wave=False)
        elif t < 3.2:
            draw_char_standing(d, "ren", 435, 470, 55, -1, t, wave=True)
        else:
            k = (t - 3.2) / 0.6
            draw_char_seated(d, "ren", 435, 470 + int((1 - k) * 40), 55, -1, "flat", "normal", "closed")
        frames.append(img)
    encode(frames, clip, fps)
    return clip, dur


def render_line(out, bg, who, text, idx, fps, tail=0.35):
    """單句對白：TTS→音量對嘴→渲染（含字幕）。回傳 scene_dur。"""
    mp3 = out / f"tts_{idx}.mp3"
    clip = out / f"clip_{idx}.mp4"
    m4a = out / f"aud_{idx}.m4a"
    asyncio.run(md._tts(text, md.VOICE[who], mp3))
    dur = ms.probe_duration(mp3)
    scene_dur = round((dur + tail) * fps) / fps
    nframes = max(1, round(scene_dur * fps))
    env = mc._energy(mp3, fps, nframes)
    frames = []
    for fi in range(nframes):
        t = fi / fps
        e = env[fi] if fi < len(env) else 0.0
        mouth = mouth_from_energy(e)
        eye = "blink" if (t % 3.0) < 0.12 else "normal"
        img = Image.open(bg).convert("RGB")
        d = ImageDraw.Draw(img)
        if who == "ren":
            draw_char_seated(d, "ren", 435, 470, 55, -1, "flat", eye, mouth)
            draw_char_seated(d, "le", 150, 470, 55, 1, "flat", "normal", "closed")
        else:
            draw_char_seated(d, "le", 150, 470, 55, 1, "flat", eye, mouth)
            draw_char_seated(d, "ren", 435, 470, 55, -1, "flat", "normal", "closed")
        draw_subtitle(d, who, text, img.size[0], img.size[1])
        frames.append(img)
    encode(frames, clip, fps)
    ms.build_audio(mp3, m4a, scene_dur)
    return scene_dur


def main():
    ap = argparse.ArgumentParser(description="場景式對話劇（融合版）")
    ap.add_argument("--bg", default=str(PROJECT_ROOT / "working" / "ai_bg3" / "hi_a.png"))
    ap.add_argument("--out", default=str(PROJECT_ROOT / "working" / "scene_demo"))
    ap.add_argument("--fps", type=int, default=15)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    bg = Path(args.bg)
    fps = args.fps

    lines = [("ren", "設計費不是亂收的，其實包含了很多專業判斷。"),
             ("le", "是喔？那你說說看，到底值多少錢啊？")]

    ent_clip, ent_dur = render_entrance(out, bg, fps)

    durs = []
    for idx, (who, text) in enumerate(lines):
        durs.append(render_line(out, bg, who, text, idx, fps))

    silent_m4a = out / "silent.m4a"
    ms.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", str(ent_dur), "-c:a", "aac", str(silent_m4a)])

    clips = [ent_clip] + [out / f"clip_{i}.mp4" for i in range(len(lines))]
    audios = [silent_m4a] + [out / f"aud_{i}.m4a" for i in range(len(lines))]
    timeline = out / "timeline.mp4"
    ms.concat_scenes(clips, audios, timeline, fps, 0.3)
    final = out / "scene_dialog.mp4"
    ms.run(["ffmpeg", "-y", "-i", str(timeline), "-c", "copy", str(final)])
    print("done ->", final)


if __name__ == "__main__":
    main()
