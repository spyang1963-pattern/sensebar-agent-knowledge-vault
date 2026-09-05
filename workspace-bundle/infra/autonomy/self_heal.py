#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# self_heal.py - autonomy watchdog.
# Scheduled every ~30 min. Does:
#  1. git pull (flood-controlled, guaranteed once/day in the pull window)
#  2. stale-lock check  -> kill runaway process, rerun once, notify
#  3. freshness check   -> if expected output too old, auto-rerun once, notify
#  4. escalating failure -> stop rerunning, notify "needs human"
# Writes state/heartbeat.json so notebook agents can diagnose passively.
import argparse
import json
import os
import sys

import common

PYTHON = sys.executable
AUTONOMY = common.HERE


def _git_sync(cfg):
    """Flood-controlled pull; guaranteed in the daily window."""
    now = common.tw_now()
    for repo in cfg.get("repos", []):
        path = repo.get("path") if isinstance(repo, dict) else repo
        hosts = repo.get("hosts") if isinstance(repo, dict) else None
        if not path or not os.path.isdir(path):
            continue
        if hosts and not common.matches_host(hosts):
            continue
        last = common.read_last_pull(path)
        in_window = any(
            now.hour == hh and now.minute >= mm for hh, mm in cfg.get("pull_window", [[5, 45]])
        )
        if common.is_old(last, 6) or in_window:
            ok, out = common.git_pull(path)
            common.write_last_pull(path)
            common.append_log({"name": "_git", "log": None}, f"pull {path} -> ok={ok} {out[:120]}")
            if not ok:
                common.send_telegram(f"[Autonomy] git pull 失敗\nrepo={path}\n{out[:300]}")


def _lock_seconds_age(m):
    lock = common.lock_path(m)
    if not os.path.exists(lock):
        return -1, None
    try:
        data = json.load(open(lock, encoding="utf-8"))
        start = common.datetime.fromisoformat(data["start"])
        age = (common.datetime.now(common.timezone.utc) - start).total_seconds()
        return age, data.get("pid")
    except Exception:
        return -1, None


def _trigger(name, m):
    """Detached rerun of a mission via the generic runner."""
    common.spawn_detached([PYTHON, os.path.join(AUTONOMY, "runner.py"), m["path"], "--reason", "self-heal"],
                          m.get("workdir") or ".")
    st = common.read_status(name)
    st["last_trigger"] = common.now_iso()
    st["trigger_reason"] = "self-heal"
    common.write_status(name, st)


def _freshness(m, st, now):
    """Return (gap_exceeded, note)."""
    name = m["name"]
    sched = m.get("schedule", {})
    kind = sched.get("kind", "interval")
    if kind == "interval":
        period_min = int(sched.get("minutes", 30))
        gap = max(period_min * 1.5, int(m.get("timeout_min", 30)))
    else:  # daily
        # Daily task must have completed today after its start time.
        start = sched.get("start", "00:00")
        hh, mm = map(int, start.split(":"))
        due = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if now < due:
            return False, "尚未到期"
        gap = 60  # completed today is enough
    last_complete = st.get("last_complete")
    if not last_complete:
        return True, "從未完成"
    try:
        t = common.datetime.fromisoformat(last_complete)
        if t.tzinfo is None:
            t = t.replace(tzinfo=common.TW)
        age_min = (now - t).total_seconds() / 60
    except Exception:
        return True, "狀態時間解析失敗"
    return age_min > gap, f"距上次完成 {age_min:.0f}min > 容許 {gap}min"


def _guard_one(m, now, do_trigger=True):
    name = m["name"]
    if m.get("workdir") and not os.path.isdir(m["workdir"]):
        common.append_log(m, "workdir 不存在，跳過")
        return []
    if not common.matches_host(m.get("hosts")):
        return []
    st = common.read_status(name)
    msgs = []

    # 1) stale / runaway process
    age_s, pid = _lock_seconds_age(m)
    if age_s >= int(m.get("timeout_min", 30)) * 60:
        if pid:
            common.kill_pid(pid)
        lock = common.lock_path(m)
        if os.path.exists(lock):
            os.remove(lock)
        msgs.append(f"⚠️ {name} 卡住(>{(age_s/60):.0f}min)，已強制終止" + (f" (pid {pid})" if pid else ""))
        st["stuck_kills"] = st.get("stuck_kills", 0) + 1
        _trigger(name, m)
        msgs.append(f"✅ {name} 已自動重跑")

    # 2) freshness
    gap, note = _freshness(m, st, now)
    if gap:
        streak = st.get("fail_streak", 0)
        if streak >= 2 and common.is_old(st.get("last_fail"), 4):
            if st.get("degraded_at") != common.now_iso()[:10]:
                st["degraded_at"] = common.now_iso()[:10]
                msgs.append(f"🚨 {name} 連敗中(fail_streak={streak})，暫停自動補跑，需人工檢查")
        else:
            fl = st.get("last_trigger")
            if not fl or common.is_old(fl, 1):
                if do_trigger:
                    _trigger(name, m)
                    msgs.append(f"🔄 {name} 逾時未產出（{note}），已自動補跑")
                else:
                    msgs.append(f"🔄 {name} 逾時未產出（{note}），待處理")
    return msgs


def main():
    ap = argparse.ArgumentParser(description="Autonomy watchdog")
    ap.add_argument("--check", help="show status of one mission and exit")
    ap.add_argument("--dry", action="store_true", help="detect but do not rerun")
    args = ap.parse_args()

    if args.check:
        st = common.read_status(args.check)
        print(json.dumps(st, ensure_ascii=False, indent=1))
        return

    cfg = common.load_config()
    msgs = []
    _git_sync(cfg)

    now = common.tw_now()
    for m in common.list_missions():
        msgs += _guard_one(m, now, do_trigger=not args.dry)

    # heartbeat for passive diagnosis
    hb = {"ts": common.now_iso(), "missions": {}}
    for m in common.list_missions():
        hb["missions"][m["name"]] = common.read_status(m["name"])
    common.write_status("_heartbeat", hb)

    if msgs:
        common.send_telegram("[Autonomy 看門狗]\n" + "\n".join(msgs))
    print("\n".join(msgs) or "一切正常")


if __name__ == "__main__":
    main()