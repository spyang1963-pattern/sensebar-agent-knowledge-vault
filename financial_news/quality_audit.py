#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quality audit - quantifiable health check of the collected/analyzed data.

Covers the KPI table in QUALITY_ASSURANCE.md:
  - fresh vs stale data
  - duplicate rate
  - source diversity (top-source dominance)
  - key-news misclassification (recall check)
  - verification coverage for important events
  - confidence distribution
  - staleness of latest market snapshot

Usage:
  python quality_audit.py             # full audit
  python quality_audit.py --recent 24 # only last N hours
"""
import os
import sys
import argparse
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

TW = timezone(timedelta(hours=8))


def audit(recent_hours=None):
    now = datetime.now(timezone.utc)
    out = {}
    conn = db.connect()
    try:
        since = None
        if recent_hours:
            since = (now - timedelta(hours=recent_hours)).isoformat(timespec="seconds")

        base = ""
        params = []
        if since:
            base = " AND fetched_at>=?"
            params.append(since)

        # 1. volume
        total = conn.execute(
            "SELECT COUNT(*) FROM events" + (" WHERE 1=1" if since else ""), params
        ).fetchone()[0]
        out["total_events"] = total

        # 2. dedup rate (within window uses is_duplicate flag from that window's pass)
        dup = conn.execute(
            "SELECT COUNT(*) FROM events WHERE is_duplicate=1" + base, params
        ).fetchone()[0]
        out["duplicates"] = dup
        out["dedup_rate_pct"] = round(100 * dup / max(total, 1), 1)

        # 3. freshness: age of newest kept event
        row = conn.execute(
            "SELECT MAX(published) FROM events WHERE is_noise=0 AND is_duplicate=0"
            + base.replace("fetched_at", "published"),
            params,
        ).fetchone()
        newest = row[0]
        if newest:
            try:
                ts = datetime.fromisoformat(newest)
                if ts.tzinfo:
                    ts = ts.astimezone(timezone.utc)
                age_min = (now - ts).total_seconds() / 60
                out["newest_event_age_min"] = round(age_min, 1)
                out["newest_event_at_tw"] = ts.astimezone(TW).strftime("%H:%M")
            except Exception:
                pass

        # 4. source diversity: share of top source
        if since:
            row = conn.execute(
                "SELECT source, COUNT(*) n FROM events WHERE is_duplicate=0"
                + base + " GROUP BY source ORDER BY n DESC LIMIT 1", params
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT source, COUNT(*) n FROM events WHERE is_duplicate=0 "
                "GROUP BY source ORDER BY n DESC LIMIT 1"
            ).fetchone()
        if row and total:
            out["top_source"] = row["source"]
            out["top_source_pct"] = round(100 * row["n"] / total, 1)

        # 5. verification coverage for important events
        # 'verified'/'conflict' = real second-model judgement; 'unverified' = attempt failed
        vrow = conn.execute(
            "SELECT COUNT(*) n, "
            "SUM(CASE WHEN verification='verified' THEN 1 ELSE 0 END) ok, "
            "SUM(CASE WHEN verification='conflict' THEN 1 ELSE 0 END) cf, "
            "SUM(CASE WHEN verification='unverified' THEN 1 ELSE 0 END) uv "
            "FROM events WHERE severity>=2 AND is_duplicate=0" + base, params
        ).fetchone()
        vn, vok, vcf, vuv = vrow["n"], vrow["ok"], vrow["cf"], vrow["uv"]
        judged = (vok or 0) + (vcf or 0)
        out["important_events"] = vn
        out["judged_by_verifier"] = judged
        out["verify_attempted"] = judged + (vuv or 0)
        out["verify_coverage_pct"] = round(100 * judged / max(vn, 1), 1)
        out["verified_agree_pct"] = round(100 * (vok or 0) / max(judged, 1), 1)
        out["conflicts"] = vcf or 0
        out["unverified"] = vuv or 0

        # 6. confidence distribution
        out["confidence"] = {}
        for r in conn.execute(
            "SELECT confidence, COUNT(*) n FROM events WHERE is_duplicate=0"
            + base + " AND confidence IS NOT NULL GROUP BY confidence", params
        ):
            out["confidence"][r["confidence"]] = r["n"]

        # 7. key-news recall: any important market-close event mislabeled as noise
        mis = conn.execute(
            "SELECT COUNT(*) FROM events WHERE is_noise=1 AND "
            "(title LIKE '%收盤%' OR title LIKE '%加權指數%')" + base, params
        ).fetchone()[0]
        out["suspect_noise_market_close"] = mis

        # 8. market snapshot freshness
        srow = conn.execute(
            "SELECT MAX(COALESCE(asof_at, captured_at)) m FROM market_snapshots"
        ).fetchone()
        if srow and srow["m"]:
            try:
                ts = datetime.fromisoformat(srow["m"])
                if ts.tzinfo:
                    ts = ts.astimezone(timezone.utc)
                out["snapshot_age_h"] = round((now - ts).total_seconds() / 3600, 1)
            except Exception:
                pass
    finally:
        conn.close()
    return out


def main():
    parser = argparse.ArgumentParser(description="Quality audit")
    parser.add_argument("--recent", type=int, default=0, help="only last N hours")
    args = parser.parse_args()

    res = audit(recent_hours=args.recent or None)
    for k, v in res.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
