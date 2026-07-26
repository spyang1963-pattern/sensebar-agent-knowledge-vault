#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用監控器 - 給所有背景程序使用
每 60 秒健康檢查，異常自動修復或通報

彙報頻率：15min → 1hr → 4hr（遞增，持續正常才降頻）
異常：立即通報 + 自行修復 + 修復後回報
無法處理：停止工作 + 立即通報待命

用法:
  在 worker 或 scheduler 的 main() 中呼叫 watchdog.start()
"""
import os, sys, json, time, socket, threading, subprocess, yaml
from datetime import datetime

_line = None
_email = None
_notify_config_loaded = False

NOTEBOOK_IP = "100.111.44.63"  # Notebook Tailscale IP
CHECKPOINT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notebook_checkpoint.json")

def _load_notifiers():
    global _line, _email, _notify_config_loaded
    if _notify_config_loaded:
        return
    _notify_config_loaded = True
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        cfg_path = os.path.join(base, "notify_config.yaml")
        sys.path.insert(0, os.path.join(base, "stock-monitor", "src"))
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            from notifier import LineNotifier, EmailNotifier
            _line = LineNotifier(cfg.get("line", {}))
            _email = EmailNotifier(cfg.get("email", {}))
    except Exception:
        pass

def notify_line_and_email(title, message):
    _load_notifiers()
    try:
        if _line:
            _line.send(f"{title}\n{message}")
    except Exception:
        pass
    try:
        if _email:
            _email.send(title, f"<html><body style='font-family:sans-serif'><h2>{title}</h2><pre>{message}</pre></body></html>")
    except Exception:
        pass

def get_free_space_gb(path="D:\\"):
    import ctypes
    free = ctypes.c_ulonglong()
    try:
        drive = os.path.splitdrive(path)[0] + "\\"
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(drive, None, None, ctypes.byref(free))
        return free.value / 1024**3
    except:
        return 0

class Watchdog:
    """通用健康監控器"""

    # 彙報間隔表（持續正常才降頻）
    REPORT_INTERVALS = [15 * 60, 60 * 60, 4 * 60 * 60]  # 15分鐘, 1小時, 4小時

    def __init__(self, name="worker", check_interval=60, task_status_path=None,
                 disk_path="D:\\", disk_min_gb=2.0, on_critical=None):
        self.name = name
        self.interval = check_interval
        self.task_status_path = task_status_path
        self.disk_path = disk_path
        self.disk_min_gb = disk_min_gb
        self.on_critical = on_critical  # callback(issue_type, message)
        self._last_done_count = 0
        self._last_done_change = time.time()
        self._running = True
        self._report_level = 0  # 0=15min, 1=1hr, 2=4hr
        self._last_report_time = 0
        self._healthy = True  # 當前是否健康
        self._last_healthy = True  # 上次週期是否健康
        self._start_time = time.time()

    def start(self):
        t = threading.Thread(target=self._loop, daemon=True, name=f"watchdog-{self.name}")
        t.start()
        return t

    def stop(self):
        self._running = False

    def _loop(self):
        self._last_report_time = time.time()
        while self._running:
            try:
                self._check()
            except Exception as e:
                print(f"[watchdog] 內部異常: {e}")
                notify_line_and_email("[watchdog] 內部異常", str(e))
            time.sleep(self.interval)

    def _get_next_report_interval(self):
        """根據目前健康等級返回下次彙報間隔"""
        return self.REPORT_INTERVALS[min(self._report_level, len(self.REPORT_INTERVALS) - 1)]

    def _should_report(self):
        """判斷是否該發彙報"""
        elapsed = time.time() - self._last_report_time
        return elapsed >= self._get_next_report_interval()

    def _check(self):
        issues = []

        # 1. 磁碟空間
        free = get_free_space_gb(self.disk_path)
        if free < self.disk_min_gb:
            issues.append(("critical", f"磁碟空間嚴重不足: {free:.1f}GB (下限 {self.disk_min_gb}GB)"))

        # 2. task_status.json 進度
        done_count = self._last_done_count
        if self.task_status_path and os.path.exists(self.task_status_path):
            try:
                with open(self.task_status_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                tasks = data.get("tasks", {})
                now = time.time()
                done_count = sum(1 for t in tasks.values() if t.get("status") == "done")
                if done_count != self._last_done_count:
                    self._last_done_count = done_count
                    self._last_done_change = now
                elif now - self._last_done_change > self.interval * 10:
                    processing = [t for t in tasks.values() if t.get("status") == "processing"]
                    if processing:
                        p = processing[0]
                        started = p.get("started_at", "")
                        issues.append(("warning", f"任務可能卡住: {p.get('name','?')} 自 {started} 仍在進行中"))
            except Exception as e:
                issues.append(("warning", f"讀取 task_status 失敗: {e}"))

        # 3. Share 連線
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect(("100.113.234.81", 445))
            s.close()
        except Exception:
            issues.append(("critical", "PC2 Share 連線失敗 (port 445)"))

        # 4. 空間吃緊預警
        if free < 10.0 and free >= self.disk_min_gb:
            issues.append(("warning", f"磁碟空間吃緊: {free:.1f}GB"))
            notify_line_and_email("[watchdog] 磁碟空間警告", f"D 槽剩餘 {free:.1f}GB，建議清理")

        # 5. Notebook 心跳檢查（所有機器都監控，僅更新 checkpoint 不發 alert）
        nb_online = _ping_notebook()
        _update_notebook_status(nb_online)

        # 6. Worker 程序是否還活著（檢查 worker.py 進程）
        try:
            import psutil
            worker_alive = False
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline', [])
                    if cmdline and 'worker.py' in ' '.join(cmdline):
                        worker_alive = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            if not worker_alive:
                issues.append(("critical", "Worker 進程已死亡，需要重啟"))
        except ImportError:
            # psutil not available, skip worker check
            pass

        # 7. 檢查卡在 processing 的任務（worker 崩潰殘留）
        stuck_tasks = self._find_stuck_processing_tasks(timeout_minutes=30)
        if stuck_tasks:
            for tid, name, elapsed_min in stuck_tasks:
                issues.append(("warning", f"任務 #{tid} ({name}) 卡在 processing 已 {elapsed_min:.0f} 分鐘，需重置"))

        if not self._running:
            issues.append(("critical", "Watchdog 自身停止"))

        # === 判定健康狀態 ===
        self._last_healthy = self._healthy
        has_critical = any(sev == "critical" for sev, _ in issues)
        has_warning = any(sev == "warning" for sev, _ in issues)
        self._healthy = not has_critical and not has_warning

        # 處理異常
        if has_critical or has_warning:
            msg_lines = [f"{sev}: {desc}" for sev, desc in issues]
            msg = "\n".join(msg_lines)
            icon = "[WARN]" if has_warning else "[CRIT]"
            print(f"[watchdog] {icon} 問題:")
            for l in msg_lines:
                print(f"  {l}")

            # 嘗試自行修正（不發通知）
            fixed = self._self_heal(issues)
            if fixed:
                print(f"[watchdog] 已自動修復問題")
                self._healthy = True
            else:
                if has_critical:
                    printable = '\n'.join(desc for _, desc in issues)
                    print(f"[watchdog] 嚴重異常（僅記錄，繼續運行）: {printable}")
                    self._healthy = False
                else:
                    # 警告問題無法修正 → 通報但繼續
                    notify_line_and_email(
                        f"[{self.name}] 異常通報",
                        f"無法自動修復，請注意:\n{msg}"
                    )

        # === 正常狀態：不發定期彙報 ===
        if self._healthy:
            pass

    def _self_heal(self, issues):
        """自行修正已知問題，回傳 True 表示已全部處理"""
        all_fixed = True
        for sev, desc in issues:
            fixed = self._heal_one(sev, desc)
            if not fixed:
                all_fixed = False
        return all_fixed

    def _heal_one(self, sev, desc):
        """嘗試修正單一問題"""
        # Share 連線失敗 → 嘗試 net use
        if "Share 連線失敗" in desc:
            try:
                subprocess.run(
                    ["net", "use", r"\\100.113.234.81\Share", "/user:user", "abc123"],
                    capture_output=True, text=True, timeout=10
                )
                # 驗證
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3)
                s.connect(("100.113.234.81", 445))
                s.close()
                return True
            except Exception:
                return False

        # 讀取 task_status 失敗 → 嘗試修復
        if "讀取 task_status 失敗" in desc and self.task_status_path:
            try:
                with open(self.task_status_path, 'rb') as f:
                    raw = f.read()
                text = raw.decode('utf-8', 'replace').replace('\ufffd', '')
                import re
                text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
                d = json.loads(text)
                with open(self.task_status_path, 'w', encoding='utf-8') as f:
                    json.dump(d, f, ensure_ascii=False, indent=2)
                return True
            except Exception:
                return False

        # Worker 死亡 → 自動重啟
        if "Worker 進程已死亡" in desc:
            try:
                project_root = os.path.dirname(os.path.abspath(__file__))
                worker_script = os.path.join(project_root, "worker.py")
                subprocess.Popen(
                    [sys.executable, worker_script],
                    cwd=project_root,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                print("[watchdog] 已自動重啟 worker")
                return True
            except Exception as e:
                print(f"[watchdog] 重啟 worker 失敗: {e}")
                return False

        # 卡在 processing 的任務 → 自動重置
        if "卡在 processing" in desc:
            return self._reset_stuck_processing_tasks()

        return False

    def _find_stuck_processing_tasks(self, timeout_minutes=30):
        """找出卡在 processing 超時的任務，回傳 [(task_id, name, elapsed_minutes), ...]"""
        tasks_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared", "tasks")
        if not os.path.exists(tasks_dir):
            return []

        stuck = []
        now = datetime.now()
        for fname in os.listdir(tasks_dir):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(tasks_dir, fname), "r", encoding="utf-8") as f:
                    ti = json.load(f)
                info = ti.get("task_info", {})
                if info.get("status") != "processing":
                    continue
                started_str = info.get("started_at")
                if not started_str:
                    stuck.append((info.get("task_id", "?"), info.get("name", "?"), 9999))
                    continue
                started = datetime.fromisoformat(started_str)
                elapsed = (now - started).total_seconds() / 60
                if elapsed > timeout_minutes:
                    stuck.append((info.get("task_id", "?"), info.get("name", "?"), elapsed))
            except Exception:
                pass
        return stuck

    def _reset_stuck_processing_tasks(self, timeout_minutes=30):
        """將卡在 processing 超時的任務重置為 pending"""
        tasks_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared", "tasks")
        if not os.path.exists(tasks_dir):
            return False

        now = datetime.now()
        recovered = 0
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
                    elapsed_min = 9999
                else:
                    started = datetime.fromisoformat(started_str)
                    elapsed_min = (now - started).total_seconds() / 60
                    stuck = elapsed_min > timeout_minutes
                if stuck:
                    tid = info.get("task_id", fname.replace("task_", "").replace(".json", ""))
                    info["status"] = "pending"
                    info["assigned_to"] = None
                    info["started_at"] = None
                    info["machine"] = None
                    info["last_error"] = f"Auto-recovered by watchdog: stuck >{timeout_minutes}min"
                    ti["task_info"] = info
                    ti["status"] = "pending"
                    ti["assigned_to"] = None
                    ti["last_updated"] = now.isoformat()
                    ti["updated_by"] = "watchdog"
                    ti["error"] = None
                    with open(fpath, "w", encoding="utf-8") as f:
                        json.dump(ti, f, indent=2, ensure_ascii=False)
                    print(f"[watchdog] 已重置 #{tid} ({info.get('name','?')}) 從 processing → pending")
                    recovered += 1
            except Exception:
                pass
        if recovered > 0:
            print(f"[watchdog] 已重置 {recovered} 個卡住的任務")
        return recovered > 0


# ===== Notebook 離線追蹤 =====

def _ping_notebook():
    """Ping notebook (via Tailscale IP), return True if reachable"""
    try:
        r = subprocess.run(["ping", "-n", "1", "-w", "3000", NOTEBOOK_IP],
                           capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def _update_notebook_status(online):
    """更新 notebook_checkpoint.json"""
    try:
        cp = {}
        if os.path.exists(CHECKPOINT_FILE):
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                cp = json.load(f)

        now = datetime.now().isoformat()
        was_offline = cp.get("notebook_offline", False)

        if online:
            cp["notebook_offline"] = False
            cp["offline_since"] = None
            cp["last_ping_ok"] = now
            if was_offline:
                notify_line_and_email(
                    "[watchdog] Notebook recover",
                    f"Notebook ({NOTEBOOK_IP}) 重新連線"
                )
        else:
            if not was_offline:
                # 剛離線，記錄 checkpoint
                cp["notebook_offline"] = True
                cp["offline_since"] = now
                cp["last_ping_ok"] = cp.get("last_ping_ok", None)
                notify_line_and_email(
                    "[watchdog] Notebook offline",
                    f"Notebook ({NOTEBOOK_IP}) 無法連線"
                )

        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(cp, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ===== 快捷函數 =====

def start_watchdog(name="worker", task_status_path=None, disk_path="D:\\", disk_min_gb=2.0):
    """快速啟動 watchdog"""
    w = Watchdog(name=name, task_status_path=task_status_path,
                 disk_path=disk_path, disk_min_gb=disk_min_gb)
    w.start()
    return w


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Watchdog 監控器")
    parser.add_argument("--name", default="worker", help="監控器名稱")
    parser.add_argument("--interval", type=int, default=60, help="檢查間隔(秒)")
    args = parser.parse_args()

    print(f"[watchdog] 啟動 (name={args.name}, interval={args.interval}s)")
    w = Watchdog(name=args.name, check_interval=args.interval,
                 task_status_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "task_status.json"))
    w.start()
    print(f"[watchdog] 監控中...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[watchdog] 停止")
        w.stop()
