#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""publish_outbox.py — 產出機（PC1/PC2/PC3）把完成的 KB 產出打包到 outbox。

用途
----
三機不互相同步 `knowledge-base/`（只有 notebook 是正本）。產出機把「文字產出」
複製到 `shared\\<machine>\\outbox\\<task_id>\\`，最後寫 `manifest.json`；
notebook 端再用 `harvest_pc.py` 主動 pull 回去。

設計依據：`workspace-bundle/STEP7-HARVEST-DESIGN.md`
- **複製不搬**：本機 KB 條目照舊留著（產出機自己也要能查）
- **manifest.json 最後寫**：先寫 `.tmp` 再 os.replace，收割器看到 manifest 就代表整包完整
- **重跑同一 task 先清空該目錄**，避免新舊檔混在一起
- **冪等**：帳本 `working/_outbox_published.json` 記下檔案大小＋mtime，沒變就跳過

用法
----
    python -X utf8 publish_outbox.py                 # 所有已完成任務（沒變的會跳過）
    python -X utf8 publish_outbox.py --task 1951     # 只處理一筆
    python -X utf8 publish_outbox.py --dry-run       # 只印會做什麼，不寫任何檔
    python -X utf8 publish_outbox.py --force         # 忽略帳本，全部重打包
    python -X utf8 publish_outbox.py --outbox D:\\tmp\\outbox   # 測試用

結束碼 = 失敗的任務數（沿用 smoke_test.py 慣例）。
"""
import argparse
import datetime as dt
import glob
import hashlib
import io
import json
import os
import re
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
SHARED_ROOT = Path(config.SHARED_ROOT)
LEDGER = PROJECT_ROOT / "working" / "_outbox_published.json"
PROGRESS_DIR = PROJECT_ROOT / "working" / "_task_progress"

# 哪些副檔名算「文字產出」
EXTS = {".md", ".srt", ".txt", ".docx"}

# 任務型別 → 是否有 KB 產出可收割
HARVESTABLE = {"youtube", "note", "summary", "video", "subtitle", "audio", "document", "web"}

# 同一支影片的 youtube / note / summary 任務會指向同一個 stem，只打包一次
SEEN_STEMS = set()


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


# ------------------------------------------------------------------ 任務來源
def iter_tasks():
    """讀 shared/tasks（唯一來源）；shared 不存在才退回 task_status.json。"""
    tasks_dir = SHARED_ROOT / "tasks"
    files = sorted(tasks_dir.glob("task_*.json")) if tasks_dir.is_dir() else []
    if files:
        for p in files:
            t = load_json(p)
            if not isinstance(t, dict):
                continue
            info = t.get("task_info") or {}
            status = t.get("status") or info.get("status")
            tid = str(info.get("task_id") or p.stem.split("_", 1)[1])
            yield tid, info, status
        return

    st = load_json(PROJECT_ROOT / "task_status.json", {}) or {}
    items = st.get("tasks") or {}
    if isinstance(items, list):
        items = {str(x.get("task_id")): x for x in items}
    for tid, info in items.items():
        yield str(tid), (info or {}), (info or {}).get("status")


# ------------------------------------------------------------------ 找 stem
def stem_from_progress(tid):
    """worker 完成時會寫 `KB: <md 路徑>`，最可靠。"""
    d = load_json(PROGRESS_DIR / f"{tid}.json")
    msg = (d or {}).get("message") or ""
    if msg.startswith("KB:"):
        p = msg[3:].strip()
        if p.lower().endswith(".md"):
            return Path(p)
    return None


VID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")


def derive_video_id(md_path):
    """note / summary 任務常常沒有 video_id 欄位（獨立派生），從 KB 條目回填。

    順序：`<stem>.link.txt`（channel_watcher 產生，內容就是 URL）→ 逐字稿前 40 行。
    都找不到回空字串（收割器會退回「同名比對」，比較容易誤判衝突）。
    """
    link = md_path.with_name(md_path.stem + ".link.txt")
    try:
        if link.exists():
            m = VID_RE.search(link.read_text(encoding="utf-8", errors="replace"))
            if m:
                return m.group(1)
    except OSError:
        pass
    try:
        with io.open(md_path, encoding="utf-8", errors="replace") as f:
            head = "".join(f.readlines()[:40])
    except OSError:
        head = ""
    m = VID_RE.search(head)
    return m.group(1) if m else ""


def stem_from_link(kb_dir, video_id):
    if not video_id or not kb_dir.is_dir():
        return None
    for f in kb_dir.glob("*.link.txt"):
        try:
            txt = io.open(f, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if video_id in txt:
            return f.with_name(f.name[: -len(".link.txt")] + ".md")
    return None


def resolve_stem(tid, info):
    """回傳 KB 條目 .md 的路徑（不存在回 None）。"""
    ttype = (info.get("type") or "").lower()

    # note / summary：從 source_md 推
    src = info.get("source_md")
    if src:
        p = Path(src)
        if p.suffix.lower() == ".md":
            return p

    # youtube：優先用 worker 的進度訊息，其次用 video_id 比對 .link.txt
    p = stem_from_progress(tid)
    if p and p.exists():
        return p

    vid = (info.get("video_id") or "").strip()
    subdir = (info.get("kb_subdir") or "youtube-clips").strip("/\\")
    kb_dir = KB_ROOT / subdir
    p = stem_from_link(kb_dir, vid)
    if p and p.exists():
        return p

    # 最後：document/web → title 命名的 .md
    title = (info.get("title") or info.get("name") or "").strip()
    if title:
        safe = "".join("_" if c in '\\/:*?"<>|' else c for c in title)
        for cand in (kb_dir / f"{safe}.md", KB_ROOT / f"{safe}.md"):
            if cand.exists():
                return cand
    return None


def collect_files(md_path):
    """同一 stem 的所有產出（逐字稿、srt、link、筆記、摘要…）。"""
    stem = md_path.with_suffix("")
    out = []
    for f in sorted(stem.parent.glob(md_path.stem + "*")):
        if not f.is_file():
            continue
        if f.suffix.lower() not in EXTS:
            continue
        rest = f.name[len(md_path.stem):]
        # `<stem>.md` 或 `<stem> 課程筆記.md`；排除只是前綴相同的其他條目
        if rest and not rest.startswith((".", " ")):
            continue
        out.append(f)
    return out


def local_video_for(md_path):
    """產出機上的影片檔（燒字幕版優先）。"""
    vids = Path(config.get_machine_paths().get("videos") or PROJECT_ROOT / "videos")
    for c in (Path(r"D:\YouTube_Videos") / (md_path.stem + "_字幕.mp4"),
              Path(r"D:\YouTube_Videos") / (md_path.stem + ".mp4"),
              vids / (md_path.stem + ".mp4")):
        if c.exists():
            return str(c)
    return ""


def net_video_for(md_path):
    r"""notebook 點的網路影片路徑（\\<ip>\YouTube_Videos\...）。"""
    local = local_video_for(md_path)
    ip = (config.TAILSCALE_IPS or {}).get(config.MACHINE)
    if local and ip and local.startswith("D:\\YouTube_Videos"):
        return local.replace("D:\\YouTube_Videos", f"\\\\{ip}\\YouTube_Videos", 1)
    return ""


# ------------------------------------------------------------------ 主流程
def publish_one(tid, info, out_root, kb_root, ledger, dry_run=False, force=False):
    ttype = (info.get("type") or "").lower()
    if ttype not in HARVESTABLE:
        return "ignore"  # 不是要收割的型別，安靜跳過

    md_path = resolve_stem(tid, info)
    if not md_path or not Path(md_path).exists():
        return "skip" if ttype in ("video", "subtitle", "audio") else f"#{tid} 找不到 KB 條目（{ttype}）"

    md_path = Path(md_path)
    try:
        md_path = kb_root / md_path.resolve().relative_to(kb_root.resolve()) \
            if str(md_path).lower().startswith(str(kb_root.resolve()).lower()) else md_path
    except Exception:
        pass

    files = collect_files(md_path)
    if not files:
        return f"#{tid} 條目存在但沒有可收割的檔案"

    if md_path.stem in SEEN_STEMS:
        return "skip"  # 同支影片的另一筆任務已打包
    SEEN_STEMS.add(md_path.stem)

    fingerprint = {f.name: [f.stat().st_size, int(f.stat().st_mtime)] for f in files}
    key = f"{config.MACHINE}:{md_path.stem}"
    if not force and ledger.get(key, {}).get("fingerprint") == fingerprint:
        return "skip"  # 沒變，跳過

    dest = out_root / str(tid)
    rel = None
    try:
        rel = str(md_path.resolve().parent.relative_to(kb_root.resolve())).replace("\\", "/")
    except Exception:
        rel = (info.get("kb_subdir") or "").strip("/\\") or "."

    if dry_run:
        log(f"  [DRY] #{tid} {ttype} → {dest}  ({len(files)} 檔, kb_subdir={rel})")
        for f in files:
            log(f"        + {f.name}")
        return "ok"

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    manifest_files = []
    for f in files:
        target = dest / f.name
        shutil.copy2(f, target)
        manifest_files.append({"name": f.name, "bytes": target.stat().st_size,
                               "sha256": sha256(target)})

    # note / summary 任務多半沒有 video_id，從 KB 條目回填（收割器靠它精確去重）
    vid = (info.get("video_id") or "").strip() or derive_video_id(md_path)

    manifest = {
        "schema": 1,
        "task_id": str(tid),
        "machine": config.MACHINE,
        "video_id": vid,
        "title": (info.get("title") or info.get("name") or md_path.stem),
        "kb_subdir": rel,
        "stem": md_path.stem,
        "local_video": local_video_for(md_path),
        "net_video": net_video_for(md_path),
        "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "files": manifest_files,
    }
    tmp = dest / "manifest.json.tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    os.replace(tmp, dest / "manifest.json")  # 最後才出現 → 代表整包完整

    ledger[key] = {"published_at": manifest["created_at"], "task_id": str(tid),
                   "dest": str(dest), "fingerprint": fingerprint}
    log(f"  [OK] #{tid} {ttype} → {dest}（{len(files)} 檔）")
    return "ok"


def main():
    ap = argparse.ArgumentParser(description="把完成的 KB 產出打包到 outbox")
    ap.add_argument("--task", help="只處理指定 task id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="忽略帳本，全部重打包")
    ap.add_argument("--outbox", help="覆寫 outbox 根（預設 shared/<machine>/outbox）")
    ap.add_argument("--kb", help="覆寫 knowledge-base 根（測試用）")
    ap.add_argument("--ledger", help="覆寫帳本路徑（測試用）")
    args = ap.parse_args()

    out_root = Path(args.outbox) if args.outbox else SHARED_ROOT / config.MACHINE / "outbox"
    kb_root = Path(args.kb) if args.kb else KB_ROOT
    ledger = {} if args.dry_run else (load_json(args.ledger or LEDGER, {}) or {})
    SEEN_STEMS.clear()

    log(f"機器 {config.MACHINE}｜KB {kb_root}")
    log(f"outbox {out_root}{'（dry-run）' if args.dry_run else ''}")

    errors, n_ok, n_skip = [], 0, 0
    for tid, info, status in iter_tasks():
        if args.task and str(tid) != str(args.task):
            continue
        if status != "completed":
            continue
        r = publish_one(tid, info, out_root, kb_root, ledger,
                        dry_run=args.dry_run, force=args.force)
        if r == "ok":
            n_ok += 1
        elif r in (None, "skip", "ignore"):
            n_skip += 1
        else:
            errors.append(r)

    if not args.dry_run:
        save_json(args.ledger or LEDGER, ledger)

    log(f"\n完成：打包 {n_ok}｜未變/跳過 {n_skip}｜失敗 {len(errors)}")
    for e in errors[:20]:
        log(f"  ⚠ {e}")
    if len(errors) > 20:
        log(f"  …另有 {len(errors) - 20} 筆")
    return len(errors)


if __name__ == "__main__":
    sys.exit(main())
