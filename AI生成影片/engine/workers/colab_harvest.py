#!/usr/bin/env python3
"""engine/workers/colab_harvest.py - P5-5 local harvester"""
import json
import zipfile
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
WORKING = ROOT / "working"
INBOX = WORKING / "_colab_inbox"
OUT = WORKING / "_colab_out"
TASK_DIR = WORKING / "_colab_tasks"


def ensure_dirs():
    INBOX.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    TASK_DIR.mkdir(parents=True, exist_ok=True)


def mark_done(tid):
    p = TASK_DIR / f"{tid}.json"
    if not p.exists():
        return
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        d["status"] = "done"
        d["updated_at"] = datetime.now().astimezone().isoformat()
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def main():
    ensure_dirs()
    zips = sorted(INBOX.glob("*.zip"))
    if not zips:
        print(f"no zips in {INBOX}")
        return
    for zp in zips:
        print(f"harvesting {zp.name}")
        try:
            with zipfile.ZipFile(zp, 'r') as z:
                z.extractall(OUT)
            # try to infer task id
            name = zp.stem
            if name.startswith("t-"):
                mark_done(name)
            else:
                # maybe just move
                pass
            print(f"  -> extracted to {OUT}")
        except Exception as e:
            print(f"  ERR: {e}")


if __name__ == "__main__":
    main()
