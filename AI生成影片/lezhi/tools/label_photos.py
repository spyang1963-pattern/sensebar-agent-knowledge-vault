"""Label portfolio crop photos with Gemini Vision (cached).

Writes lezhi/assets/labels.json = { "filename": "short zh-TW description" }.
Used by script_engine so narration scenes can be matched to the right photo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LEZHI = Path(__file__).resolve().parents[1]
CROPS = LEZHI / "assets" / "crops"
LABELS = LEZHI / "assets" / "labels.json"
MODEL = "gemini-3.5-flash-lite"


def load_key() -> str:
    import os
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"].strip()
    p = Path.home() / ".gemini_api_key"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    sys.exit("[ERR] 找不到 Gemini API Key")


def main():
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=load_key())
    labels = {}
    if LABELS.exists():
        labels = json.loads(LABELS.read_text(encoding="utf-8-sig"))

    imgs = sorted([p for p in CROPS.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png")])
    prompt = ("這是一張室內設計作品集的照片。請用繁體中文給一句 12~22 字的描述，"
              "重點寫：空間類型（客廳/臥室/廚房/浴室/玄關/餐廳/書房…）＋主要材質或家具"
              "（木地板、系統櫃、石材、燈具…）＋視角（全景/局部/細節）。"
              "只輸出這一句，不要標點以外的廢話，不要加引號。")
    for p in imgs:
        if p.name in labels:
            continue
        try:
            part = types.Part.from_bytes(data=p.read_bytes(), mime_type="image/jpeg")
            r = client.models.generate_content(model=MODEL, contents=[prompt, part],
                                               config=types.GenerateContentConfig(temperature=0.2))
            labels[p.name] = (r.text or "").strip().replace("\n", " ")[:40]
            print(f"  {p.name} -> {labels[p.name]}")
        except Exception as e:
            print(f"  [skip] {p.name}: {e}")
    LABELS.write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"labels -> {LABELS} ({len(labels)} photos)")


if __name__ == "__main__":
    main()
