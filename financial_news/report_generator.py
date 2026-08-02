#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily report generator - writes financial analysis into the knowledge base
as a markdown file, readable via Obsidian.

Output: knowledge-base/金融/每日報告/YYYY-MM-DD.md
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
import market_data

KB_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "knowledge-base",
    "金融",
    "每日報告",
)

CATEGORY_NAMES = {
    "stock": "股市",
    "bond": "債市",
    "currency": "匯市",
    "commodity": "商品(油金)",
    "geopolitics": "地緣政治",
    "macro": "總體經濟",
    "other": "其他",
}

SEV_NAMES = {0: "低", 1: "中低", 2: "中高", 3: "高"}


def _fmt_ts(ts):
    if not ts:
        return ""
    try:
        d = datetime.fromisoformat(ts)
        if d.tzinfo:
            d = d.astimezone(timezone(timedelta(hours=8)))
        return d.strftime("%m-%d %H:%M")
    except Exception:
        return ts


def generate_report(events, title_date=None):
    """Generate markdown report text for a list of events."""
    now = datetime.now(timezone(timedelta(hours=8)))
    date_str = title_date or now.strftime("%Y-%m-%d")
    lines = []
    lines.append(f"# 金融重點報告 {date_str}")
    lines.append("")
    lines.append(f"> 產出時間: {now.strftime('%Y-%m-%d %H:%M')}（台灣時間）")
    lines.append("> 本報告由 AI 自動生成，僅供參考，不構成投資建議。")
    lines.append("")

    # --- Market snapshot ---
    lines.append("## 市場行情快照")
    lines.append("")
    snap = market_data.latest_table()
    if snap:
        lines.append("```")
        lines.extend(snap)
        lines.append("```")
        lines.append("")

    # --- Top important events ---
    important = [e for e in events if e["severity"] >= 2]
    lines.append("## 重大事件（severity ≥ 2）")
    lines.append("")
    if not important:
        lines.append("_今日無重大事件。_")
    else:
        for e in sorted(important, key=lambda x: (-x["severity"], x["published"] or "")):
            sev = SEV_NAMES.get(e["severity"], "?")
            cat = CATEGORY_NAMES.get(e["category"], e["category"] or "未分類")
            senti = e["sentiment"] or "neutral"
            lines.append(f"- **[{sev}][{cat}][{senti}]** {e['title']}")
            lines.append(f"  - 影響: {e['impact_notes'] or '無'}")
            if e.get("related_tickers"):
                lines.append(f"  - 標的: `{e['related_tickers']}`")
            lines.append("")
    lines.append("---")
    lines.append("")

    # --- By category ---
    lines.append("## 分類彙整")
    lines.append("")
    by_cat = {}
    for e in events:
        by_cat.setdefault(e["category"] or "other", []).append(e)
    for cat in ["stock", "bond", "currency", "commodity", "geopolitics", "macro", "other"]:
        group = by_cat.get(cat, [])
        if not group:
            continue
        lines.append(f"### {CATEGORY_NAMES.get(cat, cat)}（{len(group)}）")
        lines.append("")
        for e in sorted(group, key=lambda x: -(x["severity"] or 0)):
            sev = SEV_NAMES.get(e["severity"], "?")
            senti = e["sentiment"] or "neutral"
            lines.append(f"- **[{sev}][{senti}]** {e['title']}")
            lines.append(f"  - 影響: {e['impact_notes'] or '無'}")
            lines.append("")
    lines.append("---")
    lines.append("")

    # --- Full event list ---
    lines.append("## 全部事件")
    lines.append("")
    for e in sorted(events, key=lambda x: x["published"] or "", reverse=True):
        sev = SEV_NAMES.get(e["severity"], "?")
        ts = _fmt_ts(e["published"])
        lines.append(
            f"- `[{ts}]` **[sev{sev}]** {e['title']} `{e['source']}`"
        )
    lines.append("")
    return "\n".join(lines)


def write_daily_report(events, date=None):
    """Write the daily report into the KB."""
    os.makedirs(KB_DIR, exist_ok=True)
    now = datetime.now(timezone(timedelta(hours=8)))
    date_str = date or now.strftime("%Y-%m-%d")
    md = generate_report(events, date_str)
    path = os.path.join(KB_DIR, f"{date_str}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Daily financial report generator")
    parser.add_argument("--day", default=None, help="YYYY-MM-DD (default today)")
    parser.add_argument("--limit", type=int, default=60, help="max events")
    parser.add_argument("--since-hours", type=int, default=24, help="only events newer than N hours")
    args = parser.parse_args()

    events = db.recent_events(limit=args.limit, severity_min=0)
    path = write_daily_report(events, args.day)
    print(f"report written: {path}")
    print(f"events included: {len(events)}")


if __name__ == "__main__":
    main()
