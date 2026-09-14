"""
胚騰 AI Agent - 排程狀態監控
顯示排程執行器的運作狀態
"""
import tkinter as tk
from tkinter import ttk, scrolledtext
import yaml
import os
import sys
import subprocess
import threading
import time
from datetime import datetime

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")


class SchedulerMonitor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("胚騰 AI Agent - 排程監控")
        self.root.geometry("600x400")
        self.root.configure(bg="#0f172a")
        
        self.running = False
        self.create_widgets()
        self.check_scheduler()
        self.refresh_status()
    
    def create_widgets(self):
        main = tk.Frame(self.root, bg="#0f172a")
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        tk.Label(main, text="排程執行器狀態", bg="#0f172a", fg="#60a5fa",
                font=("Microsoft JhengHei", 14, "bold")).pack(pady=(0, 10))
        
        # 狀態顯示
        self.status_frame = tk.LabelFrame(main, text="執行器狀態", bg="#334155", fg="#e2e8f0")
        self.status_frame.pack(fill=tk.X, pady=5)
        
        self.status_label = tk.Label(self.status_frame, text="檢查中...", bg="#334155", fg="#e2e8f0",
                                    font=("Microsoft JhengHei", 12))
        self.status_label.pack(padx=10, pady=10)
        
        # 控制按鈕
        btn_frame = tk.Frame(main, bg="#0f172a")
        btn_frame.pack(fill=tk.X, pady=5)
        
        self.start_btn = tk.Button(btn_frame, text="啟動執行器", command=self.start_scheduler,
                                  bg="#10b981", fg="white", width=15)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = tk.Button(btn_frame, text="停止執行器", command=self.stop_scheduler,
                                 bg="#ef4444", fg="white", width=15, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="重新整理", command=self.refresh_status,
                 bg="#64748b", fg="white", width=10).pack(side=tk.RIGHT, padx=5)
        
        # 訊息排程
        sched_frame = tk.LabelFrame(main, text="訊息排程", bg="#334155", fg="#e2e8f0")
        sched_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.sched_tree = ttk.Treeview(sched_frame, columns=("name", "time", "status"), show="headings", height=6)
        self.sched_tree.heading("name", text="訊息名稱")
        self.sched_tree.heading("time", text="發送時間")
        self.sched_tree.heading("status", text="狀態")
        self.sched_tree.column("name", width=200)
        self.sched_tree.column("time", width=100)
        self.sched_tree.column("status", width=100)
        self.sched_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 日誌
        log_frame = tk.LabelFrame(main, text="執行日誌", bg="#334155", fg="#e2e8f0")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, bg="#1e293b", fg="#e2e8f0",
                                                 font=("Consolas", 9), height=6)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def check_scheduler(self):
        """檢查排程執行器是否在運行"""
        try:
            result = subprocess.run(
                ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
                capture_output=True, text=True
            )
            self.running = "message_scheduler" in result.stdout
        except:
            self.running = False
        
        if self.running:
            self.status_label.config(text="🟢 執行器運作中", fg="#10b981")
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
        else:
            self.status_label.config(text="⚪ 執行器未啟動", fg="#64748b")
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
    
    def refresh_status(self):
        """重新整理狀態"""
        self.check_scheduler()
        self.load_messages()
        self.log("重新整理完成")
    
    def load_messages(self):
        """載入訊息排程"""
        self.sched_tree.delete(*self.sched_tree.get_children())
        
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            
            for msg in config.get("messages", []):
                status = msg.get("status", "編輯中")
                sched = msg.get("schedule", {})
                time_str = sched.get("time", "")
                repeat = sched.get("repeat", "")
                
                status_display = {
                    "編輯中": "📝 編輯中",
                    "待命": "🔵 待命",
                    "運作中": "🟢 運作中",
                    "已停止": "⚪ 已停止"
                }.get(status, status)
                
                self.sched_tree.insert("", tk.END, values=(
                    msg.get("name", ""),
                    f"{time_str} ({repeat})",
                    status_display
                ))
        except Exception as e:
            self.log(f"載入失敗: {e}")
    
    def start_scheduler(self):
        """啟動排程執行器"""
        try:
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "message_scheduler.py")
            subprocess.Popen([sys.executable, script_path], 
                           creationflags=subprocess.CREATE_NO_WINDOW,
                           cwd=os.path.dirname(os.path.abspath(__file__)))
            self.log("執行器已啟動")
            time.sleep(2)
            self.check_scheduler()
        except Exception as e:
            self.log(f"啟動失敗: {e}")
    
    def stop_scheduler(self):
        """停止排程執行器"""
        try:
            subprocess.run(["taskkill", "/F", "/IM", "python.exe"], capture_output=True)
            self.log("執行器已停止")
            time.sleep(1)
            self.check_scheduler()
        except Exception as e:
            self.log(f"停止失敗: {e}")
    
    def log(self, msg):
        """記錄日誌"""
        time_str = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{time_str}] {msg}\n")
        self.log_text.see(tk.END)
    
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = SchedulerMonitor()
    app.run()
