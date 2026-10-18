"""Build a labelled contact sheet of the extracted assets for quick review."""
from pathlib import Path
from PIL import Image, ImageDraw

PHOTOS = Path(r"D:\AI-Agent-Workspace\AI生成影片\lezhi\assets\photos")
OUT = Path(r"D:\AI-Agent-Workspace\AI生成影片\lezhi\assets\_contact_sheet.jpg")

files = sorted(PHOTOS.glob("*.jpeg"))
COLS, THUMB, PAD, LABEL = 10, 180, 6, 16
rows = (len(files) + COLS - 1) // COLS
W = COLS * (THUMB + PAD) + PAD
H = rows * (THUMB + LABEL + PAD) + PAD
sheet = Image.new("RGB", (W, H), (30, 30, 30))
draw = ImageDraw.Draw(sheet)

for i, f in enumerate(files):
    r, c = divmod(i, COLS)
    x = PAD + c * (THUMB + PAD)
    y = PAD + r * (THUMB + LABEL + PAD)
    try:
        im = Image.open(f).convert("RGB")
        im.thumbnail((THUMB, THUMB))
        sheet.paste(im, (x + (THUMB - im.width) // 2, y))
    except Exception as exc:  # noqa: BLE001
        draw.text((x, y), f"ERR {exc}", fill=(255, 0, 0))
    kb = f.stat().st_size // 1024
    draw.text((x, y + THUMB + 2), f"{f.stem.split('_')[0]} {kb}K", fill=(200, 200, 200))

sheet.save(OUT, quality=85)
print("sheet:", OUT, sheet.size, "files:", len(files))
