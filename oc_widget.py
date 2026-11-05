#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
oc_widget.py — OpenCode 額度常駐小窗（零 token 成本）
====================================================
一個小小的置頂視窗，每 60 秒自己抓一次數字：

  Go   ：GET https://opencode.ai/inference/go/v1/usage（官方值，純 HTTP）
  免費 ：本機 opencode.db 估算「免費池日」累計（08:55 換日）+ 5h 參考值

**完全不經過模型**，不送任何 prompt、不佔任何額度、不花錢。
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
                      last_hits, fmt_reset, fmt_local, free_day_start, free_used_before)

import datetime as dt  # noqa: E402
import sqlite3  # noqa: E402

FREE_WINDOW_H = 5
# 兩道閘門並存（2026-11-05 實測，見 AGENTS.md）：
#   ① 5h 滾動窗 ~200 次（改制後沒有任何一次成功的 5h 窗 > 233；三次撞牆都在 205~232）
#   ② 日/帳號層級（11-04 撞牆時 5h 只有 153、日累計 337；11-02 撞牆時 5h 只有 1、24h 234）
FREE_5H_LIMIT = 200
WIN_WARN_AT = int(FREE_5H_LIMIT * 0.60)   # 5h 60% = 120 → 黃
WIN_BAD_AT = int(FREE_5H_LIMIT * 0.80)    # 5h 80% = 160 → 紅
# 日累計沒有真分母，也不顯示百分比。警戒線是動態的：
#   上次撞牆當下的日累計 × 0.9（例：上次撞在 337 → 303 起轉紅）
# 沒有撞牆紀錄就維持綠色（不知道上限，不亂嚇人）。
DAY_ALERT_RATIO = 0.9
FREE_WARN_AT = 150                        # 舊名保留（CLI 說明用）
FREE_BAD_AT = 320                         # 舊名保留（無撞牆紀錄時的參考值）


def collect():
    db = find_db()
    data = {"free": None, "go": None, "db": str(db) if db else None}
    if db:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        now = dt.datetime.now().astimezone()
        now_ts = int(now.timestamp())
        day_start = free_day_start(now)
        uday = counts(con, int(day_start.timestamp()), now_ts)
        used = sum(c for p, m, c in uday if is_free(p, m))
        win = counts(con, now_ts - FREE_WINDOW_H * 3600, now_ts)
        used5 = sum(c for p, m, c in win if is_free(p, m))

        hit = None
        hits = last_hits(db.parent / "log" / "opencode.log", 1)
        if hits:
            try:
                ht = dt.datetime.fromisoformat(hits[-1].replace("Z", "+00:00")).astimezone()
                hts = int(ht.timestamp() * 1000)
                ds = int(free_day_start(ht).timestamp() * 1000)
                hit = {"at": fmt_local(hits[-1]),
                       "day_used": free_used_before(con, hts, ds)}
            except Exception:
                pass

        alert_at = None
        if hit and hit.get("day_used"):
            alert_at = int(round(hit["day_used"] * DAY_ALERT_RATIO))

        data["free"] = {
            "used": used,
            "used_5h": used5,
            "limit_5h": FREE_5H_LIMIT,
            "day_reset_at": day_start.strftime("%H:%M"),
            "next_reset": (day_start + dt.timedelta(days=1)).strftime("%m/%d %H:%M"),
            "hit": hit,
            "day_alert_at": alert_at,
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
        self.win_lbl = tk.Label(root, font=f_big, bg=self.BG, fg=self.FG, anchor="w", padx=10)
        self.win_lbl.pack(fill="x")
        self.free_note = tk.Label(root, font=f_small, bg=self.BG, fg=self.DIM, anchor="w",
                                  padx=10, justify="left")
        self.free_note.pack(fill="x")
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
            used, used5 = f["used"], f["used_5h"]
            alert_at = f.get("day_alert_at")
            win_color = (self.BAD if used5 >= WIN_BAD_AT
                         else self.WARN if used5 >= WIN_WARN_AT else self.OK)
            # 日累計只看次數；警戒線 = 上次撞牆日累計 × 0.9（動態）。沒有紀錄就維持綠。
            day_color = self.BAD if (alert_at and used >= alert_at) else self.OK
            win_pct = used5 / f["limit_5h"] * 100
            self.free_lbl.config(text=f"免費 日 {used} 次", fg=day_color)
            self.win_lbl.config(
                text=f"5h {used5}/{f['limit_5h']}（{win_pct:.0f}%）", fg=win_color)

            note = f"{f['day_reset_at']} 換日 · 下次 {f['next_reset']}"
            note += f"\n5h 色階：黃 {WIN_WARN_AT}（60%）／紅 {WIN_BAD_AT}（80%）"
            if alert_at:
                note += f"\n日警戒線 {alert_at} 次（上次撞牆日累計 × 0.9）"
            else:
                note += "\n日警戒線：尚無撞牆紀錄（維持綠色）"
            hit = f.get("hit")
            if hit:
                note += f"\n上次撞牆 {hit['at'][5:16]}（當時日 {hit['day_used']} 次）"
            self.free_note.config(text=note)
        else:
            self.free_lbl.config(text="免費 —（找不到 DB）", fg=self.DIM)
            self.win_lbl.config(text="")
            self.free_note.config(text="")

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
                extra = f"\n月 100%（官方 status={m.get('status')}）→ {fmt_reset(m.get('resetsAt'))} 重置"
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
