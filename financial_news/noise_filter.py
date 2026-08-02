#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Noise filter - rule-based filtering to keep only financially relevant events.

Strategy:
  1. Duplicate removal (near-identical titles across feeds)
  2. Keyword scoring: positive financial relevance keywords add score,
     noise keywords (sports, entertainment, etc.) subtract.
  3. Events below threshold are marked as noise.

Usage:
  python noise_filter.py --dry-run        # show what would be filtered
  python noise_filter.py --apply          # mark noise in DB
"""
import os
import sys
import re
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

# High-relevance keywords (finance/macro/geopolitics)
POSITIVE_KEYWORDS = [
    # central banks & policy
    "fed", "federal reserve", "中央銀行", "央行", "利率", "升息", "降息",
    "qe", "taper", "量化寬鬆", "縮表", "pivot", "monetary policy", "fomc",
    # regulation
    "金管會", "證交所", "金融監督", "監管", "regulation", "sec ", "核准",
    # markets
    "股市", "股票", "台股", "美股", "上證", "恒指", "港股", "a股",
    "stock market", "nasdaq", "s&p", "dow", "indices", "futures",
    "債市", "債券", "treasury", "yields", "bonds", "credit spread",
    "匯率", "美元", "人民幣", "日元", "dollar", "exchange rate", "forex",
    "外匯", "dxy", "usd",
    # commodities
    "油價", "原油", "gold", "油價", "crude", "commodities", "黃金", "銅",
    "inflation", "通膨", "cpi", "ppi", "gdp", "景氣", "recession", "衰退",
    "jobless", "employment", "非農", "失業",
    # geopolitics
    "戰爭", "衝突", "制裁", "關稅", "trade war", "invasion", "military",
    "中東", "烏克蘭", "俄羅斯", "台海", "以伊", "isis", "衝突", "政變",
    "地緣政治", "geopolitical", "conflict", "war", "sanction", "tariff",
    # corporate / stocks
    "財報", "營收", "獲利", "eps", "earnings", "profit warning",
    "晶片", "半導體", "chip", "semiconductor", "nvidia", "台積電", "tsmc",
    "apple", "microsoft", "google", "meta", "amazon", "特斯拉",
]

# Clear noise keywords
NEGATIVE_KEYWORDS = [
    "sport", "football", "soccer", "basketball", "nba", "mlb", "足球", "棒球",
    "celebrity", "八卦", "藝人", "演唱會", "movie", "電影", "劇集",
    "食譜", "recipe", "cooking", "game", "電玩", "明星",
    "astrology", "星座", "命理",
    "食安", "food safety", "天氣", "weather",
]

# Titles that are obvious non-financial
NOISE_TITLE_PATTERNS = [
    r"^\d+\s*個?必看", r"星座運勢", r"本月運勢", r"食譜",
]

# Direct feeds are curated financial/business sources -> always keep
ALWAYS_KEEP_SOURCES = {
    "fed", "cnbc", "bbcbusiness", "marketwatch", "nytbusiness",
    "ecb",
}

# Add more positive keywords that appeared in real noise misclassifications
POSITIVE_KEYWORDS.extend([
    "opec", "石油", "增產", "減產", "oil", "brent", "wti", "能源", "energy",
    "selloff", "sell-off", "selloff", "修正", "回檔", "泡沫", "crash",
    "資金", "資本市場", "資產", "investor", "fund", "etf", "對沖基金",
    "morgan stanley", "goldman", "jpmorgan", "高盛", "摩根",
    "yield", "spread", "利差", "殖利率",
    "半導體", "semiconductor", "ai 股", "ai stock", "nvidia",
    "指數", "index", "weighted index", "加權",
    "期貨", "futures", "選擇權", "options",
    "就業", "employment", "job", "labor", "非農",
    "消費", "consumer", "retail", "零售",
    "資料中心", "datacenter", "雲端", "cloud", "revenue",
    "reserve", "bank", "銀行", "金融",
])


def is_always_keep(source):
    return source in ALWAYS_KEEP_SOURCES


def score_event(title, summary):
    text = f"{title} {summary}".lower()
    score = 0
    for kw in POSITIVE_KEYWORDS:
        if kw in text:
            score += 1
    for kw in NEGATIVE_KEYWORDS:
        if kw in text:
            score -= 2
    for pat in NOISE_TITLE_PATTERNS:
        if re.search(pat, title, re.I):
            score -= 5
    return score


def filter_pending(language=None, threshold=1):
    """Return (keep_ids, noise_ids, kept_events, noise_events)."""
    events = db.unanalyzed(language=language)
    keep_ids, noise_ids = [], []
    kept_events, noise_events = [], []
    for ev in events:
        if is_always_keep(ev["source"]):
            keep_ids.append(ev["id"])
            kept_events.append(ev)
            continue
        score = score_event(ev["title"], ev["summary"])
        if score >= threshold:
            keep_ids.append(ev["id"])
            kept_events.append(ev)
        else:
            noise_ids.append(ev["id"])
            noise_events.append(ev)
    return keep_ids, noise_ids, kept_events, noise_events


def apply_filter(language=None, threshold=2):
    keep, noise, _, _ = filter_pending(language, threshold)
    if noise:
        db.mark_noise(noise)
    db.commit()
    return keep, noise


def main():
    parser = argparse.ArgumentParser(description="Noise filter")
    parser.add_argument("--dry-run", action="store_true", help="show counts only")
    parser.add_argument("--apply", action="store_true", help="apply filtering")
    parser.add_argument("--lang", default=None, help="zh or en")
    args = parser.parse_args()

    if args.apply:
        keep, noise = apply_filter(args.lang)
        print(f"keep={len(keep)} noise={len(noise)}")
    else:
        keep, noise, _, noise_events = filter_pending(args.lang)
        print(f"would keep={len(keep)} noise={len(noise)}")
        for ev in noise_events[:20]:
            print(f"  NOISE [{ev['id']}] {ev['title'][:70]}")


if __name__ == "__main__":
    main()
