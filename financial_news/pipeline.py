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
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
import news_collector
import noise_filter
import analysis_engine
import report_generator
import deep_report

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "pipeline.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def run_collect():
    t0 = time.time()
    a, b = news_collector.collect_all()
    db.commit()
    msg = (
        f"collect: google(+{a[0]}/{a[1]}dup/{a[2]}fail) "
        f"direct(+{b[0]}/{b[1]}dup/{b[2]}fail) {time.time()-t0:.1f}s"
    )
    print(msg)
    logging.info(msg)
    return a[0] + b[0]


def run_filter():
    keep, noise = noise_filter.apply_filter()
    msg = f"filter: keep={len(keep)} noise={len(noise)}"
    print(msg)
    logging.info(msg)
    return len(keep)


def run_analyze(batch_size=40):
    analyzed, quota_hit = analysis_engine.analyze_pending(batch_size=batch_size)
    msg = f"analyze: analyzed={analyzed} quota_hit={quota_hit}"
    print(msg)
    logging.info(msg)
    return analyzed, quota_hit


def run_report(deep=False, slot=None):
    events = db.recent_events(limit=80, severity_min=0)
    path = report_generator.write_daily_report(events)
    msg = f"report: {path} ({len(events)} events)"
    print(msg)
    logging.info(msg)
    if deep:
        try:
            docx_path = deep_report.run(slot=slot)
            msg2 = f"deep report: {docx_path}"
            print(msg2)
            logging.info(msg2)
        except Exception as e:
            msg2 = f"deep report failed: {e}"
            print(msg2)
            logging.error(msg2)
    return path


def run_full(analyze_batch=40):
    run_collect()
    run_filter()
    analyzed, quota_hit = run_analyze(analyze_batch)
    if not quota_hit:
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
    args = parser.parse_args()

    if args.full:
        run_full(args.batch)
    else:
        if args.collect:
            run_collect()
        if args.filter:
            run_filter()
        if args.analyze:
            run_analyze(args.batch)
        if args.report:
            run_report(deep=args.deep or not args.no_deep, slot=args.slot)
        if not any([args.collect, args.filter, args.analyze, args.report]):
            parser.print_help()


if __name__ == "__main__":
    main()
