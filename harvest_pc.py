#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""harvest_pc.py — notebook 端「單向收割」：把產出機 outbox 的文字產出收進 KB。

架構（`workspace-bundle/STEP7-HARVEST-DESIGN.md`）：
    PC1/PC2/PC3                          notebook
    shared\<machine>\outbox\<tid>\  ──UNC 唯讀──▶  knowledge-base\<kb_subdir>\

- **pull 不 push**：只有 notebook 讀 PC，PC 不需要寫入 notebook 的權限。
- **PC 端只開唯讀 SMB**（見 STEP7 設計稿 §6）。
- **manifest.json 最後寫**，看到它就代表整包完整；沒看到就當「還沒好」跳過。
- 衝突（同名檔內容不同）**不覆蓋**，整包移到 `knowledge-base\_harvest_conflicts\`。
- **例外：`--replace` 指定的檔名可以用產出機版本覆蓋**（例：prompt 改版後重生摘要）。
  覆蓋前舊檔會備份到 `knowledge-base\_harvest_overwritten\<machine>\<tid>\<時間>\`，
  不會無聲消失。同家族的「逐字稿／筆記」預設仍保留 notebook 正本。

用法
----
    python -X utf8 harvest_pc.py                    # 收所有可連線的機器
    python -X utf8 harvest_pc.py --machine pc1      # 只收一台
    python -X utf8 harvest_pc.py --dry-run          # 只列計畫，不寫檔、不動帳本
    python -X utf8 harvest_pc.py --machine pc1 --replace " 摘要.md" --replace " 摘要.docx"
    python -X utf8 harvest_pc.py --root D:\tmp\outbox --kb D:\tmp\kb   # 測試用

結束碼 = 失敗數（offline 不算失敗）。
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
import shutil
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config

PROJECT_ROOT = Path(config.PROJECT_ROOT)
KB_ROOT = PROJECT_ROOT / "knowledge-base"
LEDGER = PROJECT_ROOT / "working" / "harvest_ledger.json"


def log(msg):
    print(msg, flush=True)


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def load_json(path, default=None):
    try:
        with io.open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def safe_rel(subdir):
    """manifest 的 kb_subdir 只能是 KB 內的相對路徑。"""
    if not subdir or subdir in (".", "/"):
        return Path(".")
    p = Path(str(subdir).replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or ":" in str(p):
        return None
    return p


def machine_root(machine):
    ip = (config.TAILSCALE_IPS or {}).get(machine)
    if not ip:
        return None
    return Path(f"\\\\{ip}\\AI-Agent-Workspace\\shared\\{machine}\\outbox")


def base_stem(stem):
    """`<stem> 摘要` / `<stem> 課程筆記` → `<stem>`，用來判斷是否同一支影片。"""
    for suf in (" 摘要", " 課程筆記", " 重點整理"):
        if stem.endswith(suf):
            return stem[: -len(suf)]
    return stem


# ------------------------------------------------------------------ 收割單包
def harvest_one(pkg_dir, machine, kb_root, ledger, index, dry_run=False, replace=()):
    """回傳 (結果, 說明)。結果：harvested / skipped_same / skipped_exists / conflict / bad / error

    replace：檔名子字串清單。同名但內容不同時，命中者「允許被產出機版本覆蓋」（先備份舊檔），
    沒命中者照舊保留 notebook 正本。用於 prompt 改版後重生摘要那種「本機確實該換」的情境。
    """
    manifest = load_json(pkg_dir / "manifest.json")
    if not isinstance(manifest, dict):
        return "error", "manifest.json 讀不到"

    schema = manifest.get("schema")
    if schema != 1:
        return "bad", f"不認識的 manifest schema={schema}（跳過，不猜）"

    task_id = str(manifest.get("task_id") or pkg_dir.name)
    key = f"{machine}:{task_id}"
    video_id = (manifest.get("video_id") or "").strip()
    files = manifest.get("files") or []
    if not files:
        return "bad", "manifest 沒有 files"

    rel = safe_rel(manifest.get("kb_subdir"))
    if rel is None:
        return "bad", f"kb_subdir 不合法：{manifest.get('kb_subdir')!r}"
    dest_dir = kb_root / rel

    # 1) 已在 KB（video_id 精確比對）
    #    同一支影片的「逐字稿／摘要／筆記」是同一組檔名家族 → 繼續往下逐檔補齊（只缺摘要也能補）
    #    不同檔名家族 → 代表 notebook 用不同日期前綴存在，跳過以免產生重複條目
    names = [f.get("name") or "" for f in files]
    same_family = False
    if video_id and video_id in index:
        existing = Path(str(index[video_id]))
        pkg_stem = (manifest.get("stem") or "").strip()
        if pkg_stem:
            same_family = base_stem(existing.stem) == base_stem(pkg_stem)
        else:
            fam = base_stem(existing.stem)
            same_family = any(
                n == existing.name
                or n.startswith(fam + " ")
                or n.startswith(fam + ".")
                for n in names
            )
        if not same_family:
            log(f"    ⏭ 已在 KB（檔名不同）：{video_id} → {existing}")
            return "skipped_exists", str(existing)
        log(f"    ↪ 同支影片已在 KB（{existing.name}），逐檔補齊缺的產出")

    # 2) 帳本已收過且 sha256 全對
    rec = ledger.get(key) or {}
    if rec.get("sha256") and all(rec["sha256"].get(f.get("name")) == f.get("sha256") for f in files):
        return "skipped_same", "帳本相符"

    # 3) 逐檔比對
    #    - 不存在 → 要補
    #    - 存在但內容不同：同一支影片（同 stem）→ 保留 notebook 正本、不覆蓋（kept）；
    #      **但檔名命中 --replace → 走「覆蓋」（先備份舊檔）**
    #      不同支影片（僅同名）→ 視為衝突，整包隔離
    #    - 存在且相同 → 略過
    def _want_replace(name):
        return bool(replace) and any(p and p in name for p in replace)

    conflicts, already, kept, missing, replaced = [], [], [], [], []
    for f in files:
        name = f.get("name") or ""
        if not name or "/" in name or "\\" in name or name in (".", ".."):
            return "bad", f"檔名不合法：{name!r}"
        target = dest_dir / name
        if not target.exists():
            missing.append(f)
            continue
        try:
            if sha256(target) == f.get("sha256"):
                already.append(name)
            elif same_family:
                if _want_replace(name):
                    replaced.append(f)
                else:
                    kept.append(name)
            else:
                conflicts.append(name)
        except OSError:
            conflicts.append(name)
    if conflicts:
        if not dry_run:
            dst = kb_root / "_harvest_conflicts" / machine / task_id
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(pkg_dir, dst)
        return "conflict", f"同名不同內容：{', '.join(conflicts[:3])} → _harvest_conflicts/{machine}/{task_id}"
    if not missing and not replaced:
        msg = "KB 已有相同檔案" if not kept else f"KB 已有（保留正本）：{', '.join(kept[:3])}"
        return "skipped_same", msg
    if kept:
        log(f"    ⚠ 保留 notebook 既有版本（內容不同，未覆蓋）：{', '.join(kept[:3])}")
    if replaced:
        log(f"    ↻ 覆蓋（--replace）：{', '.join(f['name'] for f in replaced[:3])}")
        if dry_run:
            log(f"    [DRY] 舊檔會先備份到 _harvest_overwritten/{machine}/{task_id}/")

    if dry_run:
        log(f"    [DRY] → {dest_dir}（補 {len(missing)} 檔、覆蓋 {len(replaced)} 檔、略過 {len(already) + len(kept)} 檔）")
        return "harvested", f"(dry-run) {dest_dir}"

    # 4) 逐檔複製 → 驗 sha256 → 全過才寫帳本（覆蓋前先把舊檔備份）
    dest_dir.mkdir(parents=True, exist_ok=True)
    written = []
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = kb_root / "_harvest_overwritten" / machine / task_id / stamp
    try:
        for f in missing + replaced:
            name = f["name"]
            src = pkg_dir / name
            if not src.exists():
                return "error", f"outbox 缺檔：{name}"
            target = dest_dir / name
            if target.exists():
                backup_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup_dir / name)
            tmp = dest_dir / (name + ".part")
            shutil.copy2(src, tmp)
            got = sha256(tmp)
            if got != f.get("sha256"):
                tmp.unlink(missing_ok=True)
                return "error", f"sha256 不符：{name}"
            os.replace(tmp, target)
            written.append(name)
    except Exception as e:
        return "error", f"複製失敗：{e}"

    ledger[key] = {
        "video_id": video_id,
        "harvested_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "dest": str(dest_dir / written[0]) if written else str(dest_dir),
        "title": manifest.get("title"),
        "sha256": {f["name"]: f.get("sha256") for f in files},
    }
    if video_id:
        # 索引一律指向「逐字稿本體」`<stem>.md`；指向 ` 摘要.md` 會讓下一次判斷不同家族
        base = dest_dir / f"{(manifest.get('stem') or '').strip()}.md"
        if (manifest.get("stem") or "").strip() and base.exists():
            index[video_id] = str(base)
        elif video_id not in index:
            index[video_id] = str(dest_dir / written[0]) if written else str(dest_dir)
    return "harvested", f"{len(written)} 檔 → {dest_dir}"


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="收割產出機 outbox 到 notebook KB")
    ap.add_argument("--machine", action="append", help="只收指定機器（可重複）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--root", help="覆寫 outbox 根（測試用，配 --machine 名稱）")
    ap.add_argument("--kb", help="覆寫 KB 根（測試用）")
    ap.add_argument("--ledger", help="覆寫帳本路徑（預設 working\\harvest_ledger.json）")
    ap.add_argument("--no-dedupe", action="store_true", help="不做 video_id 去重（僅測試）")
    ap.add_argument("--replace", action="append", default=[], metavar="PATTERN",
                    help="同名但內容不同時，允許用產出機版本覆蓋的檔名（子字串比對，可重複）。"
                         "覆蓋前舊檔會備份到 knowledge-base\\_harvest_overwritten\\<machine>\\<tid>\\<時間>\\。"
                         "例：--replace \" 摘要.md\" --replace \" 摘要.docx\"")
    args = ap.parse_args()

    kb_root = Path(args.kb) if args.kb else KB_ROOT
    if args.ledger:
        ledger_path = Path(args.ledger)
    elif args.kb:
        ledger_path = kb_root.parent / "harvest_ledger.json"   # 測試不污染正式帳本
    else:
        ledger_path = LEDGER
    machines = args.machine or ["pc1", "pc2", "pc3"]
    ledger = {} if args.dry_run else (load_json(ledger_path, {}) or {})

    index = {}
    if not args.no_dedupe:
        log("建立 KB video_id 索引（第一次約 1 分鐘）…")
        try:
            import channel_watcher
            index = channel_watcher.kb_video_index(kb_root=kb_root, refresh=True) or {}
            log(f"  索引 {len(index)} 筆")
        except Exception as e:
            log(f"  ⚠ 索引建立失敗（改為不去重）：{e}")

    counts = {"harvested": 0, "skipped_same": 0, "skipped_exists": 0,
              "conflict": 0, "bad": 0, "error": 0, "offline": 0}
    details = []

    for machine in machines:
        root = Path(args.root) if (args.root and len(machines) == 1) else machine_root(machine)
        if root is None:
            log(f"\n[{machine}] 未設定 Tailscale IP，略過")
            counts["offline"] += 1
            continue
        log(f"\n[{machine}] {root}")
        try:
            if not root.is_dir():
                log("  offline（連不到，下次再試）")
                counts["offline"] += 1
                continue
            pkgs = sorted(p for p in root.iterdir() if p.is_dir())
        except OSError as e:
            # 跨機 UNC 在「沒有認證」時會拋 WinError 1326 而不是回 False，
            # 排程跑的時候不能因此中斷整批（pc1 收完、pc2 沒設帳號就會這樣）
            log(f"  offline（{e.__class__.__name__}: {e}）")
            counts["offline"] += 1
            continue

        for pkg in pkgs:
            if not (pkg / "manifest.json").exists():
                continue  # 還沒寫好 manifest
            res, msg = harvest_one(pkg, machine, kb_root, ledger, index, args.dry_run,
                                   replace=tuple(args.replace))
            counts[res] = counts.get(res, 0) + 1
            mark = {"harvested": "✅", "conflict": "⚠", "bad": "⚠",
                    "error": "❌", "skipped_same": "·", "skipped_exists": "⏭"}.get(res, "·")
            log(f"  {mark} {pkg.name}: {msg}")
            if res in ("conflict", "bad", "error"):
                details.append(f"{machine}/{pkg.name}: {msg}")

    if not args.dry_run:
        save_json(ledger_path, ledger)

    log("\n" + "｜".join(f"{k} {v}" for k, v in counts.items() if v))
    for d in details:
        log(f"  ⚠ {d}")

    # 失敗數 = error + bad（offline / conflict 不算「程式失敗」，但要人看）
    return counts["error"] + counts["bad"]


if __name__ == "__main__":
    sys.exit(main())
