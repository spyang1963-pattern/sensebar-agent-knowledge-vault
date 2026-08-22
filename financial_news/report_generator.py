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

SEV_COLORS = {0: "#9e9e9e", 1: "#1a73e8", 2: "#e8710a", 3: "#d93025"}


def _sev_badge(sev):
    """Colored severity badge for markdown (renders in Obsidian + HTML site)."""
    name = SEV_NAMES.get(sev, "?")
    color = SEV_COLORS.get(sev, "#9e9e9e")
    return f'<span style="color:{color};font-weight:bold">[{name}]</span>'


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


def _quality_dashboard():
    """Build a one-line quality dashboard for the report header."""
    try:
        import quality_audit
        q = quality_audit.audit()
        parts = []
        if "newest_event_age_min" in q:
            parts.append(f"資料新鮮度 ≤{int(q['newest_event_age_min'])}min")
        if "dedup_rate_pct" in q:
            parts.append(f"去重率 {q['dedup_rate_pct']}%")
        if "top_source_pct" in q:
            parts.append(f"最大來源佔 {q['top_source_pct']}%")
        if "verify_coverage_pct" in q:
            parts.append(f"驗證覆蓋 {q['verify_coverage_pct']}%")
        if q.get("suspect_noise_market_close"):
            parts.append(f"⚠️疑似誤殺 {q['suspect_noise_market_close']}")
        if q.get("snapshot_age_h") and q["snapshot_age_h"] > 24:
            parts.append(f"⚠️快照 {q['snapshot_age_h']}h")
        return " | ".join(parts) if parts else "品質儀表板不可用"
    except Exception as e:
        return f"品質儀表板錯誤: {e}"


def generate_report(events, title_date=None, new_events=None, since_display=None):
    """Generate markdown report text for a list of events.

    new_events: events fetched since the previous report run (time-flow list of
    what arrived since the last snapshot). since_display: human label of that
    cutoff, e.g. "14:00".
    """
    now = datetime.now(timezone(timedelta(hours=8)))
    date_str = title_date or now.strftime("%Y-%m-%d")
    lines = []
    lines.append(f"# 金融重點報告 {date_str}")
    lines.append("")
    lines.append(f"> 產出時間: {now.strftime('%Y-%m-%d %H:%M')}（台灣時間）")
    lines.append(f"> 品質儀表板: {_quality_dashboard()}")
    lines.append("> 本報告由 AI 自動生成，僅供參考，不構成投資建議。")
    lines.append("")

    # --- New events since last run (time flow) ---
    # Recency feed: show everything fetched since the previous write,
    # including not-yet-analyzed events (they carry severity=0). The point
    # of this section is "what just arrived", not importance ranking.
    if new_events:
        lines.append("## 🆕 本次新增事件")
        lines.append("")
        label = f"（自上次產出 {since_display} 以來）" if since_display else ""
        lines.append(f"> 本次新增 {len(new_events)} 筆{label}")
        lines.append("")
        for e in sorted(new_events, key=lambda x: x["fetched_at"] or "", reverse=True):
            cat = CATEGORY_NAMES.get(e["category"], e["category"] or "未分類")
            senti = e["sentiment"] or "neutral"
            ts = _fmt_ts(e["fetched_at"] or e["published"])
            lines.append(f"- `[{ts}]` **{_sev_badge(e['severity'])}[{cat}][{senti}]** {e['title']} `{e['source']}`")
            lines.append(f"  - 影響: {e['impact_notes'] or '無'}")
            if e.get("related_tickers"):
                lines.append(f"  - 標的: `{e['related_tickers']}`")
            lines.append("")
        lines.append("---")
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
        cap_disp, age_h, stale = market_data.latest_meta()
        if cap_disp:
            note = f"（快照資料時間：{cap_disp}，台股收盤為最近一個交易日）"
            if stale:
                note += " ⚠️ 快照已逾 24 小時未更新，可能為舊收盤資料"
            lines.append(f"> {note}")
            lines.append("")

    # --- Top important events (newest first, severity as tiebreak) ---
    important = [e for e in events if e["severity"] >= 2]
    lines.append("## 重大事件（severity ≥ 2）")
    lines.append("")
    if not important:
        lines.append("_今日無重大事件。_")
    else:
        for e in sorted(important,
                        key=lambda x: (x["published"] or "", -x["severity"]),
                        reverse=True):
            cat = CATEGORY_NAMES.get(e["category"], e["category"] or "未分類")
            senti = e["sentiment"] or "neutral"
            ts = _fmt_ts(e["published"])
            lines.append(f"- `[{ts}]` **{_sev_badge(e['severity'])}[{cat}][{senti}]** {e['title']}")
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
        for e in sorted(group,
                        key=lambda x: (x["published"] or "", -(x["severity"] or 0)),
                        reverse=True):
            senti = e["sentiment"] or "neutral"
            ts = _fmt_ts(e["published"])
            lines.append(f"- `[{ts}]` **{_sev_badge(e['severity'])}[{senti}]** {e['title']}")
            lines.append(f"  - 影響: {e['impact_notes'] or '無'}")
            lines.append("")
    lines.append("---")
    lines.append("")

    # --- Full event list (newest first) ---
    lines.append("## 全部事件")
    lines.append("")
    for e in sorted(events, key=lambda x: x["published"] or "", reverse=True):
        ts = _fmt_ts(e["published"])
        lines.append(
            f"- `[{ts}]` **{_sev_badge(e['severity'])}** {e['title']} `{e['source']}`"
        )
    lines.append("")
    return "\n".join(lines)


def write_daily_report(events, date=None, new_events=None, since_display=None):
    """Write the daily report into the KB."""
    os.makedirs(KB_DIR, exist_ok=True)
    now = datetime.now(timezone(timedelta(hours=8)))
    date_str = date or now.strftime("%Y-%m-%d")
    md = generate_report(events, date_str, new_events=new_events, since_display=since_display)
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
