#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
harvest_report.py — 收成報告：任務狀態總覽 + KB 待補課程筆記清單
============================================================
把「已收成但還沒產出課程筆記」的知識源找出來（＝待驗收/待補筆記），
並彙整 task_status.json 的任務狀態，方便 notebook 端收成管理。

用法:
  python harvest_report.py                 # 印出報告並寫到 working\\harvest_report_YYYY-MM-DD.md
  python harvest_report.py -o 檔案.md        # 指定輸出
  python harvest_report.py --kb-only        # 只掃 KB 待補筆記，不看任務狀態
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(os.path.dirname(os.path.abspath(__file__)))
KB = ROOT / "knowledge-base"
TASK_STATUS = ROOT / "task_status.json"
PROGRESS = ROOT / "working" / "_task_progress"


def is_transcript_md(p: Path) -> bool:
    if p.suffix.lower() != ".md":
        return False
    name = p.name
    if "課程筆記" in name or "_preview_" in name:
        return False
    try:
        head = p.read_text(encoding="utf-8", errors="replace")[:400]
    except OSError:
        return False
    return "## 逐字稿" in head or "# YouTube Metadata" in head or "## 影片資訊" in head


def expected_note(p: Path) -> Path:
    stem = re.sub(r'[\\/:*?"<>|]', "_", p.stem)
    return p.parent / f"{stem} 課程筆記.md"


def has_cover_note(p: Path) -> bool:
    if expected_note(p).exists():
        return True
    try:
        return any(f.is_file() and f.name.endswith("課程筆記.md")
                    for f in p.parent.iterdir())
    except OSError:
        return False


KB_EXCLUDE = ("金融交易",)


def kb_pending():
    rows = []
    for p in sorted(KB.rglob("*.md")):
        rel = p.relative_to(KB)
        if rel.parts and rel.parts[0] in KB_EXCLUDE:
            continue
        if is_transcript_md(p) and not expected_note(p).exists():
            rows.append((p, expected_note(p)))
    return rows


def task_progress_stage(tid):
    pf = PROGRESS / f"{tid}.json"
    if pf.exists():
        try:
            with open(pf, "r", encoding="utf-8") as f:
                d = json.load(f)
            return d.get("stage") or d.get("status")
        except Exception:
            pass
    return None


def task_summary():
    if not TASK_STATUS.exists():
        return {}
    with open(TASK_STATUS, "r", encoding="utf-8") as f:
        data = json.load(f)
    tasks = data.get("tasks", {})
    summary = {}
    for tid, t in tasks.items():
        s = (t or {}).get("status", "unknown")
        summary.setdefault(s, []).append((tid, t))
    return summary


def build_report():
    lines = ["# 收成報告", "", f"> 產生時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    summary = task_summary()
    if summary:
        order = ["assigned", "pending", "processing", "paused",
                 "completed", "done", "failed", "skipped"]
        rows = [(s, len(summary[s])) for s in order if s in summary]
        lines.append("## 任務總覽")
        for s, n in rows:
            lines.append(f"- {s}: {n}")
        lines.append("")
        failed = summary.get("failed") or []
        if failed:
            lines.append("## 失敗任務（需人工處理）")
            lines.append("")
            for tid, t in failed:
                stage = task_progress_stage(tid)
                err = (t.get("last_error") or "").strip()
                extra = f" | 進度={stage}" if stage else ""
                lines.append(f"- #{tid} {t.get('name') or t.get('title')} | {err[:120]}{extra}")
            lines.append("")
    lines.append("## KB 待補課程筆記（已收成、尚無「課程筆記.md」）")
    lines.append("")
    pending = kb_pending()
    if pending:
        for p, note in pending:
            lines.append(f"- {p.relative_to(KB)}")
    else:
        lines.append("- （無）")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="收成報告：任務狀態 + KB 待補課程筆記清單")
    ap.add_argument("-o", "--out", default=ROOT / "working" /
                    f"harvest_report_{datetime.now().strftime('%Y-%m-%d')}.md")
    ap.add_argument("--kb-only", action="store_true",
                    help="只掃 KB 待補筆記，不看任務狀態")
    args = ap.parse_args()
    report = build_report()
    if args.kb_only:
        start = report.find("## KB 待補")
        if start >= 0:
            report = report[start:]
        else:
            report = "# 收成報告\n\n（無 KB 待補資料）"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[寫出] {out}")


if __name__ == "__main__":
    main()