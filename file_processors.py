#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
file_processors.py — 聲音檔、文件檔、網頁 → 知識庫條目

用法（供 GUI 呼叫）：
    from file_processors import process_audio, process_document, process_web
    result = process_audio("path/to/file.mp3", kb_dir="音頻")
    result = process_document("path/to/file.pdf", kb_dir="文件")
    result = process_web("https://example.com", kb_dir="網頁")
"""
import os, re, sys, json, shutil, subprocess, hashlib, tempfile
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).parent
KB_ROOT = PROJECT_ROOT / "knowledge-base"
WORKING = PROJECT_ROOT / "working"


def safe_filename(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def _msg(status, message, kb_path=""):
    return {"status": status, "message": message, "kb_path": kb_path}


def _call_script(script_path, *args, timeout=600):
    """執行子程序腳本並回傳 stdout"""
    cmd = [sys.executable, "-X", "utf8", str(script_path)] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return None, r.stderr[-800:] if r.stderr else "unknown error"
        return r.stdout, None
    except subprocess.TimeoutExpired:
        return None, "逾時"
    except UnicodeDecodeError:
        r = subprocess.run(cmd, timeout=timeout)
        if r.returncode == 0:
            return "(capture disabled due to encoding)", None
        return None, "編碼錯誤"
    except Exception as e:
        return None, str(e)


def _groq_json_to_srt(json_path, srt_path):
    """將 Groq Whisper 的 verbose_json 轉成 SRT"""
    data = json.loads(json_path.read_text("utf-8"))
    segments = data.get("segments", [])
    if not segments:
        words = data.get("words", [])
        if words:
            segments = []
            current = {"start": words[0]["start"], "end": words[0]["end"], "text": words[0].get("word", "")}
            for w in words[1:]:
                if w["start"] - current["end"] < 0.3:
                    current["end"] = w["end"]
                    current["text"] += " " + w.get("word", "")
                else:
                    segments.append(current)
                    current = {"start": w["start"], "end": w["end"], "text": w.get("word", "")}
            segments.append(current)

    srt_lines = []
    for i, seg in enumerate(segments, 1):
        s = seg.get("start", 0) + i * 0.001
        e = seg.get("end", s + 2)
        text = seg.get("text", "").strip()
        if not text:
            continue
        def fmt(t):
            h, m = int(t // 3600), int((t % 3600) // 60)
            s, ms = int(t % 60), int((t % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
        srt_lines.append(str(i))
        srt_lines.append(f"{fmt(s)} --> {fmt(e)}")
        srt_lines.append(text)
        srt_lines.append("")
    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    return srt_path


def _create_kb_entry(source_id, title, content, source_path, kb_dir, srt_path=None):
    """建立通用 KB 條目"""
    safe = safe_filename(title)
    kb_dir.mkdir(parents=True, exist_ok=True)
    md_path = kb_dir / f"{safe}.md"
    link_path = kb_dir / f"{safe}.link.txt"
    md_content = f"""# {title}

## 來源
- {source_path}

---

## 內容

{content}
"""
    md_path.write_text(md_content, encoding="utf-8")
    link_path.write_text(f"{source_path}\n", encoding="utf-8")
    if srt_path and srt_path.exists():
        shutil.copy2(srt_path, kb_dir / f"{safe}.srt")
    return md_path


# ── Audio ──

def process_audio(filepath, kb_subdir="音頻", title=None):
    """聲音檔 → Groq Whisper 轉錄 → KB 條目"""
    fp = Path(filepath)
    if not fp.exists():
        return _msg("error", f"檔案不存在: {filepath}")
    name = (title or fp.stem).strip()
    src_id = hashlib.md5(str(fp.resolve()).encode()).hexdigest()[:8]
    kb_dir = KB_ROOT / kb_subdir
    temp_dir = WORKING / "fp-temp" / src_id
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: 轉錄
    sys.stderr.write(f"[audio] 轉錄 {fp.name}...\n")
    transcribe_script = PROJECT_ROOT / ".opencode" / "skills" / "audio-to-srt" / "scripts" / "transcribe_groq.py"
    raw_json = temp_dir / "raw.json"
    out, err = _call_script(transcribe_script, str(fp), "--out", str(raw_json), timeout=600)
    if err or not raw_json.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
        return _msg("error", f"轉錄失敗: {err or 'output not found'}")

    # Step 2: 取得逐字稿
    data = json.loads(raw_json.read_text("utf-8"))
    transcript = data.get("text", "").strip()
    if not transcript:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return _msg("error", "轉錄結果為空")

    # Step 3: 產生 SRT
    srt_path = temp_dir / "transcript.srt"
    _groq_json_to_srt(raw_json, srt_path)

    # Step 4: 建立 KB 條目
    try:
        md = _create_kb_entry(src_id, name, transcript, str(fp.resolve()), kb_dir, srt_path=srt_path)
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return _msg("error", f"KB 建立失敗: {e}")

    shutil.rmtree(temp_dir, ignore_errors=True)
    sys.stderr.write(f"[audio] OK → {md}\n")
    return _msg("ok", f"轉錄完成: {name}", str(md))


# ── Document ──

def _extract_pdf(filepath):
    import pypdf
    reader = pypdf.PdfReader(filepath)
    text = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            text.append(t)
    return "\n".join(text)


def _extract_docx(filepath):
    import docx
    doc = docx.Document(filepath)
    return "\n".join(p.text for p in doc.paragraphs)


def _extract_txt(filepath):
    return Path(filepath).read_text("utf-8", errors="replace")


DOC_EXT_HANDLERS = {
    ".pdf": _extract_pdf,
    ".docx": _extract_docx,
    ".doc": _extract_docx,
    ".txt": _extract_txt,
    ".md": _extract_txt,
    ".csv": _extract_txt,
    ".json": _extract_txt,
    ".xml": _extract_txt,
    ".html": _extract_txt,
    ".htm": _extract_txt,
    ".log": _extract_txt,
    ".ini": _extract_txt,
    ".cfg": _extract_txt,
    ".yaml": _extract_txt,
    ".yml": _extract_txt,
    ".toml": _extract_txt,
}


def process_document(filepath, kb_subdir="文件", title=None):
    """文件檔 → 文字提取 → KB 條目"""
    fp = Path(filepath)
    if not fp.exists():
        return _msg("error", f"檔案不存在: {filepath}")
    ext = fp.suffix.lower()
    name = (title or fp.stem).strip()
    src_id = hashlib.md5(str(fp.resolve()).encode()).hexdigest()[:8]
    kb_dir = KB_ROOT / kb_subdir

    handler = DOC_EXT_HANDLERS.get(ext)
    if not handler:
        return _msg("error", f"不支援的格式: {ext}（支援: {', '.join(DOC_EXT_HANDLERS)}）")

    try:
        content = handler(str(fp))
    except Exception as e:
        return _msg("error", f"文字提取失敗: {e}")

    if not content.strip():
        return _msg("error", "提取內容為空")

    content_preview = content[:20000]  # 限制 20000 字
    if len(content) > 20000:
        content_preview += f"\n\n--- (內容過長，僅顯示前 20000 字，原文 {len(content)} 字) ---"

    try:
        md = _create_kb_entry(src_id, name, content_preview, str(fp.resolve()), kb_dir)
    except Exception as e:
        return _msg("error", f"KB 建立失敗: {e}")

    sys.stderr.write(f"[doc] OK → {md}\n")
    return _msg("ok", f"文字提取完成: {name}（{len(content)} 字）", str(md))


# ── Web ──

def process_web(url, kb_subdir="網頁", title=None):
    """網頁 URL → 擷取內容 → KB 條目"""
    import requests
    from bs4 import BeautifulSoup
    if not url.startswith(("http://", "https://")):
        return _msg("error", "無效的網址，需以 http:// 或 https:// 開頭")
    name = (title or url).strip()
    src_id = hashlib.md5(url.encode()).hexdigest()[:8]
    kb_dir = KB_ROOT / kb_subdir

    try:
        r = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        r.encoding = r.apparent_encoding
        r.raise_for_status()
    except Exception as e:
        return _msg("error", f"取得網頁失敗: {e}")

    try:
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        content = soup.get_text(separator="\n", strip=True)
    except Exception as e:
        content = r.text[:50000]

    if not content.strip():
        return _msg("error", "網頁內容為空")

    content_preview = content[:30000]
    if len(content) > 30000:
        content_preview += f"\n\n--- (內容過長，僅顯示前 30000 字，原文 {len(content)} 字) ---"

    try:
        md = _create_kb_entry(src_id, name, content_preview, url, kb_dir)
    except Exception as e:
        return _msg("error", f"KB 建立失敗: {e}")

    sys.stderr.write(f"[web] OK → {md}\n")
    return _msg("ok", f"網頁擷取完成: {name}（{len(content)} 字）", str(md))


# ── CLI ──

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="檔案/網頁 → 知識庫條目")
    ap.add_argument("type", choices=["audio", "doc", "web"], help="處理類型")
    ap.add_argument("source", help="檔案路徑或網址")
    ap.add_argument("--kb", default="", help="KB 子目錄（預設自動判斷）")
    ap.add_argument("--title", default="", help="條目標題（預設用檔名或網址）")
    args = ap.parse_args()
    kb_map = {"audio": "音頻", "doc": "文件", "web": "網頁"}
    kb_subdir = args.kb or kb_map.get(args.type, "")
    title = args.title or None
    if args.type == "audio":
        r = process_audio(args.source, kb_subdir, title)
    elif args.type == "doc":
        r = process_document(args.source, kb_subdir, title)
    else:
        r = process_web(args.source, kb_subdir, title)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    sys.exit(0 if r["status"] == "ok" else 1)
