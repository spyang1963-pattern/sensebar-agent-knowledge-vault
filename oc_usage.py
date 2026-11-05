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
   （≈ 請求數）估算用量。

   **重要（2026-11-05 更正）**：免費額度是**兩道閘門並存**，不是單一配額。
   ① **5h 滾動窗 ~200 次**：2026-10-23 改制後，沒有任何一次「成功的」5h 窗超過 233 次，
      而三次撞牆都落在 5h 205~232（11-01 23:41/23:45、11-03 02:00）→ 200 附近是真的。
   ② **日／帳號層級**：11-04 21:31 撞牆時 5h 只有 153 次、日累計 337；
      11-02 17:09 撞牆時 5h 只有 1 次、24h 已 234 → 5h 解釋不了，另有一道較高的閘門。
      日累計可以超過 200 沒撞牆（11-03 當日 264 次、5h 最高僅 133）。
   換日時間：使用者實測為**本機 08:55**（2026-11-04 21:43 被拒 → 隔日 09:47 恢復），
   可用 `FREE_DAY_RESET_H/M` 或 `--reset-at 08:55` 調整。
   兩種撞牆訊息：`You've used today's free messages. They reset at HH:MM`（真額度）與
   `Free usage limit reached`（本機 log 只看得到後者，含暫時性）。

用法:
  python oc_usage.py                # 精簡兩行（適合貼進對話）
  python oc_usage.py --full         # 明細：各視窗、進度條、撞牆紀錄
  python oc_usage.py --go-only      # 只看 Go（零成本）
  python oc_usage.py --no-go        # 只看免費（不連網）
  python oc_usage.py --json         # 機器可讀
  python oc_usage.py --limit 200 --window 5 --log 5

注意:
  - 資料庫採唯讀（mode=ro），不會動到 OpenCode。
  - 免費池上限是伺服器**動態**值（無公告、無 API），本工具只能算「用了幾次」，
    不能算「還剩幾次」；看到數字很高不代表一定還能用，反之亦然。
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

# 免費池換日時間（本機時間）。實測：2026-11-04 21:43 被拒，訊息「reset at 08:55」，
# 隔日 09:47 恢復。可用 CLI --reset-at 覆寫。
FREE_DAY_RESET_H = 8
FREE_DAY_RESET_M = 55

# 5h 滾動窗的觀測上限。2026-10-23 改制後：沒有任何一次「成功的」5h 窗超過 233，
# 三次撞牆都落在 205~232 → 5h/200 是真的，與日額度並存。
FREE_WINDOW_LIMIT = 200


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


def free_day_start(now=None, reset_h=FREE_DAY_RESET_H, reset_m=FREE_DAY_RESET_M):
    """目前「免費池日」的起點（本機時間，預設 08:55 換日）。"""
    now = now or dt.datetime.now().astimezone()
    if now.tzinfo is None:
        now = now.astimezone()
    b = now.replace(hour=reset_h, minute=reset_m, second=0, microsecond=0)
    if now < b:
        b -= dt.timedelta(days=1)
    return b


def free_used_before(con, end_ts_ms, start_ts=None):
    """某時間點之前（預設：從 0 起算）的免費請求數。"""
    rows = con.execute(
        "select json_extract(data,'$.model.providerID'), json_extract(data,'$.model.id'), count(*)"
        " from session_message where type='assistant' and time_created between ? and ?"
        " group by 1,2",
        (start_ts if start_ts is not None else 0, end_ts_ms)).fetchall()
    return sum(c for p, m, c in rows if is_free(p, m))



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
    ap.add_argument("--limit", type=int, default=200, help="（舊）免費視窗上限，僅供相容")
    ap.add_argument("--window", type=float, default=5, help="5 小時參考視窗（預設 5）")
    ap.add_argument("--reset-at", default=f"{FREE_DAY_RESET_H:02d}:{FREE_DAY_RESET_M:02d}",
                    help="免費池換日時間（本機，預設 08:55）")
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
            now = dt.datetime.now().astimezone()
            now_ts = int(now.timestamp())
            reset_h, reset_m = (int(x) for x in args.reset_at.split(":"))
            day_start = free_day_start(now, reset_h, reset_m)
            day_ts = int(day_start.timestamp())
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_ts = int(midnight.timestamp())

            win = counts(con, now_ts - int(args.window * 3600), now_ts)
            fday = counts(con, day_ts, now_ts)
            d24 = counts(con, now_ts - 86400, now_ts)
            localday = counts(con, today_ts, now_ts)

            free_win = sum(c for p, m, c in win if is_free(p, m))
            paid_win = sum(c for p, m, c in win if not is_free(p, m))
            free_day = sum(c for p, m, c in fday if is_free(p, m))
            free_24 = sum(c for p, m, c in d24 if is_free(p, m))
            free_today = sum(c for p, m, c in localday if is_free(p, m))

            # 撞牆紀錄（本地時間）與「被拒當時的用量」對照
            hit_iso = last_hits(db.parent / "log" / "opencode.log", args.log)
            hits_local = [fmt_local(h) for h in hit_iso]
            hit_info = None
            if hit_iso:
                try:
                    ht = dt.datetime.fromisoformat(
                        hit_iso[-1].replace("Z", "+00:00")).astimezone()
                    hts = int(ht.timestamp() * 1000)
                    hit_day_start = free_day_start(ht, reset_h, reset_m).timestamp()
                    hit_info = {
                        "at": ht.strftime("%Y-%m-%d %H:%M:%S"),
                        "day_used": free_used_before(con, hts, int(hit_day_start * 1000)),
                        "same_day": hts >= int(day_ts * 1000),
                    }
                except Exception:
                    pass

            out["free"] = {
                "day_used": free_day,
                "day_reset_at": day_start.isoformat(),
                "day_reset_hhmm": f"{reset_h:02d}:{reset_m:02d}",
                "window_hours": args.window,
                "window_limit": FREE_WINDOW_LIMIT,
                "window_used": free_win,
                "today_local": free_today,
                "last24h": free_24,
                "paid_steps_in_window": paid_win,
                "hits": hits_local,
                "last_hit": hit_info,
                "by_model": [{"provider": p, "model": m, "steps": c} for p, m, c in win],
                "by_model_day": [{"provider": p, "model": m, "steps": c} for p, m, c in fday],
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
        hhmm = f["day_reset_hhmm"]
        win_pct = f["window_used"] / f["window_limit"] * 100
        line = (f"免費 日 {f['day_used']} 次（{hhmm} 換日）"
                f"｜{f['window_hours']:g}h {f['window_used']}/{f['window_limit']}"
                f"（{win_pct:.0f}%）")
        hit = f.get("last_hit") or {}
        if hit.get("same_day"):
            line += f"｜本池日已被拒 {hit['at'][11:19]}（當時累計 {hit['day_used']} 次）"
        elif f.get("hits"):
            line += f"｜上次被拒 {f['hits'][-1][5:16]}（當時累計 {hit.get('day_used', 0)} 次）"
        print(line)
        print("      兩道閘門並存：5h 滾動窗 ~200 次；日/帳號層級更高（11-04 5h 153 仍被拒時日 337）")

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
            print("── 免費模型（本機估算；伺服器無公開用量 API）──")
            print(f"  免費池日累計（{f['day_reset_hhmm']} 換日，本機時間）：{f['day_used']} 次")
            print(f"  最近 {f['window_hours']:g} 小時：{f['window_used']} / {f['window_limit']} 次（5h 滾動窗上限，實測有效）")
            print(f"  本機日曆日：{f['today_local']} 次｜最近 24h：{f['last24h']} 次")
            if f.get("last_hit"):
                h = f["last_hit"]
                print(f"  上次被拒：{h['at']}（當時本池日累計 {h['day_used']} 次）")
                print(f"  目前池日起點：{f['day_reset_at']}")
            if f["by_model_day"]:
                print("  本池日各模型：")
                for r in f["by_model_day"]:
                    print(f"    {r['provider']}/{r['model']}: {r['steps']} 次")
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
