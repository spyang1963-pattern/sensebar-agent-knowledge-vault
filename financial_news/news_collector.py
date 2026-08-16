#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
News collector - fetches financial & geopolitical news from free sources.

Sources:
  - Google News RSS (keyword searches, both zh-TW and en)
  - Central bank official RSS feeds (Fed, ECB)
  - Financial/geopolitical RSS feeds (Reuters, BBC business)

Usage:
  python news_collector.py --collect     # collect new events into SQLite
  python news_collector.py --stats       # show DB stats
  python news_collector.py --recent 20   # show recent kept events
"""
import os
import sys
import time
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import feedparser
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
import log_util

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "collector.log")
logger = log_util.get_logger(__name__, LOG_FILE)

# Google News RSS base. hl/gl/ceid control language & region.
GOOGLE_NEWS_ZH = "https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
GOOGLE_NEWS_EN = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

# Keyword queries (both languages). Format: (lang, query)
# NOTE: use direction-neutral terms so both up/down days are captured.
SEARCH_QUERIES = [
    # --- Taiwan market ---
    ("zh", '"中央銀行" 利率'),
    ("zh", "金管會"),
    ("zh", "證交所 重大訊息"),
    ("zh", "央行 升息 降息"),
    ("zh", "台股 大跌"),
    ("zh", "台股 大漲"),
    ("zh", "台股 收盤"),
    ("zh", "加權指數"),
    # --- Global macro / central banks ---
    ("en", "Federal Reserve rate decision"),
    ("en", "central bank policy"),
    ("en", "Fed Powell"),
    ("en", "Treasury yields"),
    ("en", "dollar index DXY"),
    ("en", "inflation CPI"),
    # --- Geopolitics ---
    ("zh", "戰爭 衝突"),
    ("zh", "油價"),
    ("en", "geopolitical conflict"),
    ("en", "oil price crude"),
    ("en", "sanctions trade war"),
    ("en", "Taiwan strait"),
    # --- Equity markets ---
    ("en", "stock market selloff"),
    ("en", "stock market rally"),
    ("en", "S&P 500 Nasdaq"),
    ("zh", "美股 大跌 暴漲"),
]

# Direct RSS feeds (official & major outlets)
DIRECT_FEEDS = [
    ("fed", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("cnbc", "https://www.cnbc.com/id/100727362/device/rss/rss.html"),
    ("bbcbusiness", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("marketwatch", "https://feeds.marketwatch.com/marketwatch/topstories/"),
    ("nytbusiness", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"),
    # Real-time feeds (verified fresh within minutes)
    ("yahoo-tw-finance", "https://tw.finance.yahoo.com/rss"),
    ("yahoo-tw-stock", "https://tw.stock.yahoo.com/rss"),
    ("investing-com", "https://www.investing.com/rss/news.rss"),
    ("seekingalpha", "https://seekingalpha.com/market_currents.xml"),
]

TIMEOUT = 12
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (sensebar-financial-news/1.0)"}

# --- Source governance (quality assurance) ---
# Max entries collected per feed/query per run (avoids single-source dominance).
MAX_PER_FEED = 30
# Max total entries for google-news queries and direct feeds per run.
MAX_GOOGLE_TOTAL = 400
MAX_DIRECT_TOTAL = 200
# Entries published older than this many hours are skipped (stale news).
MAX_AGE_HOURS = 48
# Sources allowed to bypass the age gate (official first-hand announcements).
AGE_GATE_BYPASS = {"fed", "ecb"}


def _too_old(entry):
    """True if the entry's published time is older than the freshness gate."""
    ts = entry.get("published_parsed") or entry.get("updated_parsed")
    if not ts:
        return False
    try:
        pub = datetime(*ts[:6], tzinfo=timezone.utc)
    except Exception:
        return False
    age = (datetime.now(timezone.utc) - pub).total_seconds() / 3600
    return age > MAX_AGE_HOURS


def _pub_time(entry):
    """Return ISO-8601 published time from an RSS entry (best effort).

    published_parsed is already UTC; time.mktime() would treat it as local
    time and add a TZ offset, so build the datetime directly instead.
    """
    ts = entry.get("published_parsed") or entry.get("updated_parsed")
    if ts:
        try:
            return datetime(*ts[:6], tzinfo=timezone.utc).isoformat(timespec="seconds")
        except Exception:
            pass
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _summary(entry):
    s = entry.get("summary") or ""
    # strip HTML tags
    import re

    s = re.sub(r"<[^>]+>", " ", s)
    return " ".join(s.split())[:800]


def fetch_feed(url, hard_timeout=25):
    """Fetch a feed with retries. Returns feedparser result or None."""
    deadline = time.time() + hard_timeout
    for attempt in range(3):
        if time.time() > deadline:
            break
        try:
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=min(TIMEOUT, deadline - time.time()))
            if resp.status_code == 200:
                return feedparser.parse(resp.content)
            logger.warning("HTTP %s for %s", resp.status_code, url)
        except Exception as e:
            logger.warning("fetch failed %s: %s", url, e)
        time.sleep(1.5 + attempt * 2)
    return None


def collect_google_news():
    inserted = existing = failed = 0
    jobs = [
        (lang, query, GOOGLE_NEWS_ZH if lang == "zh" else GOOGLE_NEWS_EN)
        for lang, query in SEARCH_QUERIES
    ]
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(_fetch_and_insert, url.format(q=requests.utils.quote(query)), f"google-news:{query}", lang):
            (lang, query)
            for lang, query, url in jobs
        }
        for fut in as_completed(futures):
            try:
                i, e, f = fut.result()
                if inserted + i <= MAX_GOOGLE_TOTAL:
                    inserted += i
                else:
                    logger.info("google total cap hit (%d)", MAX_GOOGLE_TOTAL)
                existing += e
                failed += f
            except Exception as ex:
                logger.warning("google job failed: %s", ex)
                failed += 1
    return inserted, existing, failed


def _fetch_and_insert(url, source, lang, max_entries=MAX_PER_FEED, age_gate=True):
    """Fetch a feed and insert its entries. Returns (inserted, existing, failed).

    max_entries caps how many fresh entries we keep per feed/query.
    age_gate skips entries older than MAX_AGE_HOURS (unless bypass source).
    """
    inserted = existing = failed = 0
    feed = fetch_feed(url)
    if feed is None or not feed.entries:
        return 0, 0, 1
    bypass_age = source in AGE_GATE_BYPASS
    added = 0
    for entry in feed.entries:
        if added >= max_entries:
            break
        link = entry.get("link", "")
        title = entry.get("title", "").strip()
        if not link or not title:
            continue
        if age_gate and not bypass_age and _too_old(entry):
            existing += 1
            continue
        r = db.insert_event(
            source=source,
            title=title,
            link=link,
            published=_pub_time(entry),
            summary=_summary(entry),
            language="zh" if lang == "zh" else "en",
        )
        if r == "inserted":
            inserted += 1
            added += 1
        else:
            existing += 1
    return inserted, existing, failed


def collect_direct_feeds():
    inserted = existing = failed = 0
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(_fetch_and_insert, url, name, "en", max_entries=MAX_PER_FEED, age_gate=True): name
            for name, url in DIRECT_FEEDS
        }
        for fut in as_completed(futures):
            try:
                i, e, f = fut.result()
                if inserted + i <= MAX_DIRECT_TOTAL:
                    inserted += i
                else:
                    logger.info("direct total cap hit (%d)", MAX_DIRECT_TOTAL)
                existing += e
                failed += f
            except Exception as ex:
                logger.warning("direct feed job failed: %s", ex)
                failed += 1
    return inserted, existing, failed


def collect_all():
    db.init_db()
    a = collect_google_news()
    b = collect_direct_feeds()
    db.commit()
    logger.info(
        "collect done: google(insert=%d,existing=%d,fail=%d) direct(insert=%d,existing=%d,fail=%d)",
        *a, *b,
    )
    return a, b


def main():
    parser = argparse.ArgumentParser(description="Financial news collector")
    parser.add_argument("--collect", action="store_true", help="collect new events")
    parser.add_argument("--stats", action="store_true", help="show DB stats")
    parser.add_argument("--recent", type=int, default=0, help="show recent kept events")
    args = parser.parse_args()

    if args.collect:
        t0 = time.time()
        a, b = collect_all()
        print(f"Google News: +{a[0]} new / {a[1]} existing / {a[2]} failed")
        print(f"Direct feeds: +{b[0]} new / {b[1]} existing / {b[2]} failed")
        print(f"elapsed {time.time()-t0:.1f}s")
    elif args.stats:
        for k, v in db.stats().items():
            print(f"{k}: {v}")
    elif args.recent:
        for ev in db.recent_events(limit=args.recent):
            print(f"[{ev['published']}] ({ev['language']}) {ev['title']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
