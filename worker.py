#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Worker - 三機協同模式
各機器執行此腳本，輪詢共用目錄的任务並執行

PC2: 下載站（YouTube下載+轉寫）
PC1: 臨時站（臨時任務處理）
Notebook: 收成站（KB管理+pipeline執行）

用法:
  python worker.py                    ← 處理所有 pending
  python worker.py --once             ← 只跑一個任務
  python worker.py --retry-failed     ← 重試失敗的
  python worker.py --id T001          ← 指定任務
"""
import os, sys, json, subprocess, time, argparse, shutil, re
from pathlib import Path
from datetime import datetime
from plyer import notification

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *
from ipc import Heartbeat, ErrorReporter, TaskQueue
from watchdog import notify_line_and_email

# 初始化 IPC 模組
heartbeat = Heartbeat(MACHINE)
error_reporter = ErrorReporter(MACHINE)
task_queue = TaskQueue(MACHINE)

# 課程筆記預設樣板（沿用林教授樣板；不存在時退回 python-docx 預設格式）
DEFAULT_NOTE_TEMPLATE = os.path.join(
    str(PROJECT_ROOT), "knowledge-base", "金融交易", "理周學院", "林教授",
    "_preview_林教授 量價時間角度的三道菜 課程筆記.docx")
DEFAULT_NOTE_CHUNK_CHARS = 8000

def send_notify(title, message):
    try:
        notification.notify(title=title, message=message, timeout=10)
    except Exception:
        pass
    log(f"通知: {title} - {message}")

def get_free_space_gb(path):
    import ctypes
    free = ctypes.c_ulonglong(0)
    try:
        drive = os.path.splitdrive(path)[0] + "\\"
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(drive, None, None, ctypes.byref(free))
        return free.value / 1024**3
    except:
        return 0

def _write_task_progress(tid, **kw):
    """寫入任務進度檔（供 GUI 顯示階段與已執行時間；所有任務型別共用）"""
    try:
        pdir = os.path.join(LOCAL_ROOT, "working", "_task_progress")
        os.makedirs(pdir, exist_ok=True)
        data = {"updated": datetime.now().isoformat()}
        data.update(kw)
        with open(os.path.join(pdir, f"{tid}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass

def run_pipeline(video_path, slug=None):
    cmd = [sys.executable, "-X", "utf8", str(PROJECT_ROOT / "run_pipeline.py"), video_path, "--skip-cut"]
    
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        log(f"  Pipeline attempt {attempt}/{max_retries}...")
        
        tmp_out = os.path.join(get_machine_paths()["logs"], "_pipeline_out.tmp")
        tmp_err = os.path.join(get_machine_paths()["logs"], "_pipeline_err.tmp")
        
        with open(tmp_out, "w", encoding="utf-8") as fout, \
             open(tmp_err, "w", encoding="utf-8") as ferr:
            p = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), stdout=fout, stderr=ferr)
            try:
                p.wait(timeout=1800)
            except subprocess.TimeoutExpired:
                p.kill()
                log(f"  [逾時] attempt {attempt}")
                continue
        
        with open(tmp_err, "r", encoding="utf-8", errors="replace") as f:
            stderr = f.read()
        with open(tmp_out, "r", encoding="utf-8", errors="replace") as f:
            stdout = f.read()
        try:
            os.remove(tmp_out)
            os.remove(tmp_err)
        except:
            pass
        
        if p.returncode == 0:
            return True, None
        
        # 構建詳細錯誤訊息
        error_detail = f"Exit code: {p.returncode}"
        if stderr:
            error_detail += f"\nSTDERR: {stderr[:800]}"
        if stdout:
            error_detail += f"\nSTDOUT: {stdout[:800]}"
        if not stderr and not stdout:
            error_detail += "\nNo output captured (process may have crashed)"
        
        if "rate_limit_exceeded" in stderr or "Request too large" in stderr:
            log(f"  [Rate Limit] 等 65 分鐘...")
            time.sleep(65 * 60)
            continue
        
        if "SSL" in stderr or "EOF" in stderr or "Connection" in stderr:
            log(f"  [網路錯誤] 等 30 秒重試...")
            time.sleep(30)
            continue
        
        return False, error_detail
    
    return False, "max retries exceeded"

def compress_video(src_path):
    stem = Path(src_path).stem
    local_dst = os.path.join(str(PROJECT_ROOT), "working", "compressed", f"{stem}.mp3")
    os.makedirs(os.path.dirname(local_dst), exist_ok=True)
    
    if os.path.exists(local_dst):
        log(f"  mp3 已存在，跳過壓縮")
    else:
        log(f"  壓縮中...")
        cmd = ["ffmpeg", "-i", src_path, "-vn", "-acodec", "libmp3lame",
               "-ab", "16k", "-ac", "1", "-ar", "16000", local_dst, "-y"]
        r = subprocess.run(cmd, capture_output=True, text=False)
        if r.returncode != 0:
            err_text = r.stderr.decode("utf-8", errors="replace")[:500]
            log(f"  壓縮失敗: {err_text}")
            return None
    
    log(f"  壓縮完成: {stem}.mp3")
    return local_dst


def burn_subtitles(video_path, srt_path, output_path, font_size=18, position="bottom", margin_v=15,
                   font_family="微軟正黑體"):
    """燒錄字幕到影片"""
    import subprocess, tempfile, shutil

    # 字幕位置樣式：libass alignment 1-9
    # 7 8 9  (上)
    # 4 5 6  (中)
    # 1 2 3  (下)
    position_map = {
        "bottom":       2, "bottom-center": 2, "下": 2, "下中": 2,
        "bottom-left":  1, "下左": 1,
        "bottom-right": 3, "下右": 3,
        "top":          8, "top-center":    8, "上": 8, "上中": 8,
        "top-left":     7, "上左": 7,
        "top-right":    9, "上右": 9,
        "middle":       5, "mid-center":    5, "中": 5, "正中": 5,
        "middle-left":  4, "mid-left":      4, "中左": 4,
        "middle-right": 6, "mid-right":     6, "中右": 6,
    }
    alignment = position_map.get(position, 2)

    # ffmpeg filter 語法中 `:` 與 `,` 有特殊意義（選項分隔符/濾鏡鏈分隔符），
    # Windows 磁碟機代號 `D:` 會讓解析出錯。解法：
    # 1. 將 SRT 複製到不含特殊字元的暫存路徑
    # 2. 在 force_style 值內以 `\,` 跳脫逗號
    # 3. 使用相對路徑（不含磁碟機代號）避開 `:` 問題
    work_dir = os.path.join(tempfile.gettempdir(), "opencode_subtitle")
    os.makedirs(work_dir, exist_ok=True)
    tmp_srt = os.path.join(work_dir, "subtitle.srt")
    try:
        shutil.copy2(srt_path, tmp_srt)
    except Exception:
        # 若複製失敗，直接使用原始路徑
        tmp_srt = srt_path
        work_dir = os.path.dirname(srt_path)

    style = "FontSize={}\\,MarginV={}\\,Alignment={}".format(font_size, margin_v, alignment)
    if font_family:
        style += "\\,FontName={}".format(font_family)
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", "subtitles={}:force_style={}".format(os.path.basename(tmp_srt), style),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "copy",
        output_path
    ]

    log(f"  執行: ffmpeg -y -i <video> -vf subtitles=<srt>:force_style=<style> -c:v libx264 -preset veryfast -crf 20 -c:a copy <output>")
    result = subprocess.run(cmd, capture_output=True, text=False, timeout=7200, cwd=work_dir)

    if tmp_srt != srt_path and os.path.isfile(tmp_srt):
        try:
            os.unlink(tmp_srt)
        except Exception:
            pass

    if result.returncode != 0:
        err = result.stderr[-500:].decode("utf-8", errors="replace") if result.stderr else ""
        raise RuntimeError(f"ffmpeg 失敗: {err}")

    return output_path


def process_subtitle_task(task):
    """處理燒字幕任務"""
    tid = task["task_id"]
    info = task["task_info"]

    from tracker import TaskTimer
    timer = TaskTimer(tid)
    timer.start()

    log(f"\n{'─'*50}")
    log(f"開始燒字幕 #{tid}: {info['name']}")

    heartbeat.update(status="processing", current_task=tid)
    task_queue.update_task_status(tid, "processing")
    try:
        from scheduler import sync_shared_to_local
        sync_shared_to_local()
    except Exception:
        pass
    _write_task_progress(tid, status="processing", type="subtitle", stage="燒字幕",
                         started_at=info.get("started_at") or datetime.now().isoformat())

    try:
        video_path = os.path.normpath(info["video_path"])
        srt_path = os.path.normpath(info["srt_path"])
        output_dir = info.get("output_dir")
        if output_dir:
            output_dir = os.path.normpath(output_dir)
        font_size = info.get("font_size", 18)
        position = info.get("position", "bottom")
        margin_v = info.get("margin_v", 15)
        font_family = info.get("font_family") or "微軟正黑體"

        # 確認檔案存在
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"影片不存在: {video_path}")
        if not os.path.exists(srt_path):
            raise FileNotFoundError(f"字幕不存在: {srt_path}")

        # 決定輸出路徑
        stem = os.path.splitext(video_path)[0]
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, os.path.basename(stem) + "_字幕.mp4")
        else:
            output_path = stem + "_字幕.mp4"
        output_path = os.path.normpath(output_path)

        # 燒字幕
        timer.step("burn_subtitles")
        burn_subtitles(video_path, srt_path, output_path, font_size, position, margin_v, font_family)
        timer.step_done("burn_subtitles")

        # 完成
        log(f"  完成: {output_path}")
        task_queue.update_task_status(tid, "completed")
        _write_task_progress(tid, status="completed", type="subtitle", stage="完成")
        timer.finish(success=True)
        return True

    except Exception as e:
        err = str(e)
        log(f"  [錯誤] {err}")
        task_queue.update_task_status(tid, "failed", error=err)
        _write_task_progress(tid, status="failed", type="subtitle", message=err)
        timer.finish(success=False, error=err)
        return False


def _copy_output_to_source(output_dir, video_path, tid):
    """不收成 KB 時，將 .md/.srt 複製到來源目錄"""
    try:
        video_dir = os.path.dirname(video_path)
        video_stem = os.path.splitext(os.path.basename(video_path))[0]
        # 複製 metadata.md → {video_stem}.md
        meta_src = os.path.join(output_dir, "metadata.md")
        if os.path.isfile(meta_src):
            md_dst = os.path.join(video_dir, f"{video_stem}.md")
            shutil.copy2(meta_src, md_dst)
            log(f"  [產出] .md → {md_dst}")
        # 複製 字幕.srt
        srt_src = os.path.join(output_dir, "字幕.srt")
        if os.path.isfile(srt_src):
            srt_dst = os.path.join(video_dir, "字幕.srt")
            shutil.copy2(srt_src, srt_dst)
            log(f"  [產出] .srt → {srt_dst}")
    except Exception as e:
        log(f"  [產出] 複製失敗: {e}")


def _get_next_task_id():
    """掃描 shared/tasks 找出最大 ID，避免與現有任務衝突"""
    tasks_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared", "tasks")
    max_id = 0
    if os.path.exists(tasks_dir):
        for fname in os.listdir(tasks_dir):
            if fname.startswith("task_") and fname.endswith(".json"):
                try:
                    fid = int(fname.replace("task_", "").replace(".json", ""))
                    if fid > max_id:
                        max_id = fid
                except ValueError:
                    pass
    # 向上找第一個可用的 ID
    new_id = max_id + 1
    while True:
        test_file = os.path.join(tasks_dir, f"task_{new_id}.json")
        if not os.path.exists(test_file):
            return str(new_id)
        new_id += 1


def _create_subtitle_task(orig_tid, info, video_path, output_dir):
    """影片完成後自動建立燒字幕任務"""
    try:
        srt_path = os.path.join(output_dir, "字幕.srt")
        if not os.path.isfile(srt_path):
            log(f"  [燒字幕] 跳過：找不到字幕檔 {srt_path}")
            return
        from scheduler import load_task_status, save_task_status
        tid = _get_next_task_id()
        data = load_task_status()
        current_max = max((int(k) for k in data.get("tasks", {}) if k.isdigit()), default=0)
        if int(tid) <= current_max:
            tid = str(current_max + 1)
        name = info.get("name", "unknown")
        data["tasks"][tid] = {
            "type": "subtitle", "status": "pending",
            "assigned_to": MACHINE, "priority": 0,
            "name": name,
            "video_path": video_path,
            "srt_path": srt_path,
            "output_dir": os.path.dirname(video_path),
            "font_size": info.get("font_size", 18),
            "position": info.get("position", "bottom"),
            "margin_v": info.get("margin_v", 15),
            "font_family": info.get("font_family") or "微軟正黑體",
            "note": f"自動建立（原始任務 #{orig_tid}）",
            "discovered_at": datetime.now().isoformat(),
            "started_at": None, "completed_at": None,
            "last_error": None, "machine": None,
        }
        shared_task = {
            "task_id": tid, "task_info": data["tasks"][tid],
            "status": "pending", "assigned_to": MACHINE,
        }
        shared_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "shared", "tasks", f"task_{tid}.json")
        os.makedirs(os.path.dirname(shared_file), exist_ok=True)
        with open(shared_file, "w", encoding="utf-8") as f:
            json.dump(shared_task, f, indent=2)
        # 更新 task_counter 到最新值
        existing_ids = [int(k) for k in data.get("tasks", {}) if k.isdigit()]
        data["task_counter"] = max([int(tid)] + existing_ids + [data.get("task_counter", 0)])
        save_task_status(data)
        log(f"  [燒字幕] 已建立 #{tid}（原始 #{orig_tid}）")
        return tid
    except Exception as e:
        log(f"  [燒字幕] 建立失敗: {e}")
        return None


def process_note_task(task):
    """處理「產生課程筆記」任務：逐字稿 md → 詳細課程筆記（.md + .docx）"""
    tid = task["task_id"]
    info = task["task_info"]

    from tracker import TaskTimer
    timer = TaskTimer(tid)
    timer.start()

    log(f"\n{'─'*50}")
    log(f"開始產生課程筆記 #{tid}: {info.get('name')}")

    heartbeat.update(status="processing", current_task=tid)
    task_queue.update_task_status(tid, "processing")
    try:
        from scheduler import sync_shared_to_local
        sync_shared_to_local()
    except Exception:
        pass
    _write_task_progress(tid, status="processing", type="note", stage="準備逐字稿",
                         started_at=info.get("started_at") or datetime.now().isoformat())

    try:
        from make_course_note import generate_note
        title = info["title"]
        source_md = os.path.normpath(info["source_md"])
        out_dir = os.path.normpath(info["out_dir"])
        chunk_chars = int(info.get("chunk_chars", DEFAULT_NOTE_CHUNK_CHARS))
        template = info.get("template") or DEFAULT_NOTE_TEMPLATE
        if template and not os.path.isfile(template):
            template = None

        safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)
        md_out = os.path.join(out_dir, f"{safe_title} 課程筆記.md")

        # 去重：同名課程筆記已存在就跳過（決策⑥）
        if os.path.exists(md_out):
            log(f"  已存在課程筆記，跳過：{md_out}")
            task_queue.update_task_status(tid, "completed")
            _write_task_progress(tid, status="completed", type="note", stage="已存在，略過")
            timer.finish(success=True)
            return True

        if not os.path.isfile(source_md):
            raise FileNotFoundError(f"逐字稿 md 不存在: {source_md}")
        os.makedirs(out_dir, exist_ok=True)

        def _progress(msg):
            _write_task_progress(tid, status="processing", type="note", stage=str(msg)[:60],
                                 started_at=info.get("started_at") or datetime.now().isoformat())
            log(f"  {msg}")

        generate_note(title, [source_md], out_dir, template=template,
                      chunk_chars=chunk_chars, progress=_progress)

        log(f"  完成: {md_out}")
        task_queue.update_task_status(tid, "completed")
        _write_task_progress(tid, status="completed", type="note", stage="完成")
        timer.finish(success=True)
        return True

    except Exception as e:
        err = str(e)
        log(f"  [錯誤] {err}")
        task_queue.update_task_status(tid, "failed", error=err)
        _write_task_progress(tid, status="failed", type="note", message=err)
        timer.finish(success=False, error=err)
        return False


def process_document_task(task):
    """處理「文件/網頁圖片 OCR」任務：呼叫 file_processors（含內嵌圖片）→ KB 條目
    task_info 需含：type=doc|web, source(路徑或網址), kb_subdir, title, max_images(可選,0=無限)"""
    tid = task["task_id"]
    info = task["task_info"]

    from tracker import TaskTimer
    timer = TaskTimer(tid)
    timer.start()

    log(f"\n{'─'*50}")
    log(f"開始處理文件 #{tid}: {info.get('name') or info.get('title')}")

    heartbeat.update(status="processing", current_task=tid)
    task_queue.update_task_status(tid, "processing")
    try:
        from scheduler import sync_shared_to_local
        sync_shared_to_local()
    except Exception:
        pass

    doctype = info.get("doc_type") or info.get("type") or "doc"
    source = info.get("source") or info.get("url") or info.get("path") or ""
    kb_subdir = info.get("kb_subdir") or ("網頁" if doctype == "web" else "文件")
    title = info.get("title") or None
    max_images = info.get("max_images")
    started = info.get("started_at") or datetime.now().isoformat()
    _write_task_progress(tid, status="processing", type=doctype, stage="提取內容（含圖片）",
                         started_at=started)

    try:
        import file_processors as fp
        if doctype == "web":
            r = fp.process_web(source, kb_subdir, title, tid, max_images=max_images)
        else:
            r = fp.process_document(source, kb_subdir, title, tid, max_images=max_images)
    except Exception as e:
        err = str(e)
        log(f"  [錯誤] {err}")
        task_queue.update_task_status(tid, "failed", error=err)
        _write_task_progress(tid, status="failed", type=doctype, message=err)
        timer.finish(success=False, error=err)
        return False

    status = r.get("status")
    msg = r.get("message", "")
    if status == "ok":
        log(f"  完成: {msg}")
        task_queue.update_task_status(tid, "completed")
        _write_task_progress(tid, status="completed", type=doctype, stage="完成", message=msg)
        timer.finish(success=True)
        return True
    if status == "paused":
        # 撞每日辨識上限：標 paused，隔日 worker 重拾同任務即自動接續（檢查點續傳）
        log(f"  暫停（待額度重置）: {msg}")
        task_queue.update_task_status(tid, "paused")
        _write_task_progress(tid, status="paused", type=doctype,
                             stage="已達每日上限，隔日自動續", message=msg)
        timer.finish(success=True)
        return False
    log(f"  [失敗] {msg}")
    task_queue.update_task_status(tid, "failed", error=msg)
    _write_task_progress(tid, status="failed", type=doctype, message=msg)
    timer.finish(success=False, error=msg)
    return False


def _read_harvested_kb_md(tid):
    """從 shared/tasks 讀取收成後記錄的 KB md 路徑（harvest 會寫入 task_info.kb_md）"""
    try:
        shared_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "shared", "tasks", f"task_{tid}.json")
        if not os.path.isfile(shared_file):
            return None
        with open(shared_file, "r", encoding="utf-8") as f:
            shared = json.load(f)
        return shared.get("task_info", {}).get("kb_md")
    except Exception:
        return None


def _create_note_task(orig_tid, kb_md):
    """收成後自動建立「產生課程筆記」任務（來源＝KB 逐字稿 md，輸出同目錄）"""
    try:
        if not kb_md or not os.path.isfile(kb_md):
            log(f"  [筆記] 跳過：找不到知識庫逐字稿 md（{kb_md}）")
            return None
        out_dir = os.path.dirname(kb_md)
        title = os.path.splitext(os.path.basename(kb_md))[0]
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)
        if os.path.exists(os.path.join(out_dir, f"{safe_title} 課程筆記.md")):
            log(f"  [筆記] 跳過：已存在「{safe_title} 課程筆記.md」")
            return None
        from scheduler import load_task_status, save_task_status
        tid = _get_next_task_id()
        data = load_task_status()
        current_max = max((int(k) for k in data.get("tasks", {}) if k.isdigit()), default=0)
        if int(tid) <= current_max:
            tid = str(current_max + 1)
        data["tasks"][tid] = {
            "type": "note", "status": "pending",
            "assigned_to": MACHINE, "priority": 0,
            "name": f"{title} 課程筆記",
            "title": title,
            "source_md": kb_md,
            "out_dir": out_dir,
            "chunk_chars": DEFAULT_NOTE_CHUNK_CHARS,
            "template": DEFAULT_NOTE_TEMPLATE if os.path.isfile(DEFAULT_NOTE_TEMPLATE) else None,
            "note": f"自動建立（原始任務 #{orig_tid}）",
            "discovered_at": datetime.now().isoformat(),
            "started_at": None, "completed_at": None,
            "last_error": None, "machine": None,
        }
        shared_task = {
            "task_id": tid, "task_info": data["tasks"][tid],
            "status": "pending", "assigned_to": MACHINE,
        }
        shared_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "shared", "tasks", f"task_{tid}.json")
        os.makedirs(os.path.dirname(shared_file), exist_ok=True)
        with open(shared_file, "w", encoding="utf-8") as f:
            json.dump(shared_task, f, indent=2, ensure_ascii=False)
        existing_ids = [int(k) for k in data.get("tasks", {}) if k.isdigit()]
        data["task_counter"] = max([int(tid)] + existing_ids + [data.get("task_counter", 0)])
        save_task_status(data)
        log(f"  [筆記] 已建立 #{tid}（原始 #{orig_tid}）")
        return tid
    except Exception as e:
        log(f"  [筆記] 建立失敗: {e}")
        return None


def process_task(task):
    """處理單一任務"""
    tid = task["task_id"]
    info = task["task_info"]

    # 燒字幕任務獨立處理
    if info.get("type") == "subtitle":
        return process_subtitle_task(task)

    # 課程筆記任務獨立處理
    if info.get("type") == "note":
        return process_note_task(task)

    # 文件/網頁（含內嵌圖片 OCR）任務獨立處理
    if info.get("type") in ("doc", "document", "web"):
        return process_document_task(task)
    
    # 初始化追蹤器
    from tracker import TaskTimer, OutputValidator, ErrorTracker, HealthChecker
    timer = TaskTimer(tid)
    error_tracker = ErrorTracker()
    health_checker = HealthChecker()
    
    timer.start()
    
    log(f"\n{'─'*50}")
    log(f"開始處理 #{tid}: {info['name']}")
    
    # 更新心跳：正在處理
    heartbeat.update(status="processing", current_task=tid)
    task_queue.update_task_status(tid, "processing")
    try:
        from scheduler import sync_shared_to_local
        sync_shared_to_local()
    except Exception:
        pass
    _write_task_progress(tid, status="processing", type=info.get("type", "video"),
                         stage="檢查環境",
                         started_at=info.get("started_at") or datetime.now().isoformat())
    
    # 健康檢查
    timer.step("health_check")
    health = health_checker.full_check()
    timer.step_done("health_check")
    
    if not health["healthy"]:
        err = f"健康檢查失敗: 磁碟={health['disk']['gb']}GB, 記憶體={health['memory']['pct']}%"
        log(f"  [跳過] {err}")
        error_tracker.report(tid, err, error_type="health_check_failed")
        task_queue.update_task_status(tid, "failed", error=err)
        timer.finish(success=False, error=err)
        return False
    
    # 磁碟空間檢查
    video_size = info.get("size_mb", 150)
    free_gb = health["disk"]["gb"]
    
    if free_gb < 1:
        err = f"磁碟空間不足: {free_gb:.1f} GB"
        log(f"  [跳過] {err}")
        error_tracker.report(tid, err, error_type="disk_full")
        task_queue.update_task_status(tid, "failed", error=err)
        timer.finish(success=False, error=err)
        return False
    
    # 確認影片存在
    video_path = info.get("video_relpath", "")
    # 如果是相對路徑，嘗試多個基礎目錄
    if not os.path.isabs(video_path):
        possible_bases = [
            r"D:\!!!!!理周學院老師",
            r"D:\!!!!!理周學院老師\察爾思",
            r"D:\AI-Agent-Workspace\videos",
            get_machine_paths()["videos"],
        ]
        found = False
        for base in possible_bases:
            full_path = os.path.join(base, video_path)
            if os.path.exists(full_path):
                video_path = full_path
                found = True
                break
        if not found:
            # 使用第一個基礎目錄作為預設
            video_path = os.path.join(possible_bases[0], video_path)
    
    # 確認影片存在
    timer.step("validate_video")
    if not os.path.exists(video_path):
        err = f"影片不存在: {video_path}"
        log(f"  [錯誤] {err}")
        error_tracker.report(tid, err, error_type="file_not_found")
        task_queue.update_task_status(tid, "failed", error=err)
        timer.finish(success=False, error=err)
        return False
    
    # 如果是目錄，掃描影音檔案
    if os.path.isdir(video_path):
        video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm')
        video_files = [f for f in os.listdir(video_path) if f.lower().endswith(video_extensions)]
        if not video_files:
            err = f"目錄中沒有影音檔案: {video_path}"
            log(f"  [錯誤] {err}")
            error_tracker.report(tid, err, error_type="no_video_files")
            task_queue.update_task_status(tid, "failed", error=err)
            timer.finish(success=False, error=err)
            return False
        # 使用第一個影音檔案
        video_path = os.path.join(video_path, video_files[0])
        log(f"  找到 {len(video_files)} 個影音檔案，使用第一個: {video_files[0]}")
    timer.step_done("validate_video")
    
    log(f"  影片: {video_path} ({info.get('size_mb', '?')} MB)")
    
    # 壓縮
    timer.step("compress")
    compressed = compress_video(video_path)
    timer.step_done("compress")
    
    if not compressed:
        err = "壓縮失敗"
        log(f"  [錯誤] {err}")
        error_tracker.report(tid, err, error_type="compress_failed")
        task_queue.update_task_status(tid, "failed", error=err)
        timer.finish(success=False, error=err)
        return False
    
    # 建立工作目錄
    course_dir = info["course"]
    clean_name = re.sub(r'[^\w\-]', '_', info['name'])[:40].strip('_')
    task_slug = f"{tid}_{clean_name}"
    working_dir = os.path.join(str(PROJECT_ROOT), "working", course_dir, task_slug)
    os.makedirs(working_dir, exist_ok=True)
    pipeline_input = os.path.join(working_dir, "audio.mp3")
    if os.path.abspath(compressed) != os.path.abspath(pipeline_input):
        shutil.copy2(compressed, pipeline_input)
    
    # Pipeline
    _write_task_progress(tid, status="processing", type=info.get("type", "video"),
                         stage="轉錄/產生筆記",
                         started_at=info.get("started_at") or datetime.now().isoformat())
    timer.step("pipeline")
    log(f"  執行 pipeline...")
    success, error_msg = run_pipeline(pipeline_input, slug=task_slug)
    pipeline_time = timer.step_done("pipeline")
    
    if success:
        # 驗證輸出
        timer.step("validate_output")
        output_dir = os.path.join(get_machine_paths()["output"], task_slug)
        validator = OutputValidator(output_dir)
        output_valid, issues = validator.validate()
        timer.step_done("validate_output")
        
        if not output_valid:
            log(f"  [警告] 輸出驗證問題:")
            for issue in issues:
                log(f"    - {issue['message']}")
        
        # 複製產出到共用目錄
        timer.step("upload")
        if os.path.exists(output_dir):
            task_queue.upload_results(tid, output_dir)
            log(f"  產出已同步到共用目錄")
        timer.step_done("upload")
        
        # 先標記 completed，再收成（harvest 從 shared 讀取 completed 狀態）
        total_time = timer.finish(success=True)
        log(f"  [完成] #{tid} {info['name']} (耗時: {total_time:.1f}秒)")
        task_queue.update_task_status(tid, "completed")
        
        # 同步到 task_status.json（GUI 需要）
        try:
            from scheduler import sync_shared_to_local
            sync_shared_to_local()
        except Exception:
            pass
        
        harvest_to_kb = info.get("harvest_to_kb", True)
        if harvest_to_kb:
            _write_task_progress(tid, status="processing", type=info.get("type", "video"),
                                 stage="收成知識庫",
                                 started_at=info.get("started_at") or datetime.now().isoformat())
            timer.step("harvest")
            try:
                from scheduler import harvest
                harvest()
                log(f"  已收成到知識庫")
            except Exception as e:
                log(f"  [警告] 收成失敗: {e}")
            timer.step_done("harvest")
        else:
            _copy_output_to_source(output_dir, video_path, tid)

        # 自動產生課程筆記（需先收成到知識庫，來源＝KB 逐字稿 md）
        if info.get("auto_note") and success and harvest_to_kb:
            _write_task_progress(tid, status="processing", type=info.get("type", "video"),
                                 stage="產生課程筆記",
                                 started_at=info.get("started_at") or datetime.now().isoformat())
            kb_md = _read_harvested_kb_md(tid)
            note_tid = _create_note_task(tid, kb_md)
            if note_tid:
                try:
                    from scheduler import load_task_status
                    st = load_task_status()
                    if note_tid in st.get("tasks", {}):
                        note_task = {
                            "task_id": note_tid,
                            "task_info": st["tasks"][note_tid],
                            "status": "pending",
                            "assigned_to": MACHINE,
                        }
                        process_note_task(note_task)
                        log(f"  [筆記] #{note_tid} 已在同一次處理中完成")
                except Exception as e:
                    log(f"  [筆記] 內嵌執行失敗: {e}（任務保留，可再重試）")

        # 自動燒字幕（帶入字幕樣式設定）
        if info.get("auto_subtitle") and success:
            sub_info = dict(info)
            sub_info["font_size"] = info.get("auto_subtitle_font_size", 18)
            sub_info["position"] = info.get("auto_subtitle_position", "bottom")
            sub_info["margin_v"] = info.get("auto_subtitle_margin_v", 15)
            sub_info["font_family"] = info.get("auto_subtitle_font_family") or "微軟正黑體"
            sub_tid = _create_subtitle_task(tid, sub_info, video_path, output_dir)
            # 立即內嵌執行燒字幕：不依賴下次 worker 輪詢，燒完影片當場產出
            if sub_tid:
                try:
                    from scheduler import load_task_status
                    st = load_task_status()
                    if sub_tid in st.get("tasks", {}):
                        sub_task = {
                            "task_id": sub_tid,
                            "task_info": st["tasks"][sub_tid],
                            "status": "pending",
                            "assigned_to": MACHINE,
                        }
                        process_subtitle_task(sub_task)
                        log(f"  [燒字幕] #{sub_tid} 已在同一次處理中燒錄完成")
                except Exception as e:
                    log(f"  [燒字幕] 內嵌執行失敗: {e}（任務保留，可再重試）")

        _write_task_progress(tid, status="completed", type=info.get("type", "video"), stage="完成")
        heartbeat.update(status="online", current_task=None)
        return True
    else:
        log(f"  [失敗] #{tid}: {error_msg}")
        error_tracker.report(tid, error_msg, error_type="pipeline_failed")
        
        # 自動重試邏輯
        retry_count = info.get("retry_count", 0)
        max_retries = 3
        if retry_count < max_retries:
            info["retry_count"] = retry_count + 1
            info["status"] = "pending"
            info["last_error"] = error_msg
            task["task_info"] = info
            task["status"] = "pending"
            task["last_updated"] = __import__("datetime").datetime.now().isoformat()
            with open(os.path.join("shared", "tasks", f"task_{tid}.json"), "w", encoding="utf-8") as f:
                json.dump(task, f, indent=2, ensure_ascii=False)
            log(f"  [重試] #{tid} 第 {info['retry_count']}/{max_retries} 次")
            heartbeat.update(status="online", current_task=None)
            timer.finish(success=False, error=error_msg)
            return False
        
        # 超過重試次數，標記為永久失敗
        task_queue.update_task_status(tid, "failed", error=error_msg)
        _write_task_progress(tid, status="failed", type=info.get("type", "video"), message=error_msg)
        
        # 同步到 task_status.json
        try:
            from scheduler import sync_shared_to_local
            sync_shared_to_local()
        except Exception:
            pass
        
        heartbeat.update(status="online", current_task=None)
        timer.finish(success=False, error=error_msg)
        notify_line_and_email(f"[Worker] 任務永久失敗", f"#{tid} {info['name']}\n錯誤: {error_msg}\n已重試 {max_retries} 次")
        return False

def recover_stuck_tasks(timeout_minutes=30):
    """修復卡在 processing 的任務：worker 崩潰後殘留的 processing 狀態不會被新 worker 處理。
    啟動時與 watchdog 巡檢時呼叫，將超時的 processing 任務重置為 pending。"""
    tasks_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared", "tasks")
    if not os.path.exists(tasks_dir):
        return 0

    recovered = 0
    now = datetime.now()

    for fname in os.listdir(tasks_dir):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(tasks_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                ti = json.load(f)
            info = ti.get("task_info", {})
            if info.get("status") != "processing":
                continue

            started_str = info.get("started_at")
            if not started_str:
                stuck = True
            else:
                try:
                    started = datetime.fromisoformat(started_str)
                    elapsed_min = (now - started).total_seconds() / 60
                    stuck = elapsed_min > timeout_minutes
                except (ValueError, TypeError):
                    stuck = True

            if stuck:
                task_id = info.get("task_id", fname.replace("task_", "").replace(".json", ""))
                info["status"] = "pending"
                info["assigned_to"] = None
                info["started_at"] = None
                info["machine"] = None
                info["last_error"] = f"Auto-recovered: stuck in processing >{timeout_minutes}min (worker crash?)"
                ti["task_info"] = info
                ti["status"] = "pending"
                ti["assigned_to"] = None
                ti["last_updated"] = now.isoformat()
                ti["updated_by"] = MACHINE
                ti["error"] = None
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(ti, f, indent=2, ensure_ascii=False)
                log(f"  [修復] #{task_id} 從 processing 重置為 pending (卡住 > {timeout_minutes} 分鐘)")
                recovered += 1
        except Exception as e:
            log(f"  [警告] 修復 {fname} 時出錯: {e}")

    return recovered


def main():
    parser = argparse.ArgumentParser(description="Worker")
    parser.add_argument("--once", action="store_true", help="只處理一個任務")
    parser.add_argument("--retry-failed", action="store_true", help="重試失敗的")
    parser.add_argument("--id", help="指定任務 ID")
    args = parser.parse_args()
    
    log(f"Worker 啟動 (機器: {MACHINE}, 角色: {get_machine_role()})")
    log(f"D 槽空間: {get_free_space_gb('D:\\'):.1f} GB")
    
    # 啟動時修復卡住的 processing 任務
    recovered = recover_stuck_tasks(timeout_minutes=30)
    if recovered > 0:
        log(f"  已修復 {recovered} 個卡住的任務")
    
    # 更新心跳：上線
    heartbeat.update(status="online")
    
    while True:
        # 更新心跳
        heartbeat.update(status="online")
        
        # 從共用目錄取得分配的任務
        assigned_tasks = task_queue.get_assigned_tasks()
        
        # 過濾 pending 任務（含 paused＝撞每日上限待續，隔日自動重拾接續）
        pending_tasks = [
            t for t in assigned_tasks
            if t.get("status") in ["assigned", "pending", "paused"] or t.get("task_info", {}).get("status") in ["assigned", "pending", "paused"]
        ]
        
        if args.id:
            pending_tasks = [t for t in pending_tasks if t["task_id"] == args.id]
        
        if not pending_tasks:
            log(f"沒有任務需要處理，等待 30 秒...")
            if args.once:
                break
            time.sleep(30)
            continue
        
        log(f"待處理: {len(pending_tasks)} 部")
        
        success = 0
        failed = 0
        for i, task in enumerate(pending_tasks):
            free_gb = get_free_space_gb("D:\\")
            log(f"\n[{i+1}/{len(pending_tasks)}] D 槽剩 {free_gb:.1f} GB")
            
            if free_gb < 0.5:
                log(f"  跳過: 磁碟空間不足")
                break
            
            try:
                ok = process_task(task)
            except Exception as e:
                log(f"  [FATAL] 任務異常: {e}")
                ok = False
            
            if ok:
                success += 1
            else:
                failed += 1
            
            if args.once:
                break
            
            if i < len(pending_tasks) - 1:
                time.sleep(5)
        
        log(f"\n{'='*50}")
        log(f"執行完畢: 成功 {success} / 失敗 {failed}")
        log(f"D 槽剩: {get_free_space_gb('D:\\'):.1f} GB")
        
        if args.once:
            break
        
        log(f"重新檢查新任務...")
        time.sleep(10)

if __name__ == "__main__":
    main()
