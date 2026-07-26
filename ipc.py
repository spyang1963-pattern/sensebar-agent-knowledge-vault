#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享通訊模組 - 三機協同的核心通訊機制
提供心跳、錯誤回報、任務佇列等功能
"""
import os, json, time
from datetime import datetime
from pathlib import Path

# 共用目錄根路徑
# 使用本機路徑，各機器獨立運作
# 透過手動同步或腳本同步 shared/ 目錄
SHARED_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared")

class Heartbeat:
    """心跳管理器 - 各機器用來回報自己的運作狀態"""
    
    def __init__(self, machine_name):
        self.machine = machine_name
        self.heartbeat_file = os.path.join(SHARED_ROOT, machine_name, "status", "heartbeat.json")
        self.interval = 30  # 秒
    
    def update(self, status="online", current_task=None, pid=None):
        """更新心跳狀態"""
        heartbeat = {
            "machine": self.machine,
            "status": status,
            "last_seen": datetime.now().isoformat(),
            "pid": pid or os.getpid(),
            "current_task": current_task,
        }
        
        os.makedirs(os.path.dirname(self.heartbeat_file), exist_ok=True)
        with open(self.heartbeat_file, "w", encoding="utf-8") as f:
            json.dump(heartbeat, f, indent=2)
        
        return heartbeat
    
    def read(self, machine=None):
        """讀取指定機器的心跳狀態"""
        target = machine or self.machine
        heartbeat_file = os.path.join(SHARED_ROOT, target, "status", "heartbeat.json")
        
        if not os.path.exists(heartbeat_file):
            return None
        
        with open(heartbeat_file, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def is_online(self, machine=None, timeout_seconds=120):
        """檢查機器是否在線（根據最後心跳時間）"""
        heartbeat = self.read(machine)
        if not heartbeat:
            return False
        
        try:
            last_seen = datetime.fromisoformat(heartbeat["last_seen"])
            return (datetime.now() - last_seen).total_seconds() < timeout_seconds
        except:
            return False
    
    def get_all_status(self):
        """取得所有機器的狀態"""
        status = {}
        for machine in ["pc1", "pc2", "notebook"]:
            heartbeat = self.read(machine)
            online = self.is_online(machine)
            status[machine] = {
                "heartbeat": heartbeat,
                "online": online,
            }
        return status


class ErrorReporter:
    """錯誤回報器 - 各機器用來回報無法處理的錯誤"""
    
    def __init__(self, machine_name):
        self.machine = machine_name
        self.error_dir = os.path.join(SHARED_ROOT, machine_name, "errors")
        self.global_error_file = os.path.join(SHARED_ROOT, "errors", "queue.json")
    
    def report(self, task_id, error_msg, error_type="unknown", context=None):
        """回報錯誤到共用目錄"""
        error_entry = {
            "machine": self.machine,
            "task_id": task_id,
            "error_msg": error_msg,
            "error_type": error_type,
            "context": context or {},
            "timestamp": datetime.now().isoformat(),
            "resolved": False,
        }
        
        # 寫入本機錯誤目錄
        os.makedirs(self.error_dir, exist_ok=True)
        error_file = os.path.join(self.error_dir, f"error_{task_id}_{int(time.time())}.json")
        with open(error_file, "w", encoding="utf-8") as f:
            json.dump(error_entry, f, indent=2)
        
        # 追加到全域錯誤佇列
        self._append_to_global_queue(error_entry)
        
        return error_entry
    
    def _append_to_global_queue(self, error_entry):
        """追加到全域錯誤佇列"""
        os.makedirs(os.path.dirname(self.global_error_file), exist_ok=True)
        
        # 讀取現有佇列
        queue = []
        if os.path.exists(self.global_error_file):
            with open(self.global_error_file, "r", encoding="utf-8") as f:
                queue = json.load(f)
        
        # 追加新錯誤
        queue.append(error_entry)
        
        # 寫回
        with open(self.global_error_file, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2)
    
    def get_unresolved(self):
        """取得未解決的錯誤"""
        if not os.path.exists(self.global_error_file):
            return []
        
        with open(self.global_error_file, "r", encoding="utf-8") as f:
            queue = json.load(f)
        
        return [e for e in queue if not e.get("resolved")]
    
    def mark_resolved(self, task_id, machine=None):
        """標記錯誤為已解決"""
        target_machine = machine or self.machine
        
        # 從全域佇列中標記
        if os.path.exists(self.global_error_file):
            with open(self.global_error_file, "r", encoding="utf-8") as f:
                queue = json.load(f)
            
            for error in queue:
                if error["task_id"] == task_id and error["machine"] == target_machine:
                    error["resolved"] = True
                    error["resolved_at"] = datetime.now().isoformat()
            
            with open(self.global_error_file, "w", encoding="utf-8") as f:
                json.dump(queue, f, indent=2)
        
        # 從本機錯誤目錄標記
        error_dir = os.path.join(SHARED_ROOT, target_machine, "errors")
        if os.path.exists(error_dir):
            for fname in os.listdir(error_dir):
                if fname.startswith(f"error_{task_id}_"):
                    error_file = os.path.join(error_dir, fname)
                    with open(error_file, "r", encoding="utf-8") as f:
                        error_data = json.load(f)
                    error_data["resolved"] = True
                    error_data["resolved_at"] = datetime.now().isoformat()
                    with open(error_file, "w", encoding="utf-8") as f:
                        json.dump(error_data, f, indent=2)


class TaskQueue:
    """任務佇列 - 各機器用來領取和回報任務"""
    
    def __init__(self, machine_name):
        self.machine = machine_name
        self.tasks_dir = os.path.join(SHARED_ROOT, "tasks")
        self.results_dir = os.path.join(SHARED_ROOT, self.machine, "results")
    
    def get_assigned_tasks(self):
        """取得分配給本機的任務"""
        assigned = []
        
        if not os.path.exists(self.tasks_dir):
            return assigned
        
        for fname in os.listdir(self.tasks_dir):
            if not fname.endswith(".json"):
                continue
            
            task_file = os.path.join(self.tasks_dir, fname)
            with open(task_file, "r", encoding="utf-8") as f:
                task = json.load(f)
            
            # 檢查 assigned_to：取分配給本機的 + 未分配的
            task_info = task.get("task_info", {})
            assigned_to = task_info.get("assigned_to")
            if assigned_to == self.machine or assigned_to is None:
                assigned.append(task)
        
        return assigned
    
    def update_task_status(self, task_id, status, error=None):
        """更新任務狀態（shared/tasks/*.json 為唯一狀態源）"""
        task_file = os.path.join(self.tasks_dir, f"task_{task_id}.json")
        
        if not os.path.exists(task_file):
            return False
        
        with open(task_file, "r", encoding="utf-8") as f:
            task = json.load(f)
        
        now = datetime.now().isoformat()
        
        # 更新頂層狀態
        task["status"] = status
        task["last_updated"] = now
        task["updated_by"] = self.machine
        
        # 同步更新 task_info 裡的狀態（保持一致）
        if "task_info" in task:
            ti = task["task_info"]
            ti["status"] = status
            if status == "processing" and not ti.get("started_at"):
                ti["started_at"] = now
            if status in ("completed", "done"):
                ti["completed_at"] = now
            if status in ("processing", "completed", "done"):
                ti["machine"] = self.machine
            if error:
                ti["last_error"] = error
        
        if error:
            task["error"] = error
        
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(task, f, indent=2)
        
        return True
    
    def upload_results(self, task_id, result_dir):
        """上傳結果到共用目錄"""
        target_dir = os.path.join(self.results_dir, f"task_{task_id}")
        os.makedirs(target_dir, exist_ok=True)
        
        # 複製結果檔案
        import shutil
        if os.path.exists(result_dir):
            for fname in os.listdir(result_dir):
                src = os.path.join(result_dir, fname)
                dst = os.path.join(target_dir, fname)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
        
        return target_dir


class Supervisor:
    """監控器 - Notebook 用來監控所有機器"""
    
    def __init__(self):
        self.heartbeat = Heartbeat("notebook")
        self.error_reporter = ErrorReporter("notebook")
    
    def check_all_machines(self):
        """檢查所有機器的狀態"""
        return self.heartbeat.get_all_status()
    
    def get_all_errors(self):
        """取得所有未解決的錯誤"""
        return self.error_reporter.get_unresolved()
    
    def resolve_error(self, task_id, machine):
        """解決錯誤"""
        self.error_reporter.mark_resolved(task_id, machine)
    
    def get_system_status(self):
        """取得系統整體狀態"""
        machines = self.check_all_machines()
        errors = self.get_all_errors()
        
        return {
            "machines": machines,
            "unresolved_errors": len(errors),
            "errors": errors,
            "timestamp": datetime.now().isoformat(),
        }
