#!/usr/bin/env python3
"""engine/workers/colab_dispatch.py - P5-5 local scheduler"""
import argparse
import json
import os
import zipfile
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
WORKING = ROOT / "working"
TASK_DIR = WORKING / "_colab_tasks"


def ensure_dirs():
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    (WORKING / "_colab_inbox").mkdir(parents=True, exist_ok=True)
    (WORKING / "_colab_out").mkdir(parents=True, exist_ok=True)


def make_task_id():
    return "t-" + datetime.now().strftime("%Y%m%d-%H%M%S")


def main():
    ap = argparse.ArgumentParser(description="P5-5 Colab dispatcher")
    ap.add_argument("--type", required=True, choices=["image_gen", "video_broll_fetch", "batch_rebuild"])
    ap.add_argument("--prompt", default="")
    ap.add_argument("--query", default="")
    ap.add_argument("--count", type=int, default=2)
    ap.add_argument("--w", type=int, default=1080)
    ap.add_argument("--h", type=int, default=1920)
    ap.add_argument("--orientation", default="portrait")
    ap.add_argument("--zip", action="store_true", help="also zip tasks dir")
    args = ap.parse_args()

    ensure_dirs()
    tid = make_task_id()
    params = {
        "count": args.count,
        "w": args.w,
        "h": args.h,
    }
    if args.prompt:
        params["prompt"] = args.prompt
    if args.query:
        params["query"] = args.query
    if args.orientation:
        params["orientation"] = args.orientation

    task = {
        "id": tid,
        "type": args.type,
        "status": "queued",
        "priority": 1,
        "params": params,
        "outputs": {"dir": f"colab_out/{tid}"},
        "created_at": datetime.now().astimezone().isoformat(),
        "updated_at": datetime.now().astimezone().isoformat(),
    }
    p = TASK_DIR / f"{tid}.json"
    p.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"created: {p}")

    if args.zip:
        zp = WORKING / "tasks.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for f in TASK_DIR.glob("*.json"):
                z.write(f, f.name)
        print(f"zipped: {zp}")


if __name__ == "__main__":
    main()
