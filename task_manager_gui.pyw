#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任務管理 GUI
用法:
  python task_manager_gui.py
"""
import os, sys, json, threading, time
from datetime import datetime
from tkinter import ttk, messagebox
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

REFRESH_INTERVAL = 5


class TaskManagerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"任務管理 — {MACHINE}")
        self.root.geometry("1200x700")
        self.root.configure(bg=COLOR_BG)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#313244", foreground=COLOR_FG,
                        fieldbackground="#313244", rowheight=28, font=("Consolas", 10))
        style.configure("Treeview.Heading", background=COLOR_HEADER,
                        foreground=COLOR_FG, font=("Consolas", 10, "bold"))
        style.map("Treeview", background=[("selected", "#585b70")])

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

        # 本機 Worker 控制列
        worker_row = tk.Frame(self.root, bg=COLOR_BG)
        worker_row.pack(fill="x", padx=10, pady=(0, 5))
        self.lbl_worker_hint = tk.Label(worker_row, text="本機參與運算：", bg=COLOR_BG,
                                         fg=COLOR_FG, font=("Consolas", 10))
        self.lbl_worker_hint.pack(side="left", padx=(0, 5))
        self.btn_worker_join = tk.Button(worker_row, text="☐ 可加入任務", command=self._worker_toggle,
                                          bg="#a6e3a1", fg="#1e1e2e", font=("Consolas", 10, "bold"),
                                          relief="flat", padx=15, pady=4)
        self.btn_worker_join.pack(side="left")
        self._worker_active = False

        # 操作列
        action_row = tk.Frame(self.root, bg=COLOR_BG)
        action_row.pack(fill="x", padx=10, pady=5)
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

        # 表格
        columns = ("#", "狀態", "優先級", "類型", "指派給", "機器", "名稱/標題", "大小", "錯誤")
        self.tree = ttk.Treeview(self.root, columns=columns, show="headings",
                                 selectmode="browse")
        widths = [50, 80, 60, 60, 70, 80, 350, 70, 200]
        for col, w in zip(columns, widths):
            self.tree.heading(col, text=col, anchor="w")
            self.tree.column(col, width=w, anchor="w", minwidth=40)

        scroll_y = ttk.Scrollbar(self.root, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=5)
        scroll_y.pack(side="right", fill="y", padx=(0, 10), pady=5)

        self.tree.tag_configure("pending", foreground=COLOR_PENDING)
        self.tree.tag_configure("processing", foreground=COLOR_PROCESSING)
        self.tree.tag_configure("done", foreground=COLOR_DONE)
        self.tree.tag_configure("failed", foreground=COLOR_FAILED)
        self.tree.tag_configure("high", foreground=COLOR_HIGH_PRIORITY)
        self.tree.tag_configure("warn", foreground=COLOR_WARN)
        self.tree.tag_configure("critical", foreground=COLOR_CRITICAL)

        # 底部狀態列
        self.lbl_status = tk.Label(self.root, text="就緒", bg=COLOR_BG, fg=COLOR_FG,
                                    font=("Consolas", 9), anchor="w")
        self.lbl_status.pack(fill="x", padx=10, pady=(0, 5))

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

            # 排序：高優先級在前，再依 tid
            sorted_tids = sorted(tasks.keys(), key=lambda x: (
                -tasks[x].get("priority", 0),
                int(x) if x.isdigit() else 0
            ))

            for tid in sorted_tids:
                info = tasks[tid]
                task_type = info.get("type", "video")
                status = info.get("status", "pending")
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
                    tid, status, priority_str, task_type, assigned,
                    machine, name_display, size_str, error_display
                ), tags=tags)

            self.lbl_status.config(text="更新時間: " + datetime.now().strftime('%H:%M:%S'))

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

        # 類型選擇
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

        # 容器
        container = tk.Frame(win, bg=COLOR_BG)
        container.pack(fill="both", expand=True, padx=10)

        # ---- 視訊檔表單 ----
        video_frame = tk.Frame(container, bg=COLOR_BG)
        video_entries = {}
        video_fields = [
            ("檔案路徑 * (本機或 UNC)", "path", ""),
            ("課程名稱", "course", "緊急課程"),
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

        tk.Label(video_frame, text="大小 (MB, 留空自動偵測)", bg=COLOR_BG,
                 fg=COLOR_FG, font=("Consolas", 10), anchor="w").pack(fill="x", padx=5, pady=(8, 0))
        e_vsize = tk.Entry(video_frame, font=("Consolas", 10), bg="#313244", fg=COLOR_FG,
                          insertbackground=COLOR_FG, relief="flat")
        e_vsize.pack(fill="x", padx=5, pady=(2, 0))

        # ---- YouTube 表單 ----
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

        # 初始顯示視訊檔
        video_frame.pack(fill="both", expand=True)
        yt_frame.pack_forget()

        def switch_type(*_):
            t = task_type_var.get()
            if t == "video":
                video_frame.pack(fill="both", expand=True)
                yt_frame.pack_forget()
            else:
                video_frame.pack_forget()
                yt_frame.pack(fill="both", expand=True)

        task_type_var.trace("w", switch_type)

        def submit():
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
                size_str = e_vsize.get().strip()
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
                course = video_entries["course"].get().strip() or "緊急課程"
                assigned = video_entries["assigned"].get().strip().lower()
                if assigned not in ("pc1", "pc2", "notebook"):
                    assigned = None
                note = video_entries["note"].get().strip()
                data["tasks"][tid] = {
                    "type": "video",
                    "status": "pending",
                    "assigned_to": assigned,
                    "priority": 1,
                    "course": course,
                    "name": os.path.basename(path),
                    "video_relpath": path,
                    "size_mb": round(size_mb, 1),
                    "needs_compress": size_mb > 24,
                    "note": note,
                    "discovered_at": datetime.now().isoformat(),
                    "started_at": None,
                    "completed_at": None,
                    "last_error": None,
                    "machine": None,
                    "output_keys": [],
                }
                print_text = path
            else:
                # === YouTube ===
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
                    "priority": 1,
                    "video_id": vid,
                    "title": title,
                    "url": url,
                    "note": note,
                    "discovered_at": datetime.now().isoformat(),
                    "started_at": None,
                    "completed_at": None,
                    "last_error": None,
                    "machine": None,
                }
                print_text = url

            data["generated_at"] = datetime.now().isoformat()
            save_task_status(data)
            win.destroy()
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
        import subprocess
        r = subprocess.run([sys.executable, str(PROJECT_ROOT / "scheduler.py"), "--redistribute"],
                           capture_output=True, text=True, cwd=str(PROJECT_ROOT))
        self._refresh()
        self.lbl_status.config(text=r.stdout.splitlines()[-1] if r.stdout else "重新分配完成")

    def _worker_toggle(self):
        if self._worker_active:
            # 停止：釋放所有本機任務
            if not messagebox.askyesno("確認停止", "本機所有等待/處理中的任務將釋放回中央佇列。\n確定停止運算？"):
                return
            import subprocess
            r = subprocess.run([sys.executable, str(PROJECT_ROOT / "worker.py"), "--release"],
                               capture_output=True, text=True, cwd=str(PROJECT_ROOT))
            self._worker_active = False
            self.btn_worker_join.config(text="☐ 可加入任務", bg="#a6e3a1", fg="#1e1e2e")
            self.lbl_worker_status.config(text="⬜ 無任務", fg=COLOR_FG)
            self._refresh()
            self.lbl_status.config(text="本機已停止運算，任務已釋放")
        else:
            # 開始：在背景啟動 worker 常駐（每 30 秒檢查一次）
            self._worker_active = True
            self.btn_worker_join.config(text="☑ 停止工作指派", bg="#f38ba8", fg="#1e1e2e")
            self.lbl_worker_status.config(text="🟢 工作中", fg="#a6e3a1")
            self._start_worker_loop()
            self._refresh()
            self.lbl_status.config(text="本機已加入任務分配")

    def _start_worker_loop(self):
        """在背景執行緒中持續讓 worker 搶任務"""
        def loop():
            while self._worker_active:
                try:
                    import subprocess
                    r = subprocess.run(
                        [sys.executable, str(PROJECT_ROOT / "worker.py"), "--once"],
                        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
                        timeout=3600)
                    # 更新狀態顯示
                    self.root.after(0, self._refresh)
                except subprocess.TimeoutExpired:
                    pass
                except Exception:
                    pass
                # 休息 10 秒再檢查
                for _ in range(10):
                    if not self._worker_active:
                        return
                    time.sleep(1)
        import threading
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


if __name__ == "__main__":
    TaskManagerGUI()
