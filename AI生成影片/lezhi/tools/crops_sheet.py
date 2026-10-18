"""Build a review contact sheet of the cropped photos."""
from pathlib import Path
from PIL import Image, ImageDraw

CROPS = Path(r"D:\AI-Agent-Workspace\AI生成影片\lezhi\assets\crops")
OUT = Path(r"D:\AI-Agent-Workspace\AI生成影片\lezhi\assets\_crops_sheet.jpg")

files = sorted(CROPS.glob("*.jpg"))
COLS, THUMB, PAD, LABEL = 5, 300, 8, 26
rows = (len(files) + COLS - 1) // COLS
W = COLS * (THUMB + PAD) + PAD
H = rows * (THUMB + LABEL + PAD) + PAD
sheet = Image.new("RGB", (W, H), (40, 40, 40))
draw = ImageDraw.Draw(sheet)

for i, f in enumerate(files):
    r, c = divmod(i, COLS)
    x = PAD + c * (THUMB + PAD)
    y = PAD + r * (THUMB + LABEL + PAD)
    im = Image.open(f).convert("RGB")
    im.thumbnail((THUMB, THUMB))
    sheet.paste(im, (x + (THUMB - im.width) // 2, y))
    draw.text((x + 2, y + THUMB + 4), f"{i + 1}. {f.stem[:34]}", fill=(220, 220, 220))

sheet.save(OUT, quality=88)
print("sheet:", OUT, sheet.size, "files:", len(files))
