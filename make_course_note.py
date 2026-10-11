#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_course_note.py — 課程逐字稿 → 詳細課程筆記（Word + Markdown）
====================================================================
把一堂課的多支逐字稿，依時間序整理成一份「課程筆記」：
- 每支逐字稿交給 Gemini 整理成詳細筆記章節（保留教學邏輯、定義/參數/口訣/例股）
- 合併為單一 Markdown，並用 python-docx 輸出 Word（醒目標題層級）

用法:
  python make_course_note.py --title "課程名" --mds md1 md2 ... --out 輸出目錄
  python make_course_note.py --title "課程名" --mds md... --out DIR --preview 30000
      # 試做模式：只取第一支逐字稿前 30000 字，用於確認格式與要領
"""
import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

MAX_OUTPUT_TOKENS = 20000


def load_gemini_key() -> str:
    env = os.environ.get("GEMINI_API_KEY")
    if env:
        return env.strip()
    kf = Path.home() / ".gemini_api_key"
    if kf.exists():
        return kf.read_text(encoding="utf-8").strip()
    sys.exit("[ERR] 找不到 Gemini API Key（~/.gemini_api_key）")


def strip_meta(md_text: str) -> str:
    """去掉逐字稿 md 開頭的 YouTube Metadata 區塊，只保留逐字稿正文"""
    if "# YouTube Metadata" not in md_text:
        return md_text.strip()
    idx = md_text.find("## 逐字稿")
    if idx >= 0:
        return md_text[idx + len("## 逐字稿"):].strip()
    # fallback：去掉前 8 行
    return "\n".join(md_text.splitlines()[8:]).strip()


def split_body(body: str, chunk_chars: int) -> list:
    """把長逐字稿依行切成長度約 chunk_chars 的多段（0＝不分段）"""
    if chunk_chars <= 0:
        return [body]
    chunks, cur, size = [], [], 0
    for ln in body.splitlines():
        cur.append(ln)
        size += len(ln) + 1
        if size >= chunk_chars:
            seg = "\n".join(cur).strip()
            if seg:
                chunks.append(seg)
            cur, size = [], 0
    tail = "\n".join(cur).strip()
    if tail:
        chunks.append(tail)
    return chunks or [body]


def gemini_note(transcript: str, api_key: str) -> str:
    from google import genai
    from google.genai import types

    system = "你是專業的教學共筆編輯，擅長把課程的語音逐字稿整理成結構完整、內容詳盡、深入淺出的課程筆記；目標是讓沒上到課的學習者也能讀懂每個觀念的內涵。"
    user = f"""這是某堂課程某一部分的逐字稿。請整理成「詳細課程筆記」，重點是**把細節講清楚、講透**，而不是只列大綱或重點摘要。

最高原則：
- 這是給學習者閱讀的共筆：**每一個主題、每一個重點都要有充分的文字闡述**，讓讀者真正理解其內涵，不能只有標題或一行帶過。
- 請用完整通順的句子與**段落敘述**；**不要通篇條列式大綱**。只有真正屬於「清單」的內容（如多個並列條件、操作步驟、參數項）才使用條列。
- **言之有物**：凡是講師提到的數字、條件、參數、判斷標準、推論過程、因果關係與舉例，都要具體寫出，不可含糊、不可省略。

內容要求：
1. 依講師實際授課順序推進，完整保留其推導、理由、說明與舉例，不要跳過或過度精簡。
2. 每個觀念／方法／指標，以敘述方式交代：它是什麼、**為什麼**（背後的原理與邏輯）、怎麼用、使用時機、可能的陷阱與注意事項——把講師的說明講清楚、講透。
3. 講師強調的口訣、金句、關鍵結論，請原句保留並用 **粗體** 標示。
4. 提到實際標的（股票／族群）舉例時，詳寫：標的（代號或名稱）、當時的線型／型態或數據、講師如何逐步解讀、這個例子說明了什麼規則。
5. 語音轉錄可能有錯字，請依上下文合理修正（例如技術名詞的「真說」→「增率」）；無法確認的就保留原樣。
6. 刪除「嗯、啊、好、可以嗎、各位同學」等口頭贅詞與離題閒聊；**忽略明顯的辨識亂碼與非教學雜訊**（如收尾音樂、重複的無意義字元、問候寒暄）。
7. 使用 Markdown：主題標題用 ###（必要時 #### 分小節）；內容用一般段落文字；關鍵術語或口訣用 **粗體**。
8. 全部使用繁體中文；**標點使用全形**；箭頭一律用「→」；**不要輸出 LaTeX／數學符號**（例如不要寫 `$\rightarrow$`），也不要輸出亂碼或非中英文字元。
9. **寧可詳盡，不要精簡**；內容多就完整寫出，不要為了縮短而省略細節。

請直接輸出該段課程的筆記（以「### 」為最高層級，不要輸出 #），不要加前言或結語。

===== 逐字稿 =====
{transcript}
====="""
    client = genai.Client(api_key=api_key)
    resp = _gemini_call(client, system, user, MAX_OUTPUT_TOKENS)
    return (resp.text or "").strip()


def _gemini_call(client, system: str, user: str, max_tokens: int):
    """呼叫 Gemini；503（高需求）與 429/RESOURCE_EXHAUSTED（免費層每分鐘額度）
    時額外重試，等待逐次加長（最多 6 輪、最長等 150 秒）。"""
    from google.genai import types as _types
    import time as _t
    last = None
    for attempt in range(6):
        try:
            return client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=f"{system}\n\n---\n\n{user}",
                config=_types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=max_tokens,
                ),
            )
        except Exception as e:
            msg = str(e)
            is_retryable = ("503" in msg) or ("429" in msg) or ("RESOURCE_EXHAUSTED" in msg)
            if is_retryable and attempt < 5:
                _t.sleep(min(30 * (attempt + 1), 150))
                last = e
                continue
            raise
    raise last if last else RuntimeError("gemini retry exhausted")


FONT = "華康仿宋體W6"   # 使用者確認的字型（2026-10-04）
BASE_SIZE = 12
HEADING_PT = 12                  # 標題字號（維持與正文相同，靠粗體+編號區分）
LIST_INDS = [(35.45, -11.45), (49.65, -14.2)]   # 條列縮排 L / FL（依層次）


def _pick_num_id(template_path: Path | None) -> str | None:
    """從樣板 numbering.xml 挑一個多層項目符號 numId（支援 ilvl>=1 的 bullet）"""
    if not template_path or not Path(template_path).exists():
        return None
    import zipfile, re as _re
    try:
        z = zipfile.ZipFile(str(template_path))
        if "word/numbering.xml" not in z.namelist():
            return None
        nx = z.read("word/numbering.xml").decode("utf-8", "replace")
    except Exception:
        return None
    # abstractNum 含 ilvl>=1 且 ilvl0 為 bullet 者優先
    candidates = []
    for m in _re.finditer(r'<w:abstractNum w:abstractNumId="(\d+)"(.*?)</w:abstractNum>', nx, _re.S):
        aid, body = m.group(1), m.group(2)
        lvls = _re.findall(r'<w:lvl w:ilvl="(\d+)".*?<w:numFmt w:val="([^"]+)"', body, _re.S)
        if not lvls:
            continue
        il0_fmt = lvls[0][1]
        if il0_fmt == "bullet" and any(int(i) >= 1 for i, _ in lvls):
            candidates.append(int(aid))
    if not candidates:
        return None
    best_abs = min(candidates, key=lambda a: a)
    m = _re.search(r'<w:num w:numId="(\d+)"[^>]*>\s*<w:abstractNumId w:val="' + str(best_abs) + '"', nx)
    return m.group(1) if m else None


def _fix_numbering_sizes(docx_path: Path, num_id: str):
    """產出後調整 numberOfLg 深層標號：改成小圓圈、字號小於上層（層次感分明）"""
    import zipfile
    import os as _os
    src = zipfile.ZipFile(str(docx_path), "r")
    items = {n: src.read(n) for n in src.namelist()}
    src.close()
    if "word/numbering.xml" not in items:
        return
    xml = items["word/numbering.xml"].decode("utf-8", "replace")
    m = re.search(r'<w:num w:numId="' + num_id + r'"[^>]*>\s*<w:abstractNumId w:val="(\d+)"', xml)
    if not m:
        return
    absid = m.group(1)

    def _fix_one(m2):
        ilvl = int(re.search(r'w:ilvl="(\d+)"', m2.group(1)).group(1))
        inner = m2.group(2)
        # 符號字元完全保留樣板原始設定（Symbol 私有碼），只讓「層次越低字號越小」
        sz = 12 if ilvl == 1 else 16   # ilvl0 原尺寸；ilvl1=6pt；更深=8pt
        if ilvl == 0:
            pass                     # 第一層維持樣板原尺寸，不必加 sz
        elif "<w:rPr>" in inner:
            if r'<w:sz w:val="' not in inner:
                inner = inner.replace("<w:rPr>", '<w:rPr><w:sz w:val="' + str(sz) + '"/>')
            else:
                inner = re.sub(r'<w:sz w:val="\d+"/>', '<w:sz w:val="' + str(sz) + '"/>', inner)
        else:
            inner += '<w:rPr><w:sz w:val="' + str(sz) + '"/></w:rPr>'
        return m2.group(1) + inner + m2.group(3)

    def _fix_abs(m):
        body = m.group(2)
        body = re.sub(r'(<w:lvl w:ilvl="\d+"[^>]*>)(.*?)(</w:lvl>)', _fix_one, body, flags=re.S)
        return m.group(1) + body + m.group(3)

    new_xml, n = re.subn(
        r'(<w:abstractNum w:abstractNumId="' + absid + r'"[^>]*>)(.*?)(</w:abstractNum>)',
        _fix_abs, xml, flags=re.S)
    if n == 0:
        return
    items["word/numbering.xml"] = new_xml.encode("utf-8")

    tmp = str(docx_path) + ".new"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in items.items():
            zout.writestr(name, data)
    _os.replace(tmp, str(docx_path))


def _clear_body(doc):
    """清空 body，保留 sectPr（含頁碼 footer）"""
    body = doc.element.body
    for child in list(body):
        if child.tag.endswith("}sectPr"):
            continue
        body.remove(child)


def build_docx(markdown: str, out_path: Path, template: Path | None = None):
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    num_id = None
    if template and Path(template).exists():
        doc = Document(str(template))
        _clear_body(doc)
        num_id = _pick_num_id(Path(template))
    else:
        doc = Document()
        style = doc.styles["Normal"]
        style.font.name = FONT
        style.font.size = Pt(BASE_SIZE)
        style._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        style.paragraph_format.line_spacing = 1.3
        style.paragraph_format.space_after = Pt(4)

    def _set_font(run, name=FONT, size=BASE_SIZE, bold=False, color=None):
        run.font.name = name
        run.font.size = Pt(size)
        run.bold = bold
        rPr = run._element.get_or_add_rPr()
        rFonts = rPr.find(qn("w:rFonts"))
        if rFonts is None:
            from docx.oxml import OxmlElement
            rFonts = OxmlElement("w:rFonts")
            rPr.insert(0, rFonts)
        rFonts.set(qn("w:ascii"), name)
        rFonts.set(qn("w:hAnsi"), name)
        rFonts.set(qn("w:eastAsia"), name)
        if color:
            run.font.color.rgb = RGBColor(*color)

    def add_heading(text, bold=True, color=(0, 0, 0)):
        p = doc.add_paragraph()
        r = p.add_run(text)
        _set_font(r, size=HEADING_PT, bold=bold)
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(4)
        return p

    def add_rich_line(text, base_bold=False, size=12):
        """支援 **粗體** inline 標記"""
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(3)
        tokens = re.split(r"(\*\*.+?\*\*)", text)
        for tok in tokens:
            if not tok:
                continue
            if tok.startswith("**") and tok.endswith("**"):
                r = p.add_run(tok[2:-2])
                _set_font(r, size=size, bold=True)
            else:
                r = p.add_run(tok)
                _set_font(r, size=size, bold=base_bold)
        return p

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("# ") or line.startswith("## ") or \
           line.startswith("### ") or line.startswith("#### "):
            txt = re.sub(r'^#*\s*', '', line).strip()
            add_heading(txt, bold=True)
        else:
            m = re.match(r'^(\s*)[-*•]\s+(.*)$', line)
            if m:
                indent_sp, content = m.group(1), m.group(2)
                depth = min(max(len(indent_sp) // 4, 0), 1)
                in_l, in_fl = LIST_INDS[depth]
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Pt(in_l)
                p.paragraph_format.first_line_indent = Pt(in_fl)
                p.paragraph_format.space_after = Pt(3)
                if num_id:
                    # 套用樣板的多層項目符號編號（標號層次）
                    pPr = p._p.get_or_add_pPr()
                    numPr = OxmlElement("w:numPr")
                    ilvl = OxmlElement("w:ilvl"); ilvl.set(qn("w:val"), str(depth))
                    numId = OxmlElement("w:numId"); numId.set(qn("w:val"), num_id)
                    numPr.append(ilvl); numPr.append(numId)
                    pPr.insert(0, numPr)
                tokens = re.split(r"(\*\*.+?\*\*)", content.strip())
                for tok in tokens:
                    if not tok:
                        continue
                    if tok.startswith("**") and tok.endswith("**"):
                        r = p.add_run(tok[2:-2])
                        _set_font(r, bold=True)
                    else:
                        r = p.add_run(tok)
                        _set_font(r)
            else:
                add_rich_line(line)

    doc.save(str(out_path))
    if num_id:
        _fix_numbering_sizes(out_path, num_id)
    return out_path


def generate_note(title, md_sources, out_dir, template=None, chunk_chars=0,
                  preview=0, progress=None):
    """逐字稿 md（可多支，依時間序）→ 課程筆記 (.md + .docx)。

    回傳 (md_out, docx_out)。已存在同名檔案不會自動略過（由呼叫端決定）；
    progress：可選 callable(str)，用於回報進度。
    """
    def _p(msg):
        if progress:
            try:
                progress(msg)
            except Exception:
                pass

    api_key = load_gemini_key()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)

    md_sources = [str(m) for m in md_sources]
    if preview > 0:
        _p("[試做模式] 只處理第一支的前 {} 字".format(preview))
        md_sources = md_sources[:1]

    parts_dir = out_dir / f"_parts_{safe_title}"
    parts_dir.mkdir(parents=True, exist_ok=True)

    from collections import Counter
    parent_count = Counter(Path(m).parent for m in md_sources)

    chapters = []
    for i, mdp in enumerate(md_sources):
        p = Path(mdp)
        if parent_count[p.parent] > 1:
            base = p.stem
        else:
            base = p.parent.name or p.stem
        part = parts_dir / f"{i:02d}.md"
        if part.exists():
            data = part.read_text(encoding="utf-8").split("\n", 1)
            note = data[1] if len(data) > 1 else data[0]
            chapters.append((base, note))
            _p(f"[{i+1}/{len(md_sources)}] 載入暫存 → {base}（{len(note):,} 字元）")
            continue
        _p(f"[{i+1}/{len(md_sources)}] 整理 → {base} ...")
        raw = p.read_text(encoding="utf-8", errors="replace")
        body = strip_meta(raw)
        if preview > 0 and len(body) > preview:
            body = body[:preview] + "\n…（試做截斷，其餘部分正式整理時補上）…"
        chunk = 0 if preview > 0 else chunk_chars
        segs = split_body(body, chunk)
        if len(segs) > 1:
            _p(f"        （長逐字稿分段：{len(segs)} 段）")
        notes = []
        for k, seg in enumerate(segs):
            if len(segs) > 1:
                _p(f"          - 第 {k+1}/{len(segs)} 段（{len(seg):,} 字）...")
            notes.append(gemini_note(seg, api_key))
        note = "\n\n".join(x for x in notes if x.strip())
        part.write_text(base + "\n" + note, encoding="utf-8")
        chapters.append((base, note))
        _p(f"        ✓ 完成（{len(note):,} 字元）")

    lines = [f"# {title}", ""]
    lines.append("> 課程筆記（整理自課堂逐字稿，依時間順序）。")
    lines.append(f"> 整理日期：{datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")
    multi = len(chapters) > 1
    for base, md in chapters:
        if multi:
            hdr = "## " + base.strip() if not base.startswith("##") else base
            lines.append(hdr)
            lines.append("")
        lines.append(md.strip())
        lines.append("")
    md_text = "\n".join(lines)

    md_out = out_dir / f"{safe_title} 課程筆記.md"
    if preview:
        md_out = out_dir / f"_preview_{safe_title} 課程筆記.md"
    md_out.write_text(md_text, encoding="utf-8")
    _p(f"[OK] {md_out}")

    docx_out = md_out.with_suffix(".docx")
    build_docx(md_text, docx_out, template=template)
    _p(f"[OK] {docx_out}")
    return md_out, docx_out


def main():
    ap = argparse.ArgumentParser(description="課程逐字稿 → 詳細課程筆記")
    ap.add_argument("--title", type=str, help="課程名稱（檔案主檔名）")
    ap.add_argument("--mds", nargs="+", help="逐字稿 md 路徑（依時間序）")
    ap.add_argument("--out", type=Path, default=Path("."), help="輸出目錄（預設 目前目錄）")
    ap.add_argument("--preview", type=int, default=0,
                    help="試做模式：只取第一支逐字稿前 N 字，輸出 _preview 檔")
    ap.add_argument("--chunk-chars", type=int, default=0, dest="chunk_chars",
                    help="長逐字稿分段字數（0＝不分段，建議 8000）")
    ap.add_argument("--template", type=Path, default=None,
                    help="docx 樣板（保留其頁碼/排版設定，清空內容重填）")
    ap.add_argument("--from-md", type=Path, default=None,
                    help="跳過 AI，直接用既有筆記 md 重建 docx")
    args = ap.parse_args()

    if args.from_md is not None:
        md_text = Path(args.from_md).read_text(encoding="utf-8")
        md_out = Path(args.from_md)
        docx_out = md_out.with_suffix(".docx")
        build_docx(md_text, docx_out, template=args.template)
        print(f"[OK] 已由 {md_out.name} 重建 {docx_out.name}")
        return

    if not args.title or not args.mds:
        ap.print_help()
        return
    generate_note(args.title, args.mds, args.out, template=args.template,
                  chunk_chars=args.chunk_chars, preview=args.preview,
                  progress=print)


if __name__ == "__main__":
    main()