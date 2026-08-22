#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orchestrator - runs the full financial news pipeline in order:
  collect -> filter -> analyze -> report -> notify

Usage:
  python pipeline.py --full          # run everything
  python pipeline.py --collect       # just collect
  python pipeline.py --analyze --batch 40
  python pipeline.py --report         # regenerate today's report (+ deep report)
"""
import os
import sys
import time
import argparse
import logging
import sqlite3
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
import news_collector
import noise_filter
import dedup
import analysis_engine
import report_generator
import deep_report
import log_util

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "pipeline.log")
logger = log_util.get_logger(__name__, LOG_FILE)


def run_collect():
    t0 = time.time()
    db.ensure_schema()
    a, b = news_collector.collect_all()
    # source trust governance + dedup before filtering
    conn = db.connect()
    conn.row_factory = None
    try:
        n_trust = dedup.compute_trust(conn)
    finally:
        conn.close()
    groups, merged = dedup.dedup_pass(db.connect())
    db.commit()
    msg = (
        f"collect: google(+{a[0]}/{a[1]}dup/{a[2]}fail) "
        f"direct(+{b[0]}/{b[1]}dup/{b[2]}fail) "
        f"trust_fix={n_trust} merged={merged} {time.time()-t0:.1f}s"
    )
    print(msg)
    logger.info(msg)
    return a[0] + b[0]


def run_filter():
    keep, noise = noise_filter.apply_filter()
    msg = f"filter: keep={len(keep)} noise={len(noise)}"
    print(msg)
    logger.info(msg)
    return len(keep)

def run_analyze(batch_size=40, time_budget=None):
    analyzed, quota_hit = analysis_engine.analyze_pending(
        batch_size=batch_size, time_budget=time_budget
    )
    msg = f"analyze: analyzed={analyzed} quota_hit={quota_hit}"
    print(msg)
    logger.info(msg)
    return analyzed, quota_hit


def run_report(deep=False, slot=None, no_push=False):
    # Always refresh the market snapshot right before writing a report so the
    # report never reuses yesterday's quotes (Yahoo close can lag by hours).
    try:
        import market_data
        ins, fail = market_data.collect_snapshot()
        msg = f"report: market snapshot refreshed ({ins} ok, {fail} fail)"
        print(msg)
        logger.info(msg)
    except Exception as e:
        logger.warning("report: snapshot refresh failed: %s", e)

    # Cutoff for "new since last run": mtime of today's report file, if any.
    now = datetime.now(timezone(timedelta(hours=8)))
    date_str = now.strftime("%Y-%m-%d")
    report_path = os.path.join(report_generator.KB_DIR, f"{date_str}.md")
    since_iso = None
    since_display = None
    if os.path.exists(report_path):
        mtime_utc = datetime.fromtimestamp(os.path.getmtime(report_path), tz=timezone.utc)
        since_iso = mtime_utc.isoformat(timespec="seconds")
        since_display = mtime_utc.astimezone(timezone(timedelta(hours=8))).strftime("%H:%M")
        msg = f"report: new-event cutoff = {since_display} (previous file mtime)"
        print(msg)
        logger.info(msg)

    events = db.recent_events(limit=80, severity_min=0)
    new_events = db.events_fetched_since(since_iso, limit=60, severity_min=0)
    path = report_generator.write_daily_report(
        events, date_str, new_events=new_events, since_display=since_display
    )
    msg = f"report: {path} ({len(events)} events)"
    print(msg)
    logger.info(msg)
    if deep:
        try:
            # force=True: the 07:00/19:00 scheduled run must ALWAYS produce a
            # fresh report. Otherwise a leftover file from an earlier test or
            # partial run occupies the filename and the real report is skipped
            # (deep_report.py:474 returns early when the file already exists).
            docx_path = deep_report.run(slot=slot, force=True)
            msg2 = f"deep report: {docx_path}"
            print(msg2)
            logger.info(msg2)
        except Exception as e:
            msg2 = f"deep report failed: {e}"
            print(msg2)
            logger.error(msg2)
    # Keep the GitHub Pages site in sync with the KB: rebuild + push whenever
    # a report (daily or deep) is written.
    try:
        import publisher.build as publisher
        publisher.build()
        if no_push:
            msg3 = "publish: build only (--no-push), site not pushed"
            print(msg3)
            logger.info(msg3)
        else:
            publisher.push()
    except Exception as e:
        msg3 = f"publish failed: {e}"
        print(msg3)
        logger.warning(msg3)
    return path


def run_full(analyze_batch=40, time_budget=None):
    run_collect()
    run_filter()
    try:
        conn = db.connect()
        conn.row_factory = sqlite3.Row
        buckets, merged, _ = dedup.topic_dedup_pass(conn, dry=False)
        conn.close()
        msg = f"topic dedup: {len(buckets)} buckets, {merged} merged"
        print(msg)
        logger.info(msg)
    except Exception as e:
        logger.warning("topic dedup failed: %s", e)
    analyzed, quota_hit = run_analyze(analyze_batch, time_budget=time_budget)
    # rolling backfill of verification for historical important events so
    # coverage climbs toward the target without a one-shot catch-up job
    try:
        done, vq = analysis_engine.backfill_verification(limit=20, time_budget=90)
        msg = f"verify backfill: judged={done} quota_hit={vq}"
        print(msg)
        logger.info(msg)
    except Exception as e:
        logger.warning("verify backfill failed: %s", e)
    # Regenerate the report whenever new events were analyzed, even when the
    # free-tier quota cut the batch short (quota_hit=True): each 30-min tick
    # adds 24-150 analyzed events that would otherwise be invisible until the
    # next morning/evening slot.
    if analyzed > 0:
        run_report(deep=False)
    print("pipeline done")


def main():
    parser = argparse.ArgumentParser(description="Financial news pipeline")
    parser.add_argument("--full", action="store_true", help="run everything")
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--filter", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--batch", type=int, default=40)
    parser.add_argument("--deep", action="store_true", help="report with deep analysis")
    parser.add_argument("--no-deep", action="store_true", help="report without deep analysis")
    parser.add_argument("--slot", choices=["morning", "evening"], default=None,
                        help="deep report slot (morning/evening)")
    parser.add_argument("--time-budget", type=int, default=None,
                        help="max seconds for analysis pass (default 300 or $ANALYSIS_TIME_BUDGET)")
    parser.add_argument("--no-push", action="store_true",
                        help="build the site locally but skip git push")
    args = parser.parse_args()

    if args.full:
        run_full(args.batch, time_budget=args.time_budget)
    else:
        if args.collect:
            run_collect()
        if args.filter:
            run_filter()
        if args.analyze:
            run_analyze(args.batch, time_budget=args.time_budget)
        if args.report:
            # Deep analysis must be requested explicitly (--deep). The old
            # "default-on" behavior silently burned a Gemini call every tick.
            run_report(deep=args.deep, slot=args.slot, no_push=args.no_push)
        if not any([args.collect, args.filter, args.analyze, args.report]):
            parser.print_help()


if __name__ == "__main__":
    main()
