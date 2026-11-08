r"""每日把 notebook 的正本資料備份到 NAS（`backup` 分享）。

備份內容（全部單向 notebook → NAS，永不反向）：
  1. `knowledge-base\`  → `\\\\<NAS>\\backup\\knowledge-base\`   （robocopy /MIR）
  2. `financial_news\\finance.db` → `\\\\<NAS>\\backup\\finance_db\\finance.db`（SQLite backup API，一致性快照）
  3. `shared\`          → `\\\\<NAS>\\backup\\shared\`            （robocopy /MIR；控制面鏡像）

為什麼不用「直接複製 finance.db」：DB 可能被其他程序開著，直接 copy 會拿到半寫入的頁；
`sqlite3.Connection.backup()` 會產生一致性快照，且不需要停掉任何程式。

用法：
  python -X utf8 nas_backup.py              # 正常備份（增量，第二次以後很快）
  python -X utf8 nas_backup.py --dry-run    # 只檢查可達性與大小，不寫入
  python -X utf8 nas_backup.py --skip-shared

環境變數（未設就用預設）：
  OC_NAS_HOST          預設 192.168.1.121
  OC_NAS_BACKUP_ROOT   預設 \\\\<OC_NAS_HOST>\\backup

對應登記：`workspace-bundle/NAS-WHITEPAPER.md` §5 的 N-02（backup 分享）／N-11（本排程）。
排程由 `backup_daily.bat` 呼叫，日誌在 `logs\\nas_backup.log`。
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KB = ROOT / "knowledge-base"
SHARED = ROOT / "shared"
FIN_DB = ROOT / "financial_news" / "finance.db"
LOG_DIR = ROOT / "logs"


def _smb_reachable(host: str, timeout: float = 3.0) -> bool:
    """快速確認 SMB 445 是否可連（避免 is_dir() 在跨機無認證時卡很久）。"""
    import socket
    try:
        with socket.create_connection((host, 445), timeout=timeout):
            return True
    except OSError:
        return False


def nas_root() -> Path:
    """回傳可用的 NAS backup 根目錄。

    優先序：
      1. `OC_NAS_BACKUP_ROOT`（明確指定就只用它）
      2. `OC_NAS_HOST`
      3. 內建候選：LAN `192.168.1.121` → Tailscale `100.65.113.20`

    為什麼要 fallback：notebook 在家走 LAN，外出只剩 Tailscale；
    排程（01:30）不會有人顧，寫死其中一邊就一定有一邊會失敗。
    """
    explicit = os.environ.get("OC_NAS_BACKUP_ROOT")
    if explicit:
        return Path(explicit)
    host = os.environ.get("OC_NAS_HOST")
    candidates = [host] if host else [
        "192.168.1.121",                  # 在家：LAN 直連，最快
        "100.65.113.20",                  # 外出：Tailscale IP（節點固定）
        "datanas.tail6b5f31.ts.net",      # 保險：MagicDNS FQDN
    ]
    for h in candidates:
        if h and _smb_reachable(h):
            return Path(rf"\\{h}\backup")
    # 全部不通：回第一個候選，交給 main() 印出「不可達」
    return Path(rf"\\{candidates[0]}\backup")


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def dir_stats(p: Path) -> tuple[int, int]:
    files = size = 0
    for base, _dirs, names in os.walk(p):
        for n in names:
            fp = Path(base) / n
            try:
                size += fp.stat().st_size
                files += 1
            except OSError:
                pass
    return files, size


def robocopy(src: Path, dst: Path, log: list[str]) -> int:
    """/MIR 鏡像；rc<8 視為成功（0=無變更、1=有複製、2=有額外檔案被清、3=兩者）。"""
    dst.mkdir(parents=True, exist_ok=True)
    cmd = [
        "robocopy", str(src), str(dst),
        "/MIR", "/R:2", "/W:2", "/NFL", "/NDL", "/NP",
    ]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True)
    dt = time.time() - t0
    rc = proc.returncode
    log.append(f"  robocopy {src.name} → {dst} rc={rc} ({dt:.1f}s)")
    return rc


def backup_db(dst: Path, log: list[str]) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".db.part")
    t0 = time.time()
    try:
        src = sqlite3.connect(f"file:{FIN_DB}?mode=ro", uri=True)
        out = sqlite3.connect(tmp)
        with out:
            src.backup(out)
        out.close()
        src.close()
        os.replace(tmp, dst)
    except Exception as exc:  # noqa: BLE001
        log.append(f"  finance.db 失敗：{type(exc).__name__}: {exc}")
        for p in (tmp, dst):
            try:
                if p.exists() and p == tmp:
                    p.unlink()
            except OSError:
                pass
        return False
    # 驗證：quick_check + 大小
    ok = True
    try:
        c = sqlite3.connect(f"file:{dst}?mode=ro", uri=True)
        qc = c.execute("PRAGMA quick_check").fetchone()[0]
        rows = c.execute("select count(*) from events").fetchone()[0]
        c.close()
        if qc != "ok":
            log.append(f"  finance.db quick_check = {qc}")
            ok = False
        else:
            log.append(f"  finance.db OK：{human(dst.stat().st_size)}、events={rows}（{time.time()-t0:.1f}s）")
    except Exception as exc:  # noqa: BLE001
        log.append(f"  finance.db 驗證失敗：{type(exc).__name__}: {exc}")
        ok = False
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="notebook → NAS 每日備份")
    ap.add_argument("--dry-run", action="store_true", help="只檢查，不寫入")
    ap.add_argument("--skip-shared", action="store_true", help="跳過 shared（通常不需要）")
    args = ap.parse_args()

    root = nas_root()
    log: list[str] = [f"=== {datetime.now():%Y-%m-%d %H:%M:%S}  備份 → {root}"]
    ok = True

    if not root.is_dir():
        print(f"NAS backup 不可達：{root}", file=sys.stderr)
        print("（檢查 OC_NAS_HOST、cmdkey 認證、NAS 是否開機）", file=sys.stderr)
        return 2

    kf, ks = dir_stats(KB)
    sf, ss = dir_stats(SHARED)
    log.append(f"  來源：knowledge-base {kf} 檔 / {human(ks)}；shared {sf} 檔 / {human(ss)}")
    if FIN_DB.exists():
        log.append(f"  來源：finance.db {human(FIN_DB.stat().st_size)}（{datetime.fromtimestamp(FIN_DB.stat().st_mtime):%Y-%m-%d}）")
    else:
        log.append("  警告：找不到 financial_news\\finance.db")
        ok = False

    if args.dry_run:
        for line in log:
            print(line)
        print("（--dry-run：沒有寫入）")
        return 0 if ok else 1

    rc = robocopy(KB, root / "knowledge-base", log)
    if rc >= 8:
        ok = False

    if FIN_DB.exists() and not backup_db(root / "finance_db" / "finance.db", log):
        ok = False

    if not args.skip_shared:
        rc = robocopy(SHARED, root / "shared", log)
        if rc >= 8:
            ok = False

    # 備份後比對檔案數（只看本機 vs NAS）
    try:
        nf, ns = dir_stats(root / "knowledge-base")
        log.append(f"  驗證：NAS knowledge-base {nf} 檔 / {human(ns)}（本機 {kf} 檔）")
        if nf != kf:
            log.append("  ⚠ 檔案數不一致，請人工確認（可能有檔案正在寫入）")
    except OSError as exc:
        log.append(f"  驗證失敗：{exc}")

    log.append("  結果：" + ("OK" if ok else "有失敗項目"))
    text = "\n".join(log)
    print(text)
    LOG_DIR.mkdir(exist_ok=True)
    with open(LOG_DIR / "nas_backup.log", "a", encoding="utf-8") as f:
        f.write(text + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
