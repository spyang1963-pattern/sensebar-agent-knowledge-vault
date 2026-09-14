# watchlist_manager.py
"""
自選股管理 + 警報歷史介面 v3
用 GUI 管理自選股清單 & 查看警報歷史
"""
import os
import sys
import json
import yaml
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class WatchlistManager:
    """自選股管理 + 警報歷史視窗"""
    
    def __init__(self):
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
        self.history_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "alert_history.json")
        self.config = self._load_config()
        self.watchlist = self.config.get("realtime_monitor", {}).get("watchlist", [])
        self.futures_watchlist = self.config.get("realtime_monitor", {}).get("futures_watchlist", [])
        self.alert_history = self._load_history()
        self.selected_index = None
        
        # 建立主視窗
        self.root = tk.Tk()
        self.root.title("胚騰 AI 股票管理")
        self.root.geometry("750x600")
        self.root.configure(bg="#1e293b")
        
        self._setup_ui()
        self._refresh_watchlist()
    
    def _load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
    
    def _load_history(self) -> List[Dict[str, Any]]:
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    
    def _save_config(self):
        try:
            if "realtime_monitor" not in self.config:
                self.config["realtime_monitor"] = {}
            self.config["realtime_monitor"]["watchlist"] = self.watchlist
            self.config["realtime_monitor"]["futures_watchlist"] = self.futures_watchlist
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
            messagebox.showinfo("成功", "設定已儲存！")
        except Exception as e:
            messagebox.showerror("錯誤", f"儲存失敗: {e}")
    
    def _setup_ui(self):
        # 標題
        title_frame = tk.Frame(self.root, bg="#0f172a", height=50)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        tk.Label(title_frame, text="胚騰 AI 股票管理", 
                font=("Microsoft JhengHei", 14, "bold"),
                fg="#60a5fa", bg="#0f172a").pack(pady=12)
        
        # Tab 切換
        tab_frame = tk.Frame(self.root, bg="#1e293b")
        tab_frame.pack(fill=tk.X, padx=20, pady=(10, 0))
        
        self.tab_watchlist = tk.Button(tab_frame, text="自選股管理", 
                                       command=self._show_watchlist,
                                       bg="#3b82f6", fg="white", width=15)
        self.tab_watchlist.pack(side=tk.LEFT, padx=(0, 5))
        
        self.tab_history = tk.Button(tab_frame, text="警報歷史", 
                                     command=self._show_history,
                                     bg="#64748b", fg="white", width=15)
        self.tab_history.pack(side=tk.LEFT)
        
        self.tab_futures = tk.Button(tab_frame, text="期貨管理", 
                                     command=self._show_futures,
                                     bg="#64748b", fg="white", width=15)
        self.tab_futures.pack(side=tk.LEFT, padx=(5, 0))
        
        # 內容區
        self.content_frame = tk.Frame(self.root, bg="#1e293b")
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # 預設顯示自選股
        self._show_watchlist()
    
    def _clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
    
    # ==================== 自選股管理 ====================
    def _show_watchlist(self):
        self._clear_content()
        self.tab_watchlist.configure(bg="#3b82f6")
        self.tab_history.configure(bg="#64748b")
        self.tab_futures.configure(bg="#64748b")
        
        # 左右分割
        main_frame = tk.Frame(self.content_frame, bg="#1e293b")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左側：清單
        left_frame = tk.Frame(main_frame, bg="#1e293b")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tk.Label(left_frame, text="自選股清單", 
                font=("Microsoft JhengHei", 11, "bold"),
                fg="#e2e8f0", bg="#1e293b").pack(anchor=tk.W)
        
        list_frame = tk.Frame(left_frame, bg="#0f172a")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        columns = ("code", "name", "price_drop", "volume_surge")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=12)
        self.tree.heading("code", text="代號")
        self.tree.heading("name", text="名稱")
        self.tree.heading("price_drop", text="跌幅%")
        self.tree.heading("volume_surge", text="量能倍")
        self.tree.column("code", width=70, anchor=tk.CENTER)
        self.tree.column("name", width=100, anchor=tk.W)
        self.tree.column("price_drop", width=80, anchor=tk.CENTER)
        self.tree.column("volume_surge", width=80, anchor=tk.CENTER)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        
        # 載入自選股清單
        self._refresh_watchlist()
        
        # 右側：編輯區
        right_frame = tk.Frame(main_frame, bg="#1e293b", width=220)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(15, 0))
        
        tk.Label(right_frame, text="新增/編輯", 
                font=("Microsoft JhengHei", 11, "bold"),
                fg="#e2e8f0", bg="#1e293b").pack(anchor=tk.W)
        
        tk.Label(right_frame, text="股票代號:", fg="#94a3b8", bg="#1e293b").pack(anchor=tk.W, pady=(8, 0))
        self.entry_code = tk.Entry(right_frame, width=18)
        self.entry_code.pack(fill=tk.X)
        
        tk.Label(right_frame, text="股票名稱:", fg="#94a3b8", bg="#1e293b").pack(anchor=tk.W, pady=(8, 0))
        self.entry_name = tk.Entry(right_frame, width=18)
        self.entry_name.pack(fill=tk.X)
        
        tk.Label(right_frame, text="跌幅警報%:", fg="#94a3b8", bg="#1e293b").pack(anchor=tk.W, pady=(8, 0))
        self.entry_price_drop = tk.Entry(right_frame, width=18)
        self.entry_price_drop.insert(0, "-3.0")
        self.entry_price_drop.pack(fill=tk.X)
        
        tk.Label(right_frame, text="量能倍數:", fg="#94a3b8", bg="#1e293b").pack(anchor=tk.W, pady=(8, 0))
        self.entry_volume_surge = tk.Entry(right_frame, width=18)
        self.entry_volume_surge.insert(0, "2.0")
        self.entry_volume_surge.pack(fill=tk.X)
        
        btn_frame = tk.Frame(right_frame, bg="#1e293b")
        btn_frame.pack(fill=tk.X, pady=(15, 0))
        
        tk.Button(btn_frame, text="新增", command=self._add_stock,
                 bg="#10b981", fg="white", width=6).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(btn_frame, text="編輯", command=self._edit_stock,
                 bg="#3b82f6", fg="white", width=6).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(btn_frame, text="刪除", command=self._delete_stock,
                 bg="#ef4444", fg="white", width=6).pack(side=tk.LEFT)
        
        tk.Button(right_frame, text="儲存設定", command=self._save_config,
                 bg="#10b981", fg="white", font=("Microsoft JhengHei", 9, "bold"),
                 width=18).pack(pady=(15, 0))
    
    def _on_select(self, event):
        selection = self.tree.selection()
        if not selection:
            return
        item = self.tree.item(selection[0])
        values = item["values"]
        self.entry_code.delete(0, tk.END)
        self.entry_code.insert(0, values[0])
        self.entry_name.delete(0, tk.END)
        self.entry_name.insert(0, values[1])
        self.entry_price_drop.delete(0, tk.END)
        self.entry_price_drop.insert(0, values[2])
        self.entry_volume_surge.delete(0, tk.END)
        self.entry_volume_surge.insert(0, values[3])
    
    def _on_select_futures(self, event):
        selection = self.futures_tree.selection()
        if not selection:
            return
        item = self.futures_tree.item(selection[0])
        values = item["values"]
        self.entry_fcode.delete(0, tk.END)
        self.entry_fcode.insert(0, values[0])
        self.entry_fname.delete(0, tk.END)
        self.entry_fname.insert(0, values[1])
        self.entry_fdrop.delete(0, tk.END)
        drop_val = str(values[2]).replace('%', '')
        self.entry_fdrop.insert(0, drop_val)
    
    def _refresh_watchlist(self):
        if hasattr(self, 'tree'):
            for item in self.tree.get_children():
                self.tree.delete(item)
            for stock in self.watchlist:
                code = stock.get("code", "")
                name = stock.get("name", "")
                thresholds = stock.get("thresholds", {})
                self.tree.insert("", tk.END, values=(
                    code, name, 
                    thresholds.get("price_drop_pct", -3.0),
                    thresholds.get("volume_surge_ratio", 2.0)
                ))
    
    def _add_stock(self):
        code = self.entry_code.get().strip()
        name = self.entry_name.get().strip()
        if not code:
            messagebox.showwarning("警告", "請輸入股票代號！")
            return
        for stock in self.watchlist:
            if stock.get("code") == code:
                messagebox.showwarning("警告", f"股票 {code} 已存在！")
                return
        try:
            price_drop = float(self.entry_price_drop.get())
            volume_surge = float(self.entry_volume_surge.get())
        except ValueError:
            messagebox.showwarning("警告", "請輸入有效的數字！")
            return
        self.watchlist.append({
            "code": code, "name": name or code,
            "thresholds": {"price_drop_pct": price_drop, "volume_surge_ratio": volume_surge}
        })
        self._refresh_watchlist()
        messagebox.showinfo("成功", f"已新增 {code}")
    
    def _edit_stock(self):
        code = self.entry_code.get().strip()
        if not code:
            messagebox.showwarning("警告", "請先點選要編輯的股票！")
            return
        name = self.entry_name.get().strip()
        try:
            price_drop = float(self.entry_price_drop.get())
            volume_surge = float(self.entry_volume_surge.get())
        except ValueError:
            messagebox.showwarning("警告", "請輸入有效的數字！")
            return
        for i, stock in enumerate(self.watchlist):
            if stock.get("code") == code:
                self.watchlist[i] = {
                    "code": code, "name": name or code,
                    "thresholds": {"price_drop_pct": price_drop, "volume_surge_ratio": volume_surge}
                }
                self._refresh_watchlist()
                messagebox.showinfo("成功", f"已更新 {code}")
                return
        messagebox.showwarning("警告", f"找不到 {code}")
    
    def _delete_stock(self):
        code = self.entry_code.get().strip()
        if not code:
            messagebox.showwarning("警告", "請先點選要刪除的股票！")
            return
        name = self.entry_name.get().strip()
        if messagebox.askyesno("確認", f"確定要刪除 {code} {name or code}？"):
            self.watchlist = [s for s in self.watchlist if s.get("code") != code]
            self._refresh_watchlist()
            messagebox.showinfo("成功", f"已刪除 {code}")
            self.entry_code.delete(0, tk.END)
            self.entry_name.delete(0, tk.END)
    
    # ==================== 警報歷史 ====================
    def _show_history(self):
        self._clear_content()
        self.tab_watchlist.configure(bg="#64748b")
        self.tab_history.configure(bg="#3b82f6")
        self.tab_futures.configure(bg="#64748b")
        
        # 重新載入歷史
        self.alert_history = self._load_history()
        
        # 標題列
        header_frame = tk.Frame(self.content_frame, bg="#1e293b")
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(header_frame, text=f"共 {len(self.alert_history)} 筆警報紀錄", 
                font=("Microsoft JhengHei", 11),
                fg="#94a3b8", bg="#1e293b").pack(side=tk.LEFT)
        
        tk.Button(header_frame, text="重新整理", command=self._show_history,
                 bg="#64748b", fg="white", width=10).pack(side=tk.RIGHT)
        
        # 清單
        list_frame = tk.Frame(self.content_frame, bg="#0f172a")
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ("time", "code", "name", "type", "level", "price", "change", "message")
        self.history_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
        
        self.history_tree.heading("time", text="時間")
        self.history_tree.heading("code", text="代號")
        self.history_tree.heading("name", text="名稱")
        self.history_tree.heading("type", text="類型")
        self.history_tree.heading("level", text="等級")
        self.history_tree.heading("price", text="現價")
        self.history_tree.heading("change", text="漲跌%")
        self.history_tree.heading("message", text="訊息")
        
        self.history_tree.column("time", width=130, anchor=tk.CENTER)
        self.history_tree.column("code", width=60, anchor=tk.CENTER)
        self.history_tree.column("name", width=80, anchor=tk.W)
        self.history_tree.column("type", width=80, anchor=tk.CENTER)
        self.history_tree.column("level", width=50, anchor=tk.CENTER)
        self.history_tree.column("price", width=70, anchor=tk.CENTER)
        self.history_tree.column("change", width=70, anchor=tk.CENTER)
        self.history_tree.column("message", width=200, anchor=tk.W)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 填入資料（最新在前）
        for alert in reversed(self.alert_history):
            time_str = alert.get("time", "")
            code = alert.get("code", "")
            name = alert.get("name", "")
            alert_type = alert.get("alert_type", "")
            level = alert.get("alert_level", "")
            price = alert.get("price", 0)
            change = alert.get("change_pct", 0)
            message = alert.get("message", "")
            
            # 類型中文
            type_map = {"price_drop": "跌幅", "price_rise": "漲幅", "gap": "跳空", 
                       "volume_surge": "巨量", "long_upper_shadow": "上影線", "long_lower_shadow": "下影線"}
            type_cn = type_map.get(alert_type, alert_type)
            
            # 等級顏色標記
            level_map = {"danger": "危險", "warning": "注意", "info": "資訊"}
            level_cn = level_map.get(level, level)
            
            # 漲跌格式
            if isinstance(change, (int, float)) and change != 0:
                change_str = f"{change:+.2f}%"
            else:
                change_str = "-"
            
            # 價格格式
            if isinstance(price, (int, float)) and price > 0:
                price_str = f"{price:,.1f}"
            else:
                price_str = "-"
            
            self.history_tree.insert("", tk.END, values=(
                time_str, code, name, type_cn, level_cn, 
                price_str, change_str, message[:30]
            ))
    
    # ==================== 期貨管理 ====================
    def _show_futures(self):
        self._clear_content()
        self.tab_watchlist.configure(bg="#64748b")
        self.tab_history.configure(bg="#64748b")
        self.tab_futures.configure(bg="#3b82f6")
        
        # 左右分割
        main_frame = tk.Frame(self.content_frame, bg="#1e293b")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左側：清單
        left_frame = tk.Frame(main_frame, bg="#1e293b")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tk.Label(left_frame, text="期貨自選清單", 
                font=("Microsoft JhengHei", 11, "bold"),
                fg="#e2e8f0", bg="#1e293b").pack(anchor=tk.W)
        
        list_frame = tk.Frame(left_frame, bg="#0f172a")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        columns = ("code", "name", "price_drop")
        self.futures_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=12)
        self.futures_tree.heading("code", text="代碼")
        self.futures_tree.heading("name", text="名稱")
        self.futures_tree.heading("price_drop", text="跌幅%")
        self.futures_tree.column("code", width=100, anchor=tk.CENTER)
        self.futures_tree.column("name", width=120, anchor=tk.W)
        self.futures_tree.column("price_drop", width=100, anchor=tk.CENTER)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.futures_tree.yview)
        self.futures_tree.configure(yscrollcommand=scrollbar.set)
        self.futures_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.futures_tree.bind("<<TreeviewSelect>>", self._on_select_futures)
        
        # 右側：編輯區
        right_frame = tk.Frame(main_frame, bg="#1e293b", width=220)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(15, 0))
        
        tk.Label(right_frame, text="新增/編輯", 
                font=("Microsoft JhengHei", 11, "bold"),
                fg="#e2e8f0", bg="#1e293b").pack(anchor=tk.W)
        
        tk.Label(right_frame, text="期貨代碼:", fg="#94a3b8", bg="#1e293b").pack(anchor=tk.W, pady=(8, 0))
        self.entry_fcode = tk.Entry(right_frame, width=18)
        self.entry_fcode.pack(fill=tk.X)
        
        tk.Label(right_frame, text="期貨名稱:", fg="#94a3b8", bg="#1e293b").pack(anchor=tk.W, pady=(8, 0))
        self.entry_fname = tk.Entry(right_frame, width=18)
        self.entry_fname.pack(fill=tk.X)
        
        tk.Label(right_frame, text="跌幅警戒%:", fg="#94a3b8", bg="#1e293b").pack(anchor=tk.W, pady=(8, 0))
        self.entry_fdrop = tk.Entry(right_frame, width=18)
        self.entry_fdrop.insert(0, "-1.0")
        self.entry_fdrop.pack(fill=tk.X)
        
        btn_frame = tk.Frame(right_frame, bg="#1e293b")
        btn_frame.pack(fill=tk.X, pady=(15, 0))
        
        tk.Button(btn_frame, text="新增", command=self._add_futures,
                 bg="#22c55e", fg="white", width=8).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(btn_frame, text="更新", command=self._update_futures,
                 bg="#f59e0b", fg="white", width=8).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(btn_frame, text="刪除", command=self._delete_futures,
                 bg="#ef4444", fg="white", width=8).pack(side=tk.LEFT)
        
        tk.Button(right_frame, text="儲存設定", command=self._save_config,
                 bg="#3b82f6", fg="white", width=20).pack(pady=(20, 0))
        
        # 載入期貨清單
        self._refresh_futures()
    
    def _refresh_futures(self):
        for item in self.futures_tree.get_children():
            self.futures_tree.delete(item)
        for f in self.futures_watchlist:
            code = f.get("code", "")
            name = f.get("name", "")
            drop = f.get("thresholds", {}).get("price_drop_pct", -1.0)
            self.futures_tree.insert("", tk.END, values=(code, name, f"{drop}%"))
    
    def _add_futures(self):
        code = self.entry_fcode.get().strip()
        name = self.entry_fname.get().strip()
        drop = self.entry_fdrop.get().strip()
        
        if not code:
            messagebox.showwarning("警告", "請輸入期貨代碼")
            return
        
        for f in self.futures_watchlist:
            if f.get("code") == code:
                messagebox.showwarning("警告", f"{code} 已存在")
                return
        
        try:
            drop_val = float(drop)
        except:
            drop_val = -1.0
        
        self.futures_watchlist.append({
            "code": code,
            "name": name if name else code,
            "thresholds": {"price_drop_pct": drop_val}
        })
        
        self._refresh_futures()
        self.entry_fcode.delete(0, tk.END)
        self.entry_fname.delete(0, tk.END)
        self.entry_fdrop.delete(0, tk.END)
        self.entry_fdrop.insert(0, "-1.0")
        messagebox.showinfo("成功", f"已新增 {code}")
    
    def _update_futures(self):
        code = self.entry_fcode.get().strip()
        name = self.entry_fname.get().strip()
        drop = self.entry_fdrop.get().strip()
        
        if not code:
            messagebox.showwarning("警告", "請選擇要更新的期貨")
            return
        
        try:
            drop_val = float(drop)
        except:
            drop_val = -1.0
        
        for f in self.futures_watchlist:
            if f.get("code") == code:
                f["name"] = name if name else code
                f["thresholds"] = {"price_drop_pct": drop_val}
                self._refresh_futures()
                messagebox.showinfo("成功", f"已更新 {code}")
                return
        
        messagebox.showwarning("警告", f"找不到 {code}")
    
    def _delete_futures(self):
        code = self.entry_fcode.get().strip()
        
        if not code:
            messagebox.showwarning("警告", "請選擇要刪除的期貨")
            return
        
        for i, f in enumerate(self.futures_watchlist):
            if f.get("code") == code:
                self.futures_watchlist.pop(i)
                self._refresh_futures()
                self.entry_fcode.delete(0, tk.END)
                self.entry_fname.delete(0, tk.END)
                self.entry_fdrop.delete(0, tk.END)
                self.entry_fdrop.insert(0, "-1.0")
                messagebox.showinfo("成功", f"已刪除 {code}")
                return
        
        messagebox.showwarning("警告", f"找不到 {code}")
    
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = WatchlistManager()
    app.run()
