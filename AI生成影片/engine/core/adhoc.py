"""engine.core.adhoc - 即興型產片：最低輸入 → 一支短片（Pack 驅動、通用）.

用法（個人問候 Pack）：
  python -X utf8 engine/core/adhoc.py --pack personal_greeting \
      --occasion 母親節 --to 媽媽 --relation 母子 \
      --wish "謝謝您這些年的照顧，我愛您" --lines 8 --render

流程：讀 Pack → 組通用 prompt → Gemini 產腳本 → 寫入 Pack 的 scripts/
→ （可選）依風格 registry 找 renderer 產片到 Pack 的 output/。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))
from core import pack as epack   # noqa: E402
from core import registry as reg  # noqa: E402
from core import naming as ename  # noqa: E402
from core import llm              # noqa: E402

EXPRS = ("normal", "surprise", "happy", "worry", "smug")


def build_prompt(pack, fields, chars, labels):
    char_desc = "、".join(f"{k}（{labels.get(k, k)}）" for k in chars)
    return f"""你是「{pack.get('name', '影片')}」短影音的編劇。請寫一支「{fields['occasion']}」的二人問候短片。

【對象】{fields['to']}（關係：{fields['relation']}）
【想說的話／重點】{fields['wish']}

【規則】
- 全繁體中文、口語、真誠，像當面在對他說話；每句 ≤ 18 字。
- 共 {fields['lines']} 句，雙方輪流發言，speaker 只能用：{char_desc}。
- 有起承轉合：開場問候 → 具體回憶或感謝 → 祝福 → 溫暖收尾。
- 嚴禁罐頭、嚴禁長篇大論、嚴禁「大家好」開場。
- expr 只能是：normal / surprise / happy / worry / smug。

【輸出】只輸出 JSON，不要任何其他文字或 markdown 圍籬：
{{"title": "一句話標題",
  "scenes": [{{"speaker": "{chars[0]}", "text": "第一句", "expr": "happy"}}]}}
"""


def assemble_dialog(pack, data, fields, style, slug):
    chars = pack.get("characters") or ["ren", "le"]
    scenes = []
    for s in data.get("scenes", []):
        text = (s.get("text") or "").strip()
        if not text:
            continue
        who = s.get("speaker") if s.get("speaker") in chars else chars[0]
        expr = s.get("expr") if s.get("expr") in EXPRS else "normal"
        scenes.append({"speaker": who, "text": text, "expr": expr})
    return {
        "title": data.get("title") or f"{fields['occasion']}問候",
        "pack": pack.get("key"), "topic_id": slug, "style": style, "version": 1,
        "format": "dialog",
        "scenes": scenes,
    }


def slugify(s):
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "_", s).strip("_")
    return s or "greeting"


def main():
    ap = argparse.ArgumentParser(description="即興型產片（Pack 驅動）")
    ap.add_argument("--pack", default="personal_greeting")
    ap.add_argument("--slug", default=None, help="題目 id（預設由場合/對象產生）")
    ap.add_argument("--occasion", required=True, help="場合，如 母親節 / 生日")
    ap.add_argument("--to", required=True, help="對象，如 媽媽")
    ap.add_argument("--relation", default="朋友", help="關係")
    ap.add_argument("--wish", default="", help="想說的話／重點")
    ap.add_argument("--lines", type=int, default=8)
    ap.add_argument("--style", default=None, help="覆寫風格（預設用 Pack 的 style_default）")
    ap.add_argument("--render", action="store_true", help="產完腳本後直接渲染")
    args = ap.parse_args()

    pack = epack.load(args.pack)
    style = args.style or pack.get("style_default") or "comic"
    st = reg.style(style)
    if not st:
        sys.exit(f"[ERR] 風格 {style} 不在 registry")
    fmt = st.get("format", "narr")
    if fmt != "dialog":
        sys.exit(f"[ERR] adhoc 目前僅支援 dialog 風格（{style} 是 {fmt}）")

    slug = args.slug or f"{slugify(args.occasion)}_{slugify(args.to)}_{time.strftime('%Y%m%d')}"
    chars = pack.get("characters") or ["ren", "le"]
    labels = pack.get("character_labels") or {}
    fields = {"occasion": args.occasion, "to": args.to, "relation": args.relation,
              "wish": args.wish or f"想對{args.to}說的話", "lines": args.lines}

    print(f"[adhoc] Pack={args.pack}｜風格={style}｜題目={slug}")
    prompt = build_prompt(pack, fields, chars, labels)
    raw = llm.call_gemini(prompt)
    data = llm.parse_json(raw)
    script = assemble_dialog(pack, data, fields, style, slug)

    scripts_dir = epack.resolve(pack, pack.get("scripts_dir", "scripts"))
    scripts_dir.mkdir(parents=True, exist_ok=True)
    jp = scripts_dir / ename.script_filename(slug, style, 1)
    jp.write_text(__import__("json").dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[adhoc] 腳本 -> {jp}（{len(script['scenes'])} 句）")
    for i, s in enumerate(script["scenes"], 1):
        print(f"   {i}. [{s['speaker']}/{s['expr']}] {s['text']}")

    if not args.render:
        print("[adhoc] 未渲染（加 --render 可直接產片）")
        return

    renderer = reg.renderer_path(style)
    out_dir = epack.resolve(pack, pack.get("output_dir", "output")) / jp.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-X", "utf8", str(renderer),
           "--script", str(jp), "--out", str(out_dir)]
    print("[adhoc] 渲染：" + " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.stdout:
        print(p.stdout.rstrip())
    if p.returncode != 0:
        print("[stderr] " + (p.stderr or "").rstrip()[-1500:])
        sys.exit(p.returncode)
    films = list(out_dir.glob("*.mp4"))
    print(f"[adhoc] 完成 -> {films[0] if films else out_dir}")


if __name__ == "__main__":
    main()
