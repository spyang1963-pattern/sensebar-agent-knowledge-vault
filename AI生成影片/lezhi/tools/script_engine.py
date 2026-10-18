"""押忍工作室 · 腳本引擎（Gemini 編劇）

選一個題目 → 讀品牌口吻 + 支柱類型 + 張力技巧庫 + 真實數據/照片標註
→ Gemini 產出有鉤子、有張力的旁白與分鏡 → 寫出
    lezhi/scripts/{id}.json        （給 make_short.py 渲染）
    lezhi/scripts/{id}_腳本.md      （給人審核，關卡1）

用法：
  python script_engine.py --topic h-time_18ping
  python script_engine.py --topics quote_checklist storage_liters
  python script_engine.py --starred          # 所有 ★ 但尚無腳本的題目
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

LEZHI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
ENGINE = Path(__file__).resolve().parents[2] / "engine"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))
PACK = None
try:
    from core import script as esc       # prompt 組裝（預設無設定時不改變原行為）
    from core import registry as reg     # 風格/插槽登錄表
    from core import naming as ename     # 版本化命名
    from core import pack as epack       # 領域包（Manifest-first）
    _pack = epack.load()
    PACK = _pack.get("key")
    LEZHI = epack.content_root(_pack)
except Exception:  # engine 尚未就緒時不影響既有流程
    esc = reg = ename = None
QUEUE = LEZHI / "topics" / "queue.json"
PROFILE = LEZHI / "brand" / "profile.json"
PROJECTS = LEZHI / "assets" / "projects.json"
LABELS = LEZHI / "assets" / "labels.json"
CROPS = LEZHI / "assets" / "crops"
CARDS = LEZHI / "assets" / "cards"
SCRIPTS = LEZHI / "scripts"
MODEL = "gemini-3.8-flash"

TENSION = """【張力技巧（盡量用，不必全用）】
1. 前 3 秒鉤子：衝突／反差／懸念／數字衝擊，四選一。嚴禁「大家好」「今天要介紹」「為什麼我們要」「首先」。
2. 好奇心缺口：先拋問題，先別解答。
3. 對立結構：預算vs夢想、坪數vs需求、屋主期待vs工地現實。
4. 具體數字：只能用下面提供的數字，不要編。
5. 感官細節：不要說「很有質感」，要說看得見、摸得到、聽得到的東西。
6. 反轉：讓人以為是 A，結果是 B。
7. 結尾留一個鉤子，或直接邀請留言。"""

HARD_RULES = """【硬規則】
- 全繁體中文（嚴禁簡體字）、口語，像跟朋友講話；每句 ≤ 20 字。
- 共 6～8 句，總長 120～180 字（約 35～45 秒）。
- 至少 1 個具體數字、至少 1 個感官細節。
- 每個 scene 必須是「一個完整的句子」，不要一句話拆成兩鏡。
- 材質名稱每片最多出現 1 個；不要把材質清單當成內容。
- 不要旁白式說明；要有情緒、有節奏。
- 不要出現「宣導片腔」：不喊口號、不講大道理、不鋪陳背景。"""

DELIVERY = """【最重要：一定要交付，不能只有懸念】
- 標題若是「問數字」（例如要幾公升、要多少錢）：片中**必須出現一個明確數字或公式**，前面可加「大約」。
- 標題若是「清單」（例如 5 項、3 種）：片中**必須逐項講完，而且數量要和標題一致**——標題寫 5 項，就要真的講滿 5 項。
- 知識／避坑／科普類：可以用業界通用知識（例如常見追加項目、通用收納估算），但**不得假造特定案名**、也不要把通用數字講成某個真實案例的數字。
- 案例類（有實拍）：只能使用提供的真實數據與材質。
- 交付的內容要放在中段的句子裡，不要全部塞在結尾。"""


DIALOG_RULES = """【型式：兩人逗趣對白短劇】
角色：
- 阿忍（speaker: ren）：室內設計師。專業、講人話、偶爾自嘲，被問到要害會心虛。
- 小樂（speaker: le）：屋主。預算有限、狀況外、問題很多、愛吐槽、會講出大家的內心話。
要求：
- 共 8～12 句，一來一往，節奏快。每句 ≤ 20 字。總長 150～230 字（約 40～55 秒）。
- 要有「吐槽 + 反差 + 共鳴」：小樂負責製造衝突/疑問，阿忍負責拆解/反轉。
- 第一句就是鉤子，嚴禁「大家好」「今天要聊」。
- 全部繁體中文、口語。
- 每句給一個表情 expr，只能從這五個挑：normal / surprise / happy / worry / smug。
  依語氣選：驚訝=surprise、得意或吐槽=smug、無奈或心虛=worry、開心=happy、平淡=normal。
- 至少 1 個具體數字、至少 1 個感官或畫面細節。
- 最後一句是阿忍或小樂的引流 CTA。"""

HARD_RULES_DIALOG = """【硬規則】
- 全繁體中文（嚴禁簡體字）、口語；每句 ≤ 20 字。
- 不可以一人連續講超過 2 句。
- 不要旁白式說明、不要喊口號、不要鋪陳背景。
- 每個具體數字只能來自提供資料或業界通用常識，不得假造案名。"""


def to_trad(s: str) -> str:
    try:
        import zhconv
        return zhconv.convert(s, "zh-tw")
    except Exception:
        return s


def load_key() -> str:
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"].strip()
    p = Path.home() / ".gemini_api_key"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    sys.exit("[ERR] 找不到 Gemini API Key")


def jload(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def pick_photos(topic, projects, labels):
    """挑出這題可用的真實照片（有對應專案就用該專案，否則全部）。"""
    key = f"{topic.get('title','')} {topic.get('direction','')}"
    proj = None
    for prj in projects:
        if prj["name"] in key or prj["id"] in key.lower():
            proj = prj
            break
    if proj:
        files = [f for f in proj["crops"] if f in labels]
    elif topic.get("material") == "shot":
        files = [f for f in sorted(labels)]
    else:
        files = []
    return proj, files


def build_prompt(topic, pillar, brand, project, photo_files, labels):
    v = brand.get("voice", {})
    facts = ["（本題沒有提供專案實拍與數據，請全用文字卡，不要編造案名或數字。）"]
    if project:
        facts = [f"- 案名：{project['name']}（{project['year']}，{project['city']}）",
                 f"- 坪數：{project['area']}",
                 f"- 使用材質：{'、'.join(project['materials'])}"]
    plist = "\n".join(f"{i}: {labels[f]}" for i, f in enumerate(photo_files)) or "（無）"
    return f"""你是一位專寫短影音（YouTube Shorts／IG Reels／TikTok）的頂尖編劇。
唯一目標：讓人在前 3 秒停下來、把整支看完、還想留言。你最痛恨「宣導片腔」。

【品牌口吻】
人設：{v.get('persona','')}
語氣：{v.get('tone','')}
避免：{'、'.join(v.get('avoid',[]))}

【本片類型（內容支柱）】
{pillar['name']}｜漏斗目標：{pillar['funnel']}｜{pillar['goal']}
本題方向：{topic.get('direction') or '（自訂）'}

【真實資料（只能用這些，嚴禁虛構）】
{chr(10).join(facts)}

【可用的真實照片（依編號）】
{plist}

【本題題目】{topic['title']}

{TENSION}

{DELIVERY}

{HARD_RULES}

【輸出】只輸出 JSON，不要任何其他文字、不要 markdown 圍籬：
{{
  "deliver": ["本片保證一定要講出來的具體內容（數字或清單項目），逐條列出"],
  "hook": "第一句，≤18字，必為鉤子",
  "scenes": [
    {{"narration": "中段旁白（must 交付 deliver 的內容）", "photo": 0, "card": null}},
    {{"narration": "中段旁白", "photo": null, "card": "短句（≤10字）"}}
  ],
  "cta": "最後一句（引流或留鉤子）"
}}
說明：scenes 是中段 3～6 句（不含 hook 與 cta）。有合適照片就填該照片編號，否則 photo 填 null 並給 card 短句。
自我檢查：deliver 裡的每一項，都要真的出現在某個 scene 的 narration 裡；標題的數字要和 deliver 的數量一致。
"""


def build_dialog_prompt(topic, pillar, brand):
    v = brand.get("voice", {})
    return f"""你是一位專寫「短影音二人對話短劇」的頂尖編劇（YouTube Shorts／IG Reels／TikTok）。
唯一目標：前 3 秒抓住人、讓人看完、想留言。

【品牌口吻】
人設：{v.get('persona','')}
語氣：{v.get('tone','')}
避免：{'、'.join(v.get('avoid',[]))}

【本片類型（內容支柱）】
{pillar['name']}｜漏斗目標：{pillar['funnel']}｜{pillar['goal']}
本題方向：{topic.get('direction') or '（自訂）'}

【本題題目】{topic['title']}

{DIALOG_RULES}

{DELIVERY}

{HARD_RULES_DIALOG}

【輸出】只輸出 JSON，不要任何其他文字、不要 markdown 圍籬：
{{
  "deliver": ["本片一定要講出來的具體內容（數字或清單），逐條列出"],
  "scenes": [
    {{"speaker": "le", "text": "第一句鉤子（小樂吐槽）", "expr": "smug"}},
    {{"speaker": "ren", "text": "阿忍回應", "expr": "normal"}}
  ]
}}
自我檢查：deliver 每一項都要真的被某句台詞講到；標題的數字要和實際講到的一致。
"""


def assemble_dialog(topic, data, brand, char_dir):
    scenes = []
    for s in data.get("scenes", []):
        text = to_trad((s.get("text") or "").strip())
        if not text:
            continue
        who = s.get("speaker") if s.get("speaker") in ("ren", "le") else "ren"
        expr = s.get("expr") if s.get("expr") in ("normal", "surprise", "happy", "worry", "smug") else "normal"
        scenes.append({"speaker": who, "text": text, "expr": expr})
    return {"title": topic["title"], "format": "dialog",
            "char_dir": str(char_dir),
            "voice_map": {"ren": "zh-TW-YunJheNeural", "le": "zh-TW-HsiaoYuNeural"},
            "scenes": scenes}


def write_dialog_md(topic, pillar, data, script, path):
    NAME = {"ren": "阿忍（設計師）", "le": "小樂（屋主）"}
    lines = [f"# 【對話腳本待審】{topic['title']}", "",
             f"- 型式：二人對話短劇",
             f"- 支柱：{pillar['name']}（{pillar['funnel']}）",
             f"- 方向：{topic.get('direction') or '（自訂）'}",
             f"- 句數：{len(script['scenes'])}｜總字數：{sum(len(s['text']) for s in script['scenes'])}",
             "", "## 對白", ""]
    for i, s in enumerate(script["scenes"], 1):
        lines.append(f"{i}. **{NAME.get(s['speaker'], s['speaker'])}**（{s['expr']}）：{s['text']}")
    lines += ["", "## 保證交付", ""]
    for x in data.get("deliver", []):
        lines.append(f"- {x}")
    lines += ["", "> 審核：滿意請在窗口按「○通過」，要改就按「△退回」並註明方向。"]
    path.write_text("\n".join(lines), encoding="utf-8")


def call_gemini(prompt, model=MODEL):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=load_key())
    r = client.models.generate_content(
        model=model, contents=prompt,
        config=types.GenerateContentConfig(temperature=0.9),
    )
    return (r.text or "").strip()


def parse_json(text):
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    i, j = t.find("{"), t.rfind("}")
    return json.loads(t[i:j + 1])


def assemble(topic, data, project, photo_files, brand):
    title = topic["title"]
    scenes = []
    scenes.append({"narration": to_trad(data["hook"].strip()),
                   "image_file": str(CARDS / "hook.png"), "zoom": "in"})
    for k, s in enumerate(data.get("scenes", [])):
        narration = to_trad((s.get("narration") or "").strip())
        if not narration:
            continue
        idx = s.get("photo")
        if isinstance(idx, int) and 0 <= idx < len(photo_files):
            img = str(CROPS / photo_files[idx])
        else:
            card = to_trad((s.get("card") or narration[:8]).strip())
            from make_cards import scene_card
            img = str(scene_card(card, f"c_{topic['id']}_{k}"))
        scenes.append({"narration": narration, "image_file": img,
                       "zoom": "out" if k % 2 else "in"})
    cta = to_trad((data.get("cta") or "").strip())
    if cta:
        scenes.append({"narration": cta, "image_file": str(CARDS / "endcard.png"), "zoom": "out"})
    return {"title": title, "voice": "zh-TW-HsiaoChenNeural", "style": "", "scenes": scenes}


def write_review_md(topic, pillar, data, project, photo_files, script, path):
    lines = [f"# 【腳本待審】{topic['title']}", "",
             f"- 支柱：{pillar['name']}（{pillar['funnel']}）",
             f"- 方向：{topic.get('direction') or '（自訂）'}",
             f"- 素材：{'有實拍' if project else '無需實拍'}",
             f"- 鏡頭數：{len(script['scenes'])}｜旁白總字數：{sum(len(s['narration']) for s in script['scenes'])}",
             "", "## 旁白（依序）", ""]
    for i, s in enumerate(script["scenes"], 1):
        vis = Path(s["image_file"]).name
        lines.append(f"{i}. {s['narration']}")
        lines.append(f"   - 畫面：{vis}")
    lines += ["", "## 張力檢查", "",
              f"- 鉤子：{data.get('hook','')}",
              f"- 結尾：{data.get('cta','')}",
              f"- 保證交付：{'; '.join(data.get('deliver',[]))}", "",
              "> 審核：滿意請在窗口按「○通過」，要改就按「△退回」並註明方向。"]
    path.write_text("\n".join(lines), encoding="utf-8")


def _style_for(fmt, explicit=None):
    """Resolve a style key for a format (explicit wins; else first style with that format)."""
    if explicit:
        return explicit
    if reg is not None:
        for s in reg.styles():
            if s.get("format") == fmt:
                return s.get("key")
    return fmt


def _finalize(script, tid, style_key, version, jp):
    """Stamp version metadata and write the script JSON."""
    script["topic_id"] = tid
    script["style"] = style_key
    script["version"] = version
    if PACK:
        script["pack"] = PACK
    jp.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")


def run_topic(tid, queue, brand, projects, labels, model, fmt="narr", char_dir=None, style=None):
    topic = next((t for t in queue["topics"] if t["id"] == tid), None)
    if not topic:
        print(f"[skip] 找不到題目 {tid}")
        return None
    if style:  # explicit style wins over the topic's own format
        s = reg.style(style) if reg is not None else None
        fmt = (s or {}).get("format") or fmt
    else:
        fmt = topic.get("format") or fmt
    style_key = _style_for(fmt, style or topic.get("style"))
    version = 1
    if ename is not None:
        existing = [p.name for p in SCRIPTS.glob(f"{tid}__*.json")]
        version = ename.next_version(existing, tid, style_key)
        fname = ename.script_filename(tid, style_key, version)
    else:
        fname = f"{tid}.json"
    pillar = next((p for p in queue["pillars"] if p["id"] == topic["pillar"]),
                  {"name": "未分類", "funnel": "-", "goal": ""})
    SCRIPTS.mkdir(parents=True, exist_ok=True)
    jp = SCRIPTS / fname
    mp = SCRIPTS / f"{jp.stem}_腳本.md"
    block = ""
    if esc is not None:
        block = esc.compose(**esc.topic_overrides(topic))
    if fmt == "dialog":
        cd = Path(char_dir) if char_dir else (LEZHI / "assets" / "characters")
        print(f"[編劇/對話劇] {topic['title']}｜角色：{cd.name}｜版型 {style_key}")
        raw = call_gemini(build_dialog_prompt(topic, pillar, brand) + block, model)
        data = parse_json(raw)
        script = assemble_dialog(topic, data, brand, cd)
        _finalize(script, tid, style_key, version, jp)
        write_dialog_md(topic, pillar, data, script, mp)
        print(f"  -> {jp.name}（{len(script['scenes'])} 句）＋ {mp.name}")
        for i, s in enumerate(script["scenes"], 1):
            print(f"     {i}. [{s['speaker']}/{s['expr']}] {s['text']}")
        return script
    project, photo_files = pick_photos(topic, projects, labels)
    print(f"[編劇] {topic['title']}｜照片候選 {len(photo_files)} 張｜版型 {style_key}")
    raw = call_gemini(build_prompt(topic, pillar, brand, project, photo_files, labels) + block, model)
    data = parse_json(raw)
    script = assemble(topic, data, project, photo_files, brand)
    _finalize(script, tid, style_key, version, jp)
    write_review_md(topic, pillar, data, project, photo_files, script, mp)
    print(f"  -> {jp.name}（{len(script['scenes'])} 鏡）＋ {mp.name}")
    for i, s in enumerate(script["scenes"], 1):
        print(f"     {i}. {s['narration']}")
    return script


def main():
    ap = argparse.ArgumentParser(description="押忍腳本引擎")
    ap.add_argument("--topic")
    ap.add_argument("--topics", nargs="*")
    ap.add_argument("--starred", action="store_true", help="處理所有 ★ 且尚無腳本的題目")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--format", default="narr", choices=["narr", "dialog"],
                    help="narr=旁白分鏡；dialog=二人對話短劇")
    ap.add_argument("--chars-dir", default=None, help="dialog 用角色資料夾")
    ap.add_argument("--preset", default=None, help="語氣預設 key（engine/prompts/presets.json）")
    ap.add_argument("--structure", nargs="*", default=None, help="必含要素 key（可多個）")
    ap.add_argument("--extra", default=None, help="自訂補充指示（自由文字）")
    ap.add_argument("--style", default=None, help="風格 key（engine/styles/registry.json；覆寫題目格式）")
    args = ap.parse_args()

    queue = jload(QUEUE, {"pillars": [], "topics": []})
    brand = jload(PROFILE, {})
    projects = jload(PROJECTS, [])
    labels = jload(LABELS, {})

    ids = []
    if args.topic:
        ids.append(args.topic)
    if args.topics:
        ids += args.topics
    if args.starred:
        ids += [t["id"] for t in queue["topics"] if t.get("star") and not t.get("script")]
    ids = list(dict.fromkeys(ids))
    if not ids:
        print("沒有指定題目。用 --topic / --topics / --starred")
        return

    for tid in ids:
        t = next((x for x in queue["topics"] if x["id"] == tid), None)
        if t:
            if args.preset:
                t["preset"] = args.preset
            if args.structure:
                t["structure"] = args.structure
            if args.extra:
                t["extra"] = args.extra
            if args.style:
                t["style"] = args.style
        fmt = args.format
        if args.style and reg is not None:
            s = reg.style(args.style)
            if s and s.get("format"):
                fmt = s["format"]
        try:
            run_topic(tid, queue, brand, projects, labels, args.model,
                      fmt=fmt, char_dir=args.chars_dir, style=args.style)
        except Exception as e:
            import traceback
            print(f"[ERR] {tid}: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    main()
