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


def burn_subtitles(video_path, srt_path, output_path, font_size=24, position="bottom"):
    """燒錄字幕到影片"""
    import subprocess

    # 字幕位置樣式
    if position == "top":
        margin_v = 30
        alignment = 6  # 上方置中
    else:
        margin_v = 30
        alignment = 2  # 下方置中

    # ffmpeg 燒字幕指令
    style = f"FontSize={font_size},MarginV={margin_v},Alignment={alignment}"
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"subtitles='{srt_path}':force_style='{style}'",
        "-c:a", "copy",
        output_path
    ]

    log(f"  執行: {' '.join(cmd[:5])}...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 失敗: {result.stderr[:500]}")

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
        video_path = info["video_path"]
        srt_path = info["srt_path"]
        output_dir = info.get("output_dir")
        font_size = info.get("font_size", 24)
        position = info.get("position", "bottom")

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

        # 燒字幕
        timer.step("burn_subtitles")
        burn_subtitles(video_path, srt_path, output_path, font_size, position)
        timer.step_done("burn_subtitles")

        # 完成
        log(f"  完成: {output_path}")
        task_queue.update_task_status(tid, "completed")
        timer.finish(success=True)
        return True

    except Exception as e:
        err = str(e)
        log(f"  [錯誤] {err}")
        task_queue.update_task_status(tid, "failed", error=err)
        timer.finish(success=False, error=err)
        return False


def _create_subtitle_task(orig_tid, info, video_path, output_dir):
    """影片完成後自動建立燒字幕任務"""
    try:
        srt_path = os.path.join(output_dir, "字幕.srt")
        if not os.path.isfile(srt_path):
            log(f"  [燒字幕] 跳過：找不到字幕檔 {srt_path}")
            return
        from scheduler import load_task_status, save_task_status
        data = load_task_status()
        counter = data.get("task_counter", 0) + 1
        data["task_counter"] = counter
        tid = str(counter)
        name = info.get("name", "unknown")
        data["tasks"][tid] = {
            "type": "subtitle", "status": "pending",
            "assigned_to": MACHINE, "priority": 0,
            "name": name,
            "video_path": video_path,
            "srt_path": srt_path,
            "output_dir": os.path.dirname(video_path),
            "font_size": 24, "position": "bottom",
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
        save_task_status(data)
        log(f"  [燒字幕] 已建立 #{tid}（原始 #{orig_tid}）")
    except Exception as e:
        log(f"  [燒字幕] 建立失敗: {e}")


def process_task(task):
    """處理單一任務"""
    tid = task["task_id"]
    info = task["task_info"]

    # 燒字幕任務獨立處理
    if info.get("type") == "subtitle":
        return process_subtitle_task(task)
    
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
        
        # 自動收成到知識庫
        timer.step("harvest")
        try:
            from scheduler import harvest
            harvest()
            log(f"  已收成到知識庫")
        except Exception as e:
            log(f"  [警告] 收成失敗: {e}")
        timer.step_done("harvest")

        # 自動燒字幕
        if info.get("auto_subtitle") and success:
            _create_subtitle_task(tid, info, video_path, output_dir)

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
        
        # 過濾 pending 任務
        pending_tasks = [
            t for t in assigned_tasks
            if t.get("status") in ["assigned", "pending"] or t.get("task_info", {}).get("status") in ["assigned", "pending"]
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
