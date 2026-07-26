"""
追蹤模組 - 追蹤任務處理時間、輸出驗證、錯誤記錄
"""
import os
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── 追蹤資料結構 ──────────────────────────────────────────
TRACKER_FILE = "task_tracker.json"

def load_tracker():
    """載入追蹤資料，損壞時自動重建"""
    tracker_path = os.path.join(os.path.dirname(__file__), TRACKER_FILE)
    if os.path.exists(tracker_path):
        try:
            with open(tracker_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            # 損壞時備份舊檔並重建
            backup = tracker_path + ".bak"
            try:
                import shutil
                shutil.copy2(tracker_path, backup)
            except Exception:
                pass
            print(f"[警告] task_tracker.json 損壞，已重建 ({e})")
    return {"tasks": {}, "stats": {}}

def save_tracker(data):
    """儲存追蹤資料（原子寫入，防止崩潰時損壞）"""
    tracker_path = os.path.join(os.path.dirname(__file__), TRACKER_FILE)
    tmp_path = tracker_path + ".tmp"
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # 原子替換
        import shutil
        shutil.move(tmp_path, tracker_path)
    except Exception:
        # fallback: 直接寫入
        try:
            with open(tracker_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

# ── 處理時間追蹤 ──────────────────────────────────────────
class TaskTimer:
    """任務計時器"""
    
    def __init__(self, tid):
        self.tid = tid
        self.start_time = None
        self.step_times = {}
        self.tracker = load_tracker()
    
    def start(self):
        """開始計時"""
        self.start_time = time.time()
        if self.tid not in self.tracker["tasks"]:
            self.tracker["tasks"][self.tid] = {
                "attempts": [],
                "total_time": 0,
                "avg_time": 0,
                "success_count": 0,
                "fail_count": 0,
            }
        self.current_attempt = {
            "start_time": datetime.now().isoformat(),
            "steps": {},
            "status": "processing",
        }
    
    def step(self, step_name):
        """記錄步驟開始"""
        self.step_times[step_name] = time.time()
    
    def step_done(self, step_name):
        """記錄步驟完成"""
        if step_name in self.step_times:
            elapsed = time.time() - self.step_times[step_name]
            self.current_attempt["steps"][step_name] = {
                "duration": round(elapsed, 2),
                "status": "completed"
            }
            return elapsed
        return 0
    
    def finish(self, success=True, error=None):
        """完成計時"""
        if self.start_time:
            total_time = time.time() - self.start_time
            self.current_attempt["end_time"] = datetime.now().isoformat()
            self.current_attempt["total_time"] = round(total_time, 2)
            self.current_attempt["status"] = "completed" if success else "failed"
            if error:
                self.current_attempt["error"] = error
            
            # 更新統計
            task_stats = self.tracker["tasks"][self.tid]
            task_stats["attempts"].append(self.current_attempt)
            task_stats["total_time"] += total_time
            task_stats["success_count"] += 1 if success else 0
            task_stats["fail_count"] += 0 if success else 1
            
            # 計算平均時間
            if task_stats["success_count"] > 0:
                task_stats["avg_time"] = round(
                    task_stats["total_time"] / task_stats["success_count"], 2
                )
            
            save_tracker(self.tracker)
            return total_time
        return 0

# ── 輸出驗證 ──────────────────────────────────────────────
class OutputValidator:
    """輸出驗證器"""
    
    REQUIRED_FILES = ["metadata.md", "字幕.srt"]
    OPTIONAL_FILES = ["cover.png", "剪輯後.mp4"]
    
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.issues = []
    
    def validate(self):
        """驗證輸出"""
        self.issues = []
        
        if not os.path.exists(self.output_dir):
            self.issues.append({
                "type": "missing_directory",
                "message": f"輸出目錄不存在: {self.output_dir}"
            })
            return False, self.issues
        
        # 檢查必要檔案
        for filename in self.REQUIRED_FILES:
            filepath = os.path.join(self.output_dir, filename)
            if not os.path.exists(filepath):
                self.issues.append({
                    "type": "missing_file",
                    "file": filename,
                    "message": f"缺少必要檔案: {filename}"
                })
            else:
                # 檢查檔案大小
                size = os.path.getsize(filepath)
                if size == 0:
                    self.issues.append({
                        "type": "empty_file",
                        "file": filename,
                        "message": f"檔案為空: {filename}"
                    })
                elif filename == "metadata.md" and size < 100:
                    self.issues.append({
                        "type": "file_too_small",
                        "file": filename,
                        "size": size,
                        "message": f"檔案太小: {filename} ({size} bytes)"
                    })
                elif filename == "字幕.srt" and size < 50:
                    self.issues.append({
                        "type": "file_too_small",
                        "file": filename,
                        "size": size,
                        "message": f"字幕檔案太小: {filename} ({size} bytes)"
                    })
        
        # 檢查是否有 cover 圖片
        cover_files = [f for f in os.listdir(self.output_dir) 
                      if f.startswith("cover_") and f.endswith(".png")]
        if not cover_files:
            self.issues.append({
                "type": "missing_cover",
                "message": "缺少封面圖片"
            })
        
        return len(self.issues) == 0, self.issues

# ── 錯誤追蹤 ──────────────────────────────────────────────
class ErrorTracker:
    """錯誤追蹤器"""
    
    ERROR_TYPES = {
        "disk_full": "磁碟空間不足",
        "no_video_files": "找不到影音檔案",
        "pipeline_failed": "Pipeline 執行失敗",
        "compress_failed": "壓縮失敗",
        "transcribe_failed": "轉寫失敗",
        "timeout": "處理超時",
        "unknown": "未知錯誤",
    }
    
    def __init__(self):
        self.tracker = load_tracker()
    
    def report(self, tid, error_msg, error_type="unknown"):
        """報告錯誤"""
        if tid not in self.tracker["tasks"]:
            self.tracker["tasks"][tid] = {
                "attempts": [],
                "total_time": 0,
                "avg_time": 0,
                "success_count": 0,
                "fail_count": 0,
            }
        
        task_stats = self.tracker["tasks"][tid]
        if task_stats["attempts"]:
            last_attempt = task_stats["attempts"][-1]
            last_attempt["error"] = error_msg
            last_attempt["error_type"] = error_type
            last_attempt["status"] = "failed"
        
        save_tracker(self.tracker)
    
    def get_error_history(self, tid):
        """取得錯誤歷史"""
        if tid in self.tracker["tasks"]:
            return [
                a for a in self.tracker["tasks"][tid]["attempts"]
                if a.get("status") == "failed"
            ]
        return []

# ── 進度監控 ──────────────────────────────────────────────
class ProgressMonitor:
    """進度監控器"""
    
    def __init__(self, timeout_minutes=30):
        self.timeout = timeout_minutes * 60  # 轉換為秒
    
    def check_stuck(self, tid, start_time):
        """檢查是否卡住"""
        if start_time:
            elapsed = time.time() - start_time
            if elapsed > self.timeout:
                return True, elapsed
        return False, 0
    
    def estimate_completion(self, avg_time, remaining_tasks):
        """預估完成時間"""
        if avg_time > 0:
            estimated_seconds = avg_time * remaining_tasks
            return datetime.now() + timedelta(seconds=estimated_seconds)
        return None

# ── 健康檢查 ──────────────────────────────────────────────
class HealthChecker:
    """健康檢查器"""
    
    def __init__(self):
        self.last_check = None
    
    def check_disk_space(self, path="D:\\", min_gb=1):
        """檢查磁碟空間"""
        try:
            import shutil
            total, used, free = shutil.disk_usage(path)
            free_gb = free / (1024 ** 3)
            return free_gb >= min_gb, free_gb
        except:
            return False, 0
    
    def check_memory(self):
        """檢查記憶體"""
        try:
            import psutil
            memory = psutil.virtual_memory()
            return memory.percent < 90, memory.percent
        except:
            return True, 0  # 如果無法檢查，假設正常
    
    def full_check(self):
        """完整健康檢查"""
        disk_ok, disk_gb = self.check_disk_space()
        memory_ok, memory_pct = self.check_memory()
        
        self.last_check = {
            "time": datetime.now().isoformat(),
            "disk_ok": disk_ok,
            "disk_gb": round(disk_gb, 2),
            "memory_ok": memory_ok,
            "memory_pct": memory_pct,
        }
        
        return {
            "healthy": disk_ok and memory_ok,
            "disk": {"ok": disk_ok, "gb": round(disk_gb, 2)},
            "memory": {"ok": memory_ok, "pct": memory_pct},
        }

# ── 統計報表 ──────────────────────────────────────────────
def generate_report():
    """產生統計報表"""
    tracker = load_tracker()
    
    report = {
        "generated_at": datetime.now().isoformat(),
        "total_tasks": len(tracker["tasks"]),
        "summary": {
            "success": 0,
            "failed": 0,
            "avg_time": 0,
        },
        "slowest_tasks": [],
        "failed_tasks": [],
    }
    
    total_time = 0
    for tid, stats in tracker["tasks"].items():
        report["summary"]["success"] += stats["success_count"]
        report["summary"]["failed"] += stats["fail_count"]
        total_time += stats["total_time"]
        
        if stats["avg_time"] > 0:
            report["slowest_tasks"].append({
                "tid": tid,
                "avg_time": stats["avg_time"],
            })
        
        if stats["fail_count"] > 0:
            report["failed_tasks"].append({
                "tid": tid,
                "fail_count": stats["fail_count"],
            })
    
    if report["summary"]["success"] > 0:
        report["summary"]["avg_time"] = round(
            total_time / report["summary"]["success"], 2
        )
    
    # 排序
    report["slowest_tasks"].sort(key=lambda x: x["avg_time"], reverse=True)
    report["failed_tasks"].sort(key=lambda x: x["fail_count"], reverse=True)
    
    return report

if __name__ == "__main__":
    # 測試追蹤模組
    print("=== 追蹤模組測試 ===")
    
    # 測試健康檢查
    checker = HealthChecker()
    health = checker.full_check()
    print(f"健康狀態: {health}")
    
    # 產生報表
    report = generate_report()
    print(f"統計報表: {json.dumps(report, indent=2, ensure_ascii=False)}")
