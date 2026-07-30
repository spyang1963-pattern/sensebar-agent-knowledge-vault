#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任務管理 GUI + Worker 管理面板
用法:
  python task_manager_gui.py
"""
import os, sys, json, threading, time, subprocess, socket, ctypes, re
from datetime import datetime
from tkinter import ttk, messagebox, filedialog
import tkinter as tk

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *
from disk_checker import DiskCheck

# 顏色
COLOR_BG = "#1e1e2e"
COLOR_FG = "#cdd6f4"
COLOR_PENDING = "#f9e2af"
COLOR_PROCESSING = "#89b4fa"
COLOR_DONE = "#a6e3a1"
COLOR_FAILED = "#f38ba8"
COLOR_HEADER = "#45475a"
COLOR_HIGH_PRIORITY = "#fab387"
COLOR_WARN = "#f9e2af"
COLOR_CRITICAL = "#f38ba8"
COLOR_CARD_BG = "#313244"
COLOR_CARD_BORDER = "#45475a"
COLOR_ONLINE = "#a6e3a1"
COLOR_OFFLINE = "#f38ba8"

REFRESH_INTERVAL = 5


class WorkerManager:
    """Worker 狀態管理與註冊"""

    @staticmethod
    def get_machines():
        """從 IPC 心跳模組取得各機狀態"""
        from ipc import Heartbeat
        heartbeat = Heartbeat(MACHINE)
        
        base = {
            "notebook": {"ip": "127.0.0.1", "status": "未知", "disk": "-", "last_seen": None},
            "pc1": {"ip": "100.84.223.110", "status": "未知", "disk": "-", "last_seen": None},
            "pc2": {"ip": "100.113.234.81", "status": "未知", "disk": "-", "last_seen": None},
        }
        
        # 從心跳模組取得各機狀態
        all_status = heartbeat.get_all_status()
        for machine, info in all_status.items():
            if machine in base:
                if info["online"]:
                    hb_status = info["heartbeat"].get("status", "online")
                    base[machine]["status"] = "工作中" if hb_status == "processing" else "閒置"
                    base[machine]["last_seen"] = info["heartbeat"].get("last_seen")
                    base[machine]["current_task"] = info["heartbeat"].get("current_task")
                else:
                    base[machine]["status"] = "離線"
                    base[machine]["last_seen"] = info["heartbeat"].get("last_seen") if info["heartbeat"] else None
        
        # 本機狀態
        if base[MACHINE]["status"] not in ("工作中", "閒置"):
            base[MACHINE]["status"] = "本機"
        base[MACHINE]["ip"] = "127.0.0.1"
        
        return base

    @staticmethod
    def get_share_disk():
        """取得共用目錄磁碟空間"""
        try:
            free = ctypes.c_ulonglong()
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                SHARED_ROOT, None, None, ctypes.byref(free))
            return free.value / 1024**3
        except Exception:
            return 0

    @staticmethod
    def check_schedule(machine_name):
        """檢查遠端機器是否有開機排程"""
        if machine_name == "notebook":
            return "本機無需排程"
        ip = TAILSCALE_IPS.get(machine_name)
        if not ip:
            return "未知 IP"
        return "需在該機執行確認"  # 簡化，實際可透過 SSH 或 PSExec

    @staticmethod
    def deploy_and_register(name, ip, password=None):
        """部署到新機器 + 註冊到 config"""
        # 驗證連線
        if name != socket.gethostname().lower():
            # 嘗試 ping
            p = subprocess.run(["ping", "-n", "1", ip], capture_output=True, text=True, timeout=10)
            if p.returncode != 0:
                return (False, f"無法 ping 到 {ip}")

            # 嘗試 net use
            share_dst = f"\\\\{ip}\\Share"
            r = subprocess.run(
                ["net", "use", share_dst, "/user:user", password or "abc123"],
                capture_output=True, text=True, timeout=15)
            if r.returncode != 0:
                return (False, f"net use 失敗: {r.stderr}")

            # 複製專案
            src = str(PROJECT_ROOT)
            dst = f"{share_dst}\\AI-Agent-Workspace"
            try:
                for f in ["config.py", "worker.py", "scheduler.py", "disk_checker.py",
                          "run_pipeline.py", "batch_compress.py", "sync_results.py",
                          "task_manager_gui.py", "worker.bat", "setup_pc.bat"]:
                    sf = os.path.join(src, f)
                    if os.path.exists(sf):
                        subprocess.run(["copy", sf, f"{dst}\\{f}"], capture_output=True, text=True)
                # .opencode skills
                subprocess.run(["robocopy", os.path.join(src, ".opencode"),
                                f"{dst}\\.opencode", "/E", "/NP"], capture_output=True, text=True)
            except Exception as e:
                return (False, f"檔案複製失敗: {e}")

        # 註冊到 config.py（若尚未存在）
        hostname_lower = name.lower() if name else ip
        if hostname_lower not in MACHINE_ALIASES:
            alias = name if name else f"new-{ip.replace('.', '-')}"
            MACHINE_ALIASES[hostname_lower] = alias

        return (True, f"{name} 部署完成")

    @staticmethod
    def get_local_worker_pid():
        """取得本機 worker.py 的 PID（如有在背景執行）"""
        try:
            r = subprocess.run(
                ['powershell', '-Command',
                 'Get-Process -Name python* | Where-Object { $_.CommandLine -match "worker" } | Select-Object -ExpandProperty Id'],
                capture_output=True, text=True, timeout=5)
            pids = r.stdout.strip().split()
            return [int(p) for p in pids if p.isdigit()]
        except Exception:
            return []


class TaskManagerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"知識管理 — {MACHINE}")
        self.root.geometry("1200x750")
        self.root.configure(bg=COLOR_BG)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#313244", foreground=COLOR_FG,
                        fieldbackground="#313244", rowheight=28, font=("Consolas", 10))
        style.configure("Treeview.Heading", background=COLOR_HEADER,
                        foreground=COLOR_FG, font=("Consolas", 10, "bold"))
        style.map("Treeview", background=[("selected", "#585b70")])
        style.configure("TNotebook", background=COLOR_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=COLOR_HEADER, foreground=COLOR_FG,
                        padding=[10, 5], font=("Consolas", 10))
        style.map("TNotebook.Tab", background=[("selected", "#585b70")])

        self._worker_active = False

        self._build_ui()
        self._refresh()
        self.root.after(REFRESH_INTERVAL * 1000, self._auto_refresh)
        self.root.mainloop()

    def _build_ui(self):
        # 頂部列
        top = tk.Frame(self.root, bg=COLOR_BG)
        top.pack(fill="x", padx=10, pady=(10, 0))
        self.lbl_machine = tk.Label(top, text=f"本機: {MACHINE}", bg=COLOR_BG,
                                     fg=COLOR_FG, font=("Consolas", 12, "bold"))
        self.lbl_machine.pack(side="left", padx=(0, 10))
        self.lbl_disk = tk.Label(top, text="", bg=COLOR_BG, fg=COLOR_FG,
                                  font=("Consolas", 10))
        self.lbl_disk.pack(side="left", padx=(0, 20))
        self.lbl_worker_status = tk.Label(top, text="⬜ 無任務", bg=COLOR_BG,
                                           fg=COLOR_FG, font=("Consolas", 11, "bold"))
        self.lbl_worker_status.pack(side="left", padx=(0, 20))
        self.lbl_count = tk.Label(top, text="", bg=COLOR_BG, fg=COLOR_FG,
                                   font=("Consolas", 10))
        self.lbl_count.pack(side="right")
        self.btn_refresh = tk.Button(top, text="重新整理", command=self._refresh,
                                      bg="#45475a", fg=COLOR_FG, font=("Consolas", 10),
                                      relief="flat", padx=10)
        self.btn_refresh.pack(side="right", padx=5)

        # 主標籤頁
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        # ---- 任務管理頁籤 ----
        task_tab = tk.Frame(self.notebook, bg=COLOR_BG)
        self.notebook.add(task_tab, text=" 任務管理 ")
        self._build_task_tab(task_tab)

        # ---- Worker 管理頁籤 ----
        worker_tab = tk.Frame(self.notebook, bg=COLOR_BG)
        self.notebook.add(worker_tab, text=" Worker管理 ")
        self._build_worker_tab(worker_tab)

        # 底部狀態列
        self.lbl_status = tk.Label(self.root, text="就緒", bg=COLOR_BG, fg=COLOR_FG,
                                    font=("Consolas", 9), anchor="w")
        self.lbl_status.pack(fill="x", padx=10, pady=(0, 5))

    def _build_task_tab(self, parent):
        # 本機 Worker 控制列
        worker_row = tk.Frame(parent, bg=COLOR_BG)
        worker_row.pack(fill="x", padx=5, pady=(5, 0))
        self.lbl_worker_hint = tk.Label(worker_row, text="本機參與運算：", bg=COLOR_BG,
                                          fg=COLOR_FG, font=("Consolas", 10))
        self.lbl_worker_hint.pack(side="left", padx=(0, 5))
        self.btn_worker_join = tk.Button(worker_row, text="☐ 可加入任務", command=self._worker_toggle,
                                           bg="#a6e3a1", fg="#1e1e2e", font=("Consolas", 10, "bold"),
                                           relief="flat", padx=15, pady=4)
        self.btn_worker_join.pack(side="left")

        # 操作列
        action_row = tk.Frame(parent, bg=COLOR_BG)
        action_row.pack(fill="x", padx=5, pady=5)
        self.btn_high = tk.Button(action_row, text="⬆ 調高優先級", command=self._promote_task,
                                  bg="#fab387", fg="#1e1e2e", font=("Consolas", 10),
                                  relief="flat", padx=10)
        self.btn_high.pack(side="left", padx=(0, 5))
        self.btn_normal = tk.Button(action_row, text="⬇ 設為一般", command=self._demote_task,
                                    bg="#45475a", fg=COLOR_FG, font=("Consolas", 10),
                                    relief="flat", padx=10)
        self.btn_normal.pack(side="left", padx=(0, 5))
        self.btn_redistribute = tk.Button(action_row, text="⟳ 全部重新分配", command=self._redistribute,
                                          bg="#89b4fa", fg="#1e1e2e", font=("Consolas", 10),
                                          relief="flat", padx=10)
        self.btn_redistribute.pack(side="left", padx=(5, 0))
        self.btn_new = tk.Button(action_row, text="＋ 新增任務", command=self._new_task_dialog,
                                 bg="#a6e3a1", fg="#1e1e2e", font=("Consolas", 10),
                                 relief="flat", padx=10)
        self.btn_new.pack(side="left", padx=(5, 0))
        self.btn_delete = tk.Button(action_row, text="✕ 刪除", command=self._delete_task,
                                     bg="#f38ba8", fg="#1e1e2e", font=("Consolas", 10),
                                     relief="flat", padx=10)
        self.btn_delete.pack(side="left", padx=(5, 0))
        
        # 篩選按鈕
        self.filter_var = tk.StringVar(value="all")
        self.btn_filter_pending = tk.Button(action_row, text="⏳ 只看待辦", command=self._filter_pending,
                                            bg="#f9e2af", fg="#1e1e2e", font=("Consolas", 10),
                                            relief="flat", padx=10)
        self.btn_filter_pending.pack(side="left", padx=(10, 0))
        self.btn_filter_all = tk.Button(action_row, text="📋 全部顯示", command=self._filter_all,
                                        bg="#45475a", fg=COLOR_FG, font=("Consolas", 10),
                                        relief="flat", padx=10)
        self.btn_filter_all.pack(side="left", padx=(5, 0))

        # 表格
        columns = ("#", "狀態", "優先級", "類型", "指派給", "機器", "名稱/標題", "大小", "錯誤")
        self.tree = ttk.Treeview(parent, columns=columns, show="headings",
                                 selectmode="browse")
        widths = [50, 80, 60, 60, 70, 80, 350, 70, 200]
        for col, w in zip(columns, widths):
            self.tree.heading(col, text=col, anchor="w")
            self.tree.column(col, width=w, anchor="w", minwidth=40)

        scroll_y = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)
        scroll_y.pack(side="right", fill="y", padx=(0, 5), pady=5)

        self.tree.tag_configure("pending", foreground=COLOR_PENDING)
        self.tree.tag_configure("processing", foreground=COLOR_PROCESSING)
        self.tree.tag_configure("done", foreground=COLOR_DONE)
        self.tree.tag_configure("failed", foreground=COLOR_FAILED)
        self.tree.tag_configure("high", foreground=COLOR_HIGH_PRIORITY)
        self.tree.tag_configure("warn", foreground=COLOR_WARN)
        self.tree.tag_configure("critical", foreground=COLOR_CRITICAL)

    def _build_worker_tab(self, parent):
        """Worker 管理面板 — 三機狀態卡片 + 新增 Worker"""
        # 標題
        header = tk.Frame(parent, bg=COLOR_BG)
        header.pack(fill="x", padx=10, pady=(10, 5))
        tk.Label(header, text="Worker 狀態總覽", bg=COLOR_BG, fg=COLOR_FG,
                 font=("Consolas", 14, "bold")).pack(side="left")
        self.lbl_share_disk = tk.Label(header, text="", bg=COLOR_BG, fg=COLOR_FG,
                                        font=("Consolas", 10))
        self.lbl_share_disk.pack(side="right")

        # 三機卡片容器
        self.card_frame = tk.Frame(parent, bg=COLOR_BG)
        self.card_frame.pack(fill="x", padx=10, pady=5)
        self.cards = {}
        for name in ["notebook", "pc1", "pc2"]:
            card = tk.Frame(self.card_frame, bg=COLOR_CARD_BG, highlightbackground=COLOR_CARD_BORDER,
                            highlightthickness=1, padx=12, pady=10)
            card.pack(side="left", fill="x", expand=True, padx=(0, 10))
            self.cards[name] = card
            # 主機名
            tk.Label(card, text=name.upper(), bg=COLOR_CARD_BG, fg=COLOR_FG,
                     font=("Consolas", 12, "bold")).pack(anchor="w")
            # 狀態行
            self._add_card_row(card, "狀態: ", "lbl_status_" + name, "查詢中")
            self._add_card_row(card, "IP: ", "lbl_ip_" + name,
                               TAILSCALE_IPS.get(name, "127.0.0.1"))
            self._add_card_row(card, "磁碟: ", "lbl_disk_" + name, "-")
            self._add_card_row(card, "排程: ", "lbl_schedule_" + name, "-")

        # 新增 Worker 區域
        add_frame = tk.LabelFrame(parent, text=" 新增 Worker ", bg=COLOR_BG, fg=COLOR_FG,
                                   font=("Consolas", 11, "bold"),
                                   padx=10, pady=10)
        add_frame.pack(fill="x", padx=10, pady=10)

        row1 = tk.Frame(add_frame, bg=COLOR_BG)
        row1.pack(fill="x", pady=(5, 5))
        tk.Label(row1, text="主機名:", bg=COLOR_BG, fg=COLOR_FG,
                 font=("Consolas", 10)).pack(side="left", padx=(0, 5))
        self.entry_new_name = tk.Entry(row1, font=("Consolas", 10), bg="#313244", fg=COLOR_FG,
                                        insertbackground=COLOR_FG, relief="flat", width=25)
        self.entry_new_name.pack(side="left", padx=(0, 20))
        tk.Label(row1, text="IP 位址:", bg=COLOR_BG, fg=COLOR_FG,
                 font=("Consolas", 10)).pack(side="left", padx=(0, 5))
        self.entry_new_ip = tk.Entry(row1, font=("Consolas", 10), bg="#313244", fg=COLOR_FG,
                                      insertbackground=COLOR_FG, relief="flat", width=18)
        self.entry_new_ip.pack(side="left")

        btn_frame = tk.Frame(add_frame, bg=COLOR_BG)
        btn_frame.pack(fill="x", pady=(5, 0))
        self.btn_add_worker = tk.Button(btn_frame, text="＋ 部署並註冊 Worker",
                                         command=self._add_worker,
                                         bg="#a6e3a1", fg="#1e1e2e",
                                         font=("Consolas", 10, "bold"),
                                         relief="flat", padx=15, pady=4)
        self.btn_add_worker.pack(side="left", padx=(0, 10))
        self.lbl_add_result = tk.Label(btn_frame, text="", bg=COLOR_BG, fg=COLOR_FG,
                                        font=("Consolas", 9))
        self.lbl_add_result.pack(side="left")

        # 共用目錄狀態
        status_frame = tk.Frame(parent, bg=COLOR_BG)
        status_frame.pack(fill="x", padx=10, pady=(0, 10))

        tk.Label(status_frame, text="共用目錄:", bg=COLOR_BG, fg=COLOR_FG,
                 font=("Consolas", 10)).pack(side="left")
        self.lbl_share_status = tk.Label(status_frame, text=SHARED_ROOT, bg=COLOR_BG,
                                          fg=COLOR_FG, font=("Consolas", 9))
        self.lbl_share_status.pack(side="left", padx=(5, 0))

    def _add_card_row(self, parent, label_text, attr_name, default):
        row = tk.Frame(parent, bg=COLOR_CARD_BG)
        row.pack(fill="x", pady=(2, 0))
        tk.Label(row, text=label_text, bg=COLOR_CARD_BG, fg="#6c7086",
                 font=("Consolas", 10)).pack(side="left")
        lbl = tk.Label(row, text=default, bg=COLOR_CARD_BG, fg=COLOR_FG,
                       font=("Consolas", 10))
        lbl.pack(side="left")
        setattr(self, attr_name, lbl)

    def _refresh_worker_status(self):
        """更新 Worker 面板的三機狀態"""
        try:
            machines = WorkerManager.get_machines()
            share_disk = WorkerManager.get_share_disk()
            self.lbl_share_disk.config(text=f"共用磁碟: {share_disk:.1f} GB")

            for name, info in machines.items():
                card = self.cards.get(name)
                if not card:
                    continue

                # 狀態
                status_text = info.get("status", "未知")
                status_color = COLOR_ONLINE if status_text in ("閒置", "本機", "工作中") else COLOR_OFFLINE
                lbl = getattr(self, "lbl_status_" + name, None)
                if lbl:
                    lbl.config(text=status_text, fg=status_color)

                # IP
                lbl = getattr(self, "lbl_ip_" + name, None)
                if lbl:
                    lbl.config(text=info.get("ip", "-"))

                # 磁碟（本機即時讀取）
                if name == MACHINE:
                    try:
                        dc = DiskCheck()
                        disk_text = f"C:{dc.c_free:.0f}G D:{dc.d_free:.0f}G"
                    except Exception:
                        disk_text = "-"
                else:
                    disk_text = "-"
                lbl = getattr(self, "lbl_disk_" + name, None)
                if lbl:
                    lbl.config(text=disk_text)

                # 當前任務
                current_task = info.get("current_task")
                if current_task:
                    sched_text = f"任務: {current_task}"
                else:
                    sched_text = "閒置"
                lbl = getattr(self, "lbl_schedule_" + name, None)
                if lbl:
                    lbl.config(text=sched_text)

        except Exception as e:
            self.lbl_share_disk.config(text=f"更新失敗: {e}")

        # 自動偵測本機 Worker 狀態：只在非活動時顯示預設狀態
        if not self._worker_active:
            self.lbl_worker_status.config(text="⬜ 待命（按「可加入任務」啟動）", fg=COLOR_FG)
            self.btn_worker_join.config(text="☐ 可加入任務", bg="#a6e3a1", fg="#1e1e2e")

    def _add_worker(self):
        """新增 Worker：部署 + 註冊"""
        name = self.entry_new_name.get().strip()
        ip = self.entry_new_ip.get().strip()
        if not name or not ip:
            self.lbl_add_result.config(text="請輸入主機名和 IP", fg=COLOR_FAILED)
            return

        self.btn_add_worker.config(state="disabled", text="部署中...")
        self.root.update()

        def do_add():
            success, msg = WorkerManager.deploy_and_register(name, ip)
            self.root.after(0, lambda: self._add_worker_done(success, msg))

        threading.Thread(target=do_add, daemon=True).start()

    def _add_worker_done(self, success, msg):
        self.btn_add_worker.config(state="normal", text="＋ 部署並註冊 Worker")
        if success:
            self.lbl_add_result.config(text=msg, fg=COLOR_DONE)
            self._refresh_worker_status()
        else:
            self.lbl_add_result.config(text=msg, fg=COLOR_FAILED)

    def _refresh(self):
        try:
            data = load_task_status()
            tasks = data["tasks"]
            disk = DiskCheck()

            disk_text = "C: {:.1f}GB | D: {:.1f}GB".format(disk.c_free, disk.d_free)
            if disk.d_free < 10:
                disk_text += " ⚠"
            self.lbl_disk.config(text=disk_text)

            counts = {"pending": 0, "processing": 0, "done": 0, "failed": 0}
            for _, info in tasks.items():
                s = info.get("status", "pending")
                counts[s] = counts.get(s, 0) + 1
            total = len(tasks)
            self.lbl_count.config(
                text="總 {} | ⏳{} ▶{} ✓{} ✗{}".format(
                    total, counts['pending'], counts['processing'], counts['done'], counts['failed']))

            for row in self.tree.get_children():
                self.tree.delete(row)

            sorted_tids = sorted(tasks.keys(), key=lambda x: (
                -tasks[x].get("priority", 0),
                int(x) if x.isdigit() else 0
            ))

            for tid in sorted_tids:
                info = tasks[tid]
                task_type = info.get("type", "video")
                status = info.get("status", "pending")
                
                # 燒字幕任務顯示中文狀態
                status_display = {
                    "subtitle": {"pending": "待燒錄", "processing": "燒錄中", "completed": "已燒錄", "failed": "失敗", "assigned": "待燒錄"},
                }.get(task_type, {}).get(status, status)
                
                # 篩選邏輯
                if self.filter_var.get() == "pending" and status not in ("pending", "processing"):
                    continue
                
                priority = info.get("priority", 0)
                assigned = info.get("assigned_to", "?")
                machine = info.get("machine", "-")
                error = info.get("last_error", "") or ""

                if task_type == "sensebar":
                    name = info.get("title", "?")
                    size_str = "-"
                else:
                    name = info.get("name", "?")
                    size_mb = info.get("size_mb", 0)
                    size_str = "{:.0f}MB".format(size_mb) if size_mb else "-"

                priority_str = "高" if priority == 1 else "一般"

                tags = [status]
                if priority == 1:
                    tags.append("high")
                if "critical" in error.lower() or "不足" in error or "空間" in error:
                    tags.append("critical")

                name_display = name if len(name) <= 40 else name[:37] + "..."
                error_display = error if len(error) <= 40 else error[:37] + "..."

                self.tree.insert("", "end", iid=tid, values=(
                    tid, status_display, priority_str, task_type, assigned,
                    machine, name_display, size_str, error_display
                ), tags=tags)

            self.lbl_status.config(text="更新時間: " + datetime.now().strftime('%H:%M:%S'))
            self._refresh_worker_status()

        except Exception as e:
            self.lbl_status.config(text="更新失敗: " + str(e))

    def _auto_refresh(self):
        self._refresh()
        self.root.after(REFRESH_INTERVAL * 1000, self._auto_refresh)

    def _promote_task(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示", "請先選取一個任務")
            return
        tid = sel[0]
        data = load_task_status()
        if tid not in data["tasks"]:
            return
        if data["tasks"][tid].get("priority") == 1:
            messagebox.showinfo("提示", "此任務已是高優先級")
            return
        data["tasks"][tid]["priority"] = 1
        save_task_status(data)
        self._refresh()
        self.lbl_status.config(text="#{} 已設為高優先級".format(tid))

    def _demote_task(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示", "請先選取一個任務")
            return
        tid = sel[0]
        data = load_task_status()
        if tid not in data["tasks"]:
            return
        if data["tasks"][tid].get("priority", 0) == 0:
            messagebox.showinfo("提示", "此任務已是一般優先級")
            return
        data["tasks"][tid]["priority"] = 0
        save_task_status(data)
        self._refresh()
        self.lbl_status.config(text="#{} 已設為一般優先級".format(tid))

    def _new_task_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("新增任務")
        win.geometry("550x540")
        win.configure(bg=COLOR_BG)

        type_frame = tk.Frame(win, bg=COLOR_BG)
        type_frame.pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(type_frame, text="任務類型:", bg=COLOR_BG, fg=COLOR_FG,
                 font=("Consolas", 10)).pack(side="left")
        task_type_var = tk.StringVar(value="video")
        tk.Radiobutton(type_frame, text="視訊檔", variable=task_type_var, value="video",
                       bg=COLOR_BG, fg=COLOR_FG, selectcolor=COLOR_BG,
                       font=("Consolas", 10)).pack(side="left", padx=10)
        tk.Radiobutton(type_frame, text="YouTube", variable=task_type_var,
                       value="sensebar", bg=COLOR_BG, fg=COLOR_FG,
                       selectcolor=COLOR_BG, font=("Consolas", 10)).pack(side="left")
        tk.Radiobutton(type_frame, text="燒字幕", variable=task_type_var,
                       value="subtitle", bg=COLOR_BG, fg=COLOR_FG,
                       selectcolor=COLOR_BG, font=("Consolas", 10)).pack(side="left", padx=10)

        container = tk.Frame(win, bg=COLOR_BG)
        container.pack(fill="both", expand=True, padx=10)

        # 視訊檔表單
        video_frame = tk.Frame(container, bg=COLOR_BG)
        video_entries = {}
        video_fields = [
            ("檔案路徑 * (本機或 UNC)", "path", ""),
            ("課程名稱", "course", "緊急課程"),
            ("KB 收成路徑 (相對 knowledge-base/)", "kb_subpath", ""),
            ("指派給 (pc1/pc2/notebook)", "assigned", MACHINE),
            ("備註 (選填)", "note", ""),
        ]
        for label, key, default in video_fields:
            tk.Label(video_frame, text=label, bg=COLOR_BG, fg=COLOR_FG,
                     font=("Consolas", 10), anchor="w").pack(fill="x", padx=5, pady=(8, 0))
            e = tk.Entry(video_frame, font=("Consolas", 10), bg="#313244", fg=COLOR_FG,
                         insertbackground=COLOR_FG, relief="flat")
            e.insert(0, default)
            e.pack(fill="x", padx=5, pady=(2, 0))
            video_entries[key] = e

        # 路徑變更時自動帶入課程名稱和 KB 路徑
        def auto_fill_from_path(*_):
            p = video_entries["path"].get().strip()
            if not p:
                return
            # 從路徑推斷課程名稱
            base = r"D:\!!!!!理周學院老師"
            if p.startswith(base):
                rel = os.path.relpath(p, base)
                parts = rel.split(os.sep)
                if len(parts) > 1:
                    course_name = parts[0]
                else:
                    course_name = os.path.splitext(parts[0])[0]
            else:
                course_name = os.path.basename(os.path.dirname(p))
            # 清理課程名稱：去掉 !! 前綴和 - 後的副標題
            clean_course = course_name.lstrip('!')
            if '-' in clean_course:
                clean_course = clean_course.split('-')[0].strip()
            if video_entries["course"].get().strip() in ("", "緊急課程"):
                video_entries["course"].delete(0, "end")
                video_entries["course"].insert(0, clean_course)
            # 自動帶入 KB 路徑：只帶課程名稱，讓使用者決定完整位置
            kb_e = video_entries.get("kb_subpath")
            if kb_e and not kb_e.get().strip():
                kb_e.delete(0, "end")
                kb_e.insert(0, clean_course)

        video_entries["path"].bind("<FocusOut>", auto_fill_from_path)
        video_entries["path"].bind("<Return>", auto_fill_from_path)

        tk.Label(video_frame, text="大小 (MB, 留空自動偵測)", bg=COLOR_BG,
                 fg=COLOR_FG, font=("Consolas", 10), anchor="w").pack(fill="x", padx=5, pady=(8, 0))
        e_vsize = tk.Entry(video_frame, font=("Consolas", 10), bg="#313244", fg=COLOR_FG,
                          insertbackground=COLOR_FG, relief="flat")
        e_vsize.pack(fill="x", padx=5, pady=(2, 0))

        cb_frame = tk.Frame(video_frame, bg=COLOR_BG)
        cb_frame.pack(fill="x", padx=5, pady=(8, 0))
        auto_sub_var = tk.BooleanVar(value=False)
        tk.Checkbutton(cb_frame, text="自動燒字幕", variable=auto_sub_var,
                       bg=COLOR_BG, fg=COLOR_FG, selectcolor=COLOR_BG,
                       font=("Consolas", 10)).pack(side="left", padx=(0, 15))
        harvest_kb_var = tk.BooleanVar(value=True)
        tk.Checkbutton(cb_frame, text="收成到知識庫", variable=harvest_kb_var,
                       bg=COLOR_BG, fg=COLOR_FG, selectcolor=COLOR_BG,
                       font=("Consolas", 10)).pack(side="left")

        # YouTube 表單
        yt_frame = tk.Frame(container, bg=COLOR_BG)
        yt_entries = {}
        yt_fields = [
            ("YouTube 網址 * (頻道或單一影片)", "yt_url", ""),
            ("指派給 (pc1/pc2/notebook)", "yt_assigned", "notebook"),
            ("備註 (選填)", "yt_note", ""),
        ]
        for label, key, default in yt_fields:
            tk.Label(yt_frame, text=label, bg=COLOR_BG, fg=COLOR_FG,
                     font=("Consolas", 10), anchor="w").pack(fill="x", padx=5, pady=(8, 0))
            e = tk.Entry(yt_frame, font=("Consolas", 10), bg="#313244", fg=COLOR_FG,
                         insertbackground=COLOR_FG, relief="flat")
            e.insert(0, default)
            e.pack(fill="x", padx=5, pady=(2, 0))
            yt_entries[key] = e

        yt_cb_frame = tk.Frame(yt_frame, bg=COLOR_BG)
        yt_cb_frame.pack(fill="x", padx=5, pady=(8, 0))
        yt_auto_sub = tk.BooleanVar(value=False)
        tk.Checkbutton(yt_cb_frame, text="自動燒字幕", variable=yt_auto_sub,
                       bg=COLOR_BG, fg=COLOR_FG, selectcolor=COLOR_BG,
                       font=("Consolas", 10)).pack(side="left", padx=(0, 15))
        yt_harvest_kb = tk.BooleanVar(value=True)
        tk.Checkbutton(yt_cb_frame, text="收成到知識庫", variable=yt_harvest_kb,
                       bg=COLOR_BG, fg=COLOR_FG, selectcolor=COLOR_BG,
                       font=("Consolas", 10)).pack(side="left")

        # 燒字幕表單
        sub_frame = tk.Frame(container, bg=COLOR_BG)
        sub_frame_inner = tk.Frame(sub_frame, bg=COLOR_BG)
        sub_frame_inner.pack(fill="both", expand=True, padx=10)

        # 來源：選擇 .md 檔（雙面板對話框）
        sub_src_label = tk.Label(sub_frame_inner, text="選擇 .md 檔案：", bg=COLOR_BG, fg=COLOR_FG,
                                 font=("Consolas", 10), anchor="w")
        sub_src_label.pack(fill="x", pady=(8, 0))
        sub_src_row = tk.Frame(sub_frame_inner, bg=COLOR_BG)
        sub_src_row.pack(fill="x")
        sub_src_entry = tk.Entry(sub_src_row, font=("Consolas", 10), bg="#313244", fg=COLOR_FG,
                                 insertbackground=COLOR_FG, relief="flat")
        sub_src_entry.pack(side="left", fill="x", expand=True)
        tk.Button(sub_src_row, text="選擇檔案", font=("Consolas", 9),
                  bg="#45475a", fg=COLOR_FG, relief="flat",
                  command=lambda: _open_file_dialog()).pack(side="right", padx=(5, 0))
        sub_src_info = tk.Label(sub_frame_inner, text="※ 左視窗瀏覽 .md 檔，雙擊或按加入選到右視窗",
                                bg=COLOR_BG, fg="#a6adc8", font=("Consolas", 9), anchor="w")
        sub_src_info.pack(fill="x")

        # 輸出目錄（留空=同目錄）
        sub_out_path = tk.StringVar()
        tk.Label(sub_frame_inner, text="輸出目錄 (留空=同目錄)：", bg=COLOR_BG, fg=COLOR_FG,
                 font=("Consolas", 10), anchor="w").pack(fill="x", pady=(8, 0))
        sub_out_row = tk.Frame(sub_frame_inner, bg=COLOR_BG)
        sub_out_row.pack(fill="x")
        tk.Entry(sub_out_row, textvariable=sub_out_path,
                 font=("Consolas", 10), bg="#313244", fg=COLOR_FG,
                 insertbackground=COLOR_FG, relief="flat").pack(side="left", fill="x", expand=True)
        tk.Button(sub_out_row, text="瀏覽", font=("Consolas", 9),
                  bg="#45475a", fg=COLOR_FG, relief="flat",
                  command=lambda: sub_out_path.set(filedialog.askdirectory(title="選擇輸出目錄"))
                  ).pack(side="right", padx=(5, 0))

        # 字幕樣式
        tk.Label(sub_frame_inner, text="字幕樣式：", bg=COLOR_BG, fg=COLOR_FG,
                 font=("Consolas", 10, "bold"), anchor="w").pack(fill="x", pady=(8, 0))

        # 字型大小（滑桿 + 數字輸入，8~72）
        fs_frame = tk.Frame(sub_frame_inner, bg=COLOR_BG)
        fs_frame.pack(fill="x", pady=(2, 0))
        tk.Label(fs_frame, text="字型大小:", bg=COLOR_BG, fg=COLOR_FG,
                 font=("Consolas", 10)).pack(side="left")
        sub_fontsize_var = tk.IntVar(value=24)
        sub_fontsize_scale = tk.Scale(fs_frame, from_=8, to=72, orient="horizontal",
                                      variable=sub_fontsize_var, showvalue=False,
                                      bg=COLOR_BG, fg=COLOR_FG, highlightbackground=COLOR_BG,
                                      length=150, sliderlength=15)
        sub_fontsize_scale.pack(side="left", padx=(5, 0))
        sub_fontsize_entry = tk.Entry(fs_frame, textvariable=sub_fontsize_var,
                                      font=("Consolas", 10), bg="#313244", fg=COLOR_FG,
                                      insertbackground=COLOR_FG, relief="flat", width=4)
        sub_fontsize_entry.pack(side="left", padx=5)
        tk.Label(fs_frame, text="pt", bg=COLOR_BG, fg="#a6adc8",
                 font=("Consolas", 9)).pack(side="left")

        # 垂直邊距（0~200）
        mv_frame = tk.Frame(sub_frame_inner, bg=COLOR_BG)
        mv_frame.pack(fill="x", pady=(2, 0))
        tk.Label(mv_frame, text="垂直邊距:", bg=COLOR_BG, fg=COLOR_FG,
                 font=("Consolas", 10)).pack(side="left")
        sub_margin_var = tk.IntVar(value=30)
        sub_margin_scale = tk.Scale(mv_frame, from_=0, to=200, orient="horizontal",
                                     variable=sub_margin_var, showvalue=False,
                                     bg=COLOR_BG, fg=COLOR_FG, highlightbackground=COLOR_BG,
                                     length=150, sliderlength=15)
        sub_margin_scale.pack(side="left", padx=(5, 0))
        sub_margin_entry = tk.Entry(mv_frame, textvariable=sub_margin_var,
                                     font=("Consolas", 10), bg="#313244", fg=COLOR_FG,
                                     insertbackground=COLOR_FG, relief="flat", width=4)
        sub_margin_entry.pack(side="left", padx=5)
        tk.Label(mv_frame, text="px", bg=COLOR_BG, fg="#a6adc8",
                 font=("Consolas", 9)).pack(side="left")

        # 位置：3x3 按鈕矩陣
        tk.Label(sub_frame_inner, text="位置（點選九宮格）：", bg=COLOR_BG, fg=COLOR_FG,
                 font=("Consolas", 10), anchor="w").pack(fill="x", pady=(6, 0))
        pos_frame = tk.Frame(sub_frame_inner, bg=COLOR_BG)
        pos_frame.pack()
        sub_position = tk.StringVar(value="bottom")

        pos_grid = [
            ("上左", "top-left"),     ("上中", "top"),     ("上右", "top-right"),
            ("中左", "middle-left"),  ("正中", "middle"),  ("中右", "middle-right"),
            ("下左", "bottom-left"),  ("下中", "bottom"),  ("下右", "bottom-right"),
        ]
        for idx, (label, val) in enumerate(pos_grid):
            row, col = divmod(idx, 3)
            rb = tk.Radiobutton(pos_frame, text=label, variable=sub_position, value=val,
                                bg=COLOR_BG, fg=COLOR_FG, selectcolor=COLOR_BG,
                                indicatoron=0, width=8, relief="flat",
                                font=("Consolas", 9),
                                activebackground="#45475a", activeforeground=COLOR_FG)
            rb.grid(row=row, column=col, padx=2, pady=2)

        video_frame.pack(fill="both", expand=True)
        yt_frame.pack_forget()
        sub_frame.pack_forget()

        def switch_type(*_):
            t = task_type_var.get()
            if t == "video":
                video_frame.pack(fill="both", expand=True)
                yt_frame.pack_forget()
                sub_frame.pack_forget()
            elif t == "sensebar":
                video_frame.pack_forget()
                yt_frame.pack(fill="both", expand=True)
                sub_frame.pack_forget()
            else:  # subtitle
                video_frame.pack_forget()
                yt_frame.pack_forget()
                sub_frame.pack(fill="both", expand=True)

        task_type_var.trace("w", switch_type)

        def submit():
            try:
                _submit_impl()
            except Exception as e:
                import traceback
                traceback.print_exc()
                messagebox.showerror("建立失敗", str(e))

        def _open_file_dialog():
            dlg = FileSelectionDialog(win)
            selected = dlg.show()
            if selected:
                _selected_sub_files.clear()
                _selected_sub_files.extend(selected)
                sub_src_entry.delete(0, "end")
                sub_src_entry.insert(0, f"{len(selected)} 個 .md 檔已選取")
                sub_src_entry.config(fg="#a6e3a1")

        _selected_sub_files = []

        def _md_to_srt(md_text):
            m = re.search(r'## 逐字稿\s*\n(.*)', md_text, re.DOTALL)
            if not m:
                return None
            transcript = m.group(1).strip()
            if not transcript:
                return None
            lines = [l.strip() for l in transcript.splitlines() if l.strip()]
            subs = []
            for line in lines:
                if len(line) <= 30:
                    subs.append(line)
                else:
                    parts = re.split(r'([，、。！？])', line)
                    cur = ""
                    for p in parts:
                        if len(cur) + len(p) <= 30:
                            cur += p
                        else:
                            if cur:
                                subs.append(cur)
                            cur = p
                    if cur:
                        subs.append(cur)
            if not subs:
                return None
            srt_lines = []
            t = 0.0
            for i, txt in enumerate(subs, 1):
                dur = len(txt) / 4
                h1, m1 = int(t // 3600), int((t % 3600) // 60)
                s1, ms1 = int(t % 60), int((t % 1) * 1000)
                e = t + dur
                h2, m2 = int(e // 3600), int((e % 3600) // 60)
                s2, ms2 = int(e % 60), int((e % 1) * 1000)
                srt_lines.append(f"{i}")
                srt_lines.append(f"{h1:02d}:{m1:02d}:{s1:02d},{ms1:03d} --> {h2:02d}:{m2:02d}:{s2:02d},{ms2:03d}")
                srt_lines.append(txt)
                srt_lines.append("")
                t = e + 0.3
            return "\n".join(srt_lines)

        def _submit_impl():
            t = task_type_var.get()
            data = load_task_status()
            counter = data.get("task_counter", 0) + 1
            tid = str(counter)
            data["task_counter"] = counter

            if t == "video":
                path = video_entries["path"].get().strip()
                if not path:
                    messagebox.showerror("錯誤", "請輸入檔案路徑")
                    return
                if not os.path.exists(path):
                    if not messagebox.askyesno("路徑不存在", "路徑不存在:\n" + path + "\n仍要建立任務？"):
                        return
                course = video_entries["course"].get().strip() or "緊急課程"
                assigned = video_entries["assigned"].get().strip().lower()
                if assigned not in ("pc1", "pc2", "notebook"):
                    assigned = None
                note = video_entries["note"].get().strip()
                
                # 如果是目錄，遞迴掃描所有 mp4 檔案並逐一建立任務
                if os.path.isdir(path):
                    # course = 頂層目錄名
                    course = os.path.basename(path)
                    all_videos = []
                    video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm')
                    naming_warnings = []
                    for root, dirs, files in os.walk(path):
                        for f in files:
                            if f.lower().endswith(video_extensions):
                                full_path = os.path.join(root, f)
                                # 從理周學院老師目錄開始的相對路徑
                                base = r"D:\!!!!!理周學院老師"
                                try:
                                    rel_path = os.path.relpath(full_path, base)
                                except ValueError:
                                    # 跨磁碟無法算相對路徑，用完整路徑
                                    rel_path = full_path
                                
                                # 命名驗證
                                parts = rel_path.split(os.sep)
                                for i, p in enumerate(parts):
                                    if p != p.rstrip():
                                        naming_warnings.append(f"尾部空白: .../{p}")
                                if len(parts) >= 4:
                                    file_stem = os.path.splitext(parts[-1])[0]
                                    if parts[-2].rstrip() == file_stem or parts[-2].rstrip() in file_stem:
                                        naming_warnings.append(f"重複目錄層: {parts[-2]}")
                                
                                # 自動修正：strip 每個路徑元件
                                fixed_parts = [p.rstrip() for p in parts]
                                rel_path = os.sep.join(fixed_parts)
                                
                                all_videos.append((full_path, rel_path, f))
                    
                    if naming_warnings:
                        unique_warnings = list(dict.fromkeys(naming_warnings))[:10]
                        msg = f"發現 {len(naming_warnings)} 個命名問題：\n\n"
                        for w in unique_warnings:
                            msg += f"  ⚠ {w}\n"
                        if len(naming_warnings) > 10:
                            msg += f"  ... 還有 {len(naming_warnings)-10} 個\n"
                        msg += "\n仍要建立任務？（kb_harvest 會自動修正）"
                        if not messagebox.askyesno("命名警告", msg):
                            return
                    
                    if not all_videos:
                        messagebox.showerror("錯誤", "目錄中沒有影音檔案:\n" + path)
                        return
                    
                    created_count = 0
                    skipped_count = 0
                    for full_path, rel_path, video_name in all_videos:
                        # 檢查是否已存在相同路徑的 pending 任務
                        already_exists = False
                        for existing_tid, existing_task in data["tasks"].items():
                            if (existing_task.get("status") in ("pending", "processing") and
                                existing_task.get("video_relpath") == rel_path):
                                already_exists = True
                                break
                        
                        if already_exists:
                            skipped_count += 1
                            continue
                        
                        try:
                            size_mb = os.path.getsize(full_path) / (1024 * 1024)
                        except Exception:
                            size_mb = 150
                        counter = data.get("task_counter", 0) + 1
                        data["task_counter"] = counter
                        tid = str(counter)
                        data["tasks"][tid] = {
                            "type": "video",
                            "status": "pending",
                            "assigned_to": assigned,
                            "priority": 0,
                            "course": course,
                            "name": video_name,
                            "video_relpath": rel_path,
                            "kb_subpath": video_entries["kb_subpath"].get().strip() or course,
                            "size_mb": round(size_mb, 1),
                            "needs_compress": size_mb > 24,
                            "note": note,
                            "auto_subtitle": auto_sub_var.get(),
                            "harvest_to_kb": harvest_kb_var.get(),
                            "discovered_at": datetime.now().isoformat(),
                            "started_at": None,
                            "completed_at": None,
                            "last_error": None,
                            "machine": None,
                            "output_keys": [],
                        }
                        # 同時寫入 shared/tasks/
                        shared_task = {
                            "task_id": tid,
                            "task_info": data["tasks"][tid],
                            "status": "pending",
                            "assigned_to": assigned,
                        }
                        shared_task_file = os.path.join(SHARED_ROOT, "tasks", f"task_{tid}.json")
                        os.makedirs(os.path.dirname(shared_task_file), exist_ok=True)
                        with open(shared_task_file, "w", encoding="utf-8") as f:
                            json.dump(shared_task, f, indent=2)
                        created_count += 1
                    if skipped_count > 0:
                        print_text = f"{course} ({created_count} 部新增, {skipped_count} 部已存在跳過)"
                    else:
                        print_text = f"{course} ({created_count} 部影片)"
                else:
                    size_str = e_vsize.get().strip()
                    # 檢查是否已存在相同路徑的 pending 任務
                    rel_path = os.path.basename(path)
                    for existing_tid, existing_task in data["tasks"].items():
                        if (existing_task.get("status") in ("pending", "processing") and
                            existing_task.get("video_relpath") == path):
                            messagebox.showinfo("已存在", "此影片已有 pending 任務:\n#" + existing_tid)
                            win.destroy()
                            self._refresh()
                            return
                    
                    if size_str:
                        try:
                            size_mb = float(size_str)
                        except ValueError:
                            messagebox.showerror("錯誤", "大小請輸入數字")
                            return
                    else:
                        try:
                            size_mb = os.path.getsize(path) / (1024 * 1024)
                        except Exception:
                            size_mb = 150
                    data["tasks"][tid] = {
                        "type": "video",
                        "status": "pending",
                        "assigned_to": assigned,
                        "priority": 0,
                        "course": course,
                        "name": os.path.basename(path),
                        "video_relpath": path,
                        "kb_subpath": video_entries["kb_subpath"].get().strip() or course,
                        "size_mb": round(size_mb, 1),
                        "needs_compress": size_mb > 24,
                        "note": note,
                        "auto_subtitle": auto_sub_var.get(),
                        "harvest_to_kb": harvest_kb_var.get(),
                        "discovered_at": datetime.now().isoformat(),
                        "started_at": None,
                        "completed_at": None,
                        "last_error": None,
                        "machine": None,
                        "output_keys": [],
                    }
                    # 同時寫入 shared/tasks/
                    shared_task = {
                        "task_id": tid,
                        "task_info": data["tasks"][tid],
                        "status": "pending",
                        "assigned_to": assigned,
                    }
                    shared_task_file = os.path.join(SHARED_ROOT, "tasks", f"task_{tid}.json")
                    os.makedirs(os.path.dirname(shared_task_file), exist_ok=True)
                    with open(shared_task_file, "w", encoding="utf-8") as f:
                        json.dump(shared_task, f, indent=2)
                    print_text = path
                    created_count = 1
            elif t == "sensebar":
                url = yt_entries["yt_url"].get().strip()
                if not url:
                    messagebox.showerror("錯誤", "請輸入 YouTube 網址")
                    return
                assigned = yt_entries["yt_assigned"].get().strip().lower()
                if assigned not in ("pc1", "pc2", "notebook"):
                    assigned = None
                note = yt_entries["yt_note"].get().strip()

                import re
                vid_match = re.search(r'[A-Za-z0-9_-]{11}', url)
                vid = vid_match.group(0) if vid_match else "unknown"
                title = "YouTube-" + vid

                data["tasks"][tid] = {
                    "type": "sensebar",
                    "status": "pending",
                    "assigned_to": assigned,
                    "priority": 0,
                    "video_id": vid,
                    "title": title,
                    "url": url,
                    "note": note,
                    "auto_subtitle": yt_auto_sub.get(),
                    "harvest_to_kb": yt_harvest_kb.get(),
                    "discovered_at": datetime.now().isoformat(),
                    "started_at": None,
                    "completed_at": None,
                    "last_error": None,
                    "machine": None,
                }
                print_text = url

            elif t == "subtitle":
                md_files = list(_selected_sub_files)
                if not md_files:
                    messagebox.showerror("錯誤", "請先選擇 .md 檔案")
                    return

                outdir = sub_out_path.get().strip()
                font_size = str(sub_fontsize_var.get())
                position = sub_position.get()
                margin_v = sub_margin_var.get()

                created_count = 0
                for md_path in md_files:
                    try:
                        with open(md_path, "r", encoding="utf-8") as fh:
                            md_text = fh.read()
                    except Exception:
                        continue

                    vm = re.search(r'^## 影片\s*\n(.+)', md_text, re.MULTILINE)
                    if not vm:
                        continue
                    video_path = os.path.normpath(vm.group(1).strip())
                    if not os.path.isfile(video_path):
                        continue

                    srt_path = None
                    sm = re.search(r'^## 字幕\s*\n(.+)', md_text, re.MULTILINE)
                    if sm:
                        candidate = sm.group(1).strip()
                        srp = os.path.normpath(os.path.join(os.path.dirname(md_path), candidate))
                        if os.path.isfile(srp):
                            srt_path = srp

                    if not srt_path:
                        srt_content = _md_to_srt(md_text)
                        if srt_content:
                            srt_path = os.path.join(os.path.dirname(md_path), "generated.srt")
                            with open(srt_path, "w", encoding="utf-8") as fh:
                                fh.write(srt_content)
                        else:
                            continue

                    # 找最大任務 ID，避免衝突
                    existing_ids = [int(k) for k in data.get("tasks", {}) if k.isdigit()]
                    shared_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               "shared", "tasks")
                    if os.path.exists(shared_dir):
                        for fn in os.listdir(shared_dir):
                            if fn.startswith("task_") and fn.endswith(".json"):
                                try:
                                    existing_ids.append(int(fn.replace("task_", "").replace(".json", "")))
                                except ValueError:
                                    pass
                    next_id = (max(existing_ids) if existing_ids else 0) + 1
                    tid = str(next_id)
                    name = os.path.basename(video_path)

                    data["tasks"][tid] = {
                        "type": "subtitle",
                        "status": "pending",
                        "assigned_to": MACHINE,
                        "priority": 0,
                        "name": name,
                        "video_path": video_path,
                        "srt_path": srt_path,
                        "output_dir": outdir if outdir else None,
                        "font_size": int(font_size),
                        "position": position,
                        "margin_v": margin_v,
                        "note": "",
                        "discovered_at": datetime.now().isoformat(),
                        "started_at": None,
                        "completed_at": None,
                        "last_error": None,
                        "machine": None,
                    }
                    shared_task = {
                        "task_id": tid,
                        "task_info": data["tasks"][tid],
                        "status": "pending",
                        "assigned_to": MACHINE,
                    }
                    shared_task_file = os.path.join(SHARED_ROOT, "tasks", f"task_{tid}.json")
                    os.makedirs(os.path.dirname(shared_task_file), exist_ok=True)
                    with open(shared_task_file, "w", encoding="utf-8") as f:
                        json.dump(shared_task, f, indent=2)
                    created_count += 1

                if created_count == 0:
                    messagebox.showerror("錯誤", "沒有任何可處理的 .md 檔（需包含 ## 影片 與有效的影片路徑）")
                    return
                print_text = f"燒字幕: {len(md_files)} 個檔案 ({created_count} 個任務)"

            # 更新 task_counter
            all_ids = [int(k) for k in data.get("tasks", {}) if k.isdigit()]
            data["task_counter"] = max(all_ids) if all_ids else 0
            data["generated_at"] = datetime.now().isoformat()
            save_task_status(data)
            
            # YouTube 任務也需要寫入 shared/tasks/
            if t == "sensebar":
                shared_task = {
                    "task_id": tid,
                    "task_info": data["tasks"][tid],
                    "status": "pending",
                    "assigned_to": data["tasks"][tid].get("assigned_to"),
                }
                shared_task_file = os.path.join(SHARED_ROOT, "tasks", f"task_{tid}.json")
                os.makedirs(os.path.dirname(shared_task_file), exist_ok=True)
                with open(shared_task_file, "w", encoding="utf-8") as f:
                    json.dump(shared_task, f, indent=2)
            
            win.destroy()
            self._refresh()
            
            # 自動滾動到第一個新增的任務
            current_max = max([int(k) for k in data.get("tasks", {}) if k.isdigit()] + [0])
            first_new_tid = str(current_max - (created_count if t in ("video", "subtitle") else 0) + 1)
            if first_new_tid in self.tree.get_children():
                self.tree.see(first_new_tid)
                self.tree.selection_set(first_new_tid)
            
            # 顯示建立結果
            self.lbl_status.config(text="新增任務: " + print_text)
            self._refresh()
            self.lbl_status.config(text="新增任務 #{}: {}".format(tid, print_text))

        btn_frame = tk.Frame(win, bg=COLOR_BG)
        btn_frame.pack(fill="x", padx=10, pady=15)
        tk.Button(btn_frame, text="建立", command=submit,
                  bg="#a6e3a1", fg="#1e1e2e", font=("Consolas", 10),
                  relief="flat", padx=15).pack(side="left", padx=(0, 10))
        tk.Button(btn_frame, text="取消", command=win.destroy,
                  bg="#45475a", fg=COLOR_FG, font=("Consolas", 10),
                  relief="flat", padx=15).pack(side="left")

    def _redistribute(self):
        if not messagebox.askyesno("確認重新分配", "所有 pending/processing 任務將釋放，\n由各 worker 自動搶單。\n\n確定？"):
            return
        r = subprocess.run([sys.executable, str(PROJECT_ROOT / "scheduler.py"), "--redistribute"],
                           capture_output=True, text=True, cwd=str(PROJECT_ROOT))
        self._refresh()
        self.lbl_status.config(text=r.stdout.splitlines()[-1] if r.stdout else "重新分配完成")

    def _worker_toggle(self):
        if self._worker_active:
            if not messagebox.askyesno("確認停止", "本機所有等待/處理中的任務將釋放回中央佇列。\n確定停止運算？"):
                return
            r = subprocess.run([sys.executable, str(PROJECT_ROOT / "worker.py"), "--release"],
                               capture_output=True, text=True, cwd=str(PROJECT_ROOT))
            self._worker_active = False
            self.btn_worker_join.config(text="☐ 可加入任務", bg="#a6e3a1", fg="#1e1e2e")
            self.lbl_worker_status.config(text="⬜ 無任務", fg=COLOR_FG)
            self._refresh()
            self.lbl_status.config(text="本機已停止運算，任務已釋放")
        else:
            self._worker_active = True
            self.btn_worker_join.config(text="☑ 停止工作指派", bg="#f38ba8", fg="#1e1e2e")
            self.lbl_worker_status.config(text="🟢 工作中", fg="#a6e3a1")
            self._start_worker_loop()
            self._refresh()
            self.lbl_status.config(text="本機已加入任務分配")

    def _start_worker_loop(self):
        def loop():
            while self._worker_active:
                try:
                    r = subprocess.run(
                        [sys.executable, str(PROJECT_ROOT / "worker.py"), "--once"],
                        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
                        timeout=3600)
                    self.root.after(0, self._refresh)
                except subprocess.TimeoutExpired:
                    pass
                except Exception:
                    pass
                for _ in range(10):
                    if not self._worker_active:
                        return
                    time.sleep(1)
        t = threading.Thread(target=loop, daemon=True)
        t.start()

    def _delete_task(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示", "請先選取一個任務")
            return
        tid = sel[0]
        data = load_task_status()
        if tid not in data["tasks"]:
            return
        info = data["tasks"][tid]
        name = info.get("name") or info.get("title", "?")
        if not messagebox.askyesno("確認刪除", "刪除任務 #" + tid + ": " + name + "？"):
            return
        del data["tasks"][tid]
        save_task_status(data)
        self._refresh()
        self.lbl_status.config(text="已刪除任務 #" + tid)

    def _filter_pending(self):
        """只顯示 pending/processing 任務"""
        self.filter_var.set("pending")
        self.btn_filter_pending.config(bg="#89b4fa")
        self.btn_filter_all.config(bg="#45475a")
        self._refresh()

    def _filter_all(self):
        """顯示所有任務"""
        self.filter_var.set("all")
        self.btn_filter_all.config(bg="#89b4fa")
        self.btn_filter_pending.config(bg="#f9e2af")
        self._refresh()


class FileSelectionDialog:
    """雙面板檔案選擇對話框：左視窗瀏覽 .md → 加入 → 右視窗待處理"""
    def __init__(self, parent):
        self.win = tk.Toplevel(parent)
        self.win.title("選擇 .md 檔案")
        self.win.geometry("800x500")
        self.win.configure(bg="#1e1e2e")
        self.win.transient(parent)
        self.win.grab_set()

        self.selected = []

        # 上方：目錄選擇
        top = tk.Frame(self.win, bg="#1e1e2e")
        top.pack(fill="x", padx=10, pady=(10, 5))
        tk.Label(top, text="來源目錄：", bg="#1e1e2e", fg="#cdd6f4",
                 font=("Consolas", 10)).pack(side="left")
        self.dir_entry = tk.Entry(top, font=("Consolas", 10), bg="#313244", fg="#cdd6f4",
                                  insertbackground="#cdd6f4", relief="flat")
        self.dir_entry.pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(top, text="瀏覽", font=("Consolas", 9), bg="#45475a",
                  fg="#cdd6f4", relief="flat", command=self._browse_dir).pack(side="left")
        tk.Button(top, text="掃描", font=("Consolas", 9), bg="#45475a",
                  fg="#cdd6f4", relief="flat", command=self._scan_dir).pack(side="left", padx=(5, 0))

        # 主區域：左右雙面板
        main = tk.Frame(self.win, bg="#1e1e2e")
        main.pack(fill="both", expand=True, padx=10, pady=5)

        # 左面板
        left_frame = tk.LabelFrame(main, text="可選檔案", bg="#1e1e2e", fg="#cdd6f4",
                                   font=("Consolas", 10), relief="flat")
        left_frame.pack(side="left", fill="both", expand=True)
        self.left_lb = tk.Listbox(left_frame, bg="#313244", fg="#cdd6f4",
                                  selectbackground="#585b70", relief="flat",
                                  font=("Consolas", 10), activestyle="none")
        self.left_lb.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        left_scroll = tk.Scrollbar(self.left_lb, orient="vertical")
        left_scroll.pack(side="right", fill="y")
        self.left_lb.config(yscrollcommand=left_scroll.set)
        left_scroll.config(command=self.left_lb.yview)
        self.left_lb.bind("<Double-Button-1>", lambda e: self._add_selected())

        # 中間按鈕
        mid_frame = tk.Frame(main, bg="#1e1e2e")
        mid_frame.pack(side="left", fill="y", padx=10)
        tk.Button(mid_frame, text="加入 >>", font=("Consolas", 10), bg="#45475a",
                  fg="#a6e3a1", relief="flat", command=self._add_selected).pack(pady=(80, 5))
        tk.Button(mid_frame, text="<< 移除", font=("Consolas", 10), bg="#45475a",
                  fg="#f38ba8", relief="flat", command=self._remove_selected).pack(pady=5)

        # 右面板
        right_frame = tk.LabelFrame(main, text="待處理檔案", bg="#1e1e2e", fg="#cdd6f4",
                                    font=("Consolas", 10), relief="flat")
        right_frame.pack(side="left", fill="both", expand=True)
        self.right_lb = tk.Listbox(right_frame, bg="#313244", fg="#cdd6f4",
                                   selectbackground="#585b70", relief="flat",
                                   font=("Consolas", 10), activestyle="none")
        self.right_lb.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        right_scroll = tk.Scrollbar(self.right_lb, orient="vertical")
        right_scroll.pack(side="right", fill="y")
        self.right_lb.config(yscrollcommand=right_scroll.set)
        right_scroll.config(command=self.right_lb.yview)
        self.right_lb.bind("<Double-Button-1>", lambda e: self._remove_selected())

        # 底部按鈕
        bottom = tk.Frame(self.win, bg="#1e1e2e")
        bottom.pack(fill="x", padx=10, pady=10)
        self.count_label = tk.Label(bottom, text="已選 0 個檔案", bg="#1e1e2e", fg="#a6adc8",
                                    font=("Consolas", 10))
        self.count_label.pack(side="left")
        tk.Button(bottom, text="確定", font=("Consolas", 10), bg="#a6e3a1",
                  fg="#1e1e2e", relief="flat", command=self._confirm).pack(side="right", padx=(5, 0))
        tk.Button(bottom, text="取消", font=("Consolas", 10), bg="#45475a",
                  fg="#cdd6f4", relief="flat", command=self.win.destroy).pack(side="right")

        self._all_files = []  # (display_name, full_path)

    def _browse_dir(self):
        d = filedialog.askdirectory(title="選擇包含 .md 的目錄")
        if d:
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, d)
            self._scan_dir()

    def _scan_dir(self):
        path = self.dir_entry.get().strip()
        if not path or not os.path.isdir(path):
            messagebox.showerror("錯誤", "請選擇有效的目錄", parent=self.win)
            return
        self._all_files = []
        self.left_lb.delete(0, "end")
        for root, dirs, files in os.walk(path):
            for f in sorted(files):
                if f.lower().endswith(".md"):
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, path)
                    self._all_files.append((rel, full))
                    self.left_lb.insert("end", rel)
        if not self._all_files:
            messagebox.showinfo("提示", "目錄中沒有 .md 檔案", parent=self.win)

    def _add_selected(self):
        sel = self.left_lb.curselection()
        if not sel:
            return
        for idx in reversed(sel):
            display, path = self._all_files[idx]
            # 加到右邊
            self.right_lb.insert("end", display)
            # 從左邊移除
            self.left_lb.delete(idx)
            del self._all_files[idx]
        self._update_count()

    def _remove_selected(self):
        sel = self.right_lb.curselection()
        if not sel:
            return
        for idx in reversed(sel):
            display = self.right_lb.get(idx)
            self.right_lb.delete(idx)
            # 放回左邊
            # 找到對應的完整路徑 - 需要重新掃描
            # 直接重新掃描較簡單
        # 保留右側，從右側移除的檔案暫不回左側（避免需重新掃描）
        self._update_count()

    def _update_count(self):
        count = self.right_lb.size()
        self.count_label.config(text=f"已選 {count} 個檔案")

    def _confirm(self):
        # 從右側 listbox 收集檔案路徑
        self.selected = []
        for i in range(self.right_lb.size()):
            display = self.right_lb.get(i)
            # 找對應的完整路徑 - 需要重新遍歷
        # 重新掃描目錄來匹配
        path = self.dir_entry.get().strip()
        if path and os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for f in files:
                    if f.lower().endswith(".md"):
                        full = os.path.join(root, f)
                        rel = os.path.relpath(full, path)
                        # 檢查是否在右側 listbox 中
                        for i in range(self.right_lb.size()):
                            if self.right_lb.get(i) == rel:
                                self.selected.append(full)
                                break
        self.win.destroy()

    def show(self):
        self.win.wait_window()
        return self.selected


if __name__ == "__main__":
    import tempfile
    lock_file = os.path.join(tempfile.gettempdir(), "task_manager_gui.lock")
    if os.path.exists(lock_file):
        try:
            with open(lock_file, 'r') as f:
                old_pid = int(f.read().strip())
            # 檢查舊進程是否還活著
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x100000, False, old_pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                sys.exit(0)
        except Exception:
            pass
    
    lock_fd = os.open(lock_file, os.O_CREAT | os.O_TRUNC | os.O_WRONLY)
    os.write(lock_fd, str(os.getpid()).encode())
    os.close(lock_fd)
    
    try:
        TaskManagerGUI()
    finally:
        try:
            os.remove(lock_file)
        except Exception:
            pass
