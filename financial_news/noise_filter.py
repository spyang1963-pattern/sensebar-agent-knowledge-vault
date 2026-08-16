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

# Key-news protection: even if rule score is low, these patterns force KEEP.
# This prevents important market/central-bank news from being killed as noise.
KEY_NEWS_PATTERNS = [
    # Taiwan market close / index moves
    r"台股.*(收盤|收在|收報)",
    r"(收盤|收在|收報).*台股",
    r"加權指數",
    r"(大漲|大跌|飆漲|崩跌|狂漲|暴跌)\s*[\d,]+點",
    r"(漲|跌)\s*[\d,]+點\s*(收|攻|回)",
    # Central banks / policy
    r"中央銀行", r"央行", r"升息", r"降息",
    r"Fed\b", r"FOMC", r"Federal Reserve",
    # Regulation
    r"金管會", r"證交所", r"證監會", r"\bSEC\b",
    # Geopolitics
    r"(戰爭|開戰|襲擊|空襲|入侵|交火)",
    r"(制裁|封鎖)\s*[^，。]{0,6}(俄|伊朗|中|北韓)",
    # Earnings / corporate milestones
    r"(營收|財報|獲利).{0,12}(新高|創高|破紀錄|超預期|暴雷)",
    r"(新高|創高|破紀錄|超預期|暴雷).{0,12}(營收|財報|獲利)",
]

# Sources that bypass rule scoring entirely (high trust) - split from ALWAYS_KEEP
# so that borderline sources still need a minimal relevance check.
KEEP_ON_SIGHT = {
    "fed", "ecb",
}

# Companies whose standalone corporate news (earnings, guidance, ratings...)
# is worth keeping. Everything else that is a pure single-stock event is noise.
IMPORTANT_COMPANIES = [
    # 台股權值
    "台積電", "tsmc", "2330", "鴻海", "2317", "聯發科", "2454", "台達電", "2308", "廣達", "2382",
    "聯電", "2303", "中華電", "2412", "大立光", "3008", "緯創", "3231", "日月光", "3711",
    "國泰金", "2882", "富邦金", "2881", "中鋼", "2002", "台塑", "1301", "長榮", "2603",
    "兆豐金", "2886", "玉山金", "2884", "台塑化", "6505", "南亞", "1303", "統一", "1216",
    "國巨", "2327", "華碩", "2357", "和碩", "4938",
    # 台股重要電子供應鏈
    "光寶科", "2301", "崇越", "5434", "世芯", "3661", "臻鼎", "4958", "穩懋", "3105",
    "環球晶", "6488", "緯穎", "6669", "信驊", "5274", "創意", "3443", "聯詠", "3034",
    "群聯", "8299", "南亞科", "2408", "世界先進", "5347", "京元電", "2449", "英業達", "2356",
    "仁寶", "2324", "奇鋐", "3017", "雙鴻", "3324", "台灣大哥大", "3045", "遠傳", "4904",
    # 美股大型 + AI 鏈
    "apple", "蘋果", "microsoft", "微軟", "nvidia", "輝達", "google", "alphabet",
    "meta", "amazon", "亞馬遜", "tesla", "特斯拉", "netflix", "intel", "英特爾",
    "amd", "超微", "broadcom", "博通", "qualcomm", "高通", "oracle", "adobe",
    "salesforce", "美光", "micron", "三星", "samsung", "openai", "anthropic", "tsm",
    "阿里巴巴", "騰訊", "tencent", "百度", "jpmorgan", "摩根大通", "高盛", "goldman",
    "波克夏", "berkshire", "巴菲特", "花旗", "citi", "富國銀行", "wells fargo",
    "美國銀行", "bank of america", "迪士尼", "disney", "沃爾瑪", "walmart", "輝瑞", "pfizer",
    "可口可樂", "coca-cola", "nike", "星巴克", "starbucks",
]
IMPORTANT_COMPANIES_RE = re.compile(
    "|".join(re.escape(k) for k in IMPORTANT_COMPANIES), re.I
)

# Macro context that protects a corporate-looking headline from the
# small-company-noise rule (macro news can mention earnings/guidance).
MACRO_PROTECT_PATTERNS = [
    r"股市", r"大盤", r"指數", r"加權", r"nasdaq", r"s&p", r"dow", r"道瓊",
    r"央行", r"central bank", r"fed\b", r"聯準會", r"日銀", r"BOJ",
    r"通膨", r"inflation", r"cpi", r"ppi", r"升息", r"降息", r"rate hike", r"rate cut",
    r"油價", r"原油", r"crude", r"gold\b", r"brent", r"wti",
    r"地緣", r"關稅", r"tariff", r"war\b", r"戰爭", r"制裁",
    r"navy", r"military", r"海軍", r"演習", r"drill", r"國防", r"defense", r"軍事",
    r"中國", r"china", r"北韓", r"north korea", r"伊朗", r"iran", r"俄羅斯", r"russia",
    r"台股", r"美股", r"stock market", r"stock futures", r"market", r"recession", r"衰退",
    r"利率", r"yield", r"殖利率", r"美債", r"債市", r"資金", r"etf",
    r"財報季", r"earnings season", r"企業獲利",
    r"本週", r"week ahead", r"weekly", r"週報", r"weekly report",
    r"匯率", r"外匯", r"美元指數", r"bitcoin", r"比特幣",
    r"就業", r"nonfarm", r"非農", r"unemployment", r"失業",
    r"穆迪", r"moody", r"標普", r"s&p global", r"惠譽", r"fitch", r"評級機構",
    r"系統性", r"資安", r"網路安全", r"上櫃", r"興櫃", r"上市櫃", r"產業", r"族群", r"供應鏈",
    r"重電", r"電網", r"缺電",
]
MACRO_PROTECT_RE = re.compile("|".join(MACRO_PROTECT_PATTERNS), re.I)

# Pure single-stock corporate event patterns (earnings/guidance/ratings/...).
CORPORATE_EVENT_PATTERNS = [
    r"財報", r"營收", r"每股盈餘", r"eps\b", r"dividend", r"股息", r"buyback", r"回購",
    r"執行長", r"董事長", r"任命", r"appoint", r"resign", r"辭職", r"離職",
    r"裁員", r"layoff", r"bankrupt", r"破產", r"acqui", r"併購", r"merger",
    r"評級", r"rating", r"目標價", r"target price", r"stock split", r"分割股票",
    r"下市", r"delist", r"上市", r"ipo",
]
CORPORATE_EVENT_RE = re.compile("|".join(CORPORATE_EVENT_PATTERNS), re.I)


def is_small_corp_noise(title, summary):
    """Pure single-stock corporate news about a non-important company -> noise.

    Returns True only when the event is corporate-only (no macro context) and
    does not mention any IMPORTANT_COMPANIES member.
    """
    text = f"{title} {summary}"
    if MACRO_PROTECT_RE.search(text):
        return False
    if not CORPORATE_EVENT_RE.search(text):
        return False
    if IMPORTANT_COMPANIES_RE.search(text):
        return False
    return True

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


def is_key_news(title, summary):
    """True if the event matches key-news protection rules (force keep)."""
    text = f"{title} {summary}"
    for pat in KEY_NEWS_PATTERNS:
        if re.search(pat, text, re.I):
            return True
    return False


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
        title, summary, source = ev["title"], ev["summary"], ev["source"]
        if is_key_news(title, summary):
            keep_ids.append(ev["id"])
            kept_events.append(ev)
            continue
        if source in KEEP_ON_SIGHT:
            keep_ids.append(ev["id"])
            kept_events.append(ev)
            continue
        if is_small_corp_noise(title, summary):
            noise_ids.append(ev["id"])
            noise_events.append(ev)
            continue
        score = score_event(title, summary)
        if is_always_keep(source):
            # curated feed but still needs a minimal relevance signal,
            # otherwise junk like lifestyle pieces slips through
            if score >= -1:
                keep_ids.append(ev["id"])
                kept_events.append(ev)
            else:
                noise_ids.append(ev["id"])
                noise_events.append(ev)
            continue
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


def recover_noise(hours=48, apply=False):
    """Rescue noise-flagged events that actually match key-news protection.

    Looks back `hours` hours by published time; if a noise event matches
    key-news patterns, un-mark it so it can be analyzed.  Returns rescued ids.
    """
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(
        timespec="seconds"
    )
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM events WHERE is_noise=1 AND published>=?",
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()
    rescued = []
    for ev in rows:
        ev = dict(ev)
        if is_key_news(ev["title"], ev["summary"]):
            rescued.append(ev["id"])
    if apply and rescued:
        import sqlite3 as _s
        db._WRITE_LOCK.acquire()
        try:
            mc = db._master_conn()
            mc.execute(
                "UPDATE events SET is_noise=0 WHERE id IN ({})".format(
                    ",".join("?" * len(rescued))
                ),
                rescued,
            )
            mc.commit()
        finally:
            db._WRITE_LOCK.release()
    return rescued


def main():
    parser = argparse.ArgumentParser(description="Noise filter")
    parser.add_argument("--dry-run", action="store_true", help="show counts only")
    parser.add_argument("--apply", action="store_true", help="apply filtering")
    parser.add_argument("--lang", default=None, help="zh or en")
    parser.add_argument("--recover", action="store_true",
                        help="rescue noise events that match key-news protection")
    parser.add_argument("--recover-hours", type=int, default=48)
    args = parser.parse_args()

    if args.recover:
        rescued = recover_noise(hours=args.recover_hours, apply=args.apply)
        act = "已回收" if args.apply else "將回收(dry)"
        print(f"{act} {len(rescued)} 筆命中關鍵新聞保護的誤殺事件")
        for eid in rescued[:20]:
            print(f"  id={eid}")
        return
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
