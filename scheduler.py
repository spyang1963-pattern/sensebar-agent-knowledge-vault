#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
排程器 - 三機協同模式
掃描影片 → 分配任務 → 收成到知識庫

用法:
  python scheduler.py --validate               ← 預檢目錄
  python scheduler.py --validate "F:\新課程"    ← 預檢指定路徑
  python scheduler.py --validate --auto-fix     ← 預檢並自動修正
  python scheduler.py --scan                    ← 掃描目錄
  python scheduler.py --scan "F:\新課程"        ← 掃描指定路徑
  python scheduler.py --watch                   ← 持續監控（每 5 分鐘）
  python scheduler.py --harvest                 ← 收成到知識庫
  python scheduler.py --assign                  ← 分配任務給各機器
  python scheduler.py --status                  ← 顯示三機狀態
"""
import os, sys, json, time, glob, shutil, argparse, re
from datetime import datetime
from plyer import notification

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *
from disk_checker import DiskCheck, D_DRIVE_SAFE_GB
from watchdog import start_watchdog

# 已跳過的課程（講座/不需要處理）
SKIP_COURSES = {
    "0.1.操盤手給散戶的三忠告   (講座)",
    "0.2 準備「期權」 安心上路   (講座)",
    "0.4  「撿錢黃金點」隔日沖到ETF套利實戰   (講座)",
}

def send_notify(title, message):
    try:
        notification.notify(title=title, message=message, timeout=10)
    except Exception:
        pass
    log(f"通知: {title} - {message}")

# ── 掃描 ──────────────────────────────────────────────────

def scan_directory(source_dir=None):
    scan_root = source_dir or get_machine_paths()["videos"]
    if not os.path.exists(scan_root):
        log(f"目錄不存在: {scan_root}")
        return []

    log(f"掃描: {scan_root}")
    found = []

    # 掃描所有支援的影音格式
    video_extensions = ["*.mp4", "*.mkv", "*.avi", "*.mov", "*.wmv", "*.flv", "*.webm"]
    for ext in video_extensions:
        for video_file in glob.glob(os.path.join(scan_root, "**", ext), recursive=True):
            size_mb = os.path.getsize(video_file) / (1024 * 1024)
            if size_mb < 1:
                continue

            rel = os.path.relpath(video_file, scan_root)
            parts = rel.split(os.sep)
            course = parts[0] if len(parts) > 1 else "未知課程"
            name = os.path.basename(video_file)

            found.append({
                "path": video_file,
                "name": name,
                "course": course,
                "size_mb": round(size_mb, 1),
            })

    log(f"找到 {len(found)} 部影片")
    return found

def _get_max_task_id():
    """取得 shared/tasks 中最大 ID + task_status.json 中最大 ID"""
    max_id = 0
    tasks_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared", "tasks")
    if os.path.exists(tasks_dir):
        for fname in os.listdir(tasks_dir):
            if fname.startswith("task_") and fname.endswith(".json"):
                try:
                    fid = int(fname.replace("task_", "").replace(".json", ""))
                    if fid > max_id:
                        max_id = fid
                except ValueError:
                    pass
    return max_id


def create_tasks(videos):
    data = load_task_status()
    tasks = data["tasks"]
    max_id = _get_max_task_id()

    existing = set()
    for tid, info in tasks.items():
        existing.add((info["course"], info["name"]))

    new_count = 0
    for v in videos:
        key = (v["course"], v["name"])
        if key in existing:
            continue
        if v["course"] in SKIP_COURSES:
            continue

        max_id += 1
        tid = str(max_id)

        status = STATUS_PENDING

        tasks[tid] = {
            "status": status,
            "course": v["course"],
            "name": v["name"],
            "video_relpath": v["path"],
            "size_mb": v["size_mb"],
            "discovered_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "last_error": None,
            "assigned_to": None,
            "harvested": False,
        }
        new_count += 1
        log(f"  新任務 #{tid}: {v['course']} / {v['name']}")

    if new_count > 0:
        data["task_counter"] = max_id
        data["generated_at"] = datetime.now().isoformat()
        save_task_status(data)
        log(f"新增 {new_count} 個任務")
        send_notify(f"新影片 {new_count} 部", "已加入任務佇列")

    return new_count

# ── 任務分配 ──────────────────────────────────────────────

def assign_tasks():
    """根據機器能力分配任務"""
    data = load_task_status()
    tasks = data["tasks"]
    
    # 檢查各機器在線狀態
    machine_status = {}
    for machine in ["pc1", "pc2", "notebook"]:
        machine_status[machine] = check_machine_online(machine)
    
    log(f"機器狀態: {machine_status}")
    
    # 找出待分配的任務
    pending_tasks = [
        (tid, info) for tid, info in tasks.items()
        if info["status"] == STATUS_PENDING and not info.get("assigned_to")
    ]
    
    if not pending_tasks:
        log("沒有待分配的任務")
        return 0
    
    assigned_count = 0
    for tid, info in pending_tasks:
        # 根據任務類型分配
        task_type = info.get("type", "video")
        assigned_machine = None
        
        if task_type == "youtube_download":
            # YouTube下載任務 → PC2
            if machine_status.get("pc2"):
                assigned_machine = "pc2"
        elif task_type == "adhoc_download":
            # 臨時下載任務 → PC1
            if machine_status.get("pc1"):
                assigned_machine = "pc1"
        else:
            # 一般影片處理 → 根據負載分配
            # 簡單策略：輪流分配
            if machine_status.get("pc2"):
                assigned_machine = "pc2"
            elif machine_status.get("pc1"):
                assigned_machine = "pc1"
            elif machine_status.get("notebook"):
                assigned_machine = "notebook"
        
        if assigned_machine:
            tasks[tid]["assigned_to"] = assigned_machine
            tasks[tid]["status"] = STATUS_ASSIGNED
            assigned_count += 1
            log(f"  分配 #{tid} → {assigned_machine}")
    
    if assigned_count > 0:
        data["generated_at"] = datetime.now().isoformat()
        save_task_status(data)
        log(f"已分配 {assigned_count} 個任務")
        # 同步到 shared/tasks/ 目錄
        sync_tasks_to_shared(data)
    
    return assigned_count

def sync_tasks_to_shared(data=None):
    """同步 task_status.json 到 shared/tasks/ 目錄"""
    if data is None:
        data = load_task_status()
    
    shared_tasks_dir = os.path.join(SHARED_ROOT, "tasks")
    os.makedirs(shared_tasks_dir, exist_ok=True)
    
    synced = 0
    for tid, info in data["tasks"].items():
        if info["status"] not in (STATUS_ASSIGNED, STATUS_PROCESSING, STATUS_PENDING):
            continue
        
        # 建立 shared task 格式
        shared_task = {
            "task_id": tid,
            "task_info": {
                "type": info.get("type", "video"),
                "status": info["status"],
                "assigned_to": info.get("assigned_to"),
                "priority": info.get("priority", 0),
                "course": info["course"],
                "name": info["name"],
                "video_relpath": info.get("video_relpath", ""),
                "size_mb": info.get("size_mb", 0),
                "needs_compress": info.get("needs_compress", True),
                "note": info.get("note", ""),
                "discovered_at": info.get("discovered_at"),
                "started_at": info.get("started_at"),
                "completed_at": info.get("completed_at"),
                "last_error": info.get("last_error"),
                "machine": info.get("machine"),
                "output_keys": info.get("output_keys", []),
            },
            "status": info["status"],
            "assigned_to": info.get("assigned_to"),
        }
        
        task_file = os.path.join(shared_tasks_dir, f"task_{tid}.json")
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(shared_task, f, indent=2)
        synced += 1
    
    if synced > 0:
        log(f"已同步 {synced} 個任務到 shared/tasks/")

def sync_shared_to_local():
    """從 shared/tasks/*.json 同步狀態到 task_status.json（shared 為唯一狀態源）"""
    shared_tasks_dir = os.path.join(SHARED_ROOT, "tasks")
    if not os.path.exists(shared_tasks_dir):
        return

    data = load_task_status()
    synced = 0

    for fname in os.listdir(shared_tasks_dir):
        if not fname.endswith(".json"):
            continue
        # task_123.json -> 123
        tid = fname[5:-5]
        if not tid.isdigit():
            continue

        task_file = os.path.join(shared_tasks_dir, fname)
        try:
            with open(task_file, "r", encoding="utf-8") as f:
                shared = json.load(f)
        except Exception:
            continue

        ti = shared.get("task_info", {})
        shared_status = ti.get("status") or shared.get("status")
        if not shared_status:
            continue

        # 更新 local task_status.json
        if tid in data["tasks"]:
            local = data["tasks"][tid]
            changed = False
            for key in ("started_at", "completed_at", "machine", "last_error", "assigned_to"):
                sv = ti.get(key)
                if sv is not None and sv != local.get(key):
                    local[key] = sv
                    changed = True
            if shared_status != local.get("status"):
                local["status"] = shared_status
                changed = True
            if changed:
                synced += 1
        else:
            # shared 裡有但 local 沒有 -> 新增
            data["tasks"][tid] = {
                "status": shared_status,
                "course": ti.get("course", ""),
                "name": ti.get("name", ""),
                "video_relpath": ti.get("video_relpath", ""),
                "size_mb": ti.get("size_mb", 0),
                "discovered_at": ti.get("discovered_at"),
                "started_at": ti.get("started_at"),
                "completed_at": ti.get("completed_at"),
                "last_error": ti.get("last_error"),
                "assigned_to": ti.get("assigned_to"),
                "harvested": False,
                "type": ti.get("type", "video"),
            }
            synced += 1

    if synced > 0:
        save_task_status(data)
        log(f"已從 shared 同步 {synced} 個任務狀態到 local")

def get_machine_workload():
    """取得各機器的工作負載"""
    data = load_task_status()
    tasks = data["tasks"]
    
    workload = {"pc1": 0, "pc2": 0, "notebook": 0}
    for tid, info in tasks.items():
        if info["status"] in [STATUS_PROCESSING, STATUS_ASSIGNED]:
            machine = info.get("assigned_to")
            if machine in workload:
                workload[machine] += 1
    
    return workload

# ── 收成 ──────────────────────────────────────────────────

HARVEST_EXTS = {".srt", ".md"}

def parse_srt_to_text(srt_content):
    """將 SRT 轉成純文字（去掉時間碼）"""
    lines = []
    for line in srt_content.split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.isdigit():
            continue
        if '-->' in line:
            continue
        lines.append(line)
    return '\n'.join(lines)


def harvest():
    """收成：從 shared/tasks/*.json 讀取狀態，從各機器的產出整合到知識庫"""
    shared_tasks_dir = os.path.join(SHARED_ROOT, "tasks")
    if not os.path.exists(shared_tasks_dir):
        log("shared/tasks/ 目錄不存在")
        return

    kb_dir = os.path.join(str(PROJECT_ROOT), "knowledge-base")
    os.makedirs(kb_dir, exist_ok=True)

    harvested = 0
    local_data = load_task_status()

    for fname in sorted(os.listdir(shared_tasks_dir)):
        if not fname.endswith(".json"):
            continue
        tid = fname[5:-5]
        if not tid.isdigit():
            continue

        task_file = os.path.join(shared_tasks_dir, fname)
        try:
            with open(task_file, "r", encoding="utf-8") as f:
                shared = json.load(f)
        except Exception:
            continue

        ti = shared.get("task_info", {})
        status = ti.get("status") or shared.get("status")
        if status not in (STATUS_DONE, "completed"):
            continue

        # 檢查是否已收成（先查 shared，再查 local）
        if ti.get("harvested"):
            continue
        if tid in local_data["tasks"] and local_data["tasks"][tid].get("harvested"):
            continue

        task_type = ti.get("type", "video")
        if task_type == "sensebar":
            continue

        course = ti.get("course", "")
        task_name = ti.get("name", "")

        # 收集所有可能的產出目錄
        output_dirs = []

        # 1. 從各機器的共用目錄收成
        for machine in ["pc1", "pc2", "notebook"]:
            machine_results = os.path.join(SHARED_ROOT, machine, "results")
            if not os.path.exists(machine_results):
                continue
            for d in os.listdir(machine_results):
                if (d.startswith(f"task_{tid}") or d.startswith(f"{tid}_")) and os.path.isdir(os.path.join(machine_results, d)):
                    output_dirs.append(os.path.join(machine_results, d))

        # 2. 從 working/ 目錄收成（備用路徑）
        working_dir = os.path.join(str(PROJECT_ROOT), "working")
        if os.path.exists(working_dir):
            for d in os.listdir(working_dir):
                if d.startswith(f"{tid}_") and os.path.isdir(os.path.join(working_dir, d)):
                    output_dirs.append(os.path.join(working_dir, d))

        # 2.5 從 output/ 目錄收成（run_pipeline 輸出路徑）
        output_base = os.path.join(str(PROJECT_ROOT), "output")
        if os.path.exists(output_base):
            for d in os.listdir(output_base):
                if d.startswith(f"{tid}_") and os.path.isdir(os.path.join(output_base, d)):
                    output_dirs.append(os.path.join(output_base, d))

        # 3. 從 working/{course}/ 目錄收成（舊版格式）
        course_working = os.path.join(working_dir, course)
        if os.path.exists(course_working):
            for d in os.listdir(course_working):
                if d.startswith(f"{tid}_") and os.path.isdir(os.path.join(course_working, d)):
                    output_dirs.append(os.path.join(course_working, d))

        # 4. 從 working/ 目錄收成（按任務名稱匹配，包含後綴）
        if not output_dirs:
            clean_task_name = task_name
            for ext in ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm'):
                if task_name.endswith(ext):
                    clean_task_name = task_name[:-len(ext)]
                    break
            if os.path.exists(working_dir):
                for d in os.listdir(working_dir):
                    if (d == clean_task_name or d.startswith(clean_task_name + "-")) and os.path.isdir(os.path.join(working_dir, d)):
                        output_dirs.append(os.path.join(working_dir, d))

        # 處理找到的產出目錄
        for output_task_root in output_dirs:
          try:
            kb_course = os.path.join(kb_dir, course)
            # 只在沒有 kb_subpath 時才建 course 目錄
            if not ti.get("kb_subpath"):
                os.makedirs(kb_course, exist_ok=True)

            copied = 0
            md_content = ""
            srt_content = ""

            for fentry in os.listdir(output_task_root):
                src = os.path.join(output_task_root, fentry)
                if not os.path.isfile(src):
                    continue
                ext = os.path.splitext(fentry)[1].lower()

                if ext == ".md" and fentry.lower() == "metadata.md":
                    with open(src, 'r', encoding='utf-8') as f:
                        md_content = f.read()
                elif ext == ".srt":
                    with open(src, 'r', encoding='utf-8') as f:
                        srt_content = f.read()
                elif ext == ".txt" and fentry.lower() == "clean.txt":
                    with open(src, 'r', encoding='utf-8') as f:
                        if not srt_content:
                            srt_content = f.read()

            transcript = parse_srt_to_text(srt_content) if srt_content else ""
            if md_content and transcript:
                # 從 metadata.md 移除「## 內容摘要」段（那是 raw transcript，會與逐字稿重複）
                import re
                cleaned_md = re.sub(
                    r'\n## 內容摘要\n.*?(?=\n## |\Z)',
                    '',
                    md_content,
                    flags=re.DOTALL
                ).rstrip()
                full_md = cleaned_md + "\n\n## 逐字稿\n\n" + transcript
            elif md_content:
                full_md = md_content
            else:
                full_md = transcript

            if not full_md:
                continue

            video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm')
            clean_name = task_name
            for ext in video_extensions:
                if task_name.endswith(ext):
                    clean_name = task_name[:-len(ext)]
                    break

            # KB 路徑：優先用 task_info.kb_subpath（使用者指定），否則自動計算
            kb_subpath = ti.get("kb_subpath", "")
            video_relpath = ti.get("video_relpath", "")
            if kb_subpath:
                # 使用者指定的 KB 路徑
                # 去除前導/尾隨斜線（否則 os.path.join 會丟棄 knowledge-base 前的路徑）
                kb_subpath = kb_subpath.strip().strip('/\\')
                clean_name = os.path.splitext(os.path.basename(video_relpath) if video_relpath else task_name)[0]
                dst_md = os.path.join(kb_dir, kb_subpath, f"{clean_name}.md")
            elif video_relpath:
                video_relpath = video_relpath.strip()
                # 預設放到 knowledge-base/{course}/{filename}.md
                clean_name = os.path.splitext(os.path.basename(video_relpath))[0]
                dst_md = os.path.join(kb_dir, course, f"{clean_name}.md")
            else:
                dst_md = os.path.join(kb_course, f"{clean_name}.md")

            # 在 ## 影片 加入完整影片路徑（純文字，方便複製貼上播放）
            if full_md and "## 影片" in full_md:
                import re as _re
                video_link_match = _re.search(r'## 影片\n(.+?)(?=\n## |\Z)', full_md, _re.DOTALL)
                if video_link_match:
                    display_text = video_link_match.group(1).strip()
                    vr = video_relpath.strip() if video_relpath else ""
                    if vr and "file:///" not in full_md:
                        vfp = os.path.join(get_machine_paths()["videos"], vr)
                        full_md = full_md.replace("## 影片\n" + display_text, "## 影片\n" + vfp)

            if not os.path.exists(dst_md):
                os.makedirs(os.path.dirname(dst_md), exist_ok=True)
                with open(dst_md, 'w', encoding="utf-8") as f:
                    f.write(full_md)
                copied += 1

            # 標記已收成：更新 shared + local
            ti["harvested"] = True
            with open(task_file, "w", encoding="utf-8") as f:
                json.dump(shared, f, indent=2)
            if tid not in local_data["tasks"]:
                local_data["tasks"][tid] = {"status": status, "course": course, "name": task_name, "harvested": False}
            local_data["tasks"][tid]["harvested"] = True
            local_data["tasks"][tid]["status"] = status

            harvested += 1
            log(f"收成: {course} - {clean_name} ({copied} 檔) [from {output_task_root}]")
            break
          except Exception as e:
            log(f"收成失敗 task_{tid}: {e}")
            continue

    if harvested > 0:
        save_task_status(local_data)
        send_notify(f"知識庫已更新", f"{harvested} 部新內容")
    else:
        log("沒有新的內容可收成")

# ── 狀態報告 ──────────────────────────────────────────────

def status_report():
    data = load_task_status()
    tasks = data["tasks"]
    
    by_status = {}
    for tid, info in tasks.items():
        s = info["status"]
        by_status[s] = by_status.get(s, 0) + 1
    
    by_machine = {}
    for tid, info in tasks.items():
        m = info.get("assigned_to") or "unassigned"
        by_machine[m] = by_machine.get(m, 0) + 1
    
    total = len(tasks)
    done = by_status.get("done", 0)
    pending = by_status.get("pending", 0)
    processing = by_status.get("processing", 0)
    failed = by_status.get("failed", 0)
    assigned = by_status.get("assigned", 0)
    
    print(f"\n{'='*60}")
    print(f"任務狀態")
    print(f"{'='*60}")
    print(f"  總計: {total}")
    print(f"  完成: {done}  處理中: {processing}  已分配: {assigned}  待處理: {pending}  失敗: {failed}")
    if total:
        print(f"  進度: {done/total*100:.0f}%")
    
    print(f"\n  各機器任務數:")
    for machine in ["pc1", "pc2", "notebook", "unassigned"]:
        if machine in by_machine:
            print(f"    {machine}: {by_machine[machine]}")
    
    print(f"\n  各機器在線狀態:")
    for machine in ["pc1", "pc2", "notebook"]:
        online = check_machine_online(machine)
        status = "在線" if online else "離線"
        print(f"    {machine}: {status}")
    
    print(f"{'='*60}")

# ── 預檢功能 ──────────────────────────────────────────────

ILLEGAL_CHARS = set('\\/:*?"<>|')
MAX_PATH_LEN = 240
MAX_SIZE_MB = 500
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"}

class Issue:
    def __init__(self, level, filepath, msg, fix=None):
        self.level = level
        self.filepath = filepath
        self.msg = msg
        self.fix = fix
    
    def __str__(self):
        tag = {"error": "[ERR]", "warn": "[WRN]", "info": "[INF]"}[self.level]
        return f"{tag} {self.filepath}\n   {self.msg}"

def validate_videos(source_dir=None):
    scan_root = source_dir or get_machine_paths()["videos"]
    if not os.path.exists(scan_root):
        return [Issue("error", scan_root, "目錄不存在")], {}
    
    log(f"預檢掃描: {scan_root}")
    issues = []
    stats = {"courses": 0, "videos": 0, "errors": 0, "warns": 0}
    
    for entry in sorted(os.listdir(scan_root)):
        course_path = os.path.join(scan_root, entry)
        if not os.path.isdir(course_path):
            continue
        stats["courses"] += 1
        
        _check_name(entry, course_path, issues, is_dir=True)
        
        mp4_count = 0
        name_count = {}
        for fname in os.listdir(course_path):
            fpath = os.path.join(course_path, fname)
            if not os.path.isfile(fpath):
                continue
            
            ext = os.path.splitext(fname)[1].lower()
            if ext in VIDEO_EXTS:
                mp4_count += 1
                stats["videos"] += 1
                _check_name(fname, fpath, issues, is_dir=False)
                
                stem = os.path.splitext(fname)[0]
                name_count[stem] = name_count.get(stem, 0) + 1
                
                size_mb = os.path.getsize(fpath) / (1024 * 1024)
                if size_mb > MAX_SIZE_MB:
                    issues.append(Issue("warn", fpath,
                        f"檔案過大 ({size_mb:.0f} MB)"))
                
                if len(fpath) > MAX_PATH_LEN:
                    issues.append(Issue("error", fpath,
                        f"路徑過長 ({len(fpath)} 字元)"))
            else:
                if ext in {".srt", ".md", ".txt", ".json"}:
                    continue
                issues.append(Issue("info", fpath, f"非影音檔 ({ext})，將被跳過"))
        
        if mp4_count == 0:
            issues.append(Issue("warn", course_path, "課程目錄內無影音檔"))
        
        for stem, count in name_count.items():
            if count > 1:
                issues.append(Issue("warn", course_path,
                    f"重複檔名: \"{stem}\" 出現 {count} 次"))
    
    stats["errors"] = sum(1 for i in issues if i.level == "error")
    stats["warns"] = sum(1 for i in issues if i.level == "warn")
    return issues, stats

def _check_name(name, filepath, issues, is_dir=False):
    kind = "目錄" if is_dir else "檔案"
    found_bad = [c for c in name if c in ILLEGAL_CHARS]
    if found_bad:
        issues.append(Issue("error", filepath, f"{kind}名含非法字元: {''.join(found_bad)}"))
    if name != name.strip():
        issues.append(Issue("warn", filepath, f"{kind}名開頭或結尾有空白"))
    if "  " in name:
        issues.append(Issue("info", filepath, f"{kind}名含連續多個空白"))

def print_validation_report(issues, stats):
    print(f"\n{'='*60}")
    print(f"預檢報告")
    print(f"{'='*60}")
    print(f"  課程數: {stats.get('courses', 0)}")
    print(f"  影片數: {stats.get('videos', 0)}")
    print(f"  [ERROR] 錯誤: {stats.get('errors', 0)}")
    print(f"  [WARN]  警告: {stats.get('warns', 0)}")
    print(f"{'='*60}")
    
    if not issues:
        print("[OK] 全部通過")
        return
    
    for level, label in [("error", "[ERROR] 錯誤"), ("warn", "[WARN]  警告"), ("info", "[INFO]  資訊")]:
        group = [i for i in issues if i.level == level]
        if not group:
            continue
        print(f"\n{label}")
        print("-" * 40)
        for i, issue in enumerate(group, 1):
            print(f"  {i}. {issue}")

def auto_fix_issues(source_dir, issues):
    fixed = 0
    for issue in issues:
        if issue.level != "error":
            continue
        fp = issue.filepath
        if not os.path.exists(fp):
            continue
        dirname = os.path.dirname(fp)
        old_name = os.path.basename(fp)
        new_name = old_name
        for c in ILLEGAL_CHARS:
            new_name = new_name.replace(c, "_")
        new_name = new_name.strip()
        if new_name != old_name:
            new_path = os.path.join(dirname, new_name)
            if not os.path.exists(new_path):
                os.rename(fp, new_path)
                log(f"  修正: {old_name} -> {new_name}")
                fixed += 1
    return fixed

# ── 監控循環 ──────────────────────────────────────────────

def watch_loop(interval=300):
    log(f"啟動監控模式 (間隔 {interval} 秒)")
    send_notify("排程器啟動", "開始監控影片目錄")
    
    while True:
        try:
            # 掃描新影片
            videos = scan_directory()
            if videos:
                create_tasks(videos)
            
            # 分配任務
            assign_tasks()
            
            # 從 shared 同步狀態到 local
            sync_shared_to_local()
            
            # 收成
            harvest()
            
            # 顯示狀態
            status_report()
            
        except Exception as e:
            log(f"監控錯誤: {e}")
        
        time.sleep(interval)

# ── 主程式 ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="排程器")
    
    if any(a in sys.argv for a in ["--watch", "--harvest"]):
        start_watchdog(name="scheduler", task_status_path=TASK_STATUS_FILE, disk_path="D:\\")
    
    parser.add_argument("--scan", nargs="?", const=None, default=None)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--harvest", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--assign", action="store_true")
    parser.add_argument("--notify", action="store_true")
    parser.add_argument("--validate", nargs="?", const="", default=None)
    parser.add_argument("--auto-fix", action="store_true")
    args = parser.parse_args()
    
    if args.notify:
        send_notify("測試通知", "排程器通知功能正常")
        return
    
    if args.validate is not None:
        source = args.validate if args.validate else None
        issues, stats = validate_videos(source)
        print_validation_report(issues, stats)
        if args.auto_fix and issues:
            fixed = auto_fix_issues(source or get_machine_paths()["videos"],
                                    [i for i in issues if i.level == "error"])
            log(f"自動修正 {fixed} 個問題")
            if fixed > 0:
                issues, stats = validate_videos(source)
                print_validation_report(issues, stats)
        return
    
    if args.status:
        status_report()
        return
    
    if args.harvest:
        sync_shared_to_local()
        harvest()
        status_report()
        return
    
    if args.assign:
        assigned = assign_tasks()
        status_report()
        return
    
    if args.watch:
        watch_loop()
        return
    
    if args.scan is not None or args.scan == "":
        source = args.scan if args.scan else None
        videos = scan_directory(source)
        if videos:
            create_tasks(videos)
        status_report()
        return
    
    # 預設：掃描 + 分配 + 收成
    videos = scan_directory()
    if videos:
        create_tasks(videos)
    assign_tasks()
    sync_shared_to_local()
    harvest()
    status_report()

if __name__ == "__main__":
    main()
