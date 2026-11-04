#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
oc_widget.py — OpenCode 額度常駐小窗（零 token 成本）
====================================================
一個小小的置頂視窗，每 60 秒自己抓一次數字：

  Go   ：GET https://opencode.ai/inference/go/v1/usage（官方值，純 HTTP）
  免費 ：本機 opencode.db 估算 5h 視窗用量

**完全不經過模型**，不送任何 prompt、不佔 200 次/5h 配額、不花錢。
關掉視窗就停止。

用法:
  pythonw oc_widget.py            # 背景常駐（不開 console）
  python  oc_widget.py            # 開 console 看錯誤
  python  oc_widget.py --check    # 只印一次資料後結束（不開視窗）
  python  oc_widget.py --interval 30
"""
import argparse
import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

# 可攜：從本檔所在目錄載入 oc_usage，任何機器／任何路徑都能跑
sys.path.insert(0, str(Path(__file__).resolve().parent))
from oc_usage import (find_db, read_go_key, fetch_go_usage, counts, is_free,  # noqa: E402
                      last_hits, fmt_reset, fmt_local)

import datetime as dt  # noqa: E402
import sqlite3  # noqa: E402

FREE_LIMIT = 200
FREE_WINDOW_H = 5


def collect():
    db = find_db()
    data = {"free": None, "go": None, "db": str(db) if db else None}
    if db:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        now_ts = int(dt.datetime.now(dt.timezone.utc).timestamp())
        win = counts(con, now_ts - FREE_WINDOW_H * 3600, now_ts)
        used = sum(c for p, m, c in win if is_free(p, m))
        data["free"] = {
            "used": used,
            "limit": FREE_LIMIT,
            "percent": min(100.0, used / FREE_LIMIT * 100),
            "hits": [fmt_local(h) for h in last_hits(db.parent / "log" / "opencode.log", 1)],
        }
    data["go"] = fetch_go_usage(read_go_key(db))
    return data


class Widget:
    BG = "#12141a"
    FG = "#e6e8ee"
    DIM = "#8b90a0"
    OK = "#5ad67d"
    WARN = "#e8b93c"
    BAD = "#ef5b5b"

    def __init__(self, root, interval):
        self.root = root
        self.interval = interval
        root.title("OC 額度")
        root.configure(bg=self.BG)
        root.attributes("-topmost", True)
        root.overrideredirect(False)
        root.resizable(False, False)

        f_big = tkfont.Font(family="Consolas", size=13, weight="bold")
        f_small = tkfont.Font(family="Consolas", size=9)

        self.free_lbl = tk.Label(root, font=f_big, bg=self.BG, fg=self.FG, anchor="w", padx=10, pady=2)
        self.free_lbl.pack(fill="x")
        self.go_lbl = tk.Label(root, font=f_big, bg=self.BG, fg=self.FG, anchor="w", padx=10, pady=2)
        self.go_lbl.pack(fill="x")
        self.detail_lbl = tk.Label(root, font=f_small, bg=self.BG, fg=self.DIM, anchor="w",
                                   padx=10, pady=2, justify="left")
        self.detail_lbl.pack(fill="x")

        bar = tk.Frame(root, bg=self.BG)
        bar.pack(fill="x", padx=8, pady=(2, 8))
        tk.Button(bar, text="重抓", command=self.refresh, font=f_small,
                  bg="#232733", fg=self.FG, relief="flat", padx=8).pack(side="left")
        tk.Button(bar, text="關閉", command=root.destroy, font=f_small,
                  bg="#232733", fg=self.FG, relief="flat", padx=8).pack(side="right")

        # 右上角放置，避免擋到工作區
        root.update_idletasks()
        sw = root.winfo_screenwidth()
        root.geometry(f"+{sw - 330}+60")

        self.refresh()
        self.tick()

    def color(self, pct):
        return self.BAD if pct >= 100 else self.WARN if pct >= 80 else self.OK

    def refresh(self):
        d = collect()
        f = d.get("free")
        if f:
            self.free_lbl.config(
                text=f"免費 {f['used']}/{f['limit']}  {f['percent']:.0f}%",
                fg=self.color(f["percent"]),
            )
        else:
            self.free_lbl.config(text="免費 —（找不到 DB）", fg=self.DIM)

        g = d.get("go")
        if g:
            seg = []
            for label, key in (("5h", "rolling"), ("週", "weekly"), ("月", "monthly")):
                v = g.get(key) or {}
                pct = v.get("percent", 0)
                seg.append(f"{label}{pct:.0f}%")
            worst = max((g.get(k) or {}).get("percent", 0) for k in ("rolling", "weekly", "monthly"))
            self.go_lbl.config(text="Go " + " ".join(seg), fg=self.color(worst))
            m = g.get("monthly") or {}
            extra = ""
            if (m.get("status") or "ok") != "ok":
                extra = f"\n月額度用盡 → {fmt_reset(m.get('resetsAt'))} 重置"
            self.detail_lbl.config(
                text=f"5h 重置 {fmt_reset((g.get('rolling') or {}).get('resetsAt'))}"
                     f" · 週 {fmt_reset((g.get('weekly') or {}).get('resetsAt'))}{extra}"
            )
        else:
            self.go_lbl.config(text="Go —（無 key 或連線失敗）", fg=self.DIM)
            self.detail_lbl.config(text="")

    def tick(self):
        self.root.after(int(self.interval * 1000), self._loop)

    def _loop(self):
        try:
            self.refresh()
        except Exception:
            pass
        self.tick()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=60, help="更新秒數（預設 60）")
    ap.add_argument("--check", action="store_true", help="只印一次資料")
    args = ap.parse_args()

    if args.check:
        print(json.dumps(collect(), ensure_ascii=False, indent=2))
        return

    root = tk.Tk()
    Widget(root, args.interval)
    root.mainloop()


if __name__ == "__main__":
    main()
