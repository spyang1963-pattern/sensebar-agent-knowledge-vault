# -*- coding: utf-8 -*-
"""
Publish XQ-AI神隊友 dashboard to GitHub Pages (xq-dashboard repo).

Copies routines/outputs/xq_dashboard.html into publisher/repo/ (a git checkout
of spyang1963-pattern/xq-dashboard) as index.html and pushes.

Usage:
  python publisher/deploy.py            # copy + push
  python publisher/deploy.py --no-push  # copy only (dry deploy)
"""
import os
import shutil
import argparse
import subprocess
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "routines", "outputs", "xq_dashboard.html")
PUB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "repo")
REPO_URL = "https://github.com/spyang1963-pattern/xq-dashboard.git"
TZ = timezone(timedelta(hours=8))


def ensure_checkout():
    if os.path.isdir(os.path.join(PUB_DIR, ".git")):
        return
    os.makedirs(os.path.dirname(PUB_DIR), exist_ok=True)
    if os.path.exists(PUB_DIR):
        raise SystemExit(f"[deploy] repo dir exists but not a git checkout: {PUB_DIR}")
    print(f"[deploy] cloning {REPO_URL} -> {PUB_DIR}")
    subprocess.run(["git", "clone", REPO_URL, PUB_DIR], check=True)


def deploy():
    if not os.path.isfile(SRC):
        raise SystemExit(f"[deploy] source not found: {SRC}")
    ensure_checkout()

    shutil.copy2(SRC, os.path.join(PUB_DIR, "index.html"))
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    subprocess.run(["git", "add", "-A"], cwd=PUB_DIR, check=True)
    # 先 pull（遠端可能已有其他提交），index.html 以本地最新為準：-X ours 自動解衝突
    subprocess.run(
        ["git", "pull", "--rebase", "-X", "ours", "origin", "master"],
        cwd=PUB_DIR, check=False)
    subprocess.run(
        ["git", "commit", "-m", f"chore: update dashboard {now}", "--allow-empty"],
        cwd=PUB_DIR, check=True)
    subprocess.run(["git", "push", "origin", "HEAD:master"], cwd=PUB_DIR, check=True)
    print(f"[deploy] pushed xq-dashboard {now}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()
    if not args.no_push:
        deploy()
    else:
        if not os.path.isfile(SRC):
            raise SystemExit(f"[deploy] source not found: {SRC}")
        shutil.copy2(SRC, os.path.join(PUB_DIR, "index.html"))
        print("[deploy] copied (no push)")


if __name__ == "__main__":
    main()