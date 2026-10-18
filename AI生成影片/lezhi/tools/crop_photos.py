"""Organise extracted assets and auto-crop individual photos by layout gutters.

The portfolio PDF stores a few full-page raster layers per page: one content
layer (real photos) plus near-white blank layers. We keep the content plates,
rename them by project, and segment each plate into photo cells using white
gutter separators (text is blurred away by block pooling).
"""
import shutil
from pathlib import Path
import numpy as np
from PIL import Image

ASSETS = Path(r"D:\AI-Agent-Workspace\AI生成影片\lezhi\assets")
PHOTOS = ASSETS / "photos"
PLATES = ASSETS / "plates"
CROPS = ASSETS / "crops"
BLANKS = ASSETS / "_blank_layers"
for d in (PLATES, CROPS, BLANKS):
    d.mkdir(parents=True, exist_ok=True)

CONTENT = {
    "p01_fcc4da157dd6_4299x3024.jpeg": "00_cover.jpg",
    "p03_9ee673de29e6_4299x3024.jpeg": "01_index_about.jpg",
    "p04_d9575074260a_4299x3024.jpeg": "02_h-time_a.jpg",
    "p05_3a96f04b98a9_4299x3024.jpeg": "03_h-time_b.jpg",
    "p06_e6f0193b734b_4299x3024.jpeg": "04_taipu_mingrihui_a.jpg",
    "p07_75c8fd0be2d8_4299x3024.jpeg": "05_taipu_mingrihui_b.jpg",
    "p08_3d931b30f4fe_4299x3024.jpeg": "06_taipu_mingrihui_c.jpg",
    "p09_39d5a5cac604_4299x3024.jpeg": "07_liuli_yuan.jpg",
    "p10_ddfa8d0c34b0_4299x3024.jpeg": "08_rongyao_shiji.jpg",
}

BLOCK = 16
MIN_PX = 260


def content_mask(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape
    hb, wb = h // BLOCK, w // BLOCK
    pooled = gray[: hb * BLOCK, : wb * BLOCK].reshape(hb, BLOCK, wb, BLOCK).mean((1, 3))
    return pooled < 240  # True = content block


def gutters(mask: np.ndarray, axis: int, min_frac: float = 0.03) -> list[int]:
    frac = mask.mean(axis=axis)
    return [i for i, v in enumerate(frac) if v < min_frac]


def segments(gut: list[int], n: int, min_blocks: int) -> list[tuple[int, int]]:
    cuts = [i for i in gut]
    segs, start = [], 0
    for i in range(n):
        if i in set(cuts):
            if i - start >= min_blocks:
                segs.append((start, i))
            start = i + 1
    if n - start >= min_blocks:
        segs.append((start, n))
    return segs


def main() -> None:
    moved = 0
    for f in sorted(PHOTOS.glob("*.jpeg")):
        if f.name in CONTENT:
            shutil.move(str(f), str(PLATES / CONTENT[f.name]))
        else:
            shutil.move(str(f), str(BLANKS / f.name))
            moved += 1
    print(f"plates={len(CONTENT)} blanks_moved={moved}")

    for plate in sorted(PLATES.glob("*.jpg")):
        img = Image.open(plate).convert("RGB")
        full = np.asarray(img)
        gray = np.asarray(img.convert("L")).astype(np.float32)
        mask = content_mask(gray)
        hb, wb = mask.shape
        rows = segments(gutters(mask, 1), hb, MIN_PX // BLOCK)
        cols = segments(gutters(mask, 0), wb, MIN_PX // BLOCK)
        cells = 0
        for ri, (r0, r1) in enumerate(rows):
            for ci, (c0, c1) in enumerate(cols):
                sub = mask[r0:r1, c0:c1]
                if sub.mean() < 0.55:
                    continue
                px = (c0 * BLOCK, r0 * BLOCK, c1 * BLOCK, r1 * BLOCK)
                crop = Image.fromarray(full[px[1]:px[3], px[0]:px[2]])
                if crop.width < MIN_PX or crop.height < MIN_PX:
                    continue
                cv = np.asarray(crop.convert("L")).astype(np.float32)
                out = CROPS / f"{plate.stem}__r{ri}c{ci}.jpg"
                crop.save(out, quality=92)
                cells += 1
                print(f"  {plate.stem}: cell r{ri}c{ci} {crop.width}x{crop.height} std={cv.std():.0f}")
        print(f"{plate.name}: rows={len(rows)} cols={len(cols)} cells={cells}")


if __name__ == "__main__":
    main()
