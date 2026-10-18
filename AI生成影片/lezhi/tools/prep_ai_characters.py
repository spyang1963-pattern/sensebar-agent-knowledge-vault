"""Post-process AI characters + build comparison sheets.

1. Make near-white background transparent (raw files backed up once to _raw/).
2. Build _sheet_A.png (programmatic), _sheet_B.png (AI), _compare.png (A vs B).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
A_DIR = ROOT / "assets" / "characters"
B_DIR = ROOT / "assets" / "characters_ai"
RAW = B_DIR / "_raw"

FONT = r"C:\Windows\Fonts\msjh.ttc"
EXPRS = ["normal", "surprise", "happy", "worry", "smug"]
WHOS = {"ren": "阿忍 (設計師)", "le": "小樂 (屋主)"}


def cutout_white(path: Path):
    img = Image.open(path).convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r > 238 and g > 238 and b > 238:
                px[x, y] = (r, g, b, 0)
            elif r > 224 and g > 224 and b > 224:
                px[x, y] = (r, g, b, 140)
    img.save(path)


def prep_ai():
    RAW.mkdir(parents=True, exist_ok=True)
    for p in sorted(B_DIR.glob("*.png")):
        raw = RAW / p.name if not (RAW / p.name).exists() else None
        if raw:
            shutil.copy2(p, raw)
        cutout_white(p)
        print(f"  cutout {p.name}")


def _font(sz):
    try:
        return ImageFont.truetype(FONT, sz)
    except Exception:
        return ImageFont.load_default()


def build_sheet(d: Path, out: Path, title: str, bg=(252, 252, 252)):
    cell = 300
    pad = 10
    lab = 150
    top = 70
    W = lab + len(EXPRS) * (cell + pad) + pad
    H = top + len(WHOS) * (cell + pad) + pad
    sheet = Image.new("RGB", (W, H), bg)
    dr = ImageDraw.Draw(sheet)
    dr.text((pad, 22), title, font=_font(34), fill=(21, 26, 27))
    for ci, e in enumerate(EXPRS):
        dr.text((lab + ci * (cell + pad) + 8, 22), e, font=_font(22), fill=(117, 137, 133))
    for ri, (who, name) in enumerate(WHOS.items()):
        y = top + ri * (cell + pad)
        dr.text((pad, y + cell // 2), name, font=_font(24), fill=(21, 26, 27))
        for ci, e in enumerate(EXPRS):
            p = d / f"{who}_{e}.png"
            x = lab + ci * (cell + pad)
            dr.rectangle([x, y, x + cell, y + cell], fill=(255, 255, 255), outline=(220, 220, 220))
            if p.exists():
                im = Image.open(p).convert("RGBA")
                im.thumbnail((cell - 8, cell - 8))
                sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2), im)
    sheet.save(out)
    print(f"  {out.name} {sheet.size}")


def main():
    prep_ai()
    build_sheet(A_DIR, ROOT / "assets" / "_sheet_A.png", "A｜程式手繪版")
    build_sheet(B_DIR, ROOT / "assets" / "_sheet_B.png", "B｜AI 生成版 (Pollinations flux)")


if __name__ == "__main__":
    main()
