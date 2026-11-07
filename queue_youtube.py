#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""queue_youtube.py — 用「命令列」把 YouTube 影片／播放清單排進任務佇列。

為什麼要有這支：
  GUI 的「新增任務 → YouTube」只能在有畫面的機器上按，且以前**不記錄來源網址**
  （2026-11-06 事故：17 筆任務失敗後查不出是從哪份清單展開的）。這支補上：
  `source_url` 寫進任務、`logs\\youtube_imports.log` 留一筆匯入紀錄、可 `--dry-run` 先看會建幾筆。

用法（在**產出機**上跑，例如 PC1）：
    python -X utf8 queue_youtube.py --url "https://www.youtube.com/playlist?list=XXXX" --dry-run
    python -X utf8 queue_youtube.py --url "..."                    # 真正建立（含筆記＋摘要）
    python -X utf8 queue_youtube.py --url "..." --no-note --no-summary
    python -X utf8 queue_youtube.py --url "..." --limit 5
    python -X utf8 queue_youtube.py --url "..." --include-failed    # 已 failed 的也重建（預設略過）

去重（與 GUI 同一套規則）：
  1. 已在知識庫（任何目錄）的 video_id → 略過
  2. 已有 pending／processing／assigned 任務的 video_id → 略過
  3. 預設**略過 failed**（想重跑用 `--include-failed`，或直接 `worker.py --retry-failed`）
"""
import argparse
import datetime
import json
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config
from scheduler import load_task_status, save_task_status

SHARED_TASKS = Path(config.PROJECT_ROOT) / "shared" / "tasks"
RUNTIME_STATUS = ("pending", "processing", "assigned")


def log(msg):
    print(msg, flush=True)


def main():
    ap = argparse.ArgumentParser(description="把 YouTube 網址展開成任務（可 --dry-run）")
    ap.add_argument("--url", required=True, help="影片／播放清單／頻道網址")
    ap.add_argument("--limit", type=int, default=0, help="最多幾支（0＝全部）")
    ap.add_argument("--kb-subdir", default="youtube-clips", help="收成到知識庫的哪個子目錄")
    ap.add_argument("--assigned-to", default="", help="指定機器（pc1/pc2/notebook；空＝任一）")
    ap.add_argument("--no-kb", action="store_true", help="不收成知識庫（只留本機產出）")
    ap.add_argument("--no-note", action="store_true", help="不產課程筆記")
    ap.add_argument("--no-summary", action="store_true", help="不產摘要")
    ap.add_argument("--burn-subs", action="store_true", help="有字幕也下載影片並燒字幕")
    ap.add_argument("--include-failed", action="store_true", help="已 failed 的影片也重新建立任務")
    ap.add_argument("--dry-run", action="store_true", help="只列出會建立哪些，不寫入")
    args = ap.parse_args()

    import channel_watcher as cw

    url = args.url.strip()
    log(f"來源：{url}")
    entries = cw.expand_youtube_entries(url, limit=(args.limit or None))
    if not entries:
        log("[ERR] 展開不到任何影片（網址無效、清單為空或不可見）")
        return 2
    log(f"展開 {len(entries)} 支（cookies: {'有' if cw.yt_cookies_args() else '無'}）")

    log("比對知識庫（首次約 1 分鐘）…")
    kb_index = cw.kb_video_index(refresh=True)

    data = load_task_status()
    tasks = data.get("tasks", {})

    # 既有任務：video_id → status（mirror ＋ shared 兩邊都看）
    existing = {}
    for t in tasks.values():
        if t.get("video_id"):
            existing.setdefault(t["video_id"], t.get("status"))
    if SHARED_TASKS.is_dir():
        for f in SHARED_TASKS.glob("task_*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            info = d.get("task_info") or {}
            vid = info.get("video_id")
            if vid:
                existing.setdefault(vid, d.get("status") or info.get("status"))

    used_ids = [int(k) for k in tasks if str(k).isdigit()]
    if SHARED_TASKS.is_dir():
        for f in SHARED_TASKS.glob("task_*.json"):
            try:
                used_ids.append(int(f.stem.split("_", 1)[1]))
            except (IndexError, ValueError):
                pass
    next_id = (max(used_ids) if used_ids else 0) + 1

    created, skipped_kb, skipped_dup, skipped_failed = [], 0, 0, 0
    now_iso = datetime.datetime.now().isoformat()
    for e in entries:
        vid = (e.get("id") or "").strip()
        if not vid:
            continue
        if vid in kb_index:
            skipped_kb += 1
            continue
        st = existing.get(vid)
        if st in RUNTIME_STATUS:
            skipped_dup += 1
            continue
        if st == "failed" and not args.include_failed:
            skipped_failed += 1
            continue
        title = e.get("title") or vid
        created.append((str(next_id), vid, title))
        next_id += 1

    log(f"\n將建立 {len(created)} 筆｜已在知識庫 {skipped_kb}｜已有待處理任務 {skipped_dup}"
        f"｜已 failed 略過 {skipped_failed}")
    for tid, vid, title in created[:10]:
        log(f"  #{tid} {vid} {str(title)[:60]}")
    if len(created) > 10:
        log(f"  …另有 {len(created) - 10} 筆")

    if args.dry_run:
        log("\n(--dry-run：沒有寫入任何檔案)")
        return 0
    if not created:
        log("\n沒有需要新增的任務")
        return 0

    os.makedirs(SHARED_TASKS, exist_ok=True)
    for tid, vid, title in created:
        info = {
            "type": "youtube",
            "status": "pending",
            "assigned_to": args.assigned_to or None,
            "priority": 0,
            "name": title,
            "title": title,
            "video_id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "source_url": url[:300],          # 以後查得到「這批哪來的」
            "kb_subdir": args.kb_subdir,
            "harvest_to_kb": not args.no_kb,
            "auto_note": not args.no_note,
            "auto_summary": not args.no_summary,
            "burn_subs": bool(args.burn_subs),
            "note": f"queue_youtube.py（來源：{url[:80]}）",
            "discovered_at": now_iso,
            "started_at": None,
            "completed_at": None,
            "last_error": None,
            "machine": None,
            "output_keys": [],
        }
        tasks[tid] = info
        shared = {
            "task_id": tid,
            "task_info": info,
            "status": "pending",
            "assigned_to": args.assigned_to or None,
        }
        (SHARED_TASKS / f"task_{tid}.json").write_text(
            json.dumps(shared, indent=2, ensure_ascii=False), encoding="utf-8")

    data["task_counter"] = max([int(k) for k in tasks if str(k).isdigit()] or [0])
    data["generated_at"] = now_iso
    save_task_status(data)

    # 匯入紀錄（與 GUI 共用同一個檔）
    try:
        logs = Path(config.PROJECT_ROOT) / "logs"
        logs.mkdir(exist_ok=True)
        with open(logs / "youtube_imports.log", "a", encoding="utf-8") as f:
            f.write(f"{now_iso}\t來源={url}\t展開={len(entries)}\t建立={len(created)}"
                    f"\t已在KB={skipped_kb}\t重複={skipped_dup}\tfailed略過={skipped_failed}"
                    f"\t{' '.join(t[0] for t in created)}\n")
    except Exception as e:
        log(f"[warn] 匯入紀錄沒寫成：{e}")

    log(f"\n[OK] 已建立 {len(created)} 筆任務（#{created[0][0]}–#{created[-1][0]}）")
    log("下一步：python -X utf8 worker.py")
    if created and (not args.no_note or not args.no_summary):
        log("註：worker 路徑的 note／summary 不計每日 20 筆配額（會一次跑完）；"
            "只有 channel_watcher／backfill 才計配額。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
