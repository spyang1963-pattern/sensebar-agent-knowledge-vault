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
import os, re, sys, json, shutil, subprocess, hashlib, tempfile, time
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).parent
KB_ROOT = PROJECT_ROOT / "knowledge-base"
WORKING = PROJECT_ROOT / "working"


def safe_filename(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def _kb_dir(subdir):
    """解析 KB 子目錄，去除前導/尾隨斜線（否則 pathlib 會丟棄 KB_ROOT）"""
    s = str(subdir or "").strip().strip('/\\')
    return KB_ROOT / s if s else KB_ROOT


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

AUDIO_EXTS = ('.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac', '.wma', '.mp4')


def _process_audio_file(fp, kb_dir, title=None, task_id=None, index=None, total=None):
    """單一音訊檔 → Groq Whisper 轉錄 → KB 條目"""
    name = (title or fp.stem).strip()
    src_id = hashlib.md5(str(fp.resolve()).encode()).hexdigest()[:8]
    temp_dir = WORKING / "fp-temp" / src_id
    temp_dir.mkdir(parents=True, exist_ok=True)

    sys.stderr.write(f"[audio] 轉錄 {fp.name}...\n")
    _write_progress(task_id, type="audio", stage="transcribing", index=index, total=total, msg=f"轉錄 {fp.name}")
    transcribe_script = PROJECT_ROOT / ".opencode" / "skills" / "audio-to-srt" / "scripts" / "transcribe_groq.py"
    raw_json = temp_dir / "raw.json"
    out, err = _call_script(transcribe_script, str(fp), "--out", str(raw_json), timeout=600)
    if err or not raw_json.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
        return _msg("error", f"轉錄失敗: {fp.name}: {err or 'output not found'}")
    _write_progress(task_id, type="audio", stage="building", index=index, total=total, msg=f"建立 KB 條目 {fp.name}")

    data = json.loads(raw_json.read_text("utf-8"))
    transcript = data.get("text", "").strip()
    if not transcript:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return _msg("error", f"轉錄結果為空: {fp.name}")

    srt_path = temp_dir / "transcript.srt"
    _groq_json_to_srt(raw_json, srt_path)

    try:
        md = _create_kb_entry(src_id, name, transcript, str(fp.resolve()), kb_dir, srt_path=srt_path)
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return _msg("error", f"KB 建立失敗: {e}")

    shutil.rmtree(temp_dir, ignore_errors=True)
    sys.stderr.write(f"[audio] OK → {md}\n")
    return _msg("ok", f"轉錄完成: {name}", str(md))


def process_audio(filepath, kb_subdir="音頻", title=None, task_id=None):
    """聲音檔/資料夾 → Groq Whisper 轉錄 → KB 條目

    傳入目錄時，遞迴掃描音訊檔逐一轉錄，KB 依來源子目錄分層收成。
    """
    fp = Path(filepath)
    if not fp.exists():
        return _msg("error", f"檔案不存在: {filepath}")

    if fp.is_dir():
        files = []
        for f in sorted(fp.rglob("*")):
            if f.is_file() and f.suffix.lower() in AUDIO_EXTS:
                files.append(f)
        if not files:
            return _msg("error", f"目錄中沒有音訊檔: {fp}")
        base = fp.resolve()
        results = []
        ok_cnt = fail_cnt = skip_cnt = 0
        for i, f in enumerate(files, 1):
            rel = f.resolve().parent.relative_to(base)
            sub = os.path.join(str(kb_subdir), *rel.parts) if str(rel) != "." else str(kb_subdir)
            kb_dir = _kb_dir(sub)
            # 續傳：已收成的檔跳過（同名 md 已存在）
            existing_md = kb_dir / f"{safe_filename(f.stem)}.md"
            if existing_md.exists():
                skip_cnt += 1
                continue
            r = _process_audio_file(f, kb_dir, task_id=task_id, index=i, total=len(files))
            results.append(r)
            if r["status"] == "ok":
                ok_cnt += 1
            else:
                fail_cnt += 1
        msg = f"完成 {ok_cnt}/{len(files)} 檔" + (f"，{skip_cnt} 檔已存在跳過" if skip_cnt else "") + (f"，{fail_cnt} 檔失敗" if fail_cnt else "")
        return _msg("ok" if fail_cnt == 0 else "partial", msg)

    kb_dir = _kb_dir(kb_subdir)
    return _process_audio_file(fp, kb_dir, title=title, task_id=task_id)


# ── Document ──

def _extract_pdf(filepath, force_ocr=False, task_id=None):
    """PDF 文字提取，掃描檔自動降級 OCR"""
    import pypdf
    reader = pypdf.PdfReader(filepath)
    text_pages = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            text_pages.append(t)
    text = "\n".join(text_pages)
    if text.strip() and not force_ocr:
        return text
    # 空白 → 掃描 PDF，用 OCR
    return _ocr_pdf(filepath, task_id=task_id)


def _ocr_checkpoint_path(filepath):
    ckpt_dir = WORKING / "_ocr_checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.md5(str(Path(filepath).resolve()).encode()).hexdigest()[:12]
    return ckpt_dir / f"{h}.json"


def _save_checkpoint(ckpt_path, total, done_pages):
    ckpt_path.write_text(json.dumps({"total": total, "done_pages": done_pages, "updated": datetime.now().isoformat()}, ensure_ascii=False), encoding="utf-8")


def _load_checkpoint(ckpt_path, total):
    if ckpt_path.exists():
        try:
            data = json.loads(ckpt_path.read_text("utf-8"))
            if data.get("total") == total:
                return data.get("done_pages", {})
        except Exception:
            pass
    return {}


def _strip_think(text):
    """移除 Groq <think> 區塊，包含未閉合情況"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "<think>" in text:
        # 未閉合的 think 區塊：從最後一個 <think> 起切掉
        idx = text.rfind("<think>")
        text = text[:idx]
    return text.strip()


def _task_progress_path(task_id):
    if not task_id:
        return None
    pdir = WORKING / "_task_progress"
    pdir.mkdir(parents=True, exist_ok=True)
    return pdir / f"{task_id}.json"


def _write_progress(task_id, **kw):
    path = _task_progress_path(task_id)
    if not path:
        return
    data = {"updated": datetime.now().isoformat()}
    data.update(kw)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _ocr_lock(filepath, timeout=10):
    """同一 PDF 併發防護：取得獨佔鎖，避免多實例互寫檢查點"""
    lock_path = _ocr_checkpoint_path(filepath).with_suffix(".lock")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return lock_path
        except FileExistsError:
            # 檢查鎖是否過期（PID 已不存在）
            try:
                pid = int(lock_path.read_text().strip())
                if not _pid_alive(pid):
                    lock_path.unlink()
                    continue
            except Exception:
                pass
            time.sleep(1)
    return None


def _pid_alive(pid):
    try:
        import signal
        os.kill(pid, 0)
        return True
    except Exception:
        return False


class _QuotaStop(Exception):
    """每日 token 額度用盡，停止 OCR（不標記空頁，可續傳）"""
    pass


def _ocr_pdf_groq(filepath, model="qwen/qwen3.6-27b", task_id=None):
    """用 Groq Vision 逐頁 OCR（JPEG Q30, 600px wide），支援中斷續傳 + 併發防護 + 進度回報"""
    import groq, fitz, base64, time, re
    from io import BytesIO
    from PIL import Image

    api_key = os.environ.get("GROQ_API_KEY") or ""
    if not api_key:
        kf = Path.home() / ".groq_api_key"
        if kf.exists():
            api_key = kf.read_text("utf-8").strip()
    if not api_key:
        raise Exception("GROQ_API_KEY not found")

    ckpt_path = _ocr_checkpoint_path(filepath)

    # 併發防護：同一 PDF 同一時間只允許一個實例
    lock_path = _ocr_lock(filepath)
    if not lock_path:
        raise Exception(f"另一 OCR 實例正在處理此檔案（{_ocr_checkpoint_path(filepath).stem}.lock）")

    doc = fitz.open(filepath)
    total = len(doc)

    # 載入檢查點
    done_pages = _load_checkpoint(ckpt_path, total)
    if done_pages:
        # 空結果頁面（先前失敗）視為未完成，重新辨識
        empty_kept = [k for k, v in done_pages.items() if not str(v).strip()]
        if empty_kept:
            sys.stderr.write(f"[ocr-groq] 重新辨識空結果頁: {len(empty_kept)} 頁\n")
            done_pages = {k: v for k, v in done_pages.items() if str(v).strip()}
            _save_checkpoint(ckpt_path, total, done_pages)
    if done_pages:
        sys.stderr.write(f"[ocr-groq] 續傳模式: 已跳過 {len(done_pages)} 頁\n")

    client = groq.Groq(api_key=api_key, timeout=60, max_retries=0)

    for i in range(total):
        page_num = i + 1
        if str(page_num) in done_pages:
            continue  # 已處理

        page = doc[i]
        pix = page.get_pixmap(dpi=72)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        if pix.width > 600:
            ratio = 600 / pix.width
            img = img.resize((600, int(pix.height * ratio)), Image.LANCZOS)
        buf = BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=30)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        text = ""
        page_start = time.time()
        saved = False
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": [
                        {"type": "text", "text": "請辨識圖片中所有繁體中文字，輸出完整文字。"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                    ]}],
                    max_tokens=4096
                )
                t = resp.choices[0].message.content.strip() if resp.choices else ""
                if t:
                    t = _strip_think(t)
                    text = t
                    done_pages[str(page_num)] = t
                    sys.stderr.write(f"[ocr-groq] 第 {page_num}/{total}: {len(t)} 字\n")
                    _save_checkpoint(ckpt_path, total, done_pages)
                    _write_progress(task_id, type="ocr", page=page_num, total=total, done=len(done_pages), chars=len(t))
                    time.sleep(0.3)
                    saved = True
                    break
                # 空結果 → 視為失敗重試（最後一次才留空）
                sys.stderr.write(f"[ocr-groq] 第 {page_num} 頁空結果，重試\n")
                raise Exception("empty_response")
            except Exception as e:
                es = str(e)
                # 每日 token 額度（TPD）用盡 → 立即停止，不標空頁，等額度重置後續傳
                if "tokens per day" in es.lower() or "tokens per day (tpd)" in es.lower():
                    _write_progress(task_id, type="ocr", page=page_num, total=total,
                                    done=len(done_pages), status="paused",
                                    message="已達 Groq 每日額度，OCR 暫停；待額度重置後可續傳")
                    raise _QuotaStop(es[:300])
                is_ratelimit = "rate_limit" in es.lower() or "429" in es.lower()
                if attempt < 2:
                    wait = (20 * (attempt + 1)) if is_ratelimit else 5
                    sys.stderr.write(f"[ocr-groq] 第 {page_num} 頁{'速率限制' if is_ratelimit else '重試'} ({(attempt+1)}/3): {e}\n")
                    time.sleep(wait)
                else:
                    # 最後一次失敗（rate-limit 以外的錯誤）→ 存空結果，繼續下一頁
                    sys.stderr.write(f"[ocr-groq] 第 {page_num} 頁失敗放棄: {e}\n")
                    done_pages[str(page_num)] = ""
                    _save_checkpoint(ckpt_path, total, done_pages)
                    _write_progress(task_id, type="ocr", page=page_num, total=total, done=len(done_pages), chars=0)
                    saved = True
                    break
                # 頁面卡住過久 → 放棄此頁（留空）繼續下一頁
                if time.time() - page_start > 180 and not saved:
                    sys.stderr.write(f"[ocr-groq] 第 {page_num} 頁逾時（180s），跳過\n")
                    done_pages[str(page_num)] = ""
                    _save_checkpoint(ckpt_path, total, done_pages)
                    _write_progress(task_id, type="ocr", page=page_num, total=total, done=len(done_pages), chars=0)
                    saved = True
                    break

    doc.close()
    # 依頁碼排序輸出
    all_text = []
    for pg in sorted(int(k) for k in done_pages):
        txt = done_pages[str(pg)]
        if txt:
            all_text.append(f"--- 第 {pg} 頁 ---\n{txt}")
    # 完成後刪除檢查點與鎖
    for p in (ckpt_path, lock_path):
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass
    return "\n\n".join(all_text)


def _parse_gemini_pages(full_text, start):
    """解析 Gemini 輸出的「--- 第 N 頁 ---」區塊為 {絕對頁碼: 文字}

    注意：上傳給 Gemini 的是切割後的分段 PDF，頁碼從 1 重新編號，
    所以段內頁碼 N 要加上段起始頁偏移 start-1 才是原 PDF 頁碼。
    """
    pages = {}
    if not full_text:
        return pages
    pattern = re.compile(r"^-{3,}\s*第\s*(\d+)\s*頁\s*-{3,}\s*$")
    cur = None
    buf = []
    for line in full_text.splitlines():
        m = pattern.match(line.strip())
        if m:
            if cur is not None and buf:
                pages[str(start + cur - 1)] = "\n".join(buf).strip()
            cur = int(m.group(1))
            buf = []
        elif cur is not None:
            buf.append(line)
    if cur is not None and buf:
        pages[str(start + cur - 1)] = "\n".join(buf).strip()
    # 找不到標記時，整段塞進段首頁（至少保留文字）
    if not pages:
        pages[str(start)] = full_text
    return pages


def _ocr_pdf_gemini(filepath, model="gemini-3.5-flash-lite", task_id=None, chunk_pages=10):
    """用 Gemini 原生 PDF OCR（分段 inline 上傳，免逐頁轉圖），支援中斷續傳 + 併發防護 + 進度回報"""
    import fitz
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY") or ""
    if not api_key:
        kf = Path.home() / ".gemini_api_key"
        if kf.exists():
            api_key = kf.read_text("utf-8").strip()
    if not api_key:
        raise Exception("GEMINI_API_KEY not found")

    ckpt_path = _ocr_checkpoint_path(filepath)

    # 併發防護：同一 PDF 同一時間只允許一個實例
    lock_path = _ocr_lock(filepath)
    if not lock_path:
        raise Exception(f"另一 OCR 實例正在處理此檔案（{_ocr_checkpoint_path(filepath).stem}.lock）")

    doc = fitz.open(filepath)
    total = len(doc)

    # 載入檢查點
    done_pages = _load_checkpoint(ckpt_path, total)
    if done_pages:
        # 空結果頁面（先前失敗）視為未完成，重新辨識
        empty_kept = [k for k, v in done_pages.items() if not str(v).strip()]
        if empty_kept:
            sys.stderr.write(f"[ocr-gemini] 重新辨識空結果頁: {len(empty_kept)} 頁\n")
            done_pages = {k: v for k, v in done_pages.items() if str(v).strip()}
            _save_checkpoint(ckpt_path, total, done_pages)
    if done_pages:
        sys.stderr.write(f"[ocr-gemini] 續傳模式: 已跳過 {len(done_pages)} 頁\n")

    client = genai.Client(api_key=api_key)

    prompt = (
        "你是一個專業的繁體中文 OCR 引擎。請辨識下方 PDF 每一頁中的所有文字，"
        "完整輸出，不要省略、不要總結、不要加入任何評論。"
        "每一頁輸出開頭請用一行「--- 第 N 頁 ---」標記（N 為頁碼），"
        "接著輸出該頁全部文字。"
    )

    for start in range(1, total + 1, chunk_pages):
        end = min(start + chunk_pages - 1, total)
        need = [str(p) for p in range(start, end + 1) if str(p) not in done_pages]
        if not need:
            continue

        # 抽出分段 PDF（inline bytes，免 files.upload）
        chunk = fitz.open()
        chunk.insert_pdf(doc, from_page=start - 1, to_page=end - 1)
        pdf_bytes = chunk.tobytes()
        chunk.close()

        full_text = ""
        page_start_t = time.time()
        saved = False
        max_attempts = 8
        for attempt in range(max_attempts):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=[types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")],
                    config=types.GenerateContentConfig(
                        system_instruction=prompt, temperature=0.1
                    ),
                )
                full_text = (resp.text or "").strip()
                if not full_text:
                    raise Exception("empty_response")
                saved = True
                break
            except Exception as e:
                es = str(e)
                # 每日 token 額度用盡 → 停止，不標空頁，等重置後續傳
                if "tokens per day" in es.lower() or "daily tokens" in es.lower():
                    _write_progress(task_id, type="ocr", status="paused",
                                    message=f"已達 Gemini 每日額度，OCR 暫停（{es[:200]}）")
                    raise _QuotaStop(es[:300])
                # RPM（每分鐘請求數）限制：錯誤訊息會附建議等待秒數，等待後重試
                is_rpm = ("quota exceeded" in es.lower() or "resource_exhausted" in es.lower()) and "retry in" in es.lower()
                retry_sec = 30
                if is_rpm:
                    import re as _re
                    m = _re.search(r"retry in ([0-9.]+)s", es)
                    if m:
                        retry_sec = int(float(m.group(1))) + 2
                # 503 UNAVAILABLE：模型高需求，等待較久再重試
                is_503 = "503" in es or "unavailable" in es.lower()
                is_ratelimit = is_rpm or is_503 or "429" in es or "rate_limit" in es.lower()
                if attempt < max_attempts - 1:
                    if is_rpm:
                        wait = retry_sec
                        label = f"速率上限等待 {retry_sec}s"
                    elif is_503:
                        wait = 30 * (attempt + 1)
                        label = f"高需求等待 {wait}s"
                    else:
                        wait = 20 * (attempt + 1) if is_ratelimit else 8
                        label = f"重試等待 {wait}s"
                    sys.stderr.write(f"[ocr-gemini] 段 {start}-{end} {label} ({(attempt+1)}/{max_attempts}): {es[:120]}\n")
                    time.sleep(wait)
                else:
                    sys.stderr.write(f"[ocr-gemini] 段 {start}-{end} 失敗放棄: {e}\n")
                    full_text = ""
                    saved = True
                    break
                # 段卡住過久 → 放棄此段（留空）繼續下一段
                if time.time() - page_start_t > 600 and not saved:
                    full_text = ""
                    saved = True
                    break

        # 解析各頁文字
        seg = _parse_gemini_pages(full_text, start)
        for p in need:
            done_pages[p] = seg.get(p, "")
            if done_pages[p]:
                sys.stderr.write(f"[ocr-gemini] 第 {p}/{total}: {len(done_pages[p])} 字\n")
        _save_checkpoint(ckpt_path, total, done_pages)
        _write_progress(task_id, type="ocr", page=end, total=total,
                        done=len(done_pages), chars=sum(len(v) for v in done_pages.values()))
        time.sleep(3)

    doc.close()
    # 依頁碼排序輸出
    all_text = []
    for pg in sorted(int(k) for k in done_pages):
        txt = done_pages[str(pg)]
        if txt:
            all_text.append(f"--- 第 {pg} 頁 ---\n{txt}")
    # 完成後刪除檢查點與鎖
    for p in (ckpt_path, lock_path):
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass
    return "\n\n".join(all_text)


def _ocr_pdf(filepath, dpi=150, task_id=None):
    """掃描 PDF OCR：先試 Gemini，再 Groq Vision，最後降級 Tesseract"""
    try:
        import pytesseract, fitz
        from PIL import Image
    except ImportError:
        sys.stderr.write("[ocr] 缺少 pytesseract 或 pymupdf\n")
        return ""

    tess_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    tess_available = os.path.exists(tess_cmd)

    if tess_available:
        pytesseract.pytesseract.tesseract_cmd = tess_cmd

    doc = fitz.open(filepath)
    total = len(doc)
    all_text = []

    # Try Gemini first
    if total > 0:
        try:
            sys.stderr.write(f"[ocr] 嘗試 Gemini ({total} 頁)...\n")
            result = _ocr_pdf_gemini(filepath, task_id=task_id)
            if result.strip():
                doc.close()
                return result
        except _QuotaStop:
            doc.close()
            raise
        except Exception as e:
            sys.stderr.write(f"[ocr] Gemini 失敗: {e}，降級 Groq Vision\n")

    # Try Groq Vision second
    if total > 0:
        try:
            sys.stderr.write(f"[ocr] 嘗試 Groq Vision ({total} 頁，約 {total*25}s)...\n")
            result = _ocr_pdf_groq(filepath, task_id=task_id)
            if result.strip():
                doc.close()
                return result
        except _QuotaStop:
            doc.close()
            raise
        except Exception as e:
            sys.stderr.write(f"[ocr] Groq Vision 失敗: {e}，降級 Tesseract\n")

    # Fallback: Tesseract
    if not tess_available:
        doc.close()
        return ""

    for i in range(total):
        page = doc[i]
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img = img.convert("L").point(lambda x: 0 if x < 128 else 255)
        text = pytesseract.image_to_string(img, lang="chi_tra+eng", config="--psm 6")
        if text.strip():
            all_text.append(f"--- 第 {i+1} 頁 ---\n{text.strip()}")
        _write_progress(task_id, type="ocr-tesseract", page=i+1, total=total, done=i+1)
        if (i + 1) % 10 == 0:
            sys.stderr.write(f"[ocr] Tesseract 第 {i+1}/{total} 頁\n")

    doc.close()
    return "\n\n".join(all_text)





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


def process_document(filepath, kb_subdir="文件", title=None, task_id=None):
    """文件檔 → 文字提取 → KB 條目"""
    fp = Path(filepath)
    if not fp.exists():
        return _msg("error", f"檔案不存在: {filepath}")
    ext = fp.suffix.lower()
    name = (title or fp.stem).strip()
    src_id = hashlib.md5(str(fp.resolve()).encode()).hexdigest()[:8]
    kb_dir = _kb_dir(kb_subdir)

    handler = DOC_EXT_HANDLERS.get(ext)
    if not handler:
        return _msg("error", f"不支援的格式: {ext}（支援: {', '.join(DOC_EXT_HANDLERS)}）")

    try:
        if handler is _extract_pdf:
            content = handler(str(fp), task_id=task_id)
        else:
            content = handler(str(fp))
    except _QuotaStop:
        return _msg("paused", "已達 OCR API 每日額度，OCR 暫停；待額度重置後可續傳（檢查點已保存）")
    except Exception as e:
        return _msg("error", f"文字提取失敗: {e}")

    if not content.strip():
        ext_lower = ext.lower()
        if ext_lower == ".pdf":
            return _msg("error", "PDF 為掃描檔（無文字層），已嘗試 OCR 仍無法辨識。請檢查 Tesseract 是否安裝中文語言包（chi_tra），或手動將 PDF 轉成圖片後用聲音檔功能處理")
        return _msg("error", f"提取內容為空，不支援的檔案格式或檔案為空白")

    _write_progress(task_id, type="doc", stage="building", msg="建立 KB 條目中")
    content_preview = content[:200000]  # 限制 200000 字
    if len(content) > 200000:
        content_preview += f"\n\n--- (內容過長，僅顯示前 200000 字，原文 {len(content)} 字) ---"

    try:
        md = _create_kb_entry(src_id, name, content_preview, str(fp.resolve()), kb_dir)
    except Exception as e:
        return _msg("error", f"KB 建立失敗: {e}")

    sys.stderr.write(f"[doc] OK → {md}\n")
    return _msg("ok", f"文字提取完成: {name}（{len(content)} 字）", str(md))


# ── Web ──

def process_web(url, kb_subdir="網頁", title=None, task_id=None):
    """網頁 URL → 擷取內容 → KB 條目"""
    import requests
    from bs4 import BeautifulSoup
    if not url.startswith(("http://", "https://")):
        return _msg("error", "無效的網址，需以 http:// 或 https:// 開頭")
    name = (title or url).strip()
    src_id = hashlib.md5(url.encode()).hexdigest()[:8]
    kb_dir = _kb_dir(kb_subdir)

    _write_progress(task_id, type="web", stage="fetching", msg="取得網頁中")
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
    ap.add_argument("--task-id", default="", help="GUI 任務 ID（用於進度回報）")
    args = ap.parse_args()
    kb_map = {"audio": "音頻", "doc": "文件", "web": "網頁"}
    kb_subdir = args.kb or kb_map.get(args.type, "")
    title = args.title or None
    task_id = args.task_id or None
    if args.type == "audio":
        r = process_audio(args.source, kb_subdir, title, task_id)
    elif args.type == "doc":
        r = process_document(args.source, kb_subdir, title, task_id)
    else:
        r = process_web(args.source, kb_subdir, title, task_id)
    # 寫入最終狀態供 GUI 讀取
    if task_id:
        if r["status"] == "ok":
            final_status = "completed"
        elif r["status"] == "paused":
            final_status = "paused"
        elif r["status"] == "partial":
            final_status = "completed"
        else:
            final_status = "failed"
        _write_progress(task_id, status=final_status,
                        message=r.get("message", ""), result=r)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    sys.exit(0 if r["status"] == "ok" else 1)
