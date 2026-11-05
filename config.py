#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共用設定檔 - 三機協同架構
2026-11-04 決策：PC1 / PC2 / PC3 / Notebook 皆為「完整能力副本」，
任一台可獨立承接 finance / video / stock / XQ；MACHINE_ROLES 僅為
主要職責註記（供日誌/排程辨識），不代表能力限制。
工作區統一：三機一律 D:\\AI-Agent-Workspace（PC3 待遷移，見 MACHINE_PATHS）。
"""
import os, sys, socket, json
from pathlib import Path

# === 子行程編碼（2026-11-06 事故）===
# Windows 的 subprocess 若只寫 text=True，會用 locale（cp950）解碼管線；
# 但本專案的子行程（run_pipeline／channel_watcher 會 reconfigure、yt-dlp
# 自己強制 UTF-8）輸出的是 UTF-8 中文，於是 reader thread 直接
# UnicodeDecodeError（GUI 看到 Exception in thread Thread-N (_readerthread)），
# 子行程輸出全失。這裡只影響 stdio，不動檔案 I/O，讓所有子行程一律 UTF-8，
# 搭配呼叫點的 encoding="utf-8", errors="replace"。
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# === 機器辨識 ===
HOSTNAME = socket.gethostname().lower()

MACHINE_ALIASES = {
    "laptop-vag7lbd2": "notebook",
    "desktop-nl6va8t": "pc2",
    "desktop-ndlv9li": "pc1",
    "desktop-mfkvcso": "pc3",
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
    "pc3": None,  # 待補：PC3 遷移後以 `tailscale ip -4` 取得（勿沿用 notebook 的 IP）
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
        "videos": r"D:\!!!!!理周學院老師",
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
    "pc3": {
        # TODO(2026-11-04 決策)：PC3 遷移到 D:\AI-Agent-Workspace 後改為與 pc1/pc2 相同路徑。
        # 目前保留舊路徑，避免現役收成任務中斷；遷移步驟見 HANDOFF-3MACHINE-DEPLOY.md。
        "videos": r"D:\YouTube_Videos",
        "output": r"D:\sensebar-agent-knowledge-vault\output",
        "working": r"D:\sensebar-agent-knowledge-vault\working",
        "logs": r"D:\sensebar-agent-knowledge-vault\logs",
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

# === 機器角色（僅註記，非能力限制）===
# 2026-11-04：所有機器都是完整副本；角色只用於日誌/排程辨識。
MACHINE_ROLES = {
    "pc1": "worker",       # 全功能；目前主要跑臨時任務
    "pc2": "worker",       # 全功能；目前主要跑下載+轉寫
    "notebook": "harvester",
    "pc3": "harvester",    # 現役收成機；遷移後與 notebook 同路徑
}

def get_machine_role():
    return MACHINE_ROLES.get(MACHINE, "unknown")

def get_machine_info():
    """單一來源的機器資訊，供 health_check / GUI / 部署腳本使用"""
    return {
        "machine": MACHINE,
        "role": get_machine_role(),
        "tailscale_ip": TAILSCALE_IPS.get(MACHINE),
        "full_capability": True,   # 所有機器能力一致（不分管制）
        "root": LOCAL_ROOT,
    }

# === 功能函數 ===
def load_task_status():
    if not os.path.exists(TASK_STATUS_FILE):
        return {"generated_at": None, "task_counter": 0, "tasks": {}}
    try:
        with open(TASK_STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        backup = TASK_STATUS_FILE + ".corrupt"
        try:
            os.replace(TASK_STATUS_FILE, backup)
        except Exception:
            pass
        return {"generated_at": None, "task_counter": 0, "tasks": {}}

def save_task_status(data):
    os.makedirs(os.path.dirname(TASK_STATUS_FILE), exist_ok=True)
    tmp = TASK_STATUS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, TASK_STATUS_FILE)

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


# === 頻道監控設定 ===
import yaml as _yaml

def _load_yaml_config():
    yaml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    if not os.path.exists(yaml_path):
        return {}
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            return _yaml.safe_load(f) or {}
    except Exception:
        return {}

_YAML_CONFIG = _load_yaml_config()

WATCHED_CHANNELS = _YAML_CONFIG.get("watched_channels", [])

def get_watched_channels():
    """回傳頻道監控設定串列"""
    return WATCHED_CHANNELS

# 頻道監控狀態檔
CHANNEL_STATE_FILE = os.path.join(SHARED_ROOT, "watched_channels_state.json")

def load_channel_state():
    if not os.path.exists(CHANNEL_STATE_FILE):
        return {}
    try:
        with open(CHANNEL_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_channel_state(state):
    os.makedirs(os.path.dirname(CHANNEL_STATE_FILE), exist_ok=True)
    tmp = CHANNEL_STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CHANNEL_STATE_FILE)
