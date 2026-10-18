"""AI-generated version of the 2 characters x 5 expressions, via Pollinations (free).

Gemini image models are quota-locked on the free tier, so we use Pollinations.
A fixed seed per character keeps the look roughly consistent across expressions.

Output -> lezhi/assets/characters_ai/{who}_{expr}.png
"""
from __future__ import annotations

import time
import urllib.parse
import urllib.request
from pathlib import Path

# Pollinations anonymous tier rate-limits hard: pace requests and back off on 402.
PACE = 20

OUT = Path(__file__).resolve().parents[1] / "assets" / "characters_ai"

CHARS = {
    "ren": (101, "flat vector illustration of a young male interior designer, "
                 "short black side-parted hair, round thin black glasses, sage green shirt, "
                 "upper body, facing forward, centered, pure white background, "
                 "clean minimal cartoon, thick black outlines, no text, no watermark"),
    "le": (202, "flat vector illustration of a young homeowner, short brown hair, "
                "red baseball cap, orange t-shirt, upper body, facing forward, centered, "
                "pure white background, clean minimal cartoon, thick black outlines, no text, no watermark"),
}

EXPR = {
    "normal": "neutral calm smile",
    "surprise": "very surprised expression, wide eyes, raised eyebrows, open mouth",
    "happy": "laughing happily, eyes closed in happy arcs, big smile",
    "worry": "worried frown, slanted eyebrows, wavy mouth, a sweat drop",
    "smug": "smug confident smirk, half-closed eyes, a sparkle",
}


def fetch(prompt, seed, w=768, h=960):
    q = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{q}?width={w}&height={h}&nologo=true&seed={seed}&model=flux"
    req = urllib.request.Request(url, headers={"Referer": "https://pollinations.ai/"})
    return urllib.request.urlopen(req, timeout=120).read()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for who, (seed, desc) in CHARS.items():
        for expr, ed in EXPR.items():
            p = OUT / f"{who}_{expr}.png"
            if p.exists():
                print(f"  skip {p.name}")
                continue
            for attempt in range(6):
                try:
                    data = fetch(f"{desc}, {ed}", seed)
                    if data and len(data) > 3000:
                        p.write_bytes(data)
                        print(f"  {p.name} ok ({len(data)} bytes)")
                        break
                except Exception as e:
                    print(f"  {p.name} retry {attempt}: {str(e)[:80]}")
                    time.sleep(PACE)
            time.sleep(PACE)
    print(f"ai characters -> {OUT}")


if __name__ == "__main__":
    main()
