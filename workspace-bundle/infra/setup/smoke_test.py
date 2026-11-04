#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smoke_test.py — 部署後「唯讀」自我檢查

不寫入任何檔案、不搬動影片、不呼叫 harvest、不註冊排程。
只確認：身份、路徑、shared 狀態、模組可載入、外部工具、金鑰。

用法:
    python -X utf8 workspace-bundle/infra/setup/smoke_test.py
    python -X utf8 workspace-bundle/infra/setup/smoke_test.py --json

結束碼 = 失敗項數（0 表示全通過）。
"""
import argparse
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]  # setup -> infra -> workspace-bundle -> 專案根
sys.path.insert(0, str(ROOT))

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append({"name": name, "ok": bool(ok), "detail": str(detail)})
    return ok


def module_available(mod):
    """只檢查能否載入，不執行模組內容（find_spec 不會 import）。"""
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False


def which(exe):
    try:
        r = subprocess.run(["where.exe", exe], capture_output=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="以 JSON 輸出")
    args = ap.parse_args()

    # ── 1. 身份 ──
    try:
        import config
    except Exception as e:
        check("載入 config.py", False, e)
        return report(args)

    machine = getattr(config, "MACHINE", "?")
    role = config.get_machine_role() if hasattr(config, "get_machine_role") else "?"
    check("載入 config.py", True, f"MACHINE={machine} role={role}")
    check("機器身份已辨識", not str(machine).startswith("unknown"),
          f"hostname={os.environ.get('COMPUTERNAME', '?')}")
    check("角色已設定", bool(role) and role != "?", role)

    # ── 2. 路徑 ──
    project = Path(getattr(config, "PROJECT_ROOT", ROOT))
    shared = Path(getattr(config, "SHARED_ROOT", project / "shared"))
    check("專案根目錄", project.is_dir(), project)
    check("shared 目錄", shared.is_dir(), shared)

    for sub, hint in (("working", "執行期目錄，deploy.ps1 會建立"),
                      ("output", "執行期目錄，deploy.ps1 會建立"),
                      ("knowledge-base", "資料目錄，由收割／筆記產生")):
        p = project / sub
        check(f"{sub} 目錄", p.is_dir(),
              p if p.is_dir() else f"{p}（缺；{hint}）")

    try:
        videos = Path(config.get_machine_paths()["videos"])
    except Exception as e:
        videos = None
        check("videos 路徑", False, e)
    if videos is not None:
        # 不存在不算失敗：新機還沒放教材影片是正常的
        check("videos 路徑（不存在僅提醒）", True,
              f"{videos}{'' if videos.is_dir() else '（尚未建立）'}")

    # ── 3. shared 狀態（只讀） ──
    status_file = Path(getattr(config, "TASK_STATUS_FILE", shared / "task_status.json"))
    if status_file.exists():
        try:
            data = json.loads(status_file.read_text(encoding="utf-8-sig"))
            tasks = data.get("tasks", {})
            pending = sum(1 for t in tasks.values()
                          if t.get("status") in ("pending", "assigned", "processing"))
            check("task_status.json 可讀", True, f"共 {len(tasks)} 個任務，待處理 {pending}")
        except Exception as e:
            check("task_status.json 可讀", False, e)
    else:
        check("task_status.json 可讀", True, "不存在（尚無任務，正常）")

    state = shared / "watched_channels_state.json"
    if state.exists():
        age = (datetime.now() - datetime.fromtimestamp(state.stat().st_mtime)).days
        check("頻道監控狀態檔", True, f"{state.name}（{age} 天前更新）")
    else:
        check("頻道監控狀態檔", True, "不存在（首次掃描會建立）")

    # ── 4. 核心模組可載入（不執行） ──
    for mod in ("ipc", "scheduler", "worker", "channel_watcher", "watchdog"):
        check(f"模組 {mod}.py", module_available(mod), "")

    # ── 5. 外部工具 ──
    vlc = Path(r"C:\Program Files\VideoLAN\VLC\vlc.exe")
    check("ffmpeg（PATH）", which("ffmpeg"), "")
    check("ffprobe（PATH）", which("ffprobe"), "")
    check("VLC（燒字幕用固定路徑）", vlc.exists(), vlc)

    # ── 6. 金鑰 ──
    home = Path.home()
    check("Groq key（轉錄必備）",
          (home / ".groq_api_key").exists() or bool(os.environ.get("GROQ_API_KEY")),
          "~/.groq_api_key")
    check("Gemini key（筆記／報告）",
          (home / ".gemini_api_key").exists() or bool(os.environ.get("GEMINI_API_KEY")),
          "~/.gemini_api_key（僅提醒，影片線不需要）", )

    # ── 7. 金融 db（只讀開啟） ──
    db = project / "financial_news" / "finance.db"
    if db.exists():
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            n = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            con.close()
            check("finance.db 可讀", True, f"{db.stat().st_size / 1024 / 1024:.0f} MB，{n} 筆事件")
        except Exception as e:
            check("finance.db 可讀", False, e)
    else:
        check("finance.db 可讀", True, "不存在（不跑金融線的機器不需要）")

    return report(args)


def report(args):
    fails = [r for r in RESULTS if not r["ok"]]
    if args.json:
        print(json.dumps({"results": RESULTS, "failed": len(fails)},
                         ensure_ascii=False, indent=2))
    else:
        print("=" * 56)
        print("  部署後自我檢查（唯讀）")
        print("=" * 56)
        for r in RESULTS:
            mark = "✅" if r["ok"] else "❌"
            line = f"  {mark} {r['name']}"
            if r["detail"]:
                line += f"  — {r['detail']}"
            print(line)
        print("=" * 56)
        if fails:
            print(f"  結果：{len(fails)} 項未通過（共 {len(RESULTS)} 項）")
        else:
            print(f"  結果：全部通過（共 {len(RESULTS)} 項）")
        print("=" * 56)
    return len(fails)


if __name__ == "__main__":
    sys.exit(main())
