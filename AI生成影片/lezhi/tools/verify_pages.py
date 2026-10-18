"""Verify whether the large embedded images are full-page rasters, and locate photos."""
import fitz
import numpy as np
from pathlib import Path
from PIL import Image

SRC = Path(r"D:\!!AI agent 工作指南\3師爸近期影音repo彙整\樂之作品\2024LE作品集 Copy.pdf")
ASSETS = Path(r"D:\AI-Agent-Workspace\AI生成影片\lezhi\assets\photos")
doc = fitz.open(SRC)

for pno in [3, 5]:  # pages 4 and 6
    page = doc[pno]
    info = page.get_image_info(xrefs=True)
    print(f"--- page {pno+1} size={page.rect.width:.0f}x{page.rect.height:.0f} ---")
    for im in info:
        bb = im["bbox"]
        print(f"  xref={im['xref']:>4} {im['width']}x{im['height']} bbox=({bb[0]:.0f},{bb[1]:.0f},{bb[2]:.0f},{bb[3]:.0f})")
    # render page at width 4299
    zoom = 4299 / page.rect.width
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    render = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
    print(f"  render={pix.width}x{pix.height}")

# compare embedded large image vs render for page 4
page = doc[3]
zoom = 4299 / page.rect.width
pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
render = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
big = np.asarray(Image.open(ASSETS / "p04_d9575074260a_4299x3024.jpeg").convert("RGB"))
if big.shape != render.shape:
    big = np.asarray(Image.fromarray(big).resize((render.shape[1], render.shape[0])))
mae = float(np.abs(big.astype(np.float32) - render.astype(np.float32)).mean())
print(f"\npage4 embedded-big vs render MAE = {mae:.1f} (0=identical)")
