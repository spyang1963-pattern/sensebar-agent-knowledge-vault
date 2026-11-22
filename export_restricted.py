#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""export_restricted.py — 產生「僅供點閱」的受控分享包（單支影片）。

做了什麼
--------
1. 字幕影片：PIL 產生浮水印 PNG → ffmpeg overlay 燒進畫面（音訊直接 copy）。
2. 課程筆記／摘要 docx：移除「影片位置／內網 UNC／.lnk」段落，頁首加浮水印。
3. 產 README：僅供點閱、請勿下載或轉寄、建議期限。
4. 輸出前敏感掃描：資料夾內不得殘留 \\100. / file:/// / .lnk / _video_links / 本機 D:\ 路徑。

**绝对不带**：逐字稿 .md／.srt、.lnk、_video_links、任何憑證、task 狀態。

注意（寫死在 README）
--------------------
這不是 DRM：能播放就能翻拍。「不能下載／不能分享」只能靠
(a) 平台權限（雲端「僅檢視、不可下載」＋到期日）與 (b) 合約約束。
浮水印的功能是「外流可追責」，不是「阻擋外流」。
內容若無明確授權，僅限信任的內部對象，不得對外散布。

用法
----
    python -X utf8 export_restricted.py \
        --stem "2026-11-21_凡人修仙4-期貨-週六直播-2100" \
        --kb-subdir CMoney_直播 --viewer "內部同仁" \
        --out working/share_sample
"""
import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KB = ROOT / "knowledge-base"
INTERNAL_MARKERS = ("100.113", "100.84", "file:///", ".lnk", "_video_links",
                    "D:\\AI-Agent-Workspace", "D:\\CMoney_直播", "D:\\YouTube_Videos")


def log(msg):
    print(msg, flush=True)


def find_burned_video(stem, kb_subdir):
    """從 KB 逐字稿的標準影片行抓燒字幕影片 UNC。"""
    md = KB / kb_subdir / (stem + ".md")
    if not md.exists():
        raise SystemExit(f"找不到逐字稿：{md}")
    for line in md.read_text(encoding="utf-8", errors="replace").splitlines():
        if "燒字幕影片" in line and "｜" in line:
            p = Path(line.split("｜", 1)[1].strip())
            if p.exists():
                return p
            raise SystemExit(f"燒字幕影片路徑存在但不可讀：{p}")
    raise SystemExit("逐字稿裡找不到燒字幕影片行")


def make_watermark(text, target):
    from PIL import Image, ImageDraw, ImageFont
    font_path = "C:/Windows/Fonts/msyh.ttc"
    font = ImageFont.truetype(font_path, 24)
    probe = Image.new("RGBA", (1, 1))
    d = ImageDraw.Draw(probe)
    box = d.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    img = Image.new("RGBA", (w + 44, h + 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w + 44, h + 30), radius=8, fill=(0, 0, 0, 155))
    d.text((22, 15), text, font=font, fill=(255, 255, 255, 235))
    img.save(target)


def burn_video(video, wm, out):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("找不到 ffmpeg")
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(video), "-i", str(wm),
           "-filter_complex", "overlay=W-w-24:H-h-24",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
           "-c:a", "copy", "-movflags", "+faststart", str(out)]
    log(f"  燒浮水印中（181MB 影片，請稍候）…")
    subprocess.run(cmd, check=True, cwd=str(out.parent))


W_T = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"


def _para_all_text(para):
    """para.text 不含 hyperlink 內文字；改抓 XML 所有 <w:t> 才不會漏。"""
    return "".join(t.text or "" for t in para._element.iter(W_T))


def clean_docx(src, out, watermark_text):
    from docx import Document
    from docx.shared import Pt, RGBColor
    doc = Document(str(src))
    removed = 0
    for p in list(doc.paragraphs):
        if any(k in _para_all_text(p) for k in ("影片位置", "_video_links", "file:///", "100.113", "100.84")):
            p._element.getparent().remove(p._element)
            removed += 1
    for sec in doc.sections:
        header = sec.header
        para = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
        para.text = watermark_text
        para.alignment = 1  # CENTER
        for r in para.runs:
            r.font.size = Pt(8)
            r.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
    doc.save(str(out))
    return removed


def write_readme(out, stem, viewer, days):
    txt = f"""僅供點閱・請勿下載或轉寄
========================================

內容：{stem}
授權對象：{viewer}
建議期限：{dt.date.today().isoformat()} 起 {days} 天（期滿請刪除分享）
產出日：{dt.datetime.now().strftime('%Y-%m-%d %H:%M')}

【注意事項】
1. 本包僅供上列對象「點閱」，不得下載、另存、轉寄、上傳或公開。
2. 影片與文件已加浮水印；外流可追溯來源。
3. 這不是 DRM — 能播放就能翻拍。真正的限制要靠分享平台的
   「僅檢視、不可下載／不可列印」權限＋到期日，以及雙方約定。
4. 原始內容無明確授權，僅限信任的內部使用；請勿對外散布。

【建議遞送方式】
上傳到 Google Drive / OneDrive → 共用設定選「僅指定人可檢視」、
關掉「允許下載／列印」、設到期日，並定期檢查存取紀錄。
"""
    (out / "README_請勿轉寄.txt").write_text(txt, encoding="utf-8")


def scan_sensitive(out):
    """輸出包敏感掃描：docx 直接查 zip 內 XML/rels（含 hyperlink URL），不要用 para.text。"""
    import zipfile
    bad = []
    for p in out.rglob("*"):
        if not p.is_file():
            continue
        texts = []
        if p.suffix.lower() in (".md", ".txt"):
            texts.append(p.read_text(encoding="utf-8", errors="replace"))
        elif p.suffix.lower() == ".docx":
            with zipfile.ZipFile(p) as z:
                for member in z.namelist():
                    if member.endswith(".xml") or member.endswith(".rels"):
                        texts.append(z.read(member).decode("utf-8", errors="replace"))
        for t in texts:
            for mk in INTERNAL_MARKERS:
                if mk in t:
                    bad.append(f"{p.name}: 含 {mk}")
    return bad


def main():
    ap = argparse.ArgumentParser(description="產生僅供點閱的受控分享包")
    ap.add_argument("--stem", required=True)
    ap.add_argument("--kb-subdir", default="CMoney_直播")
    ap.add_argument("--viewer", default="內部同仁")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out", default="working/share_sample")
    args = ap.parse_args()

    out = (ROOT / args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    wm_text = f"僅供 {args.viewer} 點閱・請勿散播・{dt.date.today().isoformat()}"
    wm_png = out / "_watermark.png"

    log(f"[1/4] 找來源：{args.stem}")
    video = find_burned_video(args.stem, args.kb_subdir)
    log(f"  {video}")

    log("[2/4] 產生浮水印並燒進字幕影片")
    make_watermark(wm_text, wm_png)
    burned_out = out / (video.stem + "_僅供點閱.mp4")
    burn_video(video, wm_png, burned_out)
    wm_png.unlink(missing_ok=True)

    log("[3/4] 清理並輸出课程笔记／摘要 docx")
    for suf in (" 課程筆記.docx", " 摘要.docx"):
        src = KB / args.kb_subdir / (args.stem + suf)
        if src.exists():
            n = clean_docx(src, out / src.name, wm_text)
            log(f"  {src.name}（移除 {n} 行內部路徑）")

    write_readme(out, args.stem, args.viewer, args.days)

    log("[4/4] 敏感掃描")
    bad = scan_sensitive(out)
    if bad:
        log("  ❌ 發現殘留內部資訊，請檢查：")
        for b in bad[:20]:
            log("    " + b)
        return 1
    log("  ✅ 無內網 IP／.lnk／本機路徑殘留")
    log(f"\n完成 → {out}")
    log("  提醒：上傳到雲端後要設「僅指定人可檢視、不可下載／列印＋到期日」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
