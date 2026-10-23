"""make_comic.py - 漫畫式對話劇渲染器 v4（重點：人物動態＝嘴型/眼神/表情線條）

設計理念（依 2026-10-18 使用者回饋）：
  - 影像精緻不是方向；**人物的動態變化**才是（嘴型、眼神、表情線條）。
  - **移除讓人「不舒服」的大幅彈跳**：身體只保留極輕微呼吸（±2px），不做 pop/抖動。
  - **漫畫式（線條）**：角色為線條漫畫風；對話時嘴型快速切換（viseme），
    適時眨眼、依情緒換眼神/眉毛，配合情緒線條符號（汗滴/怒氣/閃光/驚訝線）。
  - **背景襯托**：情境背景（客廳／咖啡廳／工地／廚房），緩慢視差平移。

用法：
  python make_comic.py --script scripts/x.json --out output/x_A --bgm assets/bgm_playful.wav
  python make_comic.py --script scripts/x.json --out output/x_B --chars assets/characters_ai --reuse
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import subprocess
import sys
from pathlib import Path

LEZHI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "D:/AI-Agent-Workspace")

import make_short as ms  # noqa: E402
import make_characters as mc  # noqa: E402
import make_dialog as md  # noqa: E402  (reuse _tts / VOICE)
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

W, H = 1080, 1920
FONT = r"C:\Windows\Fonts\msjh.ttc"
FONTB = r"C:\Windows\Fonts\msjhbd.ttc"
SAGE = (117, 137, 133)
INK = (21, 26, 27)
PAPER = (252, 252, 252)

NAME = {"ren": "阿忍", "le": "小樂"}
SIDE = {"ren": "left", "le": "right"}
XC = {"ren": 322, "le": 758}
BASELINE = 1806
H_ACT, H_INA = 782, 700
BG_KINDS = ["living", "cafe", "site", "kitchen", "plain",
            "bedroom", "office", "restaurant", "balcony", "showroom", "outdoor"]
PHOTO_DIR = LEZHI / "assets" / "backgrounds" / "photo"
TRANS = ["fade", "smoothleft", "smoothup", "circleclose", "radial",
         "smoothright", "circleopen", "slideup"]
EMOTE = {"surprise": ("！", (232, 106, 92)), "worry": ("…", (96, 150, 190)),
         "happy": ("♪", (232, 176, 72)), "smug": ("★", (214, 168, 90)),
         "normal": (None, None)}
MD_MOD = {"normal": (0, 0), "surprise": (34, 30), "happy": (22, 16),
          "worry": (-16, -8), "smug": (-8, -4)}

# ---- look 插槽（engine/slots/look.json）：畫風色調＝背景分級 + 墨/紙/品牌色 ----
LOOKS = {
    "warm":  {"ink": (21, 26, 27), "paper": (252, 252, 252), "sage": (117, 137, 133),
              "mul": (1.0, 1.0, 1.0), "gamma": 1.0, "gray": False},
    "night": {"ink": (16, 20, 33), "paper": (250, 246, 235), "sage": (232, 176, 72),
              "mul": (0.52, 0.58, 0.80), "gamma": 1.12, "gray": False},
    "sage":  {"ink": (24, 34, 31), "paper": (248, 252, 249), "sage": (117, 137, 133),
              "mul": (0.88, 1.0, 0.94), "gamma": 1.0, "gray": False},
    "ink":   {"ink": (17, 17, 17), "paper": (253, 253, 253), "sage": (120, 120, 120),
              "mul": (1.0, 1.0, 1.0), "gamma": 1.0, "gray": True},
}
LOOK = "warm"


def apply_look(key):
    """啟用一個畫風：重綁 palette 全域 + 讓背景快取失效（分級是烘焙進快取的）。"""
    global LOOK, INK, PAPER, SAGE
    L = LOOKS.get(key)
    if L is None:
        key, L = "warm", LOOKS["warm"]
    LOOK, INK, PAPER, SAGE = key, L["ink"], L["paper"], L["sage"]
    try:
        _BG_CACHE.clear()
    except Exception:
        pass
    return LOOK


def _grade(img):
    """把 look 的分級套到背景畫布（warm=原樣）。"""
    L = LOOKS[LOOK]
    if L["gray"]:
        return img.convert("L").convert("RGB")
    if L["mul"] == (1.0, 1.0, 1.0) and L["gamma"] == 1.0:
        return img
    lut = []
    for m in L["mul"]:
        lut += [min(255, int(round(255 * ((i / 255) ** L["gamma"]) * m))) for i in range(256)]
    return img.point(lut)


def _grade_rgba(im):
    """角色 RGBA 灰階化（僅 ink 畫風；其他畫風維持原色）。"""
    if not LOOKS[LOOK]["gray"]:
        return im
    a = im.getchannel("A")
    g = im.convert("L").convert("RGB")
    g.putalpha(a)
    return g


def _font(sz, bold=False):
    try:
        return ImageFont.truetype(FONTB if bold else FONT, sz)
    except Exception:
        return ImageFont.load_default()


def _wrap(draw, text, font, maxw):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= maxw:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- backgrounds
BW, BH = 1200, 2080
WALL = (238, 241, 239)
FLOOR = (214, 202, 186)
WOOD = (196, 158, 120)


def _bg_canvas(wall=WALL, floor=FLOOR, horizon=1500):
    img = Image.new("RGB", (BW, BH), wall)
    d = ImageDraw.Draw(img)
    d.rectangle([0, horizon, BW, BH], fill=floor)
    d.rectangle([0, horizon - 16, BW, horizon + 8], fill=(190, 180, 166))
    for x in range(0, BW, 90):  # floor boards
        d.line([(x, horizon), (x - 160, BH)], fill=(198, 186, 170), width=3)
    return img, d


def _window(d, x, y, w, h):
    d.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=(206, 224, 236), outline=INK, width=8)
    d.line([(x + w // 2, y), (x + w // 2, y + h)], fill=INK, width=8)
    d.line([(x, y + h // 2), (x + w, y + h // 2)], fill=INK, width=8)
    d.ellipse([x + w * 0.6, y + h * 0.15, x + w * 0.85, y + h * 0.4], fill=(250, 244, 210))


def _plant(d, x, y, s=1.0):
    d.rounded_rectangle([x - 40 * s, y, x + 40 * s, y + 80 * s], radius=12,
                        fill=(190, 120, 90), outline=INK, width=7)
    for i, (dx, dy) in enumerate([(-50, -120), (0, -160), (50, -120), (-25, -70), (25, -70)]):
        d.ellipse([x + dx * s - 34 * s, y + dy * s - 20 * s, x + dx * s + 34 * s, y + dy * s + 20 * s],
                  fill=(120, 158, 120), outline=INK, width=6)


def draw_bg(kind):
    if kind == "living":
        img, d = _bg_canvas()
        _window(d, 120, 420, 420, 360)
        d.rounded_rectangle([760, 560, 1160, 700], radius=20, fill=(150, 170, 166), outline=INK, width=8)
        d.rounded_rectangle([760, 830, 1160, 1180], radius=26, fill=(170, 188, 182), outline=INK, width=8)
        d.rounded_rectangle([790, 800, 1130, 900], radius=18, fill=(150, 170, 166), outline=INK, width=7)
        d.line([(800, 1000), (1120, 1000)], fill=INK, width=5)
        _plant(d, 640, 1180, 1.0)
        d.rectangle([300, 560, 560, 800], fill=(250, 248, 242), outline=INK, width=8)
        d.line([(300, 680), (560, 680)], fill=(210, 200, 186), width=4)
    elif kind == "cafe":
        img, d = _bg_canvas(wall=(232, 226, 214), floor=(178, 158, 138))
        for lx in (360, 620, 880):
            d.line([(lx, 260), (lx, 470)], fill=INK, width=6)
            d.pieslice([lx - 70, 470, lx + 70, 590], 180, 360, fill=(180, 120, 96), outline=INK, width=7)
            d.ellipse([lx - 22, 556, lx + 22, 600], fill=(250, 240, 190), outline=INK, width=5)
        d.rounded_rectangle([120, 1180, 1080, 1330], radius=16, fill=WOOD, outline=INK, width=8)
        d.rounded_rectangle([120, 1330, 1080, 1560], radius=10, fill=(160, 126, 96), outline=INK, width=8)
        for cx in (300, 640, 960):
            _d_cup = d.ellipse([cx - 34, 1120, cx + 34, 1188], fill=PAPER, outline=INK, width=6)
            d.arc([cx - 34, 1116, cx + 34, 1156], 200, 340, fill=INK, width=6)
            d.line([(cx - 12, 1080), (cx - 6, 1104)], fill=(200, 200, 200), width=4)
            d.line([(cx + 10, 1076), (cx + 16, 1102)], fill=(200, 200, 200), width=4)
        d.rounded_rectangle([150, 430, 470, 720], radius=12, fill=(60, 66, 66), outline=INK, width=8)
        d.text((190, 470), "MENU", font=_font(60, True), fill=(240, 236, 220))
    elif kind == "site":
        img, d = _bg_canvas(wall=(226, 220, 208), floor=(190, 178, 162))
        for y in range(300, 1500, 90):  # brick wall
            d.line([(0, y), (BW, y)], fill=(198, 188, 174), width=5)
            off = 60 if (y // 90) % 2 else 0
            for x in range(-60 + off, BW, 120):
                d.line([(x, y), (x, y + 90)], fill=(198, 188, 174), width=5)
        d.line([(700, 1330), (820, 700)], fill=WOOD, width=22)  # ladder
        d.line([(870, 1330), (990, 700)], fill=WOOD, width=22)
        for ly in range(760, 1330, 110):
            t = (ly - 700) / 630
            x1 = int(700 + (820 - 700) * (1 - t) * 0 + (700 + (820 - 700) * 0))  # keep simple
            xa = int(700 + (820 - 700) * ((1330 - ly) / 630) * 0)
            xa = int(700 + (820 - 700) * (ly - 700) / 630)
            xb = int(870 + (990 - 870) * (ly - 700) / 630)
            d.line([(xa, ly), (xb, ly)], fill=WOOD, width=14)
        d.polygon([(300, 1330), (360, 1180), (420, 1330)], fill=(230, 130, 70), outline=INK)
        d.line([(320, 1330), (400, 1330)], fill=INK, width=8)
        for i in range(6):  # caution tape
            d.polygon([(100 + i * 90, 900), (170 + i * 90, 830), (245 + i * 90, 900),
                       (175 + i * 90, 970)], fill=(240, 210, 90), outline=INK)
    elif kind == "kitchen":
        img, d = _bg_canvas(wall=(236, 238, 233), floor=(206, 196, 182))
        _window(d, 150, 430, 360, 300)
        d.rectangle([0, 830, 620, 1080], fill=(222, 210, 194), outline=INK, width=8)
        d.rectangle([640, 830, BW, 1080], fill=(222, 210, 194), outline=INK, width=8)
        d.line([(620, 830), (620, 1080)], fill=INK, width=8)
        d.rectangle([0, 1080, BW, 1180], fill=(150, 160, 156), outline=INK, width=8)
        d.rounded_rectangle([300, 1085, 560, 1178], radius=12, fill=(180, 188, 186), outline=INK, width=6)
        d.line([(360, 1130), (360, 1040), (400, 1040)], fill=INK, width=8)
    elif kind == "bedroom":
        img, d = _bg_canvas(wall=(236, 232, 240), floor=(210, 196, 186))
        _window(d, 130, 420, 380, 340)
        d.rectangle([120, 1180, 560, 1400], fill=(120, 150, 180), outline=INK, width=8)
        d.rectangle([120, 1330, 560, 1500], fill=(150, 180, 205), outline=INK, width=8)
        d.rounded_rectangle([80, 1380, 560, 1500], radius=20, fill=(250, 250, 248), outline=INK, width=8)
        d.ellipse([700, 980, 1160, 1280], fill=(150, 170, 166), outline=INK, width=8)
        d.rectangle([760, 1280, 1120, 1500], fill=(150, 170, 166), outline=INK, width=8)
        _plant(d, 640, 1220, 0.9)
    elif kind == "office":
        img, d = _bg_canvas(wall=(226, 228, 232), floor=(190, 184, 176))
        _window(d, 150, 380, 340, 300)
        d.rectangle([120, 1180, 1080, 1290], fill=WOOD, outline=INK, width=8)
        d.rectangle([160, 1290, 260, 1500], fill=WOOD, outline=INK, width=6)
        d.rectangle([940, 1290, 1040, 1500], fill=WOOD, outline=INK, width=6)
        d.rounded_rectangle([300, 1080, 620, 1230], radius=16, fill=(90, 96, 100), outline=INK, width=8)
        d.rectangle([320, 1100, 600, 1210], fill=(190, 220, 250), outline=INK, width=5)
        d.rounded_rectangle([700, 1040, 1040, 1210], radius=14, fill=(120, 150, 180), outline=INK, width=8)
    elif kind == "restaurant":
        img, d = _bg_canvas(wall=(226, 214, 198), floor=(178, 158, 138))
        for lx in (360, 640, 920):
            d.line([(lx, 240), (lx, 430)], fill=INK, width=5)
            d.pieslice([lx - 60, 430, lx + 60, 540], 180, 360, fill=(150, 110, 90), outline=INK, width=6)
        d.rounded_rectangle([120, 1180, 1080, 1330], radius=16, fill=WOOD, outline=INK, width=8)
        d.rounded_rectangle([120, 1330, 1080, 1560], radius=10, fill=(150, 120, 96), outline=INK, width=8)
        for cx in (280, 620, 960):
            d.ellipse([cx - 40, 1090, cx + 40, 1170], fill=PAPER, outline=INK, width=6)
            d.arc([cx - 40, 1086, cx + 40, 1140], 200, 340, fill=INK, width=6)
        d.rounded_rectangle([150, 430, 470, 700], radius=12, fill=(60, 66, 66), outline=INK, width=8)
        d.text((190, 460), "MENU", font=_font(56, True), fill=(240, 236, 220))
    elif kind == "balcony":
        img, d = _bg_canvas(wall=(214, 226, 238), floor=(196, 184, 170))
        for x in range(80, BW, 120):
            d.rectangle([x, 380, x + 14, 1200], fill=(190, 196, 190), outline=INK, width=5)
        d.rectangle([0, 1180, BW, 1210], fill=WOOD, outline=INK, width=6)
        for px in (300, 680, 1020):
            _plant(d, px, 900, 0.8)
        d.ellipse([760, 300, 900, 400], fill=(250, 244, 210), outline=INK, width=6)
        d.line([(760, 350), (720, 380)], fill=INK, width=5)
        d.line([(900, 350), (940, 380)], fill=INK, width=5)
        d.line([(800, 420), (760, 460)], fill=INK, width=5)
        d.line([(880, 420), (920, 460)], fill=INK, width=5)
    elif kind == "showroom":
        img, d = _bg_canvas(wall=(240, 242, 240), floor=(214, 208, 200))
        d.rectangle([120, 980, 560, 1280], fill=(150, 170, 166), outline=INK, width=8)
        d.rectangle([150, 1010, 530, 1120], fill=(220, 224, 220), outline=INK, width=5)
        d.rectangle([640, 1040, 1040, 1260], fill=(186, 172, 150), outline=INK, width=8)
        d.line([(640, 1040), (840, 1260)], fill=INK, width=5)
        d.line([(840, 1040), (1040, 1260)], fill=INK, width=5)
        _plant(d, 300, 1280, 0.9)
        _plant(d, 940, 1300, 0.9)
    elif kind == "outdoor":
        img, d = _bg_canvas(wall=(206, 226, 236), floor=(150, 168, 120), horizon=1420)
        d.ellipse([820, 200, 960, 340], fill=(250, 244, 210), outline=INK, width=6)
        for cx, cy, r in ((160, 280, 46), (360, 200, 60), (620, 260, 40)):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(120, 180, 140), outline=INK, width=6)
        d.rectangle([150, 1180, 300, 1500], fill=(150, 120, 90), outline=INK, width=8)
        d.ellipse([110, 900, 340, 1250], fill=(120, 170, 120), outline=INK, width=6)
    else:
        img, d = _bg_canvas()
        d.rectangle([0, 0, BW, 360], fill=(226, 234, 230))
    return img


def _photo_bg(name):
    """Load a real-photo background from lezhi/assets/backgrounds/photo/, fit to BWxBH."""
    p = PHOTO_DIR / name
    if not p.exists():
        for cand in PHOTO_DIR.glob("*"):
            if cand.stem == name or cand.name == name:
                p = cand
                break
    if not p.exists():
        return None
    im = Image.open(p).convert("RGB")
    # cover-fit to BWxBH (center crop)
    sc = max(BW / im.width, BH / im.height)
    im = im.resize((max(BW, int(im.width * sc)), max(BH, int(im.height * sc))), Image.LANCZOS)
    x = (im.width - BW) // 2
    y = (im.height - BH) // 2
    return im.crop((x, y, x + BW, y + BH))


_BG_CACHE: dict = {}


def _bg_big(kind):
    if kind not in _BG_CACHE:
        if kind.startswith("photo:"):
            img = _photo_bg(kind[len("photo:"):])
            if img is not None:
                _BG_CACHE[kind] = _grade(img)
                return _BG_CACHE[kind]
            kind = "living"
        _BG_CACHE[kind] = _grade(draw_bg(kind))
    return _BG_CACHE[kind]


# ---------------------------------------------------------------- character
_base_cache: dict = {}


def _base_scaled(who, height):
    key = (who, height)
    if key not in _base_cache:
        b = mc.draw_base(who)
        r = height / b.height
        _base_cache[key] = b.resize((max(1, int(b.width * r)), height), Image.LANCZOS)
    return _base_cache[key]


def _face_scaled(who, brow, eye, mouth, expr, height):
    f = mc.draw_face(who, brow, eye, mouth, expr)
    r = height / f.height
    return f.resize((max(1, int(f.width * r)), height), Image.LANCZOS)


def _energy(mp3, fps, nframes):
    """Decode mp3 -> per-video-frame RMS envelope (0..1). Real lip-sync source."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp3), "-f", "f32le",
                          "-ac", "1", "-ar", "24000", "-"], capture_output=True).stdout
    if not raw:
        return [0.0] * nframes
    a = np.frombuffer(raw, dtype=np.float32)
    sr, hop = 24000, 24000 / fps
    env = np.zeros(nframes)
    for i in range(nframes):
        s = int(i * hop)
        seg = a[s:s + int(hop)]
        env[i] = math.sqrt(float(np.mean(seg * seg))) if seg.size else 0.0
    if env.size >= 3:
        env = np.convolve(env, np.ones(3) / 3, mode="same")
    m = float(np.percentile(env, 95)) if env.size else 0.0
    if m > 1e-6:
        env = np.clip(env / m, 0, 1)
    return env.tolist()


def _mouth_e(o, t):
    """Energy -> mouth shape (ladder). Keeps articulation in sync with volume."""
    if o < 0.13:
        return "m"
    if o < 0.38:
        return "u"
    if o < 0.62:
        return "o" if int(t * 13) % 2 else "u"
    if o < 0.86:
        return "e" if int(t * 15) % 2 else "a"
    return "big" if o > 0.965 else "a"


def _prosody(who, expr, text):
    """Tone matching content: expr + punctuation cues -> (rate, pitch, volume)."""
    br, bp = md.VOICE_BASE.get(who, (0, 0))
    er, ep = MD_MOD.get(expr, (0, 0))
    vol = 0
    if "！" in text or "!" in text:
        er += 12
        ep += 8
        vol += 12
    if "？" in text or "?" in text:
        ep += 7
    if "…" in text:
        er -= 8
        ep -= 4
    return f"{br + er:+d}%", f"{bp + ep:+d}Hz", f"{vol:+d}%"


def _eye(t, expr, blinks):
    for bt in blinks:
        if bt <= t < bt + 0.12:
            return "blink"
    return mc.EXPR.get(expr, mc.EXPR["normal"])[1]


def _brow(t, expr):
    return mc.EXPR.get(expr, mc.EXPR["normal"])[0]


def _blinks(dur, seed):
    rnd = random.Random(seed)
    out, t = [], rnd.uniform(0.7, 1.6)
    while t < dur - 0.3:
        out.append(t)
        t += rnd.uniform(2.4, 4.6)
    return out


def _chrome(title):
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    ft = _font(34, True)
    tw = d.textlength(title[:16], font=ft)
    d.rounded_rectangle([44, 44, 44 + tw + 44, 44 + ft.size + 40], radius=36, fill=INK)
    d.text((66, 62), title[:16], font=ft, fill=PAPER)
    d.rectangle([0, H - 118, W, H], fill=INK)
    d.text((44, H - 94), "押忍室內裝修設計有限公司", font=_font(40, True), fill=PAPER)
    d.text((W - 306, H - 94), "LE Interior", font=_font(40, True), fill=SAGE)
    return lay


def _draw_infocard(img, kind, data=None):
    """Draw domain info card overlay (P5-4)."""
    if not kind or kind == "none":
        return img
    data = data or {}
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    f_title = _font(38)
    f_body = _font(32)
    # card box top-right
    cx, cy, cw, ch = W - 520, 80, 460, 190
    d.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=28, fill=(18, 24, 38, 235), outline=INK, width=4)
    if kind == "area":
        d.text((cx + 28, cy + 18), "坪數", font=f_title, fill=(255, 255, 255))
        val = data.get("value") or "約 25 坪"
        d.text((cx + 28, cy + 78), val, font=f_body, fill=(170, 215, 255))
        note = data.get("note") or "格局建議以實際測量為準"
        d.text((cx + 28, cy + 128), note, font=f_body, fill=(210, 210, 210))
    elif kind == "budget":
        d.text((cx + 28, cy + 18), "預算", font=f_title, fill=(255, 255, 255))
        val = data.get("value") or "約 60-80 萬"
        d.text((cx + 28, cy + 78), val, font=f_body, fill=(255, 215, 140))
        note = data.get("note") or "含設計費、監工、部分建材"
        d.text((cx + 28, cy + 128), note, font=f_body, fill=(210, 210, 210))
    elif kind == "material":
        d.text((cx + 28, cy + 18), "材質建議", font=f_title, fill=(255, 255, 255))
        items = data.get("items") or ["地板：耐磨SPC", "牆面：乳膠漆", "櫃體：系統板"]
        y = cy + 78
        for it in items[:3]:
            d.text((cx + 28, y), it, font=f_body, fill=(190, 235, 190))
            y += 38
    elif kind == "layout":
        d.text((cx + 28, cy + 18), "動線重點", font=f_title, fill=(255, 255, 255))
        items = data.get("items") or ["動線：開門→玄關不交叉", "採光：避免遮擋窗戶", "收納：動線盡頭規劃"]
        y = cy + 78
        for it in items[:3]:
            d.text((cx + 28, y), it, font=f_body, fill=(220, 200, 255))
            y += 38
    elif kind == "custom":
        title_c = data.get("title") or "重點"
        d.text((cx + 28, cy + 18), title_c, font=f_title, fill=(255, 255, 255))
        items = data.get("items") or ["重點一", "重點二", "重點三"]
        y = cy + 78
        for it in items[:3]:
            d.text((cx + 28, y), it, font=f_body, fill=(235, 235, 235))
            y += 38
    out = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    return out


# ---------------------------------------------------------------- camera / fx
CAMERAS = ("static", "zoom_in", "zoom_out", "pan_l", "pan_r")
SFX_TEXT = {"surprise": "鏘！", "happy": "哇！", "smug": "哼～", "worry": "嘖…"}


def _camera_crop(big, cam, prog, idx, t):
    """Crop (+ optional zoom/pan) a BWxBH background to a WxH RGBA frame."""
    BW, BH = big.size
    z = 1.0
    if cam == "zoom_in":
        z = 1.0 + 0.10 * prog
    elif cam == "zoom_out":
        z = 1.10 - 0.10 * prog
    cw, ch = W / z, H / z
    mx, my = (BW - cw) / 2, (BH - ch) / 2
    dx = dy = 0
    if cam in ("pan_l", "pan_r"):
        s = 1 if cam == "pan_l" else -1
        dx = mx * (1 - 2 * prog) * s
    dx += int(26 * math.sin(2 * math.pi * t * 0.03 + idx))
    dy += int(18 * math.cos(2 * math.pi * t * 0.024 + idx))
    cx = BW / 2 + dx
    cy = BH / 2 + dy
    x0 = max(0.0, min(BW - cw, cx - cw / 2))
    y0 = max(0.0, min(BH - ch, cy - ch / 2))
    crop = big.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch)))
    if abs(cw - W) > 1 or abs(ch - H) > 1:
        crop = crop.resize((W, H), Image.LANCZOS)
    return crop.convert("RGBA")


def _gaze(t, who, expr, seed):
    """Eye direction beyond the base expression: squint / glance / look up."""
    if expr == "worry":
        return "squint" if math.sin(t * 1.3 + seed) > 0.55 else "normal"
    ph = math.sin(2 * math.pi * t * 0.22 + seed)
    if ph > 0.62:
        return "look_left" if SIDE[who] == "right" else "look_right"
    if ph < -0.66:
        return "look_up"
    return "normal"


def _head_turns(dur, seed):
    """Discrete head-turn events: (start, angle, hold) — turn, hold, return."""
    rnd = random.Random(seed)
    events = []
    t = rnd.uniform(0.4, 0.9)
    while t < dur - 0.9:
        ang = rnd.choice([7.0, -7.0, 5.0, -5.0])
        hold = rnd.uniform(0.3, 0.55)
        events.append((t, ang, hold))
        t += rnd.uniform(1.8, 3.2)
    return events


def _head_angle(t, events):
    """Current head angle: 0 outside events, ramp in -> hold -> ramp back."""
    TURN = 0.16
    for start, ang, hold in events:
        if start <= t < start + TURN:
            return ang * (t - start) / TURN
        if start + TURN <= t < start + TURN + hold:
            return ang
        if start + TURN + hold <= t < start + 2 * TURN + hold:
            return ang * (1 - (t - start - TURN - hold) / TURN)
    return 0.0


HEAD_TOP, HEAD_BOT = 140, 540


def _turn_head(comp, angle):
    """Rotate only the head strip around the neck (body stays still)."""
    if abs(angle) < 0.3:
        return comp
    region = comp.crop((0, HEAD_TOP, comp.width, HEAD_BOT))
    rot = region.rotate(angle, resample=Image.BILINEAR, expand=False,
                        center=(comp.width / 2, HEAD_BOT - HEAD_TOP))
    comp.paste((0, 0, 0, 0), (0, HEAD_TOP, comp.width, HEAD_BOT))
    comp.alpha_composite(rot, (0, HEAD_TOP))
    return comp


def _draw_sfx_lines(fr, kind, t, seed):
    """Comic effect lines (burst/speed/focus), drawn behind characters."""
    if not kind:
        return
    d = ImageDraw.Draw(fr)
    rnd = random.Random(seed)
    if kind == "burst":
        cx, cy = W // 2, 660
        for a in range(0, 360, 22):
            ang = math.radians(a + t * 50)
            r1 = 120 + 14 * math.sin(t * 6 + a)
            r2 = 190 + 14 * math.sin(t * 6 + a)
            d.line([(cx + r1 * math.cos(ang), cy + r1 * math.sin(ang)),
                    (cx + r2 * math.cos(ang), cy + r2 * math.sin(ang))],
                   fill=(96, 96, 104), width=6)
    elif kind == "speed":
        for i in range(7):
            y = 380 + i * 240
            lx = rnd.uniform(0, W)
            d.line([(lx, y), (lx + 200, y)], fill=(96, 96, 104), width=4)
    elif kind == "focus":
        cx, cy = W // 2, 760
        for rr in (130, 190, 250):
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(80, 80, 88), width=4)


def _fx_for_expr(expr):
    return {"surprise": "burst", "happy": "speed", "worry": "focus"}.get(expr)


def _sfx_layer(text):
    """Pre-render the big sound-effect text ONCE (avoids per-frame text raster)."""
    if not text:
        return None
    ft = _font(110, True)
    tmp = Image.new("RGBA", (W, 400), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    tw = td.textlength(text, font=ft)
    td.text(((W - tw) / 2, 20), text, font=ft, fill=(240, 90, 70),
            stroke_width=6, stroke_fill=INK)
    return tmp


def _composite_sfx(fr, layer, t):
    if layer is None:
        return
    if t < 0.2:
        sc = 0.7 + 0.3 * (t / 0.2)
        nw, nh = int(layer.width * sc), int(layer.height * sc)
        tmp = layer.resize((nw, nh), Image.LANCZOS)
        fr.alpha_composite(tmp, ((W - nw) // 2, 200))
    else:
        fr.alpha_composite(layer, (0, 200))


def render_scene(title, speaker, text, expr, char_dir, dur, fps, idx, bounds, bg_kind, env,
                 infocard=None, infocard_data=None, cam="static", sfx=None):
    """Yield RGB frames. Mouth is energy-synced; eyes blink/gaze; head sways."""
    other = "le" if speaker == "ren" else "ren"
    big = _bg_big(bg_kind)
    chrome = _chrome(title)
    if cam not in CAMERAS:
        cam = "static"

    # bubble laid out once
    bl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bl)
    f = _font(50)
    lines = _wrap(bd, text, f, 700)
    lh = int(f.size * 1.42)
    bw, bh = 780, len(lines) * lh + 74
    bx = 70 if SIDE[speaker] == "left" else W - bw - 70
    by = 900 - bh
    bd.rounded_rectangle([bx, by, bx + bw, by + bh], radius=46, fill=PAPER, outline=INK, width=6)
    ty = by + 37
    for ln in lines:
        bd.text((bx + 48, ty), ln, font=f, fill=INK)
        ty += lh
    tx = XC[speaker]
    bd.polygon([(tx - 46, by + bh - 6), (tx + 46, by + bh - 6), (tx, by + bh + 70)],
               fill=PAPER, outline=INK)
    bbox = (bx - 14, by - 14, bx + bw + 14, by + bh + 84)
    bsrc = bl.crop(bbox)

    blinks_s = _blinks(dur, idx * 7 + 3)
    blinks_o = _blinks(dur, idx * 7 + 11)
    turns_s = _head_turns(dur, idx * 7 + 5)
    turns_o = _head_turns(dur, idx * 7 + 13)
    glyph, gcol = EMOTE.get(expr, (None, None))
    fx = _fx_for_expr(expr)
    sfx_layer = _sfx_layer(sfx)
    n = max(1, round(dur * fps))
    for fi in range(n):
        t = fi / fps
        prog = fi / max(1, n - 1)
        fr = _camera_crop(big, cam, prog, idx, t)
        e_sp = env[fi] if (env is not None and fi < len(env)) else 0.0
        _draw_sfx_lines(fr, fx, t, idx * 5 + 1)

        for who, is_sp in ((other, False), (speaker, True)):
            hgl = H_ACT if is_sp else H_INA
            base = _base_scaled(who, hgl)
            e = expr if is_sp else "normal"
            if is_sp:
                mo = _mouth_e(e_sp, t)
                ey = _eye(t, e, blinks_s)
            else:
                mo = mc.EXPR.get(e, mc.EXPR["normal"])[2]
                ey = _eye(t, e, blinks_o)
            base_eye = mc.EXPR.get(e, mc.EXPR["normal"])[1]
            if ey == base_eye and base_eye == "normal":
                gz = _gaze(t, who, e, idx * 13 + (7 if is_sp else 3))
                if gz != "normal":
                    ey = gz
            if e == "smug" and not is_sp and math.sin(t * 1.2 + idx * 5) > 0.7:
                ey = "squint"
            br = _brow(t, e)
            face = _face_scaled(who, br, ey, mo, e, hgl)
            comp = base.copy()
            comp.alpha_composite(face)
            comp = _grade_rgba(comp)
            ang = _head_angle(t, turns_s if is_sp else turns_o)
            comp = _turn_head(comp, ang)
            if not is_sp:
                a = comp.getchannel("A").point(lambda v: int(v * 0.9))
                comp.putalpha(a)
            fr.alpha_composite(comp, (int(XC[who] - comp.width / 2), int(BASELINE - comp.height)))

        if sfx_layer is not None:
            _composite_sfx(fr, sfx_layer, t)
        fr.alpha_composite(chrome)
        # emotion badge near speaker's head (readable symbol)
        if glyph and e_sp > 0.02:
            ex = XC[speaker] + (208 if SIDE[speaker] == "left" else -208)
            ey2 = 1004 - int(min(1.0, t / 0.25) * 30)
            r = 56
            bd2 = ImageDraw.Draw(fr)
            bd2.ellipse([ex - r, ey2 - r, ex + r, ey2 + r], fill=gcol)
            gf = _font(62, True)
            gw = bd2.textlength(glyph, font=gf)
            bd2.text((ex - gw / 2, ey2 - gf.size / 2 - 8), glyph, font=gf, fill=PAPER)
        # bubble pop-in (subtle)
        bc = min(1.0, t / 0.18)
        if bc < 0.999:
            sc = 0.9 + 0.1 * bc
            src = bsrc.resize((int(bsrc.width * sc), int(bsrc.height * sc)), Image.LANCZOS)
            fr.alpha_composite(src, (int(bbox[0] + bsrc.width * (1 - sc) / 2),
                                     int(bbox[1] + bsrc.height * (1 - sc) / 2)))
        else:
            fr.alpha_composite(bl, (0, 0))
        fr = _draw_infocard(fr, infocard, infocard_data)
        yield fr.convert("RGB")


def encode_frames(frames, out_mp4, fps, total=None, cover_png=None):
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-an",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           str(out_mp4)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pick = (total // 4) if total else -1
    for fi, frm in enumerate(frames):
        if fi == pick and cover_png is not None:
            frm.save(cover_png)
        p.stdin.write(frm.tobytes())
    p.stdin.close()
    p.wait()


def _film_meta(script, script_path, title):
    """Indexable output info (metadata spine).

    Returns {stem, pack, topic_id, style, version, date, title}. Finds
    engine/core/naming.py in an ancestor (or its immediate subdirs);
    falls back to the plain title when unavailable.
    """
    import sys
    for parent in Path(__file__).resolve().parents:
        cands = [parent / "engine" / "core" / "naming.py"]
        cands += list(parent.glob("*/engine/core/naming.py"))
        for cand in cands:
            if cand.exists():
                sys.path.insert(0, str(cand.parent.parent))
                try:
                    from core import naming as ename
                    meta = ename.parse(Path(script_path).stem)
                    ver = meta["version"] if meta else (script.get("version") or 1)
                    tid = meta["id"] if meta else (script.get("topic_id") or Path(script_path).stem)
                    stl = meta["style"] if meta else (script.get("style") or None)
                    return ename.film_fields(stl, tid, title, ver, pack=script.get("pack"))
                except Exception:
                    pass
    return {"stem": title, "pack": script.get("pack"), "topic_id": script.get("topic_id"),
            "style": script.get("style"), "version": script.get("version") or 1,
            "date": None, "title": title}


def main():
    ap = argparse.ArgumentParser(description="押忍漫畫式對話劇 v4")
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--chars", default=None, help="（保留相容；本版用內建線條角色）")
    ap.add_argument("--bgm", default=None)
    ap.add_argument("--bgm-volume", type=float, default=0.16)
    ap.add_argument("--tail", type=float, default=0.4)
    ap.add_argument("--transition", type=float, default=0.35)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--subs", action="store_true")
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--look", default=None, help="畫風（engine/slots/look.json；預設讀腳本的 look）")
    ap.add_argument("--sfx", dest="sfx", action="store_true", default=False)
    ap.add_argument("--no-sfx", dest="sfx", action="store_false")
    args = ap.parse_args()

    script = json.loads(Path(args.script).read_text(encoding="utf-8"))
    look = apply_look(args.look or script.get("look") or "warm")
    title = script.get("title", "對話劇")
    info = _film_meta(script, args.script, title)
    stem = info["stem"]
    scenes = script["scenes"]
    vmap = {**md.VOICE, **script.get("voice_map", {})}

    out = Path(args.out)
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    sfx = md.gen_sfx(assets) if args.sfx else None
    ms.log(f"漫畫式 v4：{title}｜畫風 {look}｜{len(scenes)} 句｜音效：{'開' if sfx else '關'}")

    film_bg = script.get("bg") or (scenes[0].get("bg") if scenes else None) or "living"
    if not (film_bg in BG_KINDS or film_bg.startswith("photo:")):
        film_bg = "living"
    ms.log(f"整支背景：{film_bg}")

    clips, audios, metas = [], [], []
    for i, sc in enumerate(scenes):
        who = sc.get("speaker", "ren")
        text = sc["text"]
        expr = sc.get("expr", "normal")
        if expr not in mc.EXPR:
            expr = "normal"
        bg_kind = film_bg
        cam = sc.get("camera") or "static"
        if cam not in CAMERAS:
            cam = "static"
        sfx_txt = sc.get("sfx") or SFX_TEXT.get(expr)
        voice = sc.get("voice") or vmap.get(who, md.VOICE["ren"])
        rate, pitch, volume = _prosody(who, expr, text)
        ms.log(f"[{i+1}/{len(scenes)}] {NAME.get(who,who)}（{expr}/{bg_kind}, {rate}/{pitch}）：{text[:16]}")

        mp3 = assets / f"tts_{i}.mp3"
        bjson = assets / f"bounds_{i}.json"
        if args.reuse and mp3.exists() and bjson.exists():
            bounds = json.loads(bjson.read_text(encoding="utf-8"))
        else:
            bounds = None
            for attempt in range(4):
                try:
                    bounds = asyncio.run(md._tts(text, voice, mp3, rate, pitch, volume))
                    if bounds:
                        break
                except Exception as e:
                    ms.log(f"  TTS 重試 {attempt}：{str(e)[:50]}")
                    import time
                    time.sleep(3)
            if not bounds:
                bounds = asyncio.run(md._tts(text, "zh-TW-HsiaoChenNeural", mp3, rate, pitch, volume))
            bjson.write_text(json.dumps(bounds, ensure_ascii=False), encoding="utf-8")
        dur = ms.probe_duration(mp3)
        scene_dur = round((dur + args.tail) * args.fps) / args.fps
        nframes = max(1, round(scene_dur * args.fps))
        env = _energy(mp3, args.fps, nframes)

        clip = assets / f"clip_{i}.mp4"
        infocard = sc.get("infocard") or script.get("infocard") or "none"
        infocard_data = sc.get("infocard_data") or script.get("infocard_data") or {}
        frames = render_scene(title, who, text, expr, None, scene_dur, args.fps, i, bounds, bg_kind, env,
                              infocard=infocard, infocard_data=infocard_data, cam=cam, sfx=sfx_txt)
        encode_frames(frames, clip, args.fps,
                      total=nframes,
                      cover_png=(assets / "cover0.png") if i == 0 else None)
        aud = assets / f"aud_{i}.m4a"
        if sfx:
            md.build_audio_sfx(mp3, aud, scene_dur, sfx)
        else:
            ms.build_audio(mp3, aud, scene_dur)
        clips.append(clip)
        audios.append(aud)
        metas.append({"dur": ms.probe_duration(clip), "bounds": bounds, "text": text})

    ms.log("串接 + 轉場...")
    silent = assets / "timeline.mp4"
    ms.concat_scenes(clips, audios, silent, args.fps, args.transition, transitions=TRANS)

    video = silent
    if args.bgm:
        ms.log(f"混入 BGM（{args.bgm_volume}）...")
        mixed = assets / "timeline_mix.mp4"
        ms.mix_bgm(silent, Path(args.bgm), mixed, args.bgm_volume)
        video = mixed

    final = out / f"{stem}.mp4"
    if args.subs:
        srt = out / f"{stem}.srt"
        ms.build_srt(metas, srt, args.transition)
        ms.burn_subtitles(video, srt.name, final, out)
        subs = out / "subs"
        subs.mkdir(exist_ok=True)
        srt.replace(subs / srt.name)
    else:
        ms.run(["ffmpeg", "-y", "-i", str(video), "-c", "copy", str(final)])

    cover = out / "封面.png"
    if (assets / "cover0.png").exists():
        cover.write_bytes((assets / "cover0.png").read_bytes())
    (out / "metadata.json").write_text(json.dumps({
        "pack": info.get("pack"), "topic_id": info.get("topic_id"),
        "style": info.get("style"), "version": info.get("version"),
        "date": info.get("date"), "title": title, "format": "comic", "size": f"{W}x{H}",
        "duration_sec": round(ms.probe_duration(final), 1), "lines": len(scenes),
        "video": final.name, "cover": cover.name if cover.exists() else None,
        "subtitle": f"subs/{stem}.srt" if args.subs else None,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    ms.log(f"完成！{final}（{round(ms.probe_duration(final),1)}s）")


if __name__ == "__main__":
    main()
