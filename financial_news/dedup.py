#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deduplication - merges near-identical news across feeds/queries.

Strategy:
  1. Normalize title (lowercase, strip punctuation, strip trailing source name).
  2. Compute sha1 dedup_key over the normalized title prefix.
  3. Group by dedup_key; within a group keep the highest-trust + earliest
     published event, flag the rest as is_duplicate=1.
  4. Optional fuzzy pass (difflib ratio >= threshold) for near-duplicates that
     survived normalization differences.

Usage:
  python dedup.py --apply        # key all unkeyed events + merge duplicates
  python dedup.py --dry          # show what would be merged
  python dedup.py --stats        # dedup metrics
"""
import os
import re
import sys
import hashlib
import argparse
import sqlite3
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

# trailing source-name markers: " - 經濟日報" / " | UDN" / "- Yahoo新聞" / " | 民視新聞網 - LINE TODAY"
_SOURCE_SUFFIX_RE = re.compile(
    r"\s*[|\-]\s*[A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff ()，。·]{1,30}$"
)
_PREFIX_BRACKET_RE = re.compile(r"^[【\[]?[^】\]]{0,6}[】\]]\s*")

# trust score by source prefix (0..1). Only applies when source is a google-news
# query or a named direct feed.
SOURCE_TRUST = {
    "fed": 1.0, "ecb": 1.0,
    "cnbc": 0.8, "bbcbusiness": 0.8, "marketwatch": 0.8, "nytbusiness": 0.8,
    "yahoo-tw-finance": 0.8, "yahoo-tw-stock": 0.8,
    "investing-com": 0.8, "seekingalpha": 0.6,
}
# google-news queries are keyword aggregators -> default trust 0.6
GOOGLE_NEWS_TRUST = 0.6
DEFAULT_TRUST = 0.7


def trust_for_source(source):
    if source in SOURCE_TRUST:
        return SOURCE_TRUST[source]
    if source.startswith("google-news:"):
        return GOOGLE_NEWS_TRUST
    return DEFAULT_TRUST


def normalize_title(title):
    t = title or ""
    # lowercase (best effort for CJK is a no-op)
    t = t.lower()
    # strip [公告] / 【快訊】 style prefixes
    t = _PREFIX_BRACKET_RE.sub("", t)
    # strip trailing source-name markers
    t = _SOURCE_SUFFIX_RE.sub("", t)
    # collapse whitespace & unify CJK full-width forms
    t = t.replace("\u3000", " ").replace("，", ",").replace("。", ".")
    t = re.sub(r"\s+", " ", t)
    # drop question/exclamation endings and stray punctuation
    t = re.sub(r"[!?？！]+$", "", t).strip()
    return t.strip()


def dedup_key(title):
    return hashlib.sha1(normalize_title(title)[:100].encode("utf-8")).hexdigest()


def fuzzy_ratio(a, b):
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def compute_trust(conn, limit=5000):
    """Backfill/correct trust for events. Fixes rows whose stored trust does not
    match the source policy (e.g. google-news queries defaulted to 0.8).

    Uses the master connection so the fix is committed atomically.
    """
    rows = conn.execute(
        "SELECT id, source, trust FROM events WHERE is_duplicate=0 LIMIT ?",
        (limit,),
    ).fetchall()
    updated = 0
    db._WRITE_LOCK.acquire()
    try:
        mc = db._master_conn()
        for eid, source, trust in rows:
            expected = trust_for_source(source)
            if trust != expected:
                mc.execute("UPDATE events SET trust=? WHERE id=?", (expected, eid))
                updated += 1
        mc.commit()
    finally:
        db._WRITE_LOCK.release()
    return updated


def dedup_pass(conn, dry=False, window_hours=240):
    """Key unkeyed events and merge duplicates.

    Returns (groups, merged). groups: list of (keep_id, [dup_ids]).
    """
    groups = []
    merged = 0
    rows = conn.execute(
        """SELECT id, source, title, published, trust, status, is_noise
           FROM events
           WHERE dedup_key IS NULL AND is_duplicate=0
           ORDER BY COALESCE(trust,0) DESC,
                    CASE WHEN status='analyzed' THEN 1 ELSE 0 END DESC,
                    CASE WHEN is_noise=0 THEN 1 ELSE 0 END DESC,
                    published ASC"""
    ).fetchall()

    seen = {}  # dedup_key -> keep id (we only touch within this unkeyed set)
    for eid, source, title, published, trust, status, is_noise in rows:
        trust = trust if trust is not None else trust_for_source(source)
        k = dedup_key(title)
        prev = seen.get(k)
        if prev is None:
            seen[k] = eid
            continue
        # duplicate: keep the first seen (highest trust, analyzed, non-noise,
        # earliest published); flag the rest.
        groups.append((prev, [eid]))
        merged += 1

    if not dry:
        for keep_id, dup_ids in groups:
            db.mark_dedup(keep_id, dup_ids)
        # backfill dedup_key for every event we just processed so future passes
        # can skip them cheaply
        all_ids = set()
        for keep_id, dup_ids in groups:
            all_ids.add(keep_id)
            all_ids.update(dup_ids)
        db._WRITE_LOCK.acquire()
        try:
            mc = db._master_conn()
            for eid in all_ids:
                row = mc.execute(
                    "SELECT title FROM events WHERE id=?", (eid,)
                ).fetchone()
                if row:
                    mc.execute(
                        "UPDATE events SET dedup_key=? WHERE id=?",
                        (dedup_key(row[0]), eid),
                    )
            mc.commit()
        finally:
            db._WRITE_LOCK.release()
    return groups, merged


def stats(conn):
    total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    dup = conn.execute("SELECT COUNT(*) FROM events WHERE is_duplicate=1").fetchone()[0]
    keyed = conn.execute(
        "SELECT COUNT(DISTINCT dedup_key) FROM events WHERE dedup_key IS NOT NULL"
    ).fetchone()[0]
    return {
        "total": total,
        "duplicates": dup,
        "dedup_rate_pct": round(100 * dup / total, 1) if total else 0,
        "distinct_keys": keyed,
    }


# ---- Topic-level dedup: collapse multi-source coverage of the SAME event ----
# (title-exact dedup_key above cannot catch e.g. "CPI cools to 3.4%" from 30
#  different outlets; topic signature groups those into one bucket.)

# Strong keywords = concrete event anchors (trading-specific topics).
STRONG_TOPIC_KW = [
    "cpi", "inflation", "通膨", "ppi", "fed", "聯準會", "fomc", "升息", "降息", "央行",
    "tariff", "關稅", "war", "戰爭", "衝突", "海峽", "hormuz", "荷姆茲", "霍爾木茲",
    "sanction", "制裁", "jobs", "nonfarm", "非農", "unemployment", "失業", "gdp",
    "recession", "衰退", "earnings", "財報", "營收", "法說", "dividend", "股息",
    "rating", "評級", "oil", "crude", "油價", "原油", "brent", "wti", "opec",
    "gold", "黃金", "bitcoin", "比特幣", "treasury", "yield", "殖利率", "美債",
    "nvidia", "輝達", "台積電", "tsmc", "中東", "伊朗", "iran", "俄羅斯", "russia",
    "烏克蘭", "ukraine", "北韓", "north korea",
]

# Weak keywords (generic market words) are never enough alone to merge.
WEAK_TOPIC_KW = [
    "股市", "大盤", "指數", "nasdaq", "s&p", "dow", "道瓊", "台股", "美股",
    "stock market", "index", "futures", "美元", "dollar", "匯率", "日圓", "yen",
    "費半", "收盤", "開盤", "盤前", "盤後", "跌", "漲", "點", "資金", "etf",
]

_STRONG_TOPIC_RE = re.compile("|".join(re.escape(k) for k in STRONG_TOPIC_KW), re.I)
_WEAK_TOPIC_RE = re.compile("|".join(re.escape(k) for k in WEAK_TOPIC_KW), re.I)
_TOPIC_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(%|億|兆|萬|點|美元|元)")
_REGION_RE = re.compile(
    r"(\bus\b|美國|中國|china|台灣|taiwan|日本|日圓|yen|歐洲|euro|香港|hong kong|"
    r"南韓|korea|印度|india)",
    re.I,
)


def topic_signature(title, summary):
    """Signature of an event's topic. Returns (strong, weak, nums, regions)."""
    text = f"{title} {summary}".lower()
    strong = set(k for k in STRONG_TOPIC_KW if k in text)
    weak = set(k for k in WEAK_TOPIC_KW if k in text)
    nums = set(m[0] + m[1] for m in _TOPIC_NUM_RE.findall(title))
    regions = set(m.group(0) for m in _REGION_RE.finditer(text))
    return strong, weak, nums, regions


def topic_dedup_pass(conn, dry=False, window_hours=48, keep_per_topic=2):
    """Collapse same-topic multi-source events within a time window.

    Merge rule (conservative, to avoid eating distinct events):
      - >=2 common STRONG topic keywords AND at least one common numeric value
      - regions must not conflict (US vs China stories are never merged)
      - published times within window_hours

    Within each bucket the top `keep_per_topic` events (highest trust, then
    analyzed-first, then earliest published) are kept; the rest are marked
    is_duplicate=1 via db.mark_dedup.

    Returns (buckets, merged_count).
    """
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat(
        timespec="seconds"
    )
    rows = conn.execute(
        """SELECT id, title, summary, published, trust, status, source
           FROM events
           WHERE is_noise=0 AND is_duplicate=0 AND published>=?
           ORDER BY published ASC""",
        (cutoff,),
    ).fetchall()

    # Only events with at least 2 strong keywords can ever merge; keep the rest
    # untouched (they are distinct topics by construction).
    candidates = []
    for r in rows:
        strong, weak, nums, regions = topic_signature(r["title"], r["summary"] or "")
        if len(strong) >= 2:
            candidates.append(
                {
                    "id": r["id"], "title": r["title"], "summary": r["summary"],
                    "published": r["published"], "trust": r["trust"], "status": r["status"],
                    "source": r["source"], "strong": strong, "weak": weak,
                    "nums": nums, "regions": regions,
                }
            )

    buckets = []
    used = set()
    n = len(candidates)
    for i in range(n):
        if i in used:
            continue
        bucket = [i]
        used.add(i)
        a = candidates[i]
        t_a = datetime.fromisoformat(a["published"]) if a["published"] else None
        for j in range(i + 1, n):
            if j in used:
                continue
            b = candidates[j]
            t_b = datetime.fromisoformat(b["published"]) if b["published"] else None
            if t_a is None or t_b is None:
                continue
            if abs((t_b - t_a).total_seconds()) > window_hours * 3600:
                continue
            if a["regions"] and b["regions"] and a["regions"] != b["regions"]:
                continue
            common_strong = a["strong"] & b["strong"]
            common_nums = a["nums"] & b["nums"]
            if len(common_strong) >= 2 and common_nums:
                bucket.append(j)
                used.add(j)
        if len(bucket) > 1:
            buckets.append(bucket)

    merged_count = 0
    for bucket in buckets:
        # rank: trust desc, analyzed-first, earliest published
        def rank(ci):
            c = candidates[ci]
            trust = c["trust"] if c["trust"] is not None else trust_for_source(c["source"])
            return (-trust, 0 if c["status"] == "analyzed" else 1, c["published"])

        ordered = sorted(bucket, key=rank)
        keep_ids = ordered[:keep_per_topic]
        dup_ids = [candidates[ci]["id"] for ci in ordered[keep_per_topic:]]
        if not dup_ids:
            continue
        merged_count += len(dup_ids)
        if not dry:
            db.mark_dedup(candidates[keep_ids[0]]["id"], dup_ids)
    if not dry:
        db.commit()
    return buckets, merged_count, candidates


def main():
    parser = argparse.ArgumentParser(description="Dedup pass")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--trust-backfill", action="store_true")
    parser.add_argument("--topic", action="store_true", help="run topic-level dedup")
    parser.add_argument("--topic-dry", action="store_true", help="preview topic dedup")
    args = parser.parse_args()

    if args.stats:
        conn = db.connect()
        for k, v in stats(conn).items():
            print(f"{k}: {v}")
        conn.close()
        return

    if args.topic or args.topic_dry:
        conn = db.connect()
        conn.row_factory = sqlite3.Row
        buckets, merged, candidates = topic_dedup_pass(conn, dry=args.topic_dry)
        act = "topic-dry" if args.topic_dry else "topic-applied"
        print(f"{act}: {len(buckets)} buckets, {merged} merged")
        for b in buckets:
            print(f"=== bucket({len(b)}) ===")
            for ci in b:
                c = candidates[ci]
                print(f"  [{c['id']}] {c['title'][:75]}")
        conn.close()
        return

    conn = db.connect()
    conn.row_factory = sqlite3.Row
    db.ensure_schema()
    if args.trust_backfill or args.apply:
        n = compute_trust(conn)
        db.commit()
        print(f"trust backfilled: {n}")
    groups, merged = dedup_pass(conn, dry=args.dry)
    act = "dry-run" if args.dry else "applied"
    print(f"dedup {act}: {len(groups)} groups, {merged} duplicates merged")
    for keep, dups in groups[:10]:
        kt = conn.execute("SELECT title FROM events WHERE id=?", (keep,)).fetchone()
        print(f"  keep id={keep}: {kt['title'][:50] if kt else '?'}  (+{len(dups)} dup)")
    conn.close()


if __name__ == "__main__":
    main()
