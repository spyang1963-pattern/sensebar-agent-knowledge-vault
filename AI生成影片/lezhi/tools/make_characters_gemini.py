"""Generate the same 2 characters x 5 expressions with Gemini image models.

Base portrait first, then expressions are generated WITH the base as a
reference image so the character stays consistent.

Output -> lezhi/assets/characters_gemini/{who}_{expr}.png
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "assets" / "characters_gemini"
MODEL = "gemini-3-pro-image"

STYLE = ("簡潔扁平向量插畫風格，粗黑線條、色塊填色、2D flat design，"
         "正面半身（頭到胸口），置中，純白色背景，不要文字、不要浮水印、不要陰影。")

CHARS = {
    "ren": "一位年輕男性室內設計師，短黑髮側分，戴圓框黑色細邊眼鏡，"
           f"穿鼠尾草綠色襯衫。{STYLE}",
    "le": "一位年輕屋主，棕色短髮，戴紅色棒球帽，穿橘色T恤，"
          f"神情活潑。{STYLE}",
}

EXPR = {
    "normal": "表情平靜、自然微笑。",
    "surprise": "表情非常驚訝，眼睛睜大、眉毛上揚、嘴巴張開成O型。",
    "happy": "表情開心大笑，眼睛笑成彎彎的兩條線，嘴巴大笑。",
    "worry": "表情苦惱，眉毛皺成八字，嘴巴嘟成一條波浪線，旁邊有一滴汗。",
    "smug": "表情得意，半瞇眼、嘴角上揚露出奸笑，旁邊有閃亮星星。",
}


def load_key() -> str:
    import os
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"].strip()
    p = Path.home() / ".gemini_api_key"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    sys.exit("[ERR] 找不到 Gemini API Key")


def gen(client, types, contents):
    r = client.models.generate_content(model=MODEL, contents=contents)
    for part in r.candidates[0].content.parts:
        idata = getattr(part, "inline_data", None)
        if idata and getattr(idata, "data", None):
            return idata.data
    return None


def main():
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=load_key())
    OUT.mkdir(parents=True, exist_ok=True)
    for who, desc in CHARS.items():
        base_path = OUT / f"{who}_base.png"
        if not base_path.exists():
            for attempt in range(3):
                try:
                    data = gen(client, types, [f"{desc}\n表情平靜、自然微笑。"])
                    if data:
                        base_path.write_bytes(data)
                        print(f"  base {who} ok")
                        break
                except Exception as e:
                    print(f"  base {who} retry {attempt}: {e}")
                    time.sleep(5)
            time.sleep(2)
        ref = base_path.read_bytes() if base_path.exists() else None
        for expr, ed in EXPR.items():
            p = OUT / f"{who}_{expr}.png"
            if p.exists():
                continue
            contents = [f"沿用這張角色（{who}），只改變表情：{ed}\n務必維持完全相同的臉型、髮型、服裝、配色與畫風。{STYLE}"]
            if ref:
                contents.append(types.Part.from_bytes(data=ref, mime_type="image/png"))
            for attempt in range(3):
                try:
                    data = gen(client, types, contents)
                    if data:
                        p.write_bytes(data)
                        print(f"  {who}_{expr} ok")
                        break
                except Exception as e:
                    print(f"  {who}_{expr} retry {attempt}: {e}")
                    time.sleep(5)
            time.sleep(2)
    print(f"gemini characters -> {OUT}")


if __name__ == "__main__":
    main()
