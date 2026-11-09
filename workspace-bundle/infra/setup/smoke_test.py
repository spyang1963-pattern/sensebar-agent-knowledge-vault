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
import shutil
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


def tcp_open(host, port=445, timeout=2.5):
    """只測 TCP，不認證；用來判斷 NAS 走 LAN 還是 tailnet 可達。"""
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def cmdkey_has(host, account):
    """cmdkey 的輸出是主控台編碼；帳號本身是 ASCII，直接比對 bytes 最保險。"""
    try:
        r = subprocess.run(["cmdkey", f"/list:{host}"], capture_output=True, timeout=20)
        blob = ((r.stdout or b"") + (r.stderr or b"")).lower()
        return account.encode().lower() in blob
    except Exception:
        return False


def task_exists(name):
    try:
        r = subprocess.run(["schtasks", "/query", "/TN", name],
                           capture_output=True, timeout=25)
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
    # ipc.py 在 shared\tasks 不存在時會靜默回傳空清單 → worker 永遠領不到任務
    check("shared\\tasks 目錄", (shared / "tasks").is_dir(),
          shared / "tasks" if (shared / "tasks").is_dir() else "缺少（worker 會領不到任務）")

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
    tess_path = shutil.which("tesseract")
    tess_default = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    check("Tesseract OCR（PATH 或預設路徑）",
          bool(tess_path) or tess_default.exists(),
          tess_path or (f"{tess_default}（不在 PATH，pytesseract 會失敗）"
                        if tess_default.exists() else "未安裝"))
    la = Path(os.environ.get("LOCALAPPDATA", ""))
    obs_candidates = [la / "Obsidian" / "Obsidian.exe",
                      la / "Programs" / "Obsidian" / "Obsidian.exe"]
    obs_hit = next((p for p in obs_candidates if p.exists()), None)
    check("Obsidian", obs_hit is not None, obs_hit or "未安裝（vault 可稍後再開）")
    check("yt-dlp（YouTube 下載）", which("yt-dlp"), "")
    # 2026-11-06 事故：沒有 JS runtime 時 yt-dlp 抓 metadata 正常、真正下載影片一律 403，
    # 66 支任務因此全滅。這一項一定要在驗收時就擋下來。
    js_rt = which("deno") or which("node") or which("bun")
    js_path = shutil.which("deno") or shutil.which("node") or shutil.which("bun")
    check("JS runtime（yt-dlp 下載必備）", js_rt,
          js_path or "缺 deno：winget install --id DenoLand.Deno -e（缺它下載 YouTube 影片會 403）")

    # ── 6. 金鑰 ──
    home = Path.home()
    check("Groq key（轉錄必備）",
          (home / ".groq_api_key").exists() or bool(os.environ.get("GROQ_API_KEY")),
          "~/.groq_api_key")
    check("Gemini key（筆記／報告）",
          (home / ".gemini_api_key").exists() or bool(os.environ.get("GEMINI_API_KEY")),
          "~/.gemini_api_key（僅提醒，影片線不需要）", )

    # ── 6.5 NAS 與 Tailscale（2026-11-08 NAS 上線後） ──
    nas_lan, nas_tail = "192.168.1.121", "100.65.113.20"
    account = "harvest" if machine == "notebook" else "producer"
    lan_ok = tcp_open(nas_lan)
    tail_ok = tcp_open(nas_tail)
    nas_host = nas_lan if lan_ok else (nas_tail if tail_ok else None)
    check("NAS 可達（LAN 445 或 tailnet 445）", bool(nas_host),
          f"LAN={lan_ok} tailnet={tail_ok}"
          + ("" if nas_host else "；兩條都不通（NAS 沒開機／不同網段且 Tailscale 未登入）"))

    if nas_host:
        check(f"NAS 憑證（cmdkey {account} @ {nas_host}）", cmdkey_has(nas_host, account),
              f"缺就執行：cmdkey /add:{nas_host} /user:{account} /pass:***")
        share_ok = False
        try:
            share_ok = Path(rf"\\{nas_host}\exchange").is_dir()
        except OSError:
            share_ok = False
        check("NAS exchange 可讀", share_ok, rf"\\{nas_host}\exchange")
        if machine != "notebook":
            ob = rf"\\{nas_host}\exchange\{machine}\outbox"
            ob_ok = False
            try:
                ob_ok = Path(ob).is_dir()
            except OSError:
                ob_ok = False
            check("NAS 自己的 outbox", ob_ok, ob)

    ts_ip = ""
    try:
        r = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, timeout=20)
        if r.returncode == 0:
            ts_ip = (r.stdout or b"").decode("ascii", "replace").strip().splitlines()[0] if r.stdout else ""
    except Exception:
        ts_ip = ""
    check("Tailscale 已登入", bool(ts_ip),
          ts_ip or "未安裝或未登入；不同網段時連不到 NAS（tailscale up）")

    # ── 6.6 這台該有的排程與腳本 ──
    if machine == "notebook":
        expect_tasks = ["HarvestPCDaily", "NasBackupDaily"]
        expect_files = ["harvest_daily.bat", "backup_daily.bat"]
        for f in expect_files:
            check(f"腳本 {f}", (project / f).exists(), project / f)
        for t in expect_tasks:
            check(f"排程 {t}", task_exists(t),
                  "未註冊（切換日再跑 deploy.ps1 -SkipSetup -RegisterTasks）")
    else:
        # 產出機的「打包」有兩條合法路徑（2026-11-09 起）：
        #   只打包   → PublishOutboxDaily（22:50）
        #   有掃頻道 → ChannelWatcherDaily（22:30 跑 channel_then_publish.bat：掃完才打包）
        # 兩個都裝會在掃描還沒寫完時打包，收割端會收到半成品 → 要求剛好裝一個。
        has_pub = task_exists("PublishOutboxDaily")
        has_watch = task_exists("ChannelWatcherDaily")
        check("腳本 publish_daily.bat", (project / "publish_daily.bat").exists(), project / "publish_daily.bat")
        if machine == "pc3":
            # PC3＝金融線自成一格：每日／深度報告用 HTML 在 PC3 看、資料在 PC3 知識庫，
            # 「不收割到 notebook」是既定決策 → 沒有打包排程不算 ❌。
            check("打包排程（PC3 可省略）", True,
                  "PC3 走本機報告＋本機知識庫，不收割；哪天要收割再加 PublishOutboxDaily")
        else:
            check("打包路徑（PublishOutboxDaily 或 ChannelWatcherDaily）", has_pub or has_watch,
                  "都沒有：deploy.ps1 -SkipSetup -RegisterTasks -Tasks PublishOutboxDaily")
        check("掃描與打包未重複註冊", not (has_pub and has_watch),
              "兩個都裝了：channel_then_publish.bat 已含打包，請移除 PublishOutboxDaily")
        if has_watch:
            check("腳本 channel_then_publish.bat",
                  (project / "channel_then_publish.bat").exists(),
                  project / "channel_then_publish.bat")

    # ── 6.5 GUI 入口（2026-11-09 PC2 實踩：新機雙擊 .py 完全沒反應）──
    # 檢查兩件事：repo 內的 launch_gui.bat，以及桌面「任務管理.lnk」。
    # 捷徑指向 pythonw + task_manager_gui.py，所以不依賴各機的 .py 檔案關聯。
    check("GUI 啟動器 launch_gui.bat", (project / "launch_gui.bat").exists(),
          project / "launch_gui.bat")

    def _lnk_target(path):
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"$s=New-Object -ComObject WScript.Shell;"
                 f"$l=$s.CreateShortcut('{path}');"
                 f"Write-Output $l.TargetPath"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=25)
            return (out.stdout or "").strip()
        except Exception:
            return ""

    desktop = Path(os.path.expanduser("~")) / "Desktop"
    one_drive = Path(os.path.expanduser("~")) / "OneDrive" / "Desktop"
    lnks = [d / "任務管理.lnk" for d in (desktop, one_drive)]
    lnk = next((p for p in lnks if p.exists()), None)
    if lnk is None:
        check("桌面 GUI 捷徑（任務管理.lnk）", False,
              "不存在 → 跑 deploy.ps1，或雙擊 repo 內的 launch_gui.bat")
    else:
        tgt = _lnk_target(str(lnk))
        check("桌面 GUI 捷徑（任務管理.lnk）", "python" in tgt.lower(),
              f"{lnk} -> {tgt or '（讀不到目標）'}")

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
