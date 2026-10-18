"""Generate brand cards (hook + end card) in LE / 押忍 brand colours.

Font: 微軟正黑體 (msjh / msjhbd) as requested.
Palette: white #FCFCFC, sage #758985, charcoal #151A1B (sampled from portfolio).
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BG = (252, 252, 252)
SAGE = (117, 137, 133)
INK = (21, 26, 27)
FONT_REG = r"C:\Windows\Fonts\msjh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msjhbd.ttc"
OUT = Path(r"D:\AI-Agent-Workspace\AI生成影片\lezhi\assets\cards")

COMPANY = "押忍室內裝修設計有限公司"
TAGLINE = "高雄・屏東｜住宅室內設計"
CONTACT = "0988-813-511"
CTA = "預約免費諮詢"


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def center(draw, y, text, f, fill):
    w = draw.textlength(text, font=f)
    draw.text(((W - w) / 2, y), text, font=f, fill=fill)


def end_card() -> Path:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_comp = font(FONT_BOLD, 92)
    f_tag = font(FONT_REG, 46)
    f_cont = font(FONT_REG, 52)
    f_cta = font(FONT_BOLD, 54)

    d.rectangle([0, 0, W, 16], fill=SAGE)
    y = H * 0.34
    center(d, y, COMPANY, f_comp, INK)          # line 1
    center(d, y + 130, TAGLINE, f_tag, SAGE)    # line 2
    # divider
    d.line([W * 0.28, y + 250, W * 0.72, y + 250], fill=(210, 214, 212), width=3)
    center(d, y + 300, CONTACT, f_cont, INK)
    center(d, y + 380, "kse49210@gmail.com", f_cont, SAGE)
    # CTA pill
    pill_w, pill_h = 520, 120
    px, py = (W - pill_w) / 2, y + 540
    d.rounded_rectangle([px, py, px + pill_w, py + pill_h], radius=pill_h // 2, fill=SAGE)
    cw = d.textlength(CTA, font=f_cta)
    d.text(((W - cw) / 2, py + (pill_h - 54) / 2 - 4), CTA, font=f_cta, fill=BG)

    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "endcard.png"
    img.save(p)
    return p


def hook_card(line1="18 坪小宅", line2="怎麼住得像 30 坪？") -> Path:
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    f1 = font(FONT_BOLD, 120)
    f2 = font(FONT_REG, 78)
    d.rectangle([W * 0.14, H * 0.40, W * 0.14 + 120, H * 0.40 + 12], fill=SAGE)
    w1 = d.textlength(line1, font=f1)
    d.text(((W - w1) / 2, H * 0.44), line1, font=f1, fill=BG)
    w2 = d.textlength(line2, font=f2)
    d.text(((W - w2) / 2, H * 0.44 + 180), line2, font=f2, fill=SAGE)
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "hook.png"
    img.save(p)
    return p


def _wrap(d, text, f, maxw):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur); cur = ""; continue
        if d.textlength(cur + ch, font=f) <= maxw:
            cur += ch
        else:
            lines.append(cur); cur = ch
    if cur:
        lines.append(cur)
    return lines


def scene_card(text, name, light=False):
    """One scene card: short punch phrase in brand colours."""
    bg, fg = (BG, INK) if light else (INK, BG)
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    size = 96 if len(text) <= 14 else 78 if len(text) <= 28 else 62
    f = font(FONT_BOLD, size)
    lines = _wrap(d, text, f, W * 0.80)[:7]
    lh = int(size * 1.35)
    y0 = (H - len(lines) * lh) / 2
    d.rectangle([W * 0.16, y0 - 80, W * 0.16 + 120, y0 - 68], fill=SAGE)
    for i, ln in enumerate(lines):
        w = d.textlength(ln, font=f)
        d.text(((W - w) / 2, y0 + i * lh), ln, font=f, fill=fg)
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}.png"
    img.save(p)
    return p


if __name__ == "__main__":
    print("hook   ->", hook_card())
    print("endcard->", end_card())
