#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
oc_usage.py — 查 OpenCode 額度（免費模型 + Go 付費）
====================================================
兩條路，成本完全不同：

1. Go（付費）＝ **官方精確值、零 token 成本**
   GET https://opencode.ai/inference/go/v1/usage
   用本機 auth.json 的 opencode-go API key 認證，回傳 rolling(5h) / weekly / monthly
   的 percent、status、resetsAt。純 HTTP，不呼叫模型，不花任何 token。

2. 免費模型（opencode/*）＝ **本機估算**
   伺服器端沒有公開「剩餘量」API；本工具用本機 session 資料庫數 assistant 訊息數
   （≈ 請求數）估算 5 小時滾動視窗用量，並列出最近撞牆時間。

用法:
  python oc_usage.py                # 精簡兩行（適合貼進對話）
  python oc_usage.py --full         # 明細：各視窗、進度條、撞牆紀錄
  python oc_usage.py --go-only      # 只看 Go（零成本）
  python oc_usage.py --no-go        # 只看免費（不連網）
  python oc_usage.py --json         # 機器可讀
  python oc_usage.py --limit 200 --window 5 --log 5

注意:
  - 資料庫採唯讀（mode=ro），不會動到 OpenCode。
  - 免費模型的 200/5h 是回推值（非官方公告），誤差約 ±10~15%。
  - Go 的數字是官方值；monthly 100% 且 status=rate-limited 代表當期已用盡。
"""
import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GO_USAGE_URL = "https://opencode.ai/inference/go/v1/usage"
FREE_HINTS = ("-free", "big-pickle", "pulse-alpha", "beam-free", "flint-40b",
              "mimo-", "nemotron", "glm-5.3-flash-free", "deepseek-v4.1-flash-free")


# ---------------------------------------------------------------- 資料來源定位
def find_db():
    cands = []
    if os.environ.get("OPENCODE_DATA_DIR"):
        cands.append(Path(os.environ["OPENCODE_DATA_DIR"]))
    if os.environ.get("OPENCODE_DATA"):
        cands.append(Path(os.environ["OPENCODE_DATA"]))
    cands += [
        Path(r"D:\opencode-data\opencode"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "opencode",
        Path.home() / ".local" / "share" / "opencode",
        Path(os.environ.get("APPDATA", "")) / "opencode",
    ]
    for d in cands:
        if d and (d / "opencode.db").exists():
            return d / "opencode.db"
    return None


def read_go_key(db):
    if not db:
        return None
    p = db.parent / "auth.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        return (data.get("opencode-go") or {}).get("key")
    except Exception:
        return None


# ------------------------------------------------------------------- Go 官方值
def fetch_go_usage(key, timeout=15):
    """回傳 dict 或 None。純 HTTP，不消耗 token。"""
    if not key:
        return None
    req = urllib.request.Request(
        GO_USAGE_URL,
        headers={"Authorization": f"Bearer {key}",
                 "User-Agent": "opencode-usage-probe/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")).get("usage")
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError):
        return None


def fmt_reset(iso):
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return t.astimezone().strftime("%m/%d %H:%M")
    except Exception:
        return iso or "?"


# ------------------------------------------------------------------- 免費估算
def is_free(provider, model):
    if (provider or "") == "opencode":
        return True
    m = (model or "").lower()
    return any(h in m for h in FREE_HINTS)


def counts(con, start_ts, end_ts):
    return con.execute(
        "select json_extract(data,'$.model.providerID'), json_extract(data,'$.model.id'), count(*)"
        " from session_message"
        " where type='assistant' and time_created/1000 between ? and ?"
        " group by 1,2 order by 3 desc",
        (start_ts, end_ts),
    ).fetchall()


def last_hits(log, n):
    if not log.exists():
        return []
    hits = []
    with open(log, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "Free usage limit reached" in line and "level=ERROR" in line:
                if "timestamp=" in line:
                    hits.append(line.split("timestamp=", 1)[1].split(" ", 1)[0])
    return hits[-n:]


def fmt_local(iso):
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return t.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso


def bar(pct, width=24):
    pct = max(0.0, min(100.0, pct))
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled)


# ------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="OpenCode 額度查詢（免費估算 + Go 官方）")
    ap.add_argument("--limit", type=int, default=200, help="免費模型視窗上限（預設 200）")
    ap.add_argument("--window", type=float, default=5, help="免費視窗小時數（預設 5）")
    ap.add_argument("--log", type=int, default=5, help="列出最近 N 筆撞牆紀錄")
    ap.add_argument("--full", action="store_true", help="顯示明細")
    ap.add_argument("--go-only", action="store_true", help="只看 Go（零成本）")
    ap.add_argument("--no-go", action="store_true", help="只看免費（不連網）")
    ap.add_argument("--json", action="store_true", help="JSON 輸出")
    args = ap.parse_args()

    db = find_db()
    out = {"free": None, "go": None}

    # ---- 免費（本機估算）
    if not args.go_only:
        if not db:
            if not args.json:
                print("[ERR] 找不到 opencode.db（可用 OPENCODE_DATA_DIR 指定）")
            out["free"] = {"error": "db not found"}
        else:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            now_ts = int(dt.datetime.now(dt.timezone.utc).timestamp())
            midnight = dt.datetime.now().astimezone().replace(
                hour=0, minute=0, second=0, microsecond=0)
            today_ts = int(midnight.timestamp())

            win = counts(con, now_ts - int(args.window * 3600), now_ts)
            day = counts(con, today_ts, now_ts)
            d24 = counts(con, now_ts - 86400, now_ts)

            free_win = sum(c for p, m, c in win if is_free(p, m))
            paid_win = sum(c for p, m, c in win if not is_free(p, m))
            free_day = sum(c for p, m, c in day if is_free(p, m))
            free_24 = sum(c for p, m, c in d24 if is_free(p, m))
            pct = min(100.0, free_win / args.limit * 100) if args.limit else 0.0
            out["free"] = {
                "window_hours": args.window,
                "limit": args.limit,
                "used": free_win,
                "remaining": max(0, args.limit - free_win),
                "percent": round(pct, 1),
                "today": free_day,
                "last24h": free_24,
                "paid_steps_in_window": paid_win,
                "hits": [fmt_local(h) for h in last_hits(db.parent / "log" / "opencode.log", args.log)],
                "by_model": [{"provider": p, "model": m, "steps": c} for p, m, c in win],
            }

    # ---- Go（官方、零成本）
    if not args.no_go:
        out["go"] = fetch_go_usage(read_go_key(db))

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    # ---- 人類可讀輸出
    f = out["free"]
    if f and "error" not in f:
        mark = ""
        if f["percent"] >= 80:
            mark = "  ⚠ 接近上限"
        print(f"免費 5h {f['used']}/{f['limit']}（{f['percent']:.0f}%）｜今日 {f['today']}"
              f"｜24h {f['last24h']}｜剩 ~{f['remaining']}{mark}")

    g = out["go"]
    if g:
        parts = []
        for label, key in (("5h", "rolling"), ("週", "weekly"), ("月", "monthly")):
            v = g.get(key) or {}
            pct = v.get("percent", 0)
            blocked = v.get("status") and v.get("status") != "ok"
            s = f"{label} {pct:.0f}%"
            if blocked:
                s += f" ⛔→{fmt_reset(v.get('resetsAt'))}"
            parts.append(s)
        print("Go   " + " · ".join(parts))
    elif out["go"] is None and not args.no_go:
        print("Go   （查不到：auth.json 沒有 opencode-go key 或連線失敗）")

    if args.full:
        print()
        if f and "error" not in f:
            print(f"── 免費模型：最近 {f['window_hours']:g} 小時明細 ──")
            for r in f["by_model"]:
                tag = "FREE" if is_free(r["provider"], r["model"]) else "paid"
                print(f"  [{tag}] {r['provider']}/{r['model']}: {r['steps']} steps")
            if not f["by_model"]:
                print("  （無）")
            print(f"  [{bar(f['percent'])}] {f['percent']:.0f}%")
            if f["paid_steps_in_window"]:
                print(f"  同視窗另有 Go 呼叫 {f['paid_steps_in_window']} 次（不佔免費額度）")
            if f["hits"]:
                print(f"\n── 最近 {len(f['hits'])} 次『Free usage limit reached』──")
                for h in f["hits"]:
                    print(f"  {h}")
        if g:
            print("\n── Go 官方計量（GET /inference/go/v1/usage，零 token）──")
            for label, key in (("5 小時", "rolling"), ("每週", "weekly"), ("每月", "monthly")):
                v = g.get(key) or {}
                print(f"  {label}: {v.get('percent', 0):>3}%  status={v.get('status')}"
                      f"  重置 {fmt_reset(v.get('resetsAt'))}")


if __name__ == "__main__":
    main()
