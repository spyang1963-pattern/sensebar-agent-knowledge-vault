#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calendar-driven event engine.

Reads the curated market_calendar and generates:
  - targeted collection queries for today's scheduled events
  - formatted context for analysis and report prompts
  - coverage-check data for quality audits
"""
from datetime import date, timedelta

# Lazy import to avoid circular dependency at module load time.
_cal = None


def _calendar():
    global _cal
    if _cal is None:
        from publisher import market_calendar
        _cal = market_calendar.build_calendar()
    return _cal


def _events_for(d):
    """Return raw event dicts for a given date."""
    return [e for e in _calendar()["upcoming"] if e["date"] == d.isoformat()]


def today_events(today=None):
    """Events scheduled for *today*."""
    return _events_for(today or date.today())


def upcoming_events(today=None, days=3):
    """Events in the window [today, today + days]."""
    today = today or date.today()
    end = today + timedelta(days=days)
    return [e for e in _calendar()["upcoming"]
            if today.isoformat() <= e["date"] <= end.isoformat()]


# ── collection query generation ──────────────────────────────────────────

# Category → extra Google News queries (lang, query)
_CATEGORY_QUERIES = {
    "labor": [
        ("en", "nonfarm payrolls jobs report"),
        ("en", "US unemployment rate"),
        ("zh", "非農就業 就業報告"),
    ],
    "inflation": [
        ("en", "US CPI inflation data"),
        ("en", "US PPI producer prices"),
        ("zh", "美國 CPI 通膨"),
    ],
    "gdp": [
        ("en", "US GDP economic growth"),
        ("zh", "美國 GDP 經濟成長"),
    ],
    "cb": [
        ("en", "Federal Reserve rate decision FOMC"),
        ("zh", "聯準會利率決策"),
    ],
    "twecon": [
        ("zh", "台灣 CPI 消費者物價"),
        ("zh", "台灣出口統計"),
        ("zh", "央行理監事會議"),
    ],
    "earnings": [],  # generated dynamically from event names
}


def _earnings_queries(events):
    """Generate queries from earnings event names (e.g., '台積電 Q3 法說')."""
    queries = []
    for e in events:
        name = e.get("institution", "") + " " + e.get("event", "")
        # Extract likely company/ticker keywords (first meaningful token).
        tokens = [t for t in name.replace("/", " ").replace("（", " ").replace("）", " ").split() if len(t) >= 2]
        if tokens:
            q = " ".join(tokens[:3])
            queries.append(("en", q))
            queries.append(("zh", q))
    return queries


def event_queries(today=None):
    """Return (lang, query) pairs for collection, derived from today's events.

    Deduplicates against each other but NOT against the static SEARCH_QUERIES
    (the collector handles that).
    """
    today = today or date.today()
    events = _events_for(today)
    if not events:
        return []

    seen = set()
    queries = []
    for e in events:
        cat = e["category"]
        for q in _CATEGORY_QUERIES.get(cat, []):
            if q not in seen:
                seen.add(q)
                queries.append(q)
        # Earnings: generate from name
        if cat == "earnings":
            for q in _earnings_queries([e]):
                if q not in seen:
                    seen.add(q)
                    queries.append(q)
    return queries


# ── prompt context ───────────────────────────────────────────────────────

def event_summary_for_prompt(today=None, days=1):
    """Formatted text block for injection into analysis/report prompts.

    Returns a string listing today's (and optionally upcoming) calendar
    events with their forecasts, to force coverage.
    """
    today = today or date.today()
    evts = upcoming_events(today, days=days)
    if not evts:
        return ""
    lines = ["## 行事曆排期事件（必須主動覆蓋）\n"]
    for e in evts:
        flag = "⭐ 今天" if e["date"] == today.isoformat() else f"📅 {e['date']}"
        forecast = f"\n  法人預期：{e['forecast']}" if e.get("forecast") else ""
        lines.append(f"- {flag} [{e['impact_label']}]{e['institution']}：{e['event']}{forecast}")
    lines.append("")
    return "\n".join(lines)


def coverage_check(today=None):
    """Return list of today's high-impact events for quality audit.

    Each entry: {"event": str, "institution": str, "category": str,
                 "impact": str, "forecast": str}
    """
    return [e for e in today_events(today) if e["impact"] == "high"]


# ── CLI helper ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    today = date.today()
    print(f"=== 行事曆引擎 {today} ===\n")
    print("今日事件：")
    for e in today_events(today):
        print(f"  [{e['impact_label']}] {e['institution']}：{e['event']}")
    print(f"\n動態查詢（{len(event_queries(today))} 條）：")
    for lang, q in event_queries(today):
        print(f"  [{lang}] {q}")
    print(f"\n提示詞摘要：\n{event_summary_for_prompt(today, days=1)}")
