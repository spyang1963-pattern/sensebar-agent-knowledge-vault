#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Market snapshot collector - fetches live quotes from free Yahoo Finance API.

Symbols cover: TWSE index, key Taiwan stocks, US indices, USD/TWD, oil, gold.

Usage:
  python market_data.py --collect     # capture one snapshot round
  python market_data.py --latest      # show latest snapshot
"""
import os
import sys
import time
import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

# Yahoo Finance chart API (free, no key) - v7 quote endpoint returns 401
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"

# Symbols to track. name is display label.
SYMBOLS = [
    ("^TWII", "加權指數", "TWD"),
    ("2330.TW", "台積電", "TWD"),
    ("2317.TW", "鴻海", "TWD"),
    ("2454.TW", "聯發科", "TWD"),
    ("2308.TW", "台達電", "TWD"),
    ("2881.TW", "富邦金", "TWD"),
    ("^GSPC", "S&P 500", "USD"),
    ("^IXIC", "納斯達克", "USD"),
    ("^DJI", "道瓊", "USD"),
    ("^N225", "日經225", "JPY"),
    ("000001.SS", "上證指數", "CNY"),
    ("HSI", "恒生指數", "HKD"),
    ("AAPL", "Apple", "USD"),
    ("MSFT", "Microsoft", "USD"),
    ("NVDA", "NVIDIA", "USD"),
    ("AMZN", "Amazon", "USD"),
    ("TSLA", "Tesla", "USD"),
    ("USDJPY=X", "美元/日圓", "JPY"),
    ("USDTWD=X", "美元/台幣", "TWD"),
    ("EURUSD=X", "歐元/美元", "EUR"),
    ("CNY=X", "美元/人民幣", "CNY"),
    ("CL=F", "WTI原油", "USD"),
    ("BZ=F", "布蘭特原油", "USD"),
    ("GC=F", "黃金", "USD"),
    ("DX-Y.NYB", "美元指數DXY", "USD"),
    ("^TNX", "美債10年殖利率", "USD"),
]

HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (sensebar-financial-news/1.0)"}


def fetch_symbol(symbol):
    """Return (symbol, price, change_pct, asof_ts) or None. Uses v8 chart API.

    price/change_pct are derived from the daily close series: the last bar is
    the most recent close and the bar before it is the previous session, so
    change_pct is a true single-session change. (Do NOT use meta.chartPreviousClose:
    it is the close before the chart range, i.e. several days back.)

    asof_ts is the epoch seconds of the bar the price came from (the actual
    trading date the snapshot reflects) so callers can tell stale data apart.

    Data freshness: if the last bar's close is None (session data not ready yet,
    e.g. Yahoo lagging the close) the symbol is reported as None so the caller
    does NOT silently reuse an older close as today's quote.
    """
    try:
        r = requests.get(
            CHART_URL.format(symbol=symbol), headers=HTTP_HEADERS, timeout=15
        )
        data = r.json()
        result = data.get("chart", {}).get("result")
        if not result:
            return None
        ts = result[0].get("timestamp") or []
        quote = (result[0].get("indicators", {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        pairs = [(t, c) for t, c in zip(ts, closes) if c is not None]
        meta = result[0].get("meta") or {}
        # Freshness guard: the newest bar returned by Yahoo may have close=None
        # while the session is over (delayed data). Prefer meta.regularMarketPrice
        # (Yahoo's canonical last price + its timestamp) when the chart bar lags,
        # so we never serve an older close as today's quote.
        if closes and len(closes) == len(ts) and closes[-1] is None:
            rmt = meta.get("regularMarketTime")
            rmp = meta.get("regularMarketPrice")
            if rmt and rmp is not None and len(pairs) >= 1:
                asof_ts = rmt
                price = rmp
                prev = pairs[-1][1]
                if prev not in (None, 0):
                    change_pct = round((price - prev) / prev * 100, 2)
                    return symbol, price, change_pct, asof_ts
            print(f"  {symbol}: data not ready (latest close missing), skipped")
            return None
        if len(pairs) < 2:
            return None
        asof_ts = pairs[-1][0]
        price = pairs[-1][1]
        prev = pairs[-2][1]
        if prev in (None, 0):
            return None
        change_pct = round((price - prev) / prev * 100, 2)
        return symbol, price, change_pct, asof_ts
    except Exception as e:
        print(f"  {symbol}: ERR {str(e)[:60]}")
        return None


def collect_snapshot():
    db.init_db()
    db.ensure_schema()
    inserted = failed = 0
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(fetch_symbol, s): s for s, _, _ in SYMBOLS}
        for fut in as_completed(futures):
            res = fut.result()
            if res is None:
                failed += 1
                continue
            symbol, price, change_pct, asof_ts = res
            name = dict((s, n) for s, n, _ in SYMBOLS).get(symbol, symbol)
            cur = dict((s, c) for s, _, c in SYMBOLS).get(symbol, "USD")
            asof_at = datetime.fromtimestamp(asof_ts, tz=timezone.utc).isoformat(timespec="seconds")
            db.insert_market_snapshot(
                symbol=symbol, name=name, price=price,
                change_pct=change_pct, currency=cur, source="yahoo",
                asof_at=asof_at,
            )
            inserted += 1
    db.commit()
    return inserted, failed


def _fmt_captured(ts):
    """Convert captured_at ISO to Asia/Taipei display, or '' if unparsable."""
    try:
        d = datetime.fromisoformat(ts)
        if d.tzinfo:
            d = d.astimezone(timezone(timedelta(hours=8)))
        return d.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts


def latest_table():
    rows = []
    for symbol, name, cur in SYMBOLS:
        snap = db.latest_market_snapshot(symbol)
        if snap and snap["price"] is not None:
            chg = snap["change_pct"]
            arrow = "▲" if chg is not None and chg > 0 else ("▼" if chg is not None and chg < 0 else "―")
            rows.append(f"{name:<12} {snap['price']:>12,.2f} {cur:>4} {arrow}{chg if chg is not None else 0:+.2f}%")
    return rows


def latest_meta():
    """Snapshot metadata: (asof_display, asof_age_hours, stale).

    Uses asof_at (the trading date the data reflects) instead of captured_at
    so stale quotes are recognised even right after a collect round.
    """
    latest = None
    for symbol, name, cur in SYMBOLS:
        snap = db.latest_market_snapshot(symbol)
        if snap:
            d = snap.get("asof_at") or snap.get("captured_at")
            if d and (latest is None or d > latest):
                latest = d
    if not latest:
        return "無快照", None, True
    display = _fmt_captured(latest)
    try:
        d = datetime.fromisoformat(latest)
        now = datetime.now(timezone.utc)
        age = (now - d).total_seconds() / 3600.0
    except Exception:
        age = None
    stale = age is not None and age > 24
    return display, age, stale


def latest_structured():
    """Return list of dicts: {symbol, name, price, change_pct, currency}."""
    rows = []
    for symbol, name, cur in SYMBOLS:
        snap = db.latest_market_snapshot(symbol)
        if snap and snap["price"] is not None:
            rows.append({
                "symbol": symbol,
                "name": name,
                "price": snap["price"],
                "change_pct": snap["change_pct"],
                "currency": cur,
            })
    return rows


def main():
    parser = argparse.ArgumentParser(description="Market data collector")
    parser.add_argument("--collect", action="store_true", help="capture snapshot")
    parser.add_argument("--latest", action="store_true", help="show latest")
    args = parser.parse_args()

    if args.collect:
        ins, fail = collect_snapshot()
        print(f"snapshot: {ins} symbols, {fail} failed")
    elif args.latest:
        for line in latest_table():
            print(line)


if __name__ == "__main__":
    main()
