#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共用設定檔 - 三機協同架構
PC2: 下載站（YouTube下載+轉寫）
PC1: 臨時站（臨時任務處理）
Notebook: 收成站（KB管理+pipeline執行）
"""
import os, sys, socket, json
from pathlib import Path

# === 機器辨識 ===
HOSTNAME = socket.gethostname().lower()

MACHINE_ALIASES = {
    "laptop-vag7lbd2": "notebook",
    "desktop-nl6va8t": "pc2",
    "desktop-ndlv9li": "pc1",
}

def get_machine():
    for key, val in MACHINE_ALIASES.items():
        if key in HOSTNAME:
            return val
    return f"unknown-{HOSTNAME}"

MACHINE = get_machine()

# === Tailscale 網路設定 ===
TAILSCALE_IPS = {
    "pc2": "100.113.234.81",
    "pc1": "100.84.223.110",
    "notebook": "100.111.44.63",
}

# === 路徑設定 ===
LOCAL_ROOT = r"D:\AI-Agent-Workspace"
PROJECT_ROOT = Path(__file__).parent
TASK_STATUS_FILE = os.path.join(str(PROJECT_ROOT), "task_status.json")

# 共用目錄（本機路徑）
SHARED_ROOT = os.path.join(str(PROJECT_ROOT), "shared")

# 各機器路徑配置
MACHINE_PATHS = {
    "notebook": {
        "videos": r"D:\!!!!!理周學院老師\察爾思",
        "output": os.path.join(LOCAL_ROOT, "output"),
        "working": os.path.join(LOCAL_ROOT, "working"),
        "logs": os.path.join(LOCAL_ROOT, "logs"),
        "shared": SHARED_ROOT,
    },
    "pc1": {
        "videos": r"D:\AI-Agent-Workspace\videos",
        "output": r"D:\AI-Agent-Workspace\output",
        "working": r"D:\AI-Agent-Workspace\working",
        "logs": r"D:\AI-Agent-Workspace\logs",
        "shared": SHARED_ROOT,
    },
    "pc2": {
        "videos": r"D:\AI-Agent-Workspace\videos",
        "output": r"D:\AI-Agent-Workspace\output",
        "working": r"D:\AI-Agent-Workspace\working",
        "logs": r"D:\AI-Agent-Workspace\logs",
        "shared": SHARED_ROOT,
    },
}

# 取得當前機器的路徑
def get_machine_paths():
    return MACHINE_PATHS.get(MACHINE, MACHINE_PATHS["notebook"])

# === 任務狀態 ===
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_ASSIGNED = "assigned"

# === 機器角色 ===
MACHINE_ROLES = {
    "pc2": "downloader",      # 負責YouTube下載+轉寫
    "pc1": "adhoc_worker",    # 負責臨時任務
    "notebook": "harvester",  # 負責收成+KB管理
}

def get_machine_role():
    return MACHINE_ROLES.get(MACHINE, "unknown")

# === 功能函數 ===
def load_task_status():
    if not os.path.exists(TASK_STATUS_FILE):
        return {"generated_at": None, "task_counter": 0, "tasks": {}}
    with open(TASK_STATUS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_task_status(data):
    os.makedirs(os.path.dirname(TASK_STATUS_FILE), exist_ok=True)
    with open(TASK_STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def log(msg):
    import sys as _sys
    ts = __import__("datetime").datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] [{MACHINE}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        # 強制用 UTF-8 輸出
        try:
            _sys.stdout.buffer.write((line + "\n").encode("utf-8", errors="replace"))
            _sys.stdout.flush()
        except Exception:
            pass

# === 機器通訊 ===
def get_machine_status(machine):
    """取得其他機器的狀態"""
    # 嘗試讀取心跳檔案（新版格式）
    heartbeat_file = os.path.join(SHARED_ROOT, machine, "status", "heartbeat.json")
    if os.path.exists(heartbeat_file):
        with open(heartbeat_file, "r", encoding="utf-8") as f:
            return json.load(f)
    
    # 嘗試讀取舊版格式
    status_file = os.path.join(SHARED_ROOT, machine, "status.json")
    if os.path.exists(status_file):
        with open(status_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def update_machine_status(status_data):
    """更新本機狀態到共用目錄"""
    status_file = os.path.join(SHARED_ROOT, MACHINE, "status.json")
    os.makedirs(os.path.dirname(status_file), exist_ok=True)
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(status_data, f, indent=2)

def check_machine_online(machine, timeout_seconds=300):
    """檢查機器是否在線（根據最後更新時間）"""
    status = get_machine_status(machine)
    if not status:
        return False
    
    from datetime import datetime, timedelta
    last_seen = datetime.fromisoformat(status.get("last_seen", "2000-01-01"))
    return (datetime.now() - last_seen).total_seconds() < timeout_seconds
