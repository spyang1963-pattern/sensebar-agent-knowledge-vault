#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# runner.py - generic mission executor.
# Usage: python runner.py <mission.json> [--now]
# - fail-fast when the same mission is already running (single writer per mission)
# - runs the declared command with a timeout
# - records status/exit codes and maintains a heartbeat for the watchdog
import argparse
import json
import os
import subprocess
import sys

import common


def _read_mission(arg):
    with open(arg, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="Autonomy mission runner")
    ap.add_argument("mission", help="path to mission json")
    ap.add_argument("--reason", default="schedule")
    args = ap.parse_args()

    m = _read_mission(args.mission)
    name = m["name"]
    workdir = m.get("workdir") or "."
    cmd = m["command"]
    timeout_s = int(m.get("timeout_min", 30)) * 60

    lock = common.lock_path(m)
    common.ensure_state_dir()

    # Fail-fast: a live lock means an instance is still running.
    if os.path.exists(lock):
        print(f"[runner] {name} 已在執行中，跳過本次觸發")
        sys.exit(0)

    with open(lock, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "start": common.now_iso(),
                   "reason": args.reason}, f, ensure_ascii=False)

    common.append_log(m, f"開始 (reason={args.reason}) pid={os.getpid()} cmd={' '.join(cmd[:4])}...")

    try:
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            cmd, cwd=workdir, timeout=timeout_s, shell=False,
            capture_output=False, stdin=subprocess.DEVNULL,
            creationflags=flags,
        )
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        rc = 124
        common.append_log(m, f"逾時 (>{m.get('timeout_min', 30)}min)，該任務將由看門狗處理")
        st = common.read_status(name)
        st["last_exit"] = 124
        st["last_fail"] = common.now_iso()
        st["timeouts"] = st.get("timeouts", 0) + 1
        common.write_status(name, st)
        # Keep lock so watchdog sees it as stuck and kills the runaway process.
        print(f"[runner] {name} timeout -> status written, lock kept")
        sys.exit(2)
    except Exception as e:
        rc = 1
        common.append_log(m, f"執行器錯誤: {e}")

    common.append_log(m, f"結束 rc={rc}")
    st = common.read_status(name)
    st["last_exit"] = rc
    st["last_complete"] = common.now_iso()
    st["reason"] = args.reason
    if rc == 0:
        st["last_success"] = common.now_iso()
        st["fail_streak"] = 0
    else:
        st["last_fail"] = common.now_iso()
        st["fail_streak"] = st.get("fail_streak", 0) + 1
    common.write_status(name, st)

    # Release lock.
    if os.path.exists(lock):
        os.remove(lock)

    sys.exit(0 if rc == 0 else 1)


if __name__ == "__main__":
    main()