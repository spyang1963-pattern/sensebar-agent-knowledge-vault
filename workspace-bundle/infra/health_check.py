"""
環境一致性檢查工具
用法：python health_check.py [--json] [--remote]
  --json   輸出 JSON 格式（供其他腳本讀取）
  --remote 嘗試透過 SSH 檢查其他機器（需 Tailscale）
"""

import os
import sys
import json
import subprocess
import platform
from pathlib import Path
from datetime import datetime

# ── 路徑設定 ──
# WORKSPACE 可被 WORKSPACE_ROOT env 覆蓋；否則從本檔位置自動推導
# （<repo>\workspace-bundle\infra\health_check.py → repo 根），本機/PC3 皆適用
BUNDLE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("WORKSPACE_ROOT") or BUNDLE_DIR.parent)

# ── 機器定義 ──
MACHINES = {
    "LAPTOP-VAG7LBD2": {
        "name": "筆電",
        "role": ["collector", "analyzer", "reporter"],
        "tailscale_ip": "100.111.44.63",
        "os": "windows",
    },
    "DESKTOP-MFKVCSO": {
        "name": "PC3",
        "role": ["collector", "analyzer"],
        "tailscale_ip": "100.111.44.63",  # TODO: 確認 PC3 Tailscale IP
        "os": "windows",
    },
    "DS718+": {
        "name": "NAS",
        "role": ["collector"],
        "tailscale_ip": "192.168.1.121",
        "os": "linux",
    },
}

# ── Bundle 定義 ──
BUNDLES = {
    "infra": {
        "name": "基礎層",
        "dir": BUNDLE_DIR / "infra",
        "requirements": "requirements-base.txt",
    },
    "knowledge-management": {
        "name": "知識管理",
        "dir": BUNDLE_DIR / "knowledge-management",
        "requirements": "requirements.txt",
    },
    "stock-monitor": {
        "name": "台股看板",
        "dir": BUNDLE_DIR / "stock-monitor",
        "requirements": "requirements.txt",
    },
}

# ── 任務線定義（各線專屬 requirements + 能力檢查）──
LINES = {
    "finance": {
        "name": "金融新聞線",
        "dir": WORKSPACE / "financial_news",
        "requirements": "requirements-finance.txt",
    },
    "video": {
        "name": "影片處理線",
        "dir": WORKSPACE,
        "requirements": "requirements-video.txt",
    },
    "stock": {
        "name": "股票線",
        "dir": WORKSPACE / "stock-monitor",
        "requirements": "requirements-stock.txt",
    },
    "xq": {
        "name": "XQ 儀表板線",
        "dir": WORKSPACE / "XQ-AI神隊友",
        "requirements": None,
    },
}

# 排程任務關鍵字（動態掃描 schtasks 比對；PC3 現役＝Autonomy_* 系列）
TASK_KEYWORDS = [
    "Autonomy_finance-pipeline", "Autonomy_finance-morning",
    "Autonomy_finance-evening", "Autonomy_Guard", "ChannelWatcherDaily",
    "XQ_Snapshot_Loop2", "XQ_Postmarket_Evening", "XQ_Postmarket_Morning",
    "StockMonitor_Fetch", "StockMonitor_Scheduler",
]


def run(cmd, timeout=30, cwd=None):
    """執行命令並回傳輸出"""
    try:
        r = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            cwd=cwd,
        )
        # Windows schtasks 輸出是 Big5，嘗試多種編碼
        for enc in ["utf-8", "cp950", "big5", "latin-1"]:
            try:
                stdout = r.stdout.decode(enc)
                stderr = r.stderr.decode(enc)
                return stdout.strip(), r.returncode
            except (UnicodeDecodeError, AttributeError):
                continue
        return r.stdout.decode("latin-1", errors="replace").strip(), r.returncode
    except Exception as e:
        return str(e), 1


def get_machine_name():
    """取得本機機器名稱"""
    return platform.node()


def get_python_version():
    """取得 Python 版本"""
    return platform.python_version()


def get_git_version():
    """取得 Git repo 版本（最新 commit hash）"""
    out, code = run(["git", "rev-parse", "--short", "HEAD"], cwd=str(WORKSPACE))
    if code == 0:
        return out
    return None


def get_git_status():
    """取得 Git repo 狀態"""
    out, code = run(["git", "status", "--porcelain"], cwd=str(WORKSPACE))
    if code == 0:
        changed = len([l for l in out.splitlines() if l.strip()])
        return changed
    return -1


def check_bundle_version(bundle_key):
    """檢查 bundle 的 VERSION 檔"""
    bundle = BUNDLES[bundle_key]
    version_file = bundle["dir"] / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return None


def check_requirements(bundle_key):
    """檢查套件是否安裝"""
    bundle = BUNDLES[bundle_key]
    req_file = bundle["dir"] / bundle["requirements"]
    if not req_file.exists():
        return None, []

    # 讀 requirements.txt
    required = []
    for line in req_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("-"):
            pkg = line.split("==")[0].split(">=")[0].split("<=")[0].strip()
            required.append(pkg.lower().replace("-", "_"))

    # 檢查已安裝
    out, _ = run([sys.executable, "-m", "pip", "list", "--format=json"])
    try:
        installed = {p["name"].lower().replace("-", "_"): p["version"]
                     for p in json.loads(out)}
    except:
        installed = {}

    missing = []
    outdated = []
    for pkg in required:
        if pkg not in installed:
            missing.append(pkg)
        # TODO: 比對版本

    return len(required), missing


def check_line_requirements(line_key):
    """檢查某任務線的專屬 requirements 是否安裝齊全"""
    line = LINES[line_key]
    if line["requirements"] is None:
        return 0, []
    req_file = BUNDLE_DIR / "infra" / line["requirements"]
    if not req_file.exists():
        return 0, []
    required = []
    for ln in req_file.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and not ln.startswith("-"):
            pkg = ln.split("==")[0].split(">=")[0].split("<=")[0].strip()
            required.append(pkg.lower().replace("-", "_"))
    out, _ = run([sys.executable, "-m", "pip", "list", "--format=json"])
    try:
        installed = {p["name"].lower().replace("-", "_"): p["version"]
                     for p in json.loads(out)}
    except:
        installed = {}
    missing = [p for p in required if p not in installed]
    return len(required), missing


def _imports_ok(*names):
    """Try importing all names; returns (ok, first_missing)."""
    import importlib
    for n in names:
        try:
            importlib.import_module(n)
        except Exception:
            return False, n
    return True, None


def check_finance_line():
    """金融新聞線：db / 金鑰 / publisher remote / 關鍵模組"""
    fn = WORKSPACE / "financial_news"
    info = {
        "finance_db": (fn / "finance.db").exists(),
        "gemini_key": (Path.home() / ".gemini_api_key").exists() or bool(os.environ.get("GEMINI_API_KEY")),
        "telegram_env": (Path.home() / ".telegram_env").exists()
                        or bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "publisher_repo": (fn / "publisher" / "repo").is_dir(),
        "google_genai": _imports_ok("google.genai")[0],
    }
    return info


def check_video_line():
    """影片處理線：下載/轉寫/字幕/OCR"""
    vlc_path = Path(r"C:\Program Files\VideoLAN\VLC\vlc.exe")
    tess_path = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    ok, _ = _imports_ok("yt_dlp", "whisper", "pytesseract", "auto_editor", "psutil", "plyer", "PIL", "bs4")
    info = {
        "yt_dlp": _imports_ok("yt_dlp")[0],
        "whisper": _imports_ok("whisper")[0],
        "pytesseract": _imports_ok("pytesseract")[0],
        "tesseract_binary": tess_path.exists() or (run(["where.exe", "tesseract"], timeout=10)[1] == 0),
        "auto_editor": _imports_ok("auto_editor")[0],
        "ffmpeg": run(["where.exe", "ffmpeg"], timeout=10)[1] == 0,
        "vlc": vlc_path.exists(),
        "psutil_plyer": _imports_ok("psutil", "plyer")[0],
        "bs4_pil": _imports_ok("bs4", "PIL")[0],
    }
    return info


def check_stock_line():
    """股票線：套件 + config + cache"""
    sm = WORKSPACE / "stock-monitor"
    ok, _ = _imports_ok("pandas", "bs4", "yaml")
    info = {
        "config_yaml": (sm / "config.yaml").exists(),
        "cache_dir": (sm / "output" / "cache").is_dir(),
        "pandas_bs4_yaml": ok,
    }
    return info


def check_xq_line():
    """XQ 儀表板線：Excel COM 前置 + 快照新鮮度 + 模組"""
    xq = WORKSPACE / "XQ-AI神隊友"
    excel_up = run(["tasklist", "/FI", "IMAGENAME eq EXCEL.EXE", "/FO", "CSV"], timeout=10)[0]
    latest_snap = None
    snap_dir = xq / "routines" / "snapshots"
    if snap_dir.is_dir():
        csvs = sorted(snap_dir.glob("*_*.csv"))
        if csvs:
            latest_snap = csvs[-1]
    info = {
        "excel_running": "EXCEL.EXE" in excel_up,
        "snapshots_exist": latest_snap is not None,
        "snapshots_fresh": latest_snap is not None and
                           (datetime.now() - datetime.fromtimestamp(latest_snap.stat().st_mtime)).days <= 2,
        "gemini_key": (Path.home() / ".gemini_api_key").exists() or bool(os.environ.get("GEMINI_API_KEY")),
        "render_html": (xq / "routines" / "render_html.py").exists(),
    }
    return info


LINE_CHECKERS = {
    "finance": check_finance_line,
    "video": check_video_line,
    "stock": check_stock_line,
    "xq": check_xq_line,
}


def check_config_files():
    """檢查必要的設定檔"""
    checks = []
    config_files = [
        ("config/machine.yaml", "機器設定"),
        ("config/notify_config.yaml", "通知設定"),
        ("config/.env", "API Keys"),
    ]
    for rel_path, desc in config_files:
        path = WORKSPACE / "workspace-bundle" / rel_path
        checks.append({
            "file": rel_path,
            "desc": desc,
            "exists": path.exists(),
        })
    return checks


def check_services():
    """檢查排程任務是否存在（動態掃描 schtasks 比對關鍵字）"""
    all_names = []
    if sys.platform == "win32":
        out, _ = run(["schtasks", "/Query", "/FO", "CSV"], timeout=20)
        for row in out.splitlines()[1:]:
            parts = row.strip().split('","')
            if parts and parts[0].startswith('"'):
                all_names.append(parts[0].strip('"'))
    tasks = []
    for kw in TASK_KEYWORDS:
        tasks.append({"name": kw, "exists": any(kw in n for n in all_names)})
    return tasks


def check_vision_capability():
    """檢查視覺能力（Groq Vision API）"""
    vision_info = {
        "groq_key_exists": False,
        "vision_packages_installed": False,
        "vision_script_exists": False,
    }

    # 檢查 Groq API key
    key_path = Path.home() / ".groq_api_key"
    if key_path.exists() or os.environ.get("GROQ_API_KEY"):
        vision_info["groq_key_exists"] = True

    # 檢查 vision 套件
    try:
        import fitz  # PyMuPDF
        from PIL import Image
        from pptx import Presentation
        from docx import Document
        from groq import Groq
        vision_info["vision_packages_installed"] = True
    except ImportError:
        pass

    # 檢查 vision.py 是否存在
    vision_script = BUNDLE_DIR / "infra" / "skills" / "image-vision-sidecar" / "vision.py"
    if vision_script.exists():
        vision_info["vision_script_exists"] = True

    return vision_info


def check_draw_capability():
    """檢查生圖能力（Pollinations.ai）"""
    draw_info = {
        "draw_packages_installed": False,
        "draw_script_exists": False,
        "overlay_script_exists": False,
    }

    # 檢查 Pillow 是否安裝
    try:
        from PIL import Image
        draw_info["draw_packages_installed"] = True
    except ImportError:
        pass

    # 檢查 draw_free.py 是否存在
    draw_script = BUNDLE_DIR / "infra" / "skills" / "draw-free" / "draw_free.py"
    if draw_script.exists():
        draw_info["draw_script_exists"] = True

    # 檢查 overlay-text.py 是否存在
    overlay_script = BUNDLE_DIR / "infra" / "skills" / "draw-free" / "overlay-text.py"
    if overlay_script.exists():
        draw_info["overlay_script_exists"] = True

    return draw_info


def check_kb_capability():
    """檢查知識庫管理管線能力（頻道下載→轉錄→字幕）"""
    kb_info = {
        "gemini_key_exists": False,
        "groq_key_exists": False,
        "ffmpeg_in_path": False,
        "vlc_installed": False,
        "obsidian_installed": False,
        "yt_dlp_installed": False,
    }

    if (Path.home() / ".gemini_api_key").exists() or os.environ.get("GEMINI_API_KEY"):
        kb_info["gemini_key_exists"] = True
    if (Path.home() / ".groq_api_key").exists() or os.environ.get("GROQ_API_KEY"):
        kb_info["groq_key_exists"] = True

    out, code = run(["where.exe", "ffmpeg"], timeout=10)
    kb_info["ffmpeg_in_path"] = (code == 0)

    vlc_path = Path(r"C:\Program Files\VideoLAN\VLC\vlc.exe")
    kb_info["vlc_installed"] = vlc_path.exists()

    obsidian_path = Path.home() / "AppData" / "Local" / "Programs" / "Obsidian" / "Obsidian.exe"
    kb_info["obsidian_installed"] = obsidian_path.exists()

    try:
        import yt_dlp
        kb_info["yt_dlp_installed"] = True
    except ImportError:
        pass

    return kb_info


def build_report(as_json=False):
    """建立完整報告"""
    hostname = get_machine_name()
    machine_info = MACHINES.get(hostname, {"name": hostname, "role": []})

    report = {
        "timestamp": datetime.now().isoformat(),
        "machine": hostname,
        "machine_name": machine_info["name"],
        "machine_role": machine_info["role"],
        "python": get_python_version(),
        "git": {
            "repo_version": get_git_version(),
            "uncommitted_changes": get_git_status(),
        },
        "bundles": {},
        "config": check_config_files(),
        "services": check_services(),
        "vision": check_vision_capability(),
        "draw": check_draw_capability(),
        "kb": check_kb_capability(),
        "lines": {k: {"name": LINES[k]["name"], **LINE_CHECKERS[k]()}
                  for k in LINES},
        "line_packages": {k: {"total": t, "missing": m}
                          for k, (t, m) in [(kk, check_line_requirements(kk))
                                            for kk in LINES]},
    }

    for key in BUNDLES:
        ver = check_bundle_version(key)
        pkg_total, missing = check_requirements(key)
        report["bundles"][key] = {
            "name": BUNDLES[key]["name"],
            "version": ver,
            "packages_total": pkg_total,
            "packages_missing": missing,
        }

    if as_json:
        return report

    # 輸出可讀報告
    print(f"\n{'='*50}")
    print(f"  環境一致性報告")
    print(f"  {report['timestamp']}")
    print(f"{'='*50}")
    print(f"\n  機器：{report['machine_name']} ({report['machine']})")
    print(f"  角色：{', '.join(report['machine_role']) or '未設定'}")
    print(f"  Python：{report['python']}")
    print(f"  Git repo：{report['git']['repo_version'] or '無法取得'}")
    print(f"  未提交變更：{report['git']['uncommitted_changes']} 個檔案")

    print(f"\n  {'─'*46}")
    print(f"  Bundles：")
    for key, info in report["bundles"].items():
        ver_str = info["version"] or "未安裝"
        pkg_str = f"{info['packages_total']} 個套件" if info["packages_total"] else "無 requirements"
        missing_str = f", {len(info['packages_missing'])} 個缺少" if info["packages_missing"] else ""
        status = "✅" if not info["packages_missing"] else "⚠️"
        print(f"    {status} {info['name']}: {ver_str} ({pkg_str}{missing_str})")

    print(f"\n  {'─'*46}")
    print(f"  設定檔：")
    for cfg in report["config"]:
        status = "✅" if cfg["exists"] else "❌"
        print(f"    {status} {cfg['desc']} ({cfg['file']})")

    print(f"\n  {'─'*46}")
    print(f"  排程任務：")
    for svc in report["services"]:
        status = "✅" if svc["exists"] else "❌"
        print(f"    {status} {svc['name']}")

    print(f"\n  {'─'*46}")
    print(f"  視覺能力（Vision Sidecar）：")
    v = report["vision"]
    status_key = "✅" if v["groq_key_exists"] else "❌"
    status_pkg = "✅" if v["vision_packages_installed"] else "❌"
    status_script = "✅" if v["vision_script_exists"] else "❌"
    print(f"    {status_key} Groq API Key")
    print(f"    {status_pkg} 視覺套件（PyMuPDF, Pillow, python-pptx, python-docx, groq）")
    print(f"    {status_script} vision.py 腳本")

    print(f"\n  {'─'*46}")
    print(f"  生圖能力（Draw Free）：")
    d = report["draw"]
    status_draw_pkg = "✅" if d["draw_packages_installed"] else "❌"
    status_draw = "✅" if d["draw_script_exists"] else "❌"
    status_overlay = "✅" if d["overlay_script_exists"] else "❌"
    print(f"    {status_draw_pkg} Pillow 套件")
    print(f"    {status_draw} draw_free.py 腳本")
    print(f"    {status_overlay} overlay-text.py 腳本")

    print(f"\n  {'─'*46}")
    print(f"  知識庫管線（頻道→轉錄→字幕）：")
    k = report["kb"]
    checks = [
        ("Gemini API Key", k["gemini_key_exists"]),
        ("Groq API Key（轉錄）", k["groq_key_exists"]),
        ("ffmpeg（PATH）", k["ffmpeg_in_path"]),
        ("VLC（燒字幕，預設路徑）", k["vlc_installed"]),
        ("Obsidian（KB 瀏覽）", k["obsidian_installed"]),
        ("yt-dlp 套件", k["yt_dlp_installed"]),
    ]
    for desc, ok in checks:
        status = "✅" if ok else "❌"
        print(f"    {status} {desc}")

    print(f"\n  {'─'*46}")
    print(f"  任務線能力：")
    for lk, linfo in report["lines"].items():
        print(f"    ● {linfo['name']}（{lk}）:")
        for key, ok in linfo.items():
            if key == "name":
                continue
            status = "✅" if ok else "❌"
            print(f"      {status} {key}")
        lp = report["line_packages"].get(lk, {})
        if lp.get("total"):
            miss = lp["missing"]
            print(f"      套件：{lp['total']} 個要裝，缺 {len(miss)}{(' → ' + ', '.join(miss)) if miss else ''}")

    print(f"\n{'='*50}\n")
    return report


def main():
    as_json = "--json" in sys.argv
    report = build_report(as_json=as_json)

    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
