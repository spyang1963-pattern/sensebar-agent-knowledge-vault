"""
胚騰 AI Agent - 通知管理系統 v7
狀態管理：編輯中/待命/運作中/已停止
"""
import tkinter as tk
from tkinter import ttk, messagebox
import yaml
import os
from datetime import datetime

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")

STATUS_EDITING = "編輯中"
STATUS_STANDBY = "待命"
STATUS_RUNNING = "運作中"
STATUS_STOPPED = "已停止"
STATUS_ERROR = "錯誤"

STATUS_EMOJI = {
    STATUS_EDITING: "📝 編輯中",
    STATUS_STANDBY: "🔵 待命",
    STATUS_RUNNING: "🟢 運作中",
    STATUS_STOPPED: "⚪ 已停止",
    STATUS_ERROR: "🔴 錯誤"
}

STATUS_COLORS = {
    STATUS_EDITING: "#f59e0b",
    STATUS_STANDBY: "#3b82f6",
    STATUS_RUNNING: "#10b981",
    STATUS_STOPPED: "#64748b",
    STATUS_ERROR: "#ef4444"
}

# 接收者狀態
RECIPIENT_ACTIVE = "運作中"
RECIPIENT_PAUSED = "暫停"
RECIPIENT_ERROR = "錯誤"

RECIPIENT_EMOJI = {
    RECIPIENT_ACTIVE: "🟢 運作中",
    RECIPIENT_PAUSED: "🟡 暫停",
    RECIPIENT_ERROR: "🔴 錯誤"
}

RECIPIENT_COLORS = {
    RECIPIENT_ACTIVE: "#10b981",
    RECIPIENT_PAUSED: "#f59e0b",
    RECIPIENT_ERROR: "#ef4444"
}


class NotificationManager:
    def __init__(self):
        self.config = self.load_config()
        self.root = tk.Tk()
        self.root.title("胚騰 AI Agent - 通知管理系統")
        self.root.geometry("950x700")
        self.root.configure(bg="#0f172a")
        
        self.msg_list = list(self.config.get("messages", []))
        self.line_enabled = tk.BooleanVar()
        self.email_enabled = tk.BooleanVar()
        
        self.setup_styles()
        self.create_widgets()
        self.refresh_all()
    
    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TNotebook", background="#0f172a")
        self.style.configure("TNotebook.Tab", background="#334155", foreground="#e2e8f0", padding=[12, 5])
        self.style.map("TNotebook.Tab", background=[("selected", "#3b82f6")])
        self.style.configure("Treeview", background="#1e293b", foreground="#e2e8f0", fieldbackground="#1e293b")
        self.style.configure("Treeview.Heading", background="#334155", foreground="#e2e8f0")
        self.style.map("Treeview", background=[("selected", "#3b82f6")])
    
    def load_config(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except:
            return {"channels": {}, "messages": []}
    
    def save_all(self):
        self.config["messages"] = self.msg_list
        self.config["channels"]["line"]["enabled"] = self.line_enabled.get()
        self.config["channels"]["line"]["channel_access_token"] = self.line_token.get()
        self.config["channels"]["email"]["enabled"] = self.email_enabled.get()
        self.config["channels"]["email"]["sender_email"] = self.smtp_email.get()
        self.config["channels"]["email"]["sender_password"] = self.smtp_pass.get()
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
            messagebox.showinfo("成功", "全部設定已儲存！")
        except Exception as e:
            messagebox.showerror("錯誤", f"儲存失敗：{e}")
    
    def create_widgets(self):
        main = tk.Frame(self.root, bg="#0f172a")
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        header = tk.Frame(main, bg="#0f172a")
        header.pack(fill=tk.X)
        tk.Label(header, text="胚騰 AI Agent - 通知管理系統", bg="#0f172a", fg="#60a5fa",
                font=("Microsoft JhengHei", 14, "bold")).pack(side=tk.LEFT)
        tk.Button(header, text="儲存全部", command=self.save_all, bg="#10b981", fg="white", width=10).pack(side=tk.RIGHT, padx=5)
        tk.Button(header, text="離開", command=self.root.quit, bg="#64748b", fg="white", width=8).pack(side=tk.RIGHT)
        
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(10,0))
        
        self.create_overview_tab()
        self.create_edit_tab()
        self.create_settings_tab()
        
        self.status_label = tk.Label(main, text="就緒", bg="#0f172a", fg="#64748b", font=("Microsoft JhengHei", 9))
        self.status_label.pack(fill=tk.X, pady=(5,0))
    
    # ==================== 總覽頁籤 ====================
    def create_overview_tab(self):
        tab = tk.Frame(self.notebook, bg="#1e293b")
        self.notebook.add(tab, text=" 總覽 ")
        
        # 搜尋列
        search_frame = tk.Frame(tab, bg="#1e293b")
        search_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(search_frame, text="搜尋:", bg="#1e293b", fg="#e2e8f0").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *a: self.filter_overview())
        tk.Entry(search_frame, textvariable=self.search_var, bg="#334155", fg="#e2e8f0", insertbackground="#e2e8f0", width=25).pack(side=tk.LEFT, padx=10)
        tk.Button(search_frame, text="清除", command=lambda: self.search_var.set(""), bg="#64748b", fg="white").pack(side=tk.LEFT)
        
        self.stats_label = tk.Label(search_frame, text="", bg="#1e293b", fg="#60a5fa")
        self.stats_label.pack(side=tk.RIGHT)
        
        # 狀態圖例
        legend = tk.Frame(tab, bg="#1e293b")
        legend.pack(fill=tk.X, padx=10, pady=(5,0))
        for status, color in STATUS_COLORS.items():
            tk.Label(legend, text=f"  {status}  ", bg=color, fg="white", font=("Microsoft JhengHei", 8)).pack(side=tk.LEFT, padx=3)
        
        # 訊息總覽表
        columns = ("status", "name", "recipients", "repeat", "time", "end")
        self.overview_tree = ttk.Treeview(tab, columns=columns, show="headings", height=10)
        self.overview_tree.heading("status", text="狀態")
        self.overview_tree.heading("name", text="訊息名稱")
        self.overview_tree.heading("recipients", text="接收者")
        self.overview_tree.heading("repeat", text="週期")
        self.overview_tree.heading("time", text="時間")
        self.overview_tree.heading("end", text="終止")
        self.overview_tree.column("status", width=80)
        self.overview_tree.column("name", width=160)
        self.overview_tree.column("recipients", width=80)
        self.overview_tree.column("repeat", width=60)
        self.overview_tree.column("time", width=60)
        self.overview_tree.column("end", width=80)
        
        # 設定狀態文字顏色
        self.overview_tree.tag_configure("tag_編輯中", foreground="#f59e0b")
        self.overview_tree.tag_configure("tag_待命", foreground="#3b82f6")
        self.overview_tree.tag_configure("tag_運作中", foreground="#10b981")
        self.overview_tree.tag_configure("tag_已停止", foreground="#64748b")
        self.overview_tree.tag_configure("tag_錯誤", foreground="#ef4444")
        
        self.overview_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.overview_tree.bind("<<TreeviewSelect>>", self.on_msg_select)
        self.overview_tree.bind("<Double-1>", self.goto_edit)
        
        # 使用者總覽（根據選取訊息篩選）
        user_frame = tk.LabelFrame(tab, text="使用此訊息的使用者 (點選訊息查看)", bg="#334155", fg="#e2e8f0")
        user_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.user_tree = ttk.Treeview(user_frame, columns=("status", "name", "channel", "target"), show="headings", height=6)
        self.user_tree.heading("status", text="狀態")
        self.user_tree.heading("name", text="姓名")
        self.user_tree.heading("channel", text="管道")
        self.user_tree.heading("target", text="ID/Email")
        self.user_tree.column("status", width=80)
        self.user_tree.column("name", width=80)
        self.user_tree.column("channel", width=50)
        self.user_tree.column("target", width=280)
        
        # 設定使用者狀態文字顏色
        self.user_tree.tag_configure("tag_運作中", foreground="#10b981")
        self.user_tree.tag_configure("tag_暫停", foreground="#f59e0b")
        self.user_tree.tag_configure("tag_錯誤", foreground="#ef4444")
        
        self.user_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.user_tree.bind("<Double-1>", self.on_user_dblclick)
        
        tk.Label(tab, text="💡 點訊息→顯示使用者 | 雙擊訊息→編輯 | 雙擊使用者→篩選訊息", bg="#1e293b", fg="#64748b").pack(padx=10, anchor=tk.W)
    
    def refresh_overview(self):
        self.overview_tree.delete(*self.overview_tree.get_children())
        self.user_tree.delete(*self.user_tree.get_children())
        
        for msg in self.msg_list:
            recipients = msg.get("recipients", [])
            recip_count = len(recipients)
            sched = msg.get("schedule", {})
            status = msg.get("status", STATUS_EDITING)
            status_display = STATUS_EMOJI.get(status, status)
            
            self.overview_tree.insert("", tk.END, values=(
                status_display, msg.get("name", ""), f"{recip_count} 人", sched.get("repeat", ""), sched.get("time", ""), sched.get("end", "")
            ), tags=(f"tag_{status}",))
        
        total = len(self.msg_list)
        running = sum(1 for m in self.msg_list if m.get("status") == STATUS_RUNNING)
        standby = sum(1 for m in self.msg_list if m.get("status") == STATUS_STANDBY)
        self.stats_label.config(text=f"共 {total} 則 | 運作中 {running} | 待命 {standby}")
    
    def on_msg_select(self, event):
        """點選訊息時，顯示該訊息的接收者"""
        sel = self.overview_tree.selection()
        if not sel:
            return
        
        msg_name = self.overview_tree.item(sel[0])["values"][1]
        self.user_tree.delete(*self.user_tree.get_children())
        
        for msg in self.msg_list:
            if msg.get("name") == msg_name:
                for r in msg.get("recipients", []):
                    status = r.get("status", RECIPIENT_ACTIVE)
                    status_display = RECIPIENT_EMOJI.get(status, status)
                    self.user_tree.insert("", tk.END, values=(
                        status_display, r.get("name", ""), r.get("channel", ""), r.get("target", "")
                    ), tags=(f"tag_{status}",))
                break
    
    def on_user_dblclick(self, event):
        """雙擊使用者時，彈出視窗顯示該使用者接收的訊息"""
        sel = self.user_tree.selection()
        if not sel:
            return
        
        user_name = self.user_tree.item(sel[0])["values"][1]
        user_channel = self.user_tree.item(sel[0])["values"][2]
        user_target = self.user_tree.item(sel[0])["values"][3]
        
        # 建立彈出視窗
        dlg = tk.Toplevel(self.root)
        dlg.title(f"使用者：{user_name}")
        dlg.geometry("500x350")
        dlg.configure(bg="#1e293b")
        dlg.transient(self.root)
        dlg.grab_set()
        
        # 標題
        header = tk.Frame(dlg, bg="#1e293b")
        header.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(header, text=f"使用者：{user_name}", bg="#1e293b", fg="#60a5fa", 
                font=("Microsoft JhengHei", 12, "bold")).pack(side=tk.LEFT)
        tk.Label(header, text=f"({user_channel}: {user_target})", bg="#1e293b", fg="#94a3b8",
                font=("Microsoft JhengHei", 9)).pack(side=tk.LEFT, padx=10)
        
        # 訊息列表
        list_frame = tk.LabelFrame(dlg, text="接收的訊息", bg="#334155", fg="#e2e8f0")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        columns = ("status", "name", "repeat", "time")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        tree.heading("status", text="狀態")
        tree.heading("name", text="訊息名稱")
        tree.heading("repeat", text="週期")
        tree.heading("time", text="時間")
        tree.column("status", width=70)
        tree.column("name", width=200)
        tree.column("repeat", width=80)
        tree.column("time", width=80)
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 查詢該使用者接收的訊息
        for msg in self.msg_list:
            recipients = msg.get("recipients", [])
            for r in recipients:
                if r.get("name") == user_name:
                    sched = msg.get("schedule", {})
                    status = msg.get("status", STATUS_EDITING)
                    status_display = STATUS_EMOJI.get(status, status)
                    tree.insert("", tk.END, values=(
                        status_display, msg.get("name", ""), sched.get("repeat", ""), sched.get("time", "")
                    ))
                    break
        
        # 關閉按鈕
        tk.Button(dlg, text="關閉", command=dlg.destroy, bg="#64748b", fg="white", width=10).pack(pady=10)
    
    def filter_overview(self):
        keyword = self.search_var.get().lower()
        self.overview_tree.delete(*self.overview_tree.get_children())
        
        for msg in self.msg_list:
            name = msg.get("name", "")
            content = msg.get("content", "")
            recipients = msg.get("recipients", [])
            recip_names = " ".join([r.get("name", "") for r in recipients])
            
            if keyword and keyword not in name.lower() and keyword not in content.lower() and keyword not in recip_names.lower():
                continue
            
            sched = msg.get("schedule", {})
            status = msg.get("status", STATUS_EDITING)
            status_display = STATUS_EMOJI.get(status, status)
            recip_count = len(recipients)
            self.overview_tree.insert("", tk.END, values=(
                status_display, name, f"{recip_count} 人", sched.get("repeat", ""), sched.get("time", ""), sched.get("end", "")
            ), tags=(f"tag_{status}",))
    
    def goto_edit(self, event):
        sel = self.overview_tree.selection()
        if sel:
            name = self.overview_tree.item(sel[0])["values"][1]
            for i, msg in enumerate(self.msg_list):
                if msg.get("name") == name:
                    self.notebook.select(1)
                    self.edit_combo.current(i)
                    self.load_edit_form(i)
                    break
    
    # ==================== 編輯頁籤 ====================
    def create_edit_tab(self):
        tab = tk.Frame(self.notebook, bg="#1e293b")
        self.notebook.add(tab, text=" 編輯 ")
        
        top = tk.Frame(tab, bg="#1e293b")
        top.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(top, text="選擇訊息:", bg="#1e293b", fg="#e2e8f0").pack(side=tk.LEFT)
        self.edit_combo = ttk.Combobox(top, state="readonly", width=25)
        self.edit_combo.pack(side=tk.LEFT, padx=10)
        self.edit_combo.bind("<<ComboboxSelected>>", lambda e: self.load_edit_form(self.edit_combo.current()))
        
        # 狀態按鈕
        btn_frame = tk.Frame(top, bg="#1e293b")
        btn_frame.pack(side=tk.RIGHT)
        
        tk.Button(btn_frame, text="▶ 啟動", command=self.deploy_msg, bg="#10b981", fg="white", width=8).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="⏸ 停止", command=self.stop_msg, bg="#f59e0b", fg="white", width=8).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="複製", command=self.copy_message, bg="#8b5cf6", fg="white", width=6).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="刪除", command=self.del_message, bg="#ef4444", fg="white", width=6).pack(side=tk.LEFT, padx=2)
        
        # 狀態顯示
        self.edit_status_label = tk.Label(top, text="", bg="#1e293b", fg="white", font=("Microsoft JhengHei", 10, "bold"))
        self.edit_status_label.pack(side=tk.RIGHT, padx=10)
        
        # 編輯區
        edit_frame = tk.Frame(tab, bg="#1e293b")
        edit_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 左側
        left = tk.Frame(edit_frame, bg="#1e293b")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        row0 = tk.Frame(left, bg="#1e293b")
        row0.pack(fill=tk.X, pady=2)
        tk.Label(row0, text="名稱:", bg="#1e293b", fg="#e2e8f0", width=6).pack(side=tk.LEFT)
        self.edit_name = tk.Entry(row0, bg="#334155", fg="#e2e8f0", insertbackground="#e2e8f0", width=25)
        self.edit_name.pack(side=tk.LEFT, padx=5)
        self.edit_enabled = tk.BooleanVar()
        tk.Checkbutton(row0, text="啟用", variable=self.edit_enabled, bg="#1e293b", fg="#e2e8f0", selectcolor="#334155").pack(side=tk.LEFT, padx=10)
        
        tk.Label(left, text="訊息內容:", bg="#1e293b", fg="#e2e8f0").pack(anchor=tk.W)
        self.edit_content = tk.Text(left, bg="#334155", fg="#e2e8f0", insertbackground="#e2e8f0", height=10)
        self.edit_content.pack(fill=tk.BOTH, expand=True)
        
        # 右側
        right = tk.Frame(edit_frame, bg="#1e293b", width=350)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(10,0))
        right.pack_propagate(False)
        
        # 接收者總覽
        recip_frame = tk.LabelFrame(right, text="接收者總覽", bg="#334155", fg="#e2e8f0")
        recip_frame.pack(fill=tk.BOTH, expand=True)
        
        # 狀態圖例
        recip_legend = tk.Frame(recip_frame, bg="#334155")
        recip_legend.pack(fill=tk.X, padx=5, pady=(3,0))
        for status, color in RECIPIENT_COLORS.items():
            tk.Label(recip_legend, text=f" {status} ", bg=color, fg="white", font=("Microsoft JhengHei", 7)).pack(side=tk.LEFT, padx=2)
        
        recip_columns = ("status", "name", "channel", "target")
        self.edit_recip_tree = ttk.Treeview(recip_frame, columns=recip_columns, show="headings", height=4)
        self.edit_recip_tree.heading("status", text="狀態")
        self.edit_recip_tree.heading("name", text="姓名")
        self.edit_recip_tree.heading("channel", text="管道")
        self.edit_recip_tree.heading("target", text="ID/Email")
        self.edit_recip_tree.column("status", width=50)
        self.edit_recip_tree.column("name", width=55)
        self.edit_recip_tree.column("channel", width=45)
        self.edit_recip_tree.column("target", width=150)
        self.edit_recip_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 接收者操作按鈕
        recip_btn = tk.Frame(recip_frame, bg="#334155")
        recip_btn.pack(fill=tk.X, padx=5, pady=3)
        tk.Button(recip_btn, text="暫停", command=self.pause_recipient, bg="#f59e0b", fg="white", width=6).pack(side=tk.LEFT, padx=2)
        tk.Button(recip_btn, text="恢復", command=self.resume_recipient, bg="#10b981", fg="white", width=6).pack(side=tk.LEFT, padx=2)
        tk.Button(recip_btn, text="刪除", command=self.del_recipient, bg="#ef4444", fg="white", width=6).pack(side=tk.LEFT, padx=2)
        
        # 新增接收者
        add_r = tk.Frame(recip_frame, bg="#334155")
        add_r.pack(fill=tk.X, padx=5, pady=2)
        self.r_ch = tk.StringVar(value="line")
        tk.Radiobutton(add_r, text="LINE", variable=self.r_ch, value="line", bg="#334155", fg="#e2e8f0", selectcolor="#1e293b", font=("Microsoft JhengHei", 8)).pack(side=tk.LEFT)
        tk.Radiobutton(add_r, text="Email", variable=self.r_ch, value="email", bg="#334155", fg="#e2e8f0", selectcolor="#1e293b", font=("Microsoft JhengHei", 8)).pack(side=tk.LEFT)
        self.r_name = tk.Entry(add_r, bg="#1e293b", fg="#e2e8f0", insertbackground="#e2e8f0", width=8)
        self.r_name.pack(side=tk.LEFT, padx=2)
        self.r_name.insert(0, "姓名")
        self.r_target = tk.Entry(add_r, bg="#1e293b", fg="#e2e8f0", insertbackground="#e2e8f0", width=14)
        self.r_target.pack(side=tk.LEFT, padx=2)
        self.r_target.insert(0, "ID或Email")
        tk.Button(add_r, text="+", command=self.add_recipient, bg="#10b981", fg="white", width=3).pack(side=tk.LEFT, padx=2)
        
        # 排程
        sched_frame = tk.LabelFrame(right, text="排程設定", bg="#334155", fg="#e2e8f0")
        sched_frame.pack(fill=tk.X, pady=(5,0))
        
        s1 = tk.Frame(sched_frame, bg="#334155")
        s1.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(s1, text="開始:", bg="#334155", fg="#e2e8f0", width=4).pack(side=tk.LEFT)
        self.s_start_var = tk.StringVar(value="immediately")
        tk.Radiobutton(s1, text="立即", variable=self.s_start_var, value="immediately", bg="#334155", fg="#e2e8f0", selectcolor="#1e293b").pack(side=tk.LEFT)
        tk.Radiobutton(s1, text="指定", variable=self.s_start_var, value="custom", bg="#334155", fg="#e2e8f0", selectcolor="#1e293b").pack(side=tk.LEFT)
        self.s_start_ent = tk.Entry(s1, bg="#1e293b", fg="#e2e8f0", insertbackground="#e2e8f0", width=14)
        self.s_start_ent.pack(side=tk.LEFT, padx=3)
        
        s2 = tk.Frame(sched_frame, bg="#334155")
        s2.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(s2, text="週期:", bg="#334155", fg="#e2e8f0", width=4).pack(side=tk.LEFT)
        self.s_repeat_var = tk.StringVar(value="daily")
        for v, t in [("once","單次"),("hourly","每小時"),("daily","每日"),("weekly","每週"),("monthly","每月")]:
            tk.Radiobutton(s2, text=t, variable=self.s_repeat_var, value=v, bg="#334155", fg="#e2e8f0", selectcolor="#1e293b").pack(side=tk.LEFT, padx=2)
        
        s3 = tk.Frame(sched_frame, bg="#334155")
        s3.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(s3, text="時間:", bg="#334155", fg="#e2e8f0", width=4).pack(side=tk.LEFT)
        self.s_time_ent = tk.Entry(s3, bg="#1e293b", fg="#e2e8f0", insertbackground="#e2e8f0", width=8)
        self.s_time_ent.pack(side=tk.LEFT, padx=3)
        
        s4 = tk.Frame(sched_frame, bg="#334155")
        s4.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(s4, text="終止:", bg="#334155", fg="#e2e8f0", width=4).pack(side=tk.LEFT)
        self.s_end_var = tk.StringVar(value="never")
        tk.Radiobutton(s4, text="永不", variable=self.s_end_var, value="never", bg="#334155", fg="#e2e8f0", selectcolor="#1e293b").pack(side=tk.LEFT)
        tk.Radiobutton(s4, text="指定", variable=self.s_end_var, value="custom", bg="#334155", fg="#e2e8f0", selectcolor="#1e293b").pack(side=tk.LEFT)
        self.s_end_ent = tk.Entry(s4, bg="#1e293b", fg="#e2e8f0", insertbackground="#e2e8f0", width=14)
        self.s_end_ent.pack(side=tk.LEFT, padx=3)
        
        # 儲存
        tk.Button(tab, text="儲存此訊息", command=self.save_edit, bg="#3b82f6", fg="white",
                 font=("Microsoft JhengHei", 10, "bold")).pack(pady=5)
    
    def refresh_edit_combo(self):
        names = [m.get("name", f"訊息{i}") for i, m in enumerate(self.msg_list)]
        self.edit_combo["values"] = names
        if names:
            self.edit_combo.current(0)
    
    def load_edit_form(self, idx):
        if idx < 0 or idx >= len(self.msg_list):
            return
        msg = self.msg_list[idx]
        
        self.edit_name.delete(0, tk.END)
        self.edit_name.insert(0, msg.get("name", ""))
        self.edit_enabled.set(msg.get("enabled", True))
        
        self.edit_content.delete("1.0", tk.END)
        self.edit_content.insert(tk.END, msg.get("content", ""))
        
        self.edit_recip_tree.delete(*self.edit_recip_tree.get_children())
        for r in msg.get("recipients", []):
            status = r.get("status", RECIPIENT_ACTIVE)
            self.edit_recip_tree.insert("", tk.END, values=(status, r.get("name",""), r.get("channel",""), r.get("target","")))
        
        sched = msg.get("schedule", {})
        start = sched.get("start", "immediately")
        self.s_start_var.set("immediately" if start == "immediately" else "custom")
        self.s_start_ent.delete(0, tk.END)
        self.s_start_ent.insert(0, start if start != "immediately" else "2026-07-25 09:00")
        self.s_repeat_var.set(sched.get("repeat", "daily"))
        self.s_time_ent.delete(0, tk.END)
        self.s_time_ent.insert(0, sched.get("time", "18:00"))
        end = sched.get("end", "never")
        self.s_end_var.set("never" if end == "never" else "custom")
        self.s_end_ent.delete(0, tk.END)
        self.s_end_ent.insert(0, end if end != "never" else "2026-12-31")
        
        # 更新狀態顯示
        status = msg.get("status", STATUS_EDITING)
        status_display = STATUS_EMOJI.get(status, status)
        color = STATUS_COLORS.get(status, "#64748b")
        self.edit_status_label.config(text=status_display, fg=color)
    
    def add_recipient(self):
        ch = self.r_ch.get()
        name = self.r_name.get().strip()
        target = self.r_target.get().strip()
        if name and target:
            self.edit_recip_tree.insert("", tk.END, values=(RECIPIENT_ACTIVE, name, ch, target))
            self.r_name.delete(0, tk.END)
            self.r_target.delete(0, tk.END)
    
    def del_recipient(self):
        sel = self.edit_recip_tree.selection()
        if sel:
            self.edit_recip_tree.delete(sel[0])
    
    def pause_recipient(self):
        """暫停接收者"""
        sel = self.edit_recip_tree.selection()
        if sel:
            values = list(self.edit_recip_tree.item(sel[0])["values"])
            values[0] = RECIPIENT_PAUSED
            self.edit_recip_tree.item(sel[0], values=values)
    
    def resume_recipient(self):
        """恢復接收者"""
        sel = self.edit_recip_tree.selection()
        if sel:
            values = list(self.edit_recip_tree.item(sel[0])["values"])
            values[0] = RECIPIENT_ACTIVE
            self.edit_recip_tree.item(sel[0], values=values)
    
    def save_edit(self):
        idx = self.edit_combo.current()
        if idx < 0 or idx >= len(self.msg_list):
            return
        
        msg = self.msg_list[idx]
        msg["name"] = self.edit_name.get().strip()
        msg["enabled"] = self.edit_enabled.get()
        msg["content"] = self.edit_content.get("1.0", tk.END).strip()
        msg["recipients"] = []
        for item in self.edit_recip_tree.get_children():
            values = self.edit_recip_tree.item(item)["values"]
            msg["recipients"].append({"status": values[0], "name": values[1], "channel": values[2], "target": values[3]})
        msg["schedule"] = {
            "start": "immediately" if self.s_start_var.get() == "immediately" else self.s_start_ent.get(),
            "repeat": self.s_repeat_var.get(),
            "time": self.s_time_ent.get(),
            "end": "never" if self.s_end_var.get() == "never" else self.s_end_ent.get()
        }
        
        # 如果是編輯中，保存後變待命
        if msg.get("status") == STATUS_EDITING or msg.get("status") is None:
            msg["status"] = STATUS_STANDBY
        
        self.msg_list[idx] = msg
        self.refresh_all()
        messagebox.showinfo("成功", "訊息已儲存！")
    
    def deploy_msg(self):
        """啟動訊息"""
        idx = self.edit_combo.current()
        if idx < 0 or idx >= len(self.msg_list):
            return
        
        msg = self.msg_list[idx]
        if not msg.get("recipients"):
            messagebox.showwarning("警告", "請先新增接收者！")
            return
        
        msg["status"] = STATUS_RUNNING
        msg["enabled"] = True
        self.msg_list[idx] = msg
        self.refresh_all()
        self.edit_combo.current(idx)
        self.load_edit_form(idx)
        messagebox.showinfo("成功", f"訊息 [{msg.get('name')}] 已啟動運作！")
    
    def stop_msg(self):
        """停止訊息"""
        idx = self.edit_combo.current()
        if idx < 0 or idx >= len(self.msg_list):
            return
        
        msg = self.msg_list[idx]
        msg["status"] = STATUS_STOPPED
        self.msg_list[idx] = msg
        self.refresh_all()
        self.edit_combo.current(idx)
        self.load_edit_form(idx)
        messagebox.showinfo("成功", f"訊息 [{msg.get('name')}] 已停止！")
    
    def add_message(self):
        new_msg = {
            "id": f"msg_{len(self.msg_list)+1}",
            "name": f"新訊息 {len(self.msg_list)+1}",
            "enabled": True,
            "status": STATUS_EDITING,
            "content": "訊息內容...",
            "recipients": [],
            "schedule": {"start": "immediately", "repeat": "daily", "time": "18:00", "end": "never"}
        }
        self.msg_list.append(new_msg)
        self.refresh_all()
        self.edit_combo.current(len(self.msg_list) - 1)
        self.load_edit_form(len(self.msg_list) - 1)
    
    def copy_message(self):
        idx = self.edit_combo.current()
        if idx >= 0 and idx < len(self.msg_list):
            import copy
            new_msg = copy.deepcopy(self.msg_list[idx])
            new_msg["name"] = new_msg["name"] + " (複製)"
            new_msg["status"] = STATUS_EDITING
            self.msg_list.append(new_msg)
            self.refresh_all()
    
    def del_message(self):
        idx = self.edit_combo.current()
        if idx >= 0 and idx < len(self.msg_list):
            if messagebox.askyesno("確認", "確定刪除此訊息？"):
                self.msg_list.pop(idx)
                self.refresh_all()
    
    # ==================== 設定頁籤 ====================
    def create_settings_tab(self):
        tab = tk.Frame(self.notebook, bg="#1e293b")
        self.notebook.add(tab, text=" 設定 ")
        
        line_frame = tk.LabelFrame(tab, text="LINE 設定", bg="#334155", fg="#e2e8f0")
        line_frame.pack(fill=tk.X, padx=10, pady=5)
        row = tk.Frame(line_frame, bg="#334155")
        row.pack(fill=tk.X, padx=10, pady=5)
        tk.Checkbutton(row, text="啟用 LINE", variable=self.line_enabled, bg="#334155", fg="#e2e8f0", selectcolor="#1e293b").pack(side=tk.LEFT)
        tk.Label(row, text="Token:", bg="#334155", fg="#e2e8f0").pack(side=tk.LEFT, padx=(20,5))
        self.line_token = tk.Entry(row, bg="#1e293b", fg="#e2e8f0", insertbackground="#e2e8f0", width=50, show="*")
        self.line_token.pack(side=tk.LEFT)
        
        email_frame = tk.LabelFrame(tab, text="Email 設定", bg="#334155", fg="#e2e8f0")
        email_frame.pack(fill=tk.X, padx=10, pady=5)
        row1 = tk.Frame(email_frame, bg="#334155")
        row1.pack(fill=tk.X, padx=10, pady=3)
        tk.Checkbutton(row1, text="啟用 Email", variable=self.email_enabled, bg="#334155", fg="#e2e8f0", selectcolor="#1e293b").pack(side=tk.LEFT)
        tk.Label(row1, text="發送者:", bg="#334155", fg="#e2e8f0").pack(side=tk.LEFT, padx=(20,5))
        self.smtp_email = tk.Entry(row1, bg="#1e293b", fg="#e2e8f0", insertbackground="#e2e8f0", width=25)
        self.smtp_email.pack(side=tk.LEFT)
        tk.Label(row1, text="密碼:", bg="#334155", fg="#e2e8f0").pack(side=tk.LEFT, padx=(10,5))
        self.smtp_pass = tk.Entry(row1, bg="#1e293b", fg="#e2e8f0", insertbackground="#e2e8f0", width=15, show="*")
        self.smtp_pass.pack(side=tk.LEFT)
        
        ch = self.config.get("channels", {})
        self.line_enabled.set(ch.get("line", {}).get("enabled", False))
        self.line_token.insert(0, ch.get("line", {}).get("channel_access_token", ""))
        self.email_enabled.set(ch.get("email", {}).get("enabled", False))
        self.smtp_email.insert(0, ch.get("email", {}).get("sender_email", ""))
        self.smtp_pass.insert(0, ch.get("email", {}).get("sender_password", ""))
    
    def refresh_all(self):
        self.refresh_overview()
        self.refresh_edit_combo()
        if self.msg_list:
            self.load_edit_form(0)
    
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = NotificationManager()
    app.run()
