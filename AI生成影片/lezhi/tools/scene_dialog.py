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
import json
import math
import subprocess
import sys
import time
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

NAME = {"ren": "阿忍", "le": "小樂"}

import char_modes as cm  # noqa: E402
import char_parts as cp  # noqa: E402
_CHAR_MODE = cm.DEFAULT
_mode = cm.get(_CHAR_MODE)
draw_char = _mode.draw_char
draw_char_standing = _mode.draw_char_standing
draw_char_seated = _mode.draw_char_seated
draw_seat = getattr(_mode, "draw_seat", None)


def set_char_mode(mode_key):
    """切換角色構圖模式（2人角色-1/-2/...），重綁 draw_char 系列函式。"""
    global _CHAR_MODE, draw_char, draw_char_standing, draw_char_seated, draw_seat
    _CHAR_MODE = mode_key
    m = cm.get(mode_key)
    draw_char = m.draw_char
    draw_char_standing = m.draw_char_standing
    draw_char_seated = m.draw_char_seated
    draw_seat = getattr(m, "draw_seat", None)

# 場景姿勢：sit=都坐、stand=都站、sitstand=小樂坐＋阿忍站
POSE_MAP = {
    "sit": {"le": "sit", "ren": "sit"},
    "stand": {"le": "stand", "ren": "stand"},
    "sitstand": {"le": "sit", "ren": "stand"},
}
# 視線上下（sitstand 時站著往下看、坐著往上看，讓視線交會）
GAZE = {
    "sit": {"le": 0, "ren": 0},
    "stand": {"le": 0, "ren": 0},
    "sitstand": {"le": 0, "ren": 0},
}
# 頭部轉動角度（sitstand：小樂向下看阿忍、阿忍向上看小樂）
TILT = {
    "sit": {"le": 0, "ren": 0},
    "stand": {"le": 0, "ren": 0},
    "sitstand": {"le": -30, "ren": -30},
}
# 頭部位置微調（dx, dy 像素；sitstand 補償旋轉造成的偏移）
HEAD_SHIFT = {
    "sit": {"le": (0, 0), "ren": (0, 0)},
    "stand": {"le": (0, 0), "ren": (0, 0)},
    "sitstand": {"le": (16, 0), "ren": (-38, -21)},
}
CHAR_POS = {
    "le": {"sit": (150, 470), "stand": (150, 750)},
    "ren": {"sit": (435, 470), "stand": (435, 750)},
}
POS = None  # 覆寫（預覽介面套用）：{"le": {x,y,pose}, "ren": {x,y,pose}, "seat": bool}


def resolve_pose(pose):
    """依場景 pose（或 POS 覆寫）回傳 (le_p, ren_p, le_x, le_y, ren_x, ren_y)。"""
    if POS:
        le = POS.get("le") or {}
        ren = POS.get("ren") or {}
        le_p = le.get("pose") or POSE_MAP.get(pose, POSE_MAP["sit"])["le"]
        ren_p = ren.get("pose") or POSE_MAP.get(pose, POSE_MAP["sit"])["ren"]
        le_x = int(le.get("x", CHAR_POS["le"].get(le_p, (150, 470))[0]))
        le_y = int(le.get("y", CHAR_POS["le"].get(le_p, (150, 470))[1]))
        ren_x = int(ren.get("x", CHAR_POS["ren"].get(ren_p, (435, 750))[0]))
        ren_y = int(ren.get("y", CHAR_POS["ren"].get(ren_p, (435, 750))[1]))
        return le_p, ren_p, le_x, le_y, ren_x, ren_y
    le_p = POSE_MAP.get(pose, POSE_MAP["sit"])["le"]
    ren_p = POSE_MAP.get(pose, POSE_MAP["sit"])["ren"]
    return le_p, ren_p, CHAR_POS["le"][le_p][0], CHAR_POS["le"][le_p][1], \
        CHAR_POS["ren"][ren_p][0], CHAR_POS["ren"][ren_p][1]


def resolve_seat(pose):
    """是否畫椅子（坐姿）。POS 有指定則用指定，否則 sitstand 才畫椅。"""
    if POS and "seat" in POS:
        return bool(POS["seat"])
    return pose == "sitstand"


def resolve_wave():
    """進場是否揮手。POS 有指定則用指定，否則維持舊行為（進場揮手）。"""
    if POS:
        return bool(POS.get("wave", False))
    return True


def look_at(sx, sy, ox, oy):
    """角色在 (sx,sy) 看向 (ox,oy)：回傳 (dir, tilt, shift, lean)。
    dir＝面朝方向；tilt＝頭轉角度；shift＝(dx,dy) 頭部位移（朝對方＋看上時上移）；
    lean＝身體前傾量（看下時上半身朝對方傾）。"""
    dx = ox - sx
    dy = oy - sy
    dist = math.hypot(dx, dy)
    dir = 1 if dx >= 0 else -1
    theta = math.degrees(math.atan2(dy, abs(dx))) if abs(dx) > 1 else (90 if dy > 0 else -90)
    theta = max(-70, min(70, theta))
    tilt = -dir * theta
    amount_h = 55.0 * math.sin(math.radians(abs(theta)))
    shift_y = int(-40.0 * math.sin(math.radians(abs(theta)))) if theta < 0 else 0
    shift = (int(dir * amount_h), shift_y)
    lean = dir * (20.0 * math.sin(math.radians(abs(theta)))) if theta > 0 else 0
    return dir, tilt, shift, lean


def look_at_gated(who, sx, sy, ox, oy):
    """依「朝向」決定視線：
    auto=自動朝對方（對望，算 tilt/shift/lean）；left/right=手動朝左/右（不連動對方）；
    front/back=正視/後視（不連動）。"""
    facing = cp.get_recipe(who).get("facing", "auto")
    if facing in ("auto", "side"):
        return look_at(sx, sy, ox, oy)
    if facing == "left":
        return -1, 0, (0, 0), 0
    if facing == "right":
        return 1, 0, (0, 0), 0
    return 1, 0, (0, 0), 0  # front / back





FONT = r"C:\Windows\Fonts\msjh.ttc"
FONTB = r"C:\Windows\Fonts\msjhbd.ttc"












def draw_subtitle(d, who, text, W, H):
    """程式畫字幕：置於畫面上方、白字黑底，位置一致，不遮角色。"""
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
    bar_top = 40
    bar_bottom = bar_top + len(lines) * lh + 24
    d.rectangle([0, bar_top, W, bar_bottom], fill=(0, 0, 0))
    y = bar_top + 12
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


def _brow_from_t(t, seed):
    """依時間循環眉毛：平 → 上揚(驚喜) → 平 → 皺(擔憂)。"""
    ph = math.sin(t * 0.6 + seed)
    if ph > 0.65:
        return "up"
    if ph < -0.65:
        return "in"
    return "flat"


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


def render_entrance(out, bg, fps, pose="sit"):
    """進場：阿忍走路→揮手→（依姿勢）坐下或站定。回傳 (clip, dur)。"""
    le_p, ren_p, le_x, le_y, ren_x, ren_y = resolve_pose(pose)
    seat = resolve_seat(pose)
    wave = resolve_wave()
    le_dir, le_tilt, le_shift, le_lean = look_at_gated("le", le_x, le_y, ren_x, ren_y)
    ren_dir, ren_tilt, ren_shift, ren_lean = look_at_gated("ren", ren_x, ren_y, le_x, le_y)
    clip = out / "entrance.mp4"
    dur = 3.8
    n = int(dur * fps)
    frames = []
    for fi in range(n):
        t = fi / fps
        img = Image.open(bg).convert("RGB")
        d = ImageDraw.Draw(img)
        draw_char(d, "le", le_x, le_y, 55, le_dir, t, le_p, "flat", "normal", "closed", seat=seat, tilt=le_tilt, shift=le_shift, lean=le_lean)
        if t < 2.0:
            prog = t / 2.0
            x = int(620 - prog * (620 - ren_x))
            draw_char_standing(d, "ren", x, ren_y, 55, ren_dir, t, wave=False)
        elif t < 3.2:
            draw_char_standing(d, "ren", ren_x, ren_y, 55, ren_dir, t, wave=wave, tilt=ren_tilt, shift=ren_shift, lean=ren_lean)
        else:
            if ren_p == "sit":
                k = (t - 3.2) / 0.6
                draw_char_seated(d, "ren", ren_x, ren_y + int((1 - k) * 40), 55, ren_dir, "flat", "normal", "closed", tilt=ren_tilt, shift=ren_shift, lean=ren_lean)
            else:
                draw_char_standing(d, "ren", ren_x, ren_y, 55, ren_dir, t, wave=False, tilt=ren_tilt, shift=ren_shift, lean=ren_lean)
        frames.append(img)
    encode(frames, clip, fps)
    return clip, dur


def render_line(out, bg, who, text, idx, fps, pose="sit", tail=0.35):
    """單句對白：TTS→音量對嘴→渲染（含字幕）。回傳 scene_dur。"""
    le_p, ren_p, le_x, le_y, ren_x, ren_y = resolve_pose(pose)
    seat = resolve_seat(pose)
    le_dir, le_tilt, le_shift, le_lean = look_at_gated("le", le_x, le_y, ren_x, ren_y)
    ren_dir, ren_tilt, ren_shift, ren_lean = look_at_gated("ren", ren_x, ren_y, le_x, le_y)
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
        brow = _brow_from_t(t, idx)
        eye = "blink" if (t % 3.0) < 0.12 else ("wide" if brow == "up" else "normal")
        img = Image.open(bg).convert("RGB")
        d = ImageDraw.Draw(img)
        if who == "ren":
            draw_char(d, "ren", ren_x, ren_y, 55, ren_dir, t, ren_p, brow, eye, mouth, seat=seat, tilt=ren_tilt, shift=ren_shift, lean=ren_lean)
            draw_char(d, "le", le_x, le_y, 55, le_dir, t, le_p, "flat", "normal", "closed", seat=seat, tilt=le_tilt, shift=le_shift, lean=le_lean)
        else:
            draw_char(d, "le", le_x, le_y, 55, le_dir, t, le_p, brow, eye, mouth, seat=seat, tilt=le_tilt, shift=le_shift, lean=le_lean)
            draw_char(d, "ren", ren_x, ren_y, 55, ren_dir, t, ren_p, "flat", "normal", "closed", seat=seat, tilt=ren_tilt, shift=ren_shift, lean=ren_lean)
        draw_subtitle(d, who, text, img.size[0], img.size[1])
        frames.append(img)
    encode(frames, clip, fps)
    ms.build_audio(mp3, m4a, scene_dur)
    return scene_dur


def main():
    global POS
    ap = argparse.ArgumentParser(description="場景式對話劇（融合版）")
    ap.add_argument("--bg", default=str(PROJECT_ROOT / "working" / "ai_bg3" / "hi_a.png"))
    ap.add_argument("--out", default=str(PROJECT_ROOT / "working" / "scene_demo"))
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--lines", default=None, help="台詞 JSON 檔（[{who, text}, ...]），省略則用 demo 台詞")
    ap.add_argument("--pose", default="sit", choices=["sit", "stand", "sitstand"],
                    help="姿勢：sit=都坐、stand=都站、sitstand=小樂坐＋阿忍站")
    ap.add_argument("--pos", default=None, help="覆寫位置 JSON（預覽介面套用）：{le:{x,y,pose},ren:{x,y,pose},seat}")
    ap.add_argument("--title", default=None, help="影片標題（寫入 metadata，供產出庫顯示）")
    ap.add_argument("--topic-id", default=None, help="題目 id（用於規格化影片命名）")
    ap.add_argument("--char-mode", default=cm.DEFAULT, help="角色構圖模式（2人角色-1/-2/...）")
    ap.add_argument("--le-recipe", default=None, help="小樂長相（recipe key，如 le/frog）")
    ap.add_argument("--ren-recipe", default=None, help="阿忍長相（recipe key，如 ren/frog）")
    ap.add_argument("--le-pose", default=None, help="小樂姿勢覆寫 JSON（11 錨點 offset）")
    ap.add_argument("--ren-pose", default=None, help="阿忍姿勢覆寫 JSON（11 錨點 offset）")
    ap.add_argument("--bgm", default=None, help="背景音樂 wav 路徑")
    ap.add_argument("--bgm-volume", type=float, default=0.16)
    args = ap.parse_args()

    set_char_mode(args.char_mode)

    recipe_override = {}
    if args.le_recipe:
        recipe_override["le"] = args.le_recipe
    if args.ren_recipe:
        recipe_override["ren"] = args.ren_recipe
    if recipe_override:
        cp.set_override(recipe_override)

    pose_override = {}
    if args.le_pose:
        try:
            pose_override["le"] = json.loads(args.le_pose)
        except Exception:
            pass
    if args.ren_pose:
        try:
            pose_override["ren"] = json.loads(args.ren_pose)
        except Exception:
            pass
    if pose_override:
        cp.set_pose_override(pose_override)

    if args.pos:
        try:
            POS = json.loads(Path(args.pos).read_text(encoding="utf-8"))
        except Exception:
            POS = None

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    bg = Path(args.bg)
    fps = args.fps

    if args.lines:
        raw = json.loads(Path(args.lines).read_text(encoding="utf-8"))
        lines = [(it.get("who") or it.get("speaker") or "ren", it["text"]) for it in raw]
    else:
        lines = [("ren", "設計費不是亂收的，其實包含了很多專業判斷。"),
                 ("le", "是喔？那你說說看，到底值多少錢啊？")]

    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    ent_clip, ent_dur = render_entrance(assets, bg, fps, args.pose)

    durs = []
    for idx, (who, text) in enumerate(lines):
        durs.append(render_line(assets, bg, who, text, idx, fps, args.pose))

    silent_m4a = assets / "silent.m4a"
    ms.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", str(ent_dur), "-c:a", "aac", str(silent_m4a)])

    clips = [ent_clip] + [assets / f"clip_{i}.mp4" for i in range(len(lines))]
    audios = [silent_m4a] + [assets / f"aud_{i}.m4a" for i in range(len(lines))]
    timeline = assets / "timeline.mp4"
    ms.concat_scenes(clips, audios, timeline, fps, 0.3)
    video = timeline
    if args.bgm and Path(args.bgm).exists():
        mixed = assets / "timeline_mix.mp4"
        ms.mix_bgm(timeline, Path(args.bgm), mixed, args.bgm_volume)
        video = mixed
    final = out / "scene_dialog.mp4"
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "engine"))
        from core import naming as ename
        stem = ename.film_filename("scene", args.topic_id, args.title or "", None).rstrip(".mp4")
        # 角色構圖（配方）不同 → 檔名加角色配方，避免覆蓋先前產出
        le_recipe = recipe_override.get("le", "le")
        ren_recipe = recipe_override.get("ren", "ren")
        variant = ""
        if le_recipe != "le" or ren_recipe != "ren":
            variant = f"__{le_recipe}_{ren_recipe}"
        if stem:
            final = out / f"{stem}{variant}.mp4"
    except Exception:
        pass
    ms.run(["ffmpeg", "-y", "-i", str(video), "-c", "copy", str(final)])

    # 封面 + metadata（供產出庫顯示）
    cover = out / "封面.png"
    ms.run(["ffmpeg", "-y", "-ss", "4", "-i", str(final), "-frames:v", "1", str(cover)])
    (out / "metadata.json").write_text(json.dumps({
        "pack": "interior_lezhi", "style": "scene", "title": args.title or out.name,
        "topic_id": args.topic_id, "date": time.strftime("%Y-%m-%d"),
        "duration_sec": round(ms.probe_duration(final), 1), "video": final.name,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("done ->", final)


if __name__ == "__main__":
    main()
