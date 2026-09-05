#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# common.py - shared helpers for the Autonomy Layer.
# English comments only per global code style rule.
import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
MISSIONS_DIR = os.path.join(HERE, "missions")
STATE_DIR = os.path.join(HERE, "state")
CONFIG_PATH = os.path.join(HERE, "autonomy_config.json")

TW = timezone(timedelta(hours=8))


def ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def tw_now():
    return datetime.now(TW)


def _read_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            return _read_json(CONFIG_PATH)
        except Exception:
            pass
    return {"repos": [], "notify_telegram": False}


def load_mission(name):
    path = name if os.path.sep in name or name.endswith(".json") else \
        os.path.join(MISSIONS_DIR, name + ".json")
    return _read_json(path)


def hostname():
    return socket.gethostname().lower()


def matches_host(hosts):
    """True if this machine is among the mission's target hosts.
    Empty hosts = run everywhere. '*' = run everywhere."""
    if not hosts:
        return True
    hn = hostname()
    for h in hosts:
        h = str(h).lower()
        if h in ("*", hn) or h in hn or hn.startswith(h):
            return True
    return False


def list_missions():
    out = []
    if os.path.isdir(MISSIONS_DIR):
        for fn in sorted(os.listdir(MISSIONS_DIR)):
            if fn.endswith(".json"):
                try:
                    m = load_mission(os.path.join(MISSIONS_DIR, fn))
                    m["path"] = os.path.join(MISSIONS_DIR, fn)
                    out.append(m)
                except Exception as e:
                    print(f"[autonomy] bad mission {fn}: {e}")
    return out


def status_path(name):
    return os.path.join(STATE_DIR, name + ".json")


def lock_path(m):
    return os.path.join(STATE_DIR, m["name"] + ".lock")


def read_status(name):
    p = status_path(name)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def write_status(name, data):
    ensure_state_dir()
    p = status_path(name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def mission_log_path(m):
    return m.get("log") or os.path.join(STATE_DIR, m["name"] + ".out.log")


def append_log(m, text):
    p = mission_log_path(m)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"[{now_iso()}] {text}\n")
    except Exception:
        pass


def telegram_token_chat():
    """Read token/chat from env or <USERPROFILE>\\.telegram_env (KEY=VALUE)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if token and chat:
        return token, chat
    envf = os.path.join(os.path.expanduser("~"), ".telegram_env")
    if os.path.exists(envf):
        for line in open(envf, encoding="utf-8"):
            line = line.strip()
            if line and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == "TELEGRAM_BOT_TOKEN":
                    token = v.strip()
                elif k.strip() == "TELEGRAM_CHAT_ID":
                    chat = v.strip()
    return token, chat


def send_telegram(text):
    """Send via requests with urllib fallback. Returns True/False."""
    token, chat = telegram_token_chat()
    if not token or not chat:
        print("[notify] 未設定 Telegram（跳過）: " + text[:120])
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat, "text": text, "disable_web_page_preview": True}
    try:
        import requests
        r = requests.post(url, data=payload, timeout=15)
        ok = r.ok
    except Exception:
        import urllib.parse
        import urllib.request
        data = urllib.parse.urlencode(payload).encode()
        try:
            with urllib.request.urlopen(url, data, timeout=15) as resp:
                ok = resp.status == 200
        except Exception:
            ok = False
    print(("[notify]" + (" 已發送" if ok else " 失敗")) + f" ({len(text)} 字)")
    return ok


def git_pull(repo, timeout=180):
    """Fast-forward only; never reset. Returns (ok, out)."""
    try:
        r = subprocess.run(
            ["git", "-C", repo, "pull", "--ff-only"],
            capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode == 0, out.strip()[:400]
    except Exception as e:
        return False, str(e)


def read_last_pull(repo):
    p = os.path.join(STATE_DIR, "git_last_pull.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f).get(repo, "")
        except Exception:
            pass
    return ""


def write_last_pull(repo):
    ensure_state_dir()
    p = os.path.join(STATE_DIR, "git_last_pull.json")
    data = {}
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data[repo] = now_iso()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def is_old(iso, older_than_hours):
    if not iso:
        return True
    try:
        t = datetime.fromisoformat(iso)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t) > timedelta(hours=older_than_hours)
    except Exception:
        return True


def spawn_detached(args, workdir):
    """Start a background process without a visible window."""
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | \
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        args, cwd=workdir, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=flags, close_fds=os.name != "nt",
    )


def kill_pid(pid):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True)
    else:
        os.kill(pid, 15)