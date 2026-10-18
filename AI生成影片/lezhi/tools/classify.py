"""Classify extracted images by luminance stats to tell real photos from decor/blanks."""
from pathlib import Path
from PIL import Image
import numpy as np

P = Path(r"D:\AI-Agent-Workspace\AI生成影片\lezhi\assets\photos")
files = sorted(P.glob("*.jpeg"))
print(f"{'file':44}{'KB':>6}{'mean':>7}{'std':>7}{'uniq%':>7}  verdict")
big = []
for f in files:
    im = Image.open(f).convert("RGB")
    small = im.copy()
    small.thumbnail((160, 160))
    a = np.asarray(small).astype(np.float32)
    g = a.mean(2)
    std, mean = float(g.std()), float(g.mean())
    q = (a // 16).astype(np.uint8).reshape(-1, 3)
    uniq = len(set(map(tuple, q))) / len(q) * 100
    verdict = "SOLID?" if std < 12 else ("PHOTO" if std > 25 else "flat")
    kb = f.stat().st_size // 1024
    if kb > 500:
        big.append(f.name)
    print(f"{f.name:44}{kb:6}{mean:7.0f}{std:7.1f}{uniq:7.1f}  {verdict}")
print("\nLARGE(>500KB):", big)
