#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nas_sync.py — NAS（Synology DS718+）預備工具：連線檢查 + outbox 影子複製。

背景
----
跨機收割目前走「PC 的 SMB 分享」：
    PC 寫入  shared\\<machine>\\outbox\\<tid>\\
    notebook 讀 \\\\<tailscale-ip>\\AI-Agent-Workspace\\shared\\<machine>\\outbox\\<tid>\\
NAS 上線後要改成「PC → NAS 交換區 → notebook」。這支工具是切換前的準備：

    --check    確認 NAS 通不通、資料夾對不對、空間夠不夠（現在就能跑，未設定不算錯）
    --mirror   影子模式：把本機 outbox 複製到 NAS，收割「仍讀舊路徑」，先驗證一段時間

設計原則（沿用 publish_outbox.py）
---------------------------------
- **只複製、不刪除**：NAS 上的檔案不歸這支程式管，避免 /MIR 那種誤刪
- **manifest.json 最後寫**：收割器看到 manifest 才代表整包完整
- **來源沒有 manifest 就跳過**：那包可能還在打包中
- 預設只比「檔案大小」；`--verify` 才對 manifest 的 sha256 逐一驗證
- 沒設定 NAS 時一律回 0（排程跑不會誤報失敗）

用法
----
    python -X utf8 nas_sync.py --check
    python -X utf8 nas_sync.py --check --json
    python -X utf8 nas_sync.py --mirror --dry-run
    python -X utf8 nas_sync.py --mirror
    python -X utf8 nas_sync.py --mirror --machine pc1 --nas-root \\\\NAS\\exchange

設定（環境變數，或直接改 config.py；以下為 PowerShell）
--------------------------------------------------------
    $env:OC_NAS_HOST = "192.168.1.50"
    $env:OC_NAS_ROOT = "\\\\192.168.1.50\\exchange"
    $env:OC_OUTBOX_ROOTS = '{"pc1":"\\\\192.168.1.50\\exchange\\pc1\\outbox"}'   # 收割端切換用

結束碼
------
    0 正常（含「尚未設定」）｜1 檢查發現問題／複製有失敗｜2 參數或連線錯誤
"""
import argparse
import ctypes
import hashlib
import io
import json
import os
import socket
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config

PROJECT_ROOT = Path(config.PROJECT_ROOT)
MANIFEST = "manifest.json"


def log(msg=""):
    print(msg, flush=True)


def human(n):
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0


def disk_free(path):
    """回傳 (free, total)；UNC／對應磁碟機都支援。"""
    try:
        free, total = ctypes.c_ulonglong(0), ctypes.c_ulonglong(0)
        ok = ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            ctypes.c_wchar_p(str(path)),
            ctypes.byref(free), ctypes.byref(total), ctypes.byref(free))
        if ok:
            return free.value, total.value
    except Exception:
        pass
    return None, None


def smb_open(host, port=445, timeout=2.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, ""
    except OSError as e:
        return False, f"{e.__class__.__name__}: {e}"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def nas_settings(args):
    nas_root = (args.nas_root or getattr(config, "NAS_ROOT", "") or "").strip()
    host = (args.nas_host or getattr(config, "NAS_HOST", "") or "").strip()
    if not host and nas_root.startswith("\\\\"):
        host = nas_root.lstrip("\\").split("\\")[0]
    return host, nas_root


# ------------------------------------------------------------------ --check
def do_check(args):
    host, nas_root = nas_settings(args)
    report = {"machine": config.MACHINE, "nas_host": host, "nas_root": nas_root,
              "configured": bool(nas_root), "problems": [], "warnings": [], "dirs": {}}
    log(f"機器 {config.MACHINE}")
    log(f"  NAS_HOST : {host or '（未設定）'}")
    log(f"  NAS_ROOT : {nas_root or '（未設定）'}")

    if not nas_root:
        log("\n狀態：NAS 尚未設定（預備狀態，正常）")
        log("啟用時設定（PowerShell，擇一）：")
        log("  1) $env:OC_NAS_HOST = \"192.168.1.50\"")
        log("     $env:OC_NAS_ROOT = \"\\\\192.168.1.50\\exchange\"")
        log("  2) 直接改 config.py 的 NAS_HOST / NAS_ROOT")
        log("  3) 收割切換：$env:OC_OUTBOX_ROOTS = '{\"pc1\":\"\\\\\\\\192.168.1.50\\\\exchange\\\\pc1\\\\outbox\"}'")
        if args.json:
            log(json.dumps(report, ensure_ascii=False, indent=1))
        return 0

    if host:
        ok, err = smb_open(host)
        log(f"  SMB 445  : {'可連線' if ok else '連不上（' + err + '）'}")
        if not ok:
            report["problems"].append("SMB 445 連不上")
    else:
        log("  SMB 445  : 略過（NAS_ROOT 不是 UNC，可能是已掛載磁碟機）")

    try:
        is_dir = Path(nas_root).is_dir()
    except OSError as e:  # 沒有認證時 UNC 會拋 WinError 1326
        is_dir = False
        log(f"  讀取失敗 : {e.__class__.__name__}: {e}")
        report["problems"].append(f"讀取 NAS_ROOT 失敗：{e}")

    log(f"  根目錄   : {'存在' if is_dir else '不存在或無法讀取'}")
    if not is_dir:
        report["problems"].append("NAS_ROOT 不存在／無法讀取（檢查分享名稱與帳號）")
        if args.json:
            log(json.dumps(report, ensure_ascii=False, indent=1))
        return 1

    machines = sorted(set(["pc1", "pc2", "pc3", config.MACHINE]))
    for m in machines:
        p = Path(nas_root) / m / "outbox"
        try:
            exists = p.is_dir()
        except OSError:
            exists = False
        report["dirs"][m] = exists
        log(f"  {m:<9}: {'OK' if exists else '缺（' + str(p) + '，第一次寫入時建立）'}")
        if not exists:
            report["warnings"].append(f"{m} 目錄未建立（第一次寫入時會自動建立）")

    free, total = disk_free(nas_root)
    if free is not None:
        log(f"  空間     : 可用 {human(free)}／總計 {human(total)}")
        report["free"], report["total"] = free, total
        if free < 20 * 1024 ** 3:
            report["problems"].append(f"可用空間偏低（{human(free)}）")

    if args.write_test:
        probe = Path(nas_root) / f".nas_check_{config.MACHINE}.tmp"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            log("  寫入測試 : OK")
            report["write_test"] = "ok"
        except Exception as e:
            log(f"  寫入測試 : 失敗（{e.__class__.__name__}: {e}）")
            report["write_test"] = "fail"
            report["problems"].append("沒有寫入權限")

    log("")
    if report["problems"]:
        log("⚠ 待處理：" + "；".join(report["problems"]))
    if report["warnings"]:
        log("· 提醒：" + "；".join(report["warnings"]))
    if not report["problems"]:
        log("✅ 檢查通過")
    if args.json:
        log(json.dumps(report, ensure_ascii=False, indent=1))
    return 1 if report["problems"] else 0


# ------------------------------------------------------------------ --mirror
def copy_if_needed(src, dst, verify=False, dry_run=False):
    """回傳 'copied' / 'same' / 'differs'（verify 時 hash 不同會複製）。"""
    need = True
    if dst.exists():
        try:
            if dst.stat().st_size == src.stat().st_size:
                need = False
                if verify and dst.suffix.lower() in (".md", ".srt", ".txt", ".docx"):
                    if sha256_file(src) != sha256_file(dst):
                        need = True
        except OSError:
            need = True
    if not need:
        return "same"
    if dry_run:
        return "copied"
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    with open(src, "rb") as fi, open(tmp, "wb") as fo:
        for chunk in iter(lambda: fi.read(1 << 20), b""):
            fo.write(chunk)
    os.replace(tmp, dst)
    return "copied"


def do_mirror(args):
    _, nas_root = nas_settings(args)
    machine = args.machine or config.MACHINE
    local = Path(args.local_outbox) if args.local_outbox else Path(config.SHARED_ROOT) / machine / "outbox"

    log(f"影子複製：{local} → {nas_root or '（NAS 未設定）'}/{machine}/outbox")
    if not nas_root:
        log("NAS 尚未設定，什麼都沒做（先設 OC_NAS_ROOT）。")
        return 2
    if not local.is_dir():
        log(f"來源 outbox 不存在：{local}")
        return 2

    dest_root = Path(nas_root) / machine / "outbox"
    if not args.dry_run:
        try:
            dest_root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log(f"建立目的資料夾失敗：{e.__class__.__name__}: {e}")
            return 2

    n_pkg = n_wait = 0
    files_copied = files_same = 0
    failures = []

    for pkg in sorted(p for p in local.iterdir() if p.is_dir()):
        if not (pkg / MANIFEST).exists():
            n_wait += 1          # 還在打包，下一輪再來
            continue
        n_pkg += 1
        dest = dest_root / pkg.name
        try:
            # manifest 最後寫：先複製其他檔，再複製 manifest
            others = [f for f in pkg.iterdir() if f.is_file() and f.name != MANIFEST]
            for f in sorted(others, key=lambda x: x.name):
                r = copy_if_needed(f, dest / f.name, verify=args.verify, dry_run=args.dry_run)
                files_copied += (r == "copied")
                files_same += (r == "same")
            mf = pkg / MANIFEST
            r = copy_if_needed(mf, dest / MANIFEST, verify=False, dry_run=args.dry_run)
            files_copied += (r == "copied")
            files_same += (r == "same")
        except Exception as e:
            failures.append(f"{pkg.name}: {e.__class__.__name__}: {e}")

    log(f"\n包 {n_pkg}｜待打包跳過 {n_wait}｜檔案複製 {files_copied}｜已相同 {files_same}"
        f"｜失敗 {len(failures)}{'（dry-run）' if args.dry_run else ''}")
    for f in failures[:20]:
        log(f"  ⚠ {f}")
    if len(failures) > 20:
        log(f"  …另有 {len(failures) - 20} 筆")
    return 1 if failures else 0


def main():
    ap = argparse.ArgumentParser(description="NAS 預備工具：連線檢查／outbox 影子複製")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="檢查設定、連線、資料夾、空間（預設）")
    g.add_argument("--mirror", action="store_true", help="把本機 outbox 影子複製到 NAS")
    ap.add_argument("--nas-host", help="覆寫 NAS_HOST（預設讀 config／OC_NAS_HOST）")
    ap.add_argument("--nas-root", help="覆寫 NAS_ROOT（預設讀 config／OC_NAS_ROOT）")
    ap.add_argument("--machine", help="mirror 用：機器代號（預設 config.MACHINE）")
    ap.add_argument("--local-outbox", help="mirror 用：來源 outbox（預設 shared/<machine>/outbox）")
    ap.add_argument("--dry-run", action="store_true", help="只印會做什麼，不寫檔")
    ap.add_argument("--verify", action="store_true", help="mirror 時對 manifest 的檔案做 sha256 比對")
    ap.add_argument("--write-test", action="store_true", help="check 時順便測寫入權限")
    ap.add_argument("--json", action="store_true", help="check 時輸出 JSON")
    args = ap.parse_args()

    if args.mirror:
        return do_mirror(args)
    return do_check(args)


if __name__ == "__main__":
    sys.exit(main())
