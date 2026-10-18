"""Generate programmatic comic characters (2 chars).

This module is the character FOUNDATION for the comic (漫畫式) renderer:
  - draw_base(who)  -> body/head/hair (static, transparent PNG layer)
  - draw_face(who, brow, eye, mouth, marks) -> animated face overlay (transparent)
  - draw_character(who, expr) -> base + face (backward compatible, used to emit sprites)

Why split: comic style should animate the FACE (mouth/eyes/brows), not the body.
See make_comic.py for the frame-by-frame renderer.

Output (main): lezhi/assets/characters/{who}_{expr}.png  (10 sprites, transparent)
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "assets" / "characters"
CW, CH = 720, 900
INK = (21, 26, 27)
LW = 7

SKIN = (247, 219, 196)
SKIN_SH = (231, 195, 168)

# face feature anchors (canvas space)
CX = CW // 2
EX1, EX2, EY = CX - 58, CX + 58, 350
MY = 442

CHARS = {
    "ren": {"skin": SKIN, "hair": (38, 42, 45), "top": (117, 137, 133),
            "accent": (252, 252, 252), "glasses": True, "cap": False,
            "brow": (38, 42, 45), "hair_style": "short"},
    "le": {"skin": SKIN, "hair": (94, 66, 51), "top": (222, 158, 106),
           "accent": (252, 252, 252), "glasses": False, "cap": True,
           "brow": (94, 66, 51), "hair_style": "medium"},
}

# expression -> (brow, eye, mouth)
EXPR = {
    "normal": ("flat", "normal", "closed"),
    "surprise": ("up", "wide", "o"),
    "happy": ("up", "happy", "smile"),
    "worry": ("in", "worry", "wavy"),
    "smug": ("raise", "half", "smirk"),
}
# mouth shapes cycled while speaking (viseme-ish, zh-friendly)
VISEMES = ["a", "i", "u", "e", "o", "m", "a", "i", "closed"]


def _ell(d, box, fill, outline=INK, width=LW):
    d.ellipse(box, fill=fill, outline=outline, width=width)


def _line(d, pts, fill=INK, width=LW, joint="curve"):
    d.line(pts, fill=fill, width=width, joint=joint)


def draw_base(who: str) -> Image.Image:
    """Static layer: torso, neck, head, ears, hair, cap. No face, no glasses."""
    c = CHARS[who]
    img = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = CX
    # torso
    d.rounded_rectangle([cx - 210, 560, cx + 210, CH + 40], radius=90,
                        fill=c["top"], outline=INK, width=LW)
    d.polygon([(cx - 70, 560), (cx + 70, 560), (cx, 650)], fill=c["accent"], outline=INK)
    d.line([(cx - 70, 560), (cx, 650), (cx + 70, 560)], fill=INK, width=LW)
    # neck
    d.rounded_rectangle([cx - 46, 470, cx + 46, 600], radius=20, fill=SKIN_SH,
                        outline=INK, width=LW)
    # head
    _ell(d, [cx - 150, 180, cx + 150, 510], c["skin"])
    # ears
    _ell(d, [cx - 176, 320, cx - 138, 392], c["skin"])
    _ell(d, [cx + 138, 320, cx + 176, 392], c["skin"])
    # hair
    if c["hair_style"] == "short":
        d.pieslice([cx - 155, 165, cx + 155, 430], 180, 360, fill=c["hair"], outline=INK, width=LW)
        d.polygon([(cx - 155, 300), (cx - 120, 250), (cx - 40, 300), (cx + 40, 250),
                   (cx + 120, 300), (cx + 155, 300), (cx + 155, 230), (cx - 155, 230)],
                  fill=c["hair"], outline=INK)
    else:
        d.pieslice([cx - 158, 160, cx + 158, 440], 180, 360, fill=c["hair"], outline=INK, width=LW)
        d.polygon([(cx - 158, 320), (cx - 110, 270), (cx - 30, 320), (cx + 50, 265),
                   (cx + 130, 320), (cx + 158, 320), (cx + 158, 225), (cx - 158, 225)],
                  fill=c["hair"], outline=INK)
        d.polygon([(cx - 158, 300), (cx - 190, 380), (cx - 150, 400)], fill=c["hair"], outline=INK)
        d.polygon([(cx + 158, 300), (cx + 190, 380), (cx + 150, 400)], fill=c["hair"], outline=INK)
    if c["cap"]:
        d.pieslice([cx - 168, 150, cx + 168, 360], 180, 360, fill=(196, 92, 82), outline=INK, width=LW)
        d.rounded_rectangle([cx - 190, 300, cx + 120, 340], radius=18, fill=(196, 92, 82),
                            outline=INK, width=LW)
        d.ellipse([cx + 40, 296, cx + 70, 344], fill=(196, 92, 82), outline=INK, width=LW)
    return img


def _draw_brows(d, who, mode):
    col = CHARS[who]["brow"]
    yb = EY - 64
    w = LW + 2
    if mode == "up":
        _line(d, [(EX1 - 44, yb - 10), (EX1 + 44, yb - 36)], fill=col, width=w)
        _line(d, [(EX2 - 44, yb - 36), (EX2 + 44, yb - 10)], fill=col, width=w)
    elif mode == "in":  # worried
        _line(d, [(EX1 - 44, yb - 36), (EX1 + 44, yb - 2)], fill=col, width=w)
        _line(d, [(EX2 - 44, yb - 2), (EX2 + 44, yb - 36)], fill=col, width=w)
    elif mode == "raise":  # smug: one raised
        _line(d, [(EX1 - 44, yb - 48), (EX1 + 44, yb - 38)], fill=col, width=w)
        _line(d, [(EX2 - 44, yb - 12), (EX2 + 44, yb - 12)], fill=col, width=w)
    elif mode == "angry":
        _line(d, [(EX1 - 44, yb - 2), (EX1 + 44, yb - 32)], fill=col, width=w)
        _line(d, [(EX2 - 44, yb - 32), (EX2 + 44, yb - 2)], fill=col, width=w)
    else:  # flat
        _line(d, [(EX1 - 42, yb - 16), (EX1 + 42, yb - 16)], fill=col, width=w)
        _line(d, [(EX2 - 42, yb - 16), (EX2 + 42, yb - 16)], fill=col, width=w)


def _draw_eyes(d, mode):
    if mode in ("blink", "happy"):
        for ex in (EX1, EX2):
            dy = -26 if mode == "happy" else 0
            _line(d, [(ex - 32, EY + 3), (ex, EY + dy), (ex + 32, EY + 3)], width=LW + 1)
    elif mode == "wide":
        for ex in (EX1, EX2):
            _ell(d, [ex - 34, EY - 40, ex + 34, EY + 40], (255, 255, 255))
            _ell(d, [ex - 12, EY - 15, ex + 12, EY + 15], INK, width=4)
            _ell(d, [ex - 2, EY - 22, ex + 10, EY - 10], (255, 255, 255), outline=None, width=0)
    elif mode == "half":
        for ex in (EX1, EX2):
            _ell(d, [ex - 30, EY - 30, ex + 30, EY + 30], (255, 255, 255))
            _ell(d, [ex - 12, EY - 8, ex + 12, EY + 16], INK, width=4)
            _line(d, [(ex - 30, EY - 16), (ex + 30, EY - 16)], width=LW + 1)
    elif mode == "worry":
        for ex in (EX1, EX2):
            _ell(d, [ex - 22, EY - 22, ex + 22, EY + 22], (255, 255, 255))
            _ell(d, [ex - 10, EY - 10, ex + 10, EY + 10], INK, width=4)
    elif mode == "angry":
        for ex in (EX1, EX2):
            _ell(d, [ex - 22, EY - 18, ex + 22, EY + 22], (255, 255, 255))
            _ell(d, [ex - 10, EY - 8, ex + 10, EY + 14], INK, width=4)
            _line(d, [(ex - 26, EY - 26), (ex + 26, EY - 8)], width=LW + 1)
    elif mode == "starry":
        for ex in (EX1, EX2):
            d.ellipse([ex - 28, EY - 28, ex + 28, EY + 28], fill=INK)
            for a in range(0, 360, 45):
                r = math.radians(a)
                d.line([(ex + 9 * math.cos(r), EY + 9 * math.sin(r)),
                        (ex + 25 * math.cos(r), EY + 25 * math.sin(r))], fill=(250, 250, 250), width=4)
    else:  # normal
        for ex in (EX1, EX2):
            _ell(d, [ex - 22, EY - 28, ex + 22, EY + 26], INK, width=4)
            _ell(d, [ex - 2, EY - 20, ex + 10, EY - 8], (255, 255, 255), outline=None, width=0)


def _blush(d):
    for ex in (EX1 - 8, EX2 + 8):
        d.ellipse([ex - 36, EY + 28, ex + 36, EY + 60], fill=(242, 158, 158))


def _draw_mouth(d, mode):
    """mouth shapes; 'a/i/u/e/o' = speaking visemes, others = expression."""
    m = MY
    if mode == "a":
        _ell(d, [CX - 30, m - 6, CX + 30, m + 50], (122, 60, 60))
    elif mode == "i":
        _ell(d, [CX - 44, m + 2, CX + 44, m + 28], (122, 60, 60))
    elif mode == "u":
        _ell(d, [CX - 20, m + 0, CX + 20, m + 36], (122, 60, 60))
    elif mode == "o":
        _ell(d, [CX - 25, m + 0, CX + 25, m + 36], (122, 60, 60))
    elif mode == "e":
        _ell(d, [CX - 38, m + 2, CX + 38, m + 30], (122, 60, 60))
    elif mode == "m":
        _line(d, [(CX - 30, m + 2), (CX + 30, m + 2)])
    elif mode == "big":
        _ell(d, [CX - 44, m - 10, CX + 44, m + 60], (122, 60, 60))
    elif mode == "smile":
        d.arc([CX - 60, m - 40, CX + 60, m + 40], 15, 165, fill=INK, width=LW)
    elif mode == "wavy":
        _line(d, [(CX - 50, m), (CX - 25, m - 16), (CX, m + 4), (CX + 25, m - 16),
                  (CX + 50, m)])
    elif mode == "smirk":
        d.arc([CX - 55, m - 30, CX + 35, m + 30], 10, 120, fill=INK, width=LW)
    else:  # closed
        _line(d, [(CX - 26, m), (CX + 26, m)])


def _draw_marks(d, who, expr):
    if expr == "worry":
        # sweat drop
        d.polygon([(CX + 148, 232), (CX + 180, 292), (CX + 116, 292)],
                  fill=(120, 180, 220), outline=INK, width=5)
        d.ellipse([CX + 116, 272, CX + 180, 308], fill=(120, 180, 220))
        # gloom lines above head
        for dx in (-78, 0, 78):
            _line(d, [(CX + dx, 142), (CX + dx, 196)], fill=(120, 150, 180), width=7, joint=None)
    elif expr == "smug":
        for sx, sy in ((CX + 154, 202), (CX - 164, 224)):
            _line(d, [(sx - 18, sy), (sx + 18, sy)], (240, 200, 90), width=6)
            _line(d, [(sx, sy - 18), (sx, sy + 18)], (240, 200, 90), width=6)
    elif expr == "surprise":
        for sx in (CX - 182, CX + 182):
            for ax, ay in ((-34, -34), (-4, -50), (26, -36)):
                _line(d, [(sx + ax, 216 + ay), (sx + ax * 0.3, 172 + ay * 0.3)],
                      fill=(90, 96, 110), width=6)
    elif expr == "happy":
        for sx, sy in ((CX - 154, 232), (CX + 154, 220)):
            _line(d, [(sx - 16, sy), (sx + 16, sy)], (240, 200, 90), width=6)
            _line(d, [(sx, sy - 16), (sx, sy + 16)], (240, 200, 90), width=6)


def draw_face(who: str, brow=None, eye=None, mouth=None, expr="normal", blush=False) -> Image.Image:
    """Animated face overlay (transparent, same canvas)."""
    img = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if brow is None or eye is None or mouth is None:
        e_b, e_e, e_m = EXPR.get(expr, EXPR["normal"])
        brow = brow or e_b
        eye = eye or e_e
        mouth = mouth or e_m
    if blush or expr in ("happy", "smug"):
        _blush(d)
    _draw_brows(d, who, brow)
    _draw_eyes(d, eye)
    _draw_mouth(d, mouth)
    if CHARS[who]["glasses"]:
        _ell(d, [CX - 86, EY - 44, CX - 30, EY + 30], None, width=LW - 2)
        _ell(d, [CX + 30, EY - 44, CX + 86, EY + 30], None, width=LW - 2)
        _line(d, [(CX - 30, EY - 8), (CX + 30, EY - 8)], width=LW - 3)
        _line(d, [(CX - 86, EY - 8), (CX - 138, EY - 2)], width=LW - 3)
        _line(d, [(CX + 86, EY - 8), (CX + 138, EY - 2)], width=LW - 3)
    _draw_marks(d, who, expr)
    return img


def draw_character(who: str, expr: str) -> Image.Image:
    img = draw_base(who)
    img.alpha_composite(draw_face(who, expr=expr))
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for who in CHARS:
        for expr in EXPR:
            draw_character(who, expr).save(OUT / f"{who}_{expr}.png")
            n += 1
    print(f"characters -> {OUT} ({n} sprites)")


if __name__ == "__main__":
    main()
