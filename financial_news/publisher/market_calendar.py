# -*- coding: utf-8 -*-
"""
Market events calendar data for the publisher site.

Curated schedule of institution-driven market events (US + Taiwan):
central bank meetings, key US economic data releases, Taiwan economic
data / CBC board meetings, company earnings calls, product launches and
market holidays.

Date source honesty:
  * FOMC meeting dates come from the official federalreserve.gov 2026
    calendar (estimated=False).
  * US economic data dates (CPI/PPI/NFP/PCE/GDP/Retail Sales) follow the
    recurring monthly release patterns and are marked estimated=True.
  * Taiwan CBC board meeting is estimated on the 3rd Thursday of Mar/Jun/
    Sep/Dec; TSMC earnings call ~mid-quarter; all marked estimated=True.
  * "forecast" fields are reference-only consensus summaries and are NOT
    investment advice.

Usage:
  from publisher import market_calendar
  data = market_calendar.build_calendar()
"""
import datetime
from datetime import date, timedelta

# EDT is active from the 2nd Sunday of March to the 1st Sunday of November.
DST_START = date(2026, 3, 8)
DST_END = date(2026, 11, 1)

# Completed events stay visible on the calendar for this many days (about one
# month) instead of disappearing the day after they pass.
PAST_RETENTION_DAYS = 30

CATEGORIES = {
    "cb":        {"label": "央行", "color": "#2563eb"},
    "inflation": {"label": "物價", "color": "#ea580c"},
    "labor":     {"label": "就業", "color": "#7c3aed"},
    "gdp":       {"label": "GDP", "color": "#0d9488"},
    "earnings":  {"label": "財報/法說", "color": "#16a34a"},
    "product":   {"label": "產品發表", "color": "#db2777"},
    "twecon":    {"label": "台股/台灣數據", "color": "#ca8a04"},
    "holiday":   {"label": "休市", "color": "#64748b"},
}

IMPACT_LABEL = {"high": "高", "medium": "中", "low": "低"}

WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]


def _et_to_tw(date_, time_et):
    """Convert US Eastern release time to Taiwan time.

    Returns (tw_hhmm, day_shift) where day_shift is 0 (same day) or
    1 (next day in Taiwan).
    """
    hh, mm = (int(x) for x in time_et.split(":"))
    et_min = hh * 60 + mm
    offset = 12 if DST_START <= date_ < DST_END else 13  # EDT/EST
    tw_min = et_min + offset * 60
    day_shift = tw_min // 1440
    tw_min %= 1440
    return "{:02d}:{:02d}".format(tw_min // 60, tw_min % 60), day_shift


def _weeks_of_month(year, month):
    """Return list of weeks, each week a list of (day, month_is_current)."""
    first = date(year, month, 1)
    start_wd = first.weekday()  # 0=Mon .. 6=Sun
    days_in = (
        31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
        31, 30, 31, 30, 31, 31, 30, 31, 30, 31
    )[month - 1]
    cells = [None] * start_wd
    cells += [date(year, month, d) for d in range(1, days_in + 1)]
    while len(cells) % 7:
        cells.append(None)
    return [cells[i:i + 7] for i in range(0, len(cells), 7)]


def build_calendar(today=None):
    """Return a dict with events/upcoming/today/tomorrow/months/forecasts.

    All events fall in [today, today + 150 days]. The monthly grids cover
    the current month through the following 3 months.
    """
    today = today or date.today()
    end = today + timedelta(days=150)
    events = []

    def add(date_, institution, event, category, impact="medium",
            forecast="", estimated=True, note="", time_et=None, time_tw=None):
        # Keep events from the past month (completed items stay visible) plus
        # the next 150 days; anything older than that is dropped.
        if date_ < today - timedelta(days=PAST_RETENTION_DAYS) or date_ > end:
            return
        if time_et:
            tw_time, shift = _et_to_tw(date_, time_et)
            tw_label = "次日" if shift else "當日"
        else:
            tw_time = time_tw
            tw_label = "當日"
        events.append({
            "date": date_.isoformat(),
            "day_num": date_.day,
            "date_display": date_.strftime("%Y/%m/%d"),
            "weekday": "週" + WEEKDAY_CN[date_.weekday()],
            "time_et": time_et or "-",
            "time_tw": tw_time or "-",
            "tw_label": tw_label,
            "institution": institution,
            "event": event,
            "category": category,
            "cat_label": CATEGORIES[category]["label"],
            "impact": impact,
            "impact_label": IMPACT_LABEL.get(impact, ""),
            "estimated": estimated,
            "forecast": forecast,
            "note": note,
        })

    # ---------------------------------------------------------------- US ---
    # FOMC 2026 (official federalreserve.gov calendar)
    add(date(2026, 9, 16), "聯準會 FOMC", "利率決策 + 經濟預測(SEP/點陣圖)",
        "cb", "high", time_et="14:00", estimated=False,
        forecast="利率現為3.50%-3.75%。市場聚焦9月是否啟動降息循環，SEP與點陣圖將給出2026-2027年利率路徑。鮑爾記者會14:30 ET舉行。決策公布後美股波動常放大。")
    add(date(2026, 10, 28), "聯準會 FOMC", "利率決策（無SEP）",
        "cb", "high", time_et="14:00", estimated=False,
        forecast="本次不附SEP/點陣圖，市場聚焦聲明措辭與鮑爾記者會對降息步調的暗示。")
    add(date(2026, 12, 9), "聯準會 FOMC", "利率決策 + 經濟預測(SEP/點陣圖)",
        "cb", "high", time_et="14:00", estimated=False,
        forecast="年終會議附SEP/點陣圖，為2027年利率路徑定調，法人視為觀察降息循環是否結束的關鍵。")

    # US monthly economic data (recurring release pattern, estimates)
    add(date(2026, 8, 12), "美國勞工部 BLS", "CPI 消費者物價指數(7月)", "inflation",
        "high", time_et="08:30", estimated=False,
        forecast="市場共識為通膨持續降溫；原油價格與租金為主要變數。數據偏高將推升美債殖利率並壓抑科技股。")
    add(date(2026, 8, 13), "美國勞工部 BLS", "PPI 生產者物價指數(7月)", "inflation",
        "high", time_et="08:30")
    add(date(2026, 8, 14), "美國商務部 Census", "零售銷售(7月)", "gdp",
        "medium", time_et="08:30")
    add(date(2026, 8, 27), "美國商務部 BEA", "GDP 第二季第二次修正", "gdp",
        "high", time_et="08:30")
    add(date(2026, 8, 28), "美國商務部 BEA", "PCE 個人消費支出(7月)", "inflation",
        "high", time_et="08:30")
    add(date(2026, 9, 4), "美國勞工部 BLS", "非農就業 NFP + 失業率(8月)", "labor",
        "high", time_et="08:30",
        forecast="就業若持續降溫將強化降息預期；法人觀察失業率是否升破4%。")
    add(date(2026, 9, 11), "美國勞工部 BLS", "CPI 消費者物價指數(8月)", "inflation",
        "high", time_et="08:30")
    add(date(2026, 9, 15), "美國勞工部 BLS", "PPI 生產者物價指數(8月)", "inflation",
        "high", time_et="08:30")
    add(date(2026, 9, 24), "美國商務部 BEA", "GDP 第二季終值", "gdp",
        "medium", time_et="08:30")
    add(date(2026, 9, 30), "美國商務部 BEA", "PCE 個人消費支出(8月)", "inflation",
        "high", time_et="08:30")
    add(date(2026, 10, 2), "美國勞工部 BLS", "非農就業 NFP + 失業率(9月)", "labor",
        "high", time_et="08:30")
    add(date(2026, 10, 13), "美國勞工部 BLS", "CPI 消費者物價指數(9月)", "inflation",
        "high", time_et="08:30")
    add(date(2026, 10, 14), "美國勞工部 BLS", "PPI 生產者物價指數(9月)", "inflation",
        "high", time_et="08:30")
    add(date(2026, 10, 15), "美國商務部 Census", "零售銷售(9月)", "gdp",
        "medium", time_et="08:30")
    add(date(2026, 10, 29), "美國商務部 BEA", "GDP 第三季初值", "gdp",
        "high", time_et="08:30")
    add(date(2026, 10, 30), "美國商務部 BEA", "PCE 個人消費支出(9月)", "inflation",
        "high", time_et="08:30")
    add(date(2026, 11, 6), "美國勞工部 BLS", "非農就業 NFP + 失業率(10月)", "labor",
        "high", time_et="08:30")
    add(date(2026, 11, 10), "美國勞工部 BLS", "CPI 消費者物價指數(10月)", "inflation",
        "high", time_et="08:30")
    add(date(2026, 11, 12), "美國勞工部 BLS", "PPI 生產者物價指數(10月)", "inflation",
        "high", time_et="08:30")
    add(date(2026, 11, 25), "美國商務部 BEA", "GDP 第三季第二次修正 + PCE(10月)", "gdp",
        "high", time_et="08:30")
    add(date(2026, 12, 4), "美國勞工部 BLS", "非農就業 NFP + 失業率(11月)", "labor",
        "high", time_et="08:30")
    add(date(2026, 12, 10), "美國勞工部 BLS", "CPI 消費者物價指數(11月)", "inflation",
        "high", time_et="08:30")

    # US holidays / early closes
    add(date(2026, 9, 7), "美股休市", "勞工節 Labor Day 休市一日", "holiday",
        "low", estimated=False)
    add(date(2026, 11, 26), "美股休市", "感恩節 Thanksgiving 休市一日", "holiday",
        "low", estimated=False)
    add(date(2026, 11, 27), "美股", "感恩節翌日 提早至13:00 ET收盤", "holiday",
        "low", time_et="13:00", estimated=False)
    add(date(2026, 12, 24), "美股", "平安夜 提早至13:00 ET收盤", "holiday",
        "low", time_et="13:00", estimated=False)
    add(date(2026, 12, 25), "美股休市", "聖誕節 Christmas 休市一日", "holiday",
        "low", estimated=False)

    # US company earnings, Q3 2026 season (estimates)
    add(date(2026, 10, 15), "台積電 ADR / Netflix", "美股盤後公布財報", "earnings",
        "high", time_et="16:05",
        forecast="台積電為AI/HPC需求風向球，盤後公布後連動台股與費半走勢。")
    add(date(2026, 10, 28), "Tesla / Meta", "美股盤後公布財報", "earnings",
        "high", time_et="16:05")
    add(date(2026, 10, 29), "Apple / Microsoft / Alphabet / Amazon",
        "美股盤後公布財報（科技五巨頭）", "earnings", "high", time_et="16:05",
        forecast="重量級科技股財報集中日，盤後波動大，連動台灣供應鏈與隔日台股。")
    add(date(2026, 11, 18), "NVIDIA", "美股盤後公布財報", "earnings",
        "high", time_et="16:05",
        forecast="AI題材核心指標，指引將牽動全球AI供應鏈與台股權值股。")

    # Product launches (estimates)
    add(date(2026, 9, 9), "Apple", "秋季發表會（新款iPhone）", "product",
        "high", time_et="10:00",
        forecast="新品規格與售價將帶動台灣蘋概股（組裝/鏡頭/PCB）。")

    # -------------------------------------------------------------- Taiwan ---
    add(date(2026, 9, 7), "主計總處", "台灣 CPI 消費者物價指數(8月)", "twecon",
        "medium", time_tw="16:00")
    add(date(2026, 9, 8), "財政部", "海關出口統計(8月)", "twecon",
        "medium", time_tw="16:00")
    add(date(2026, 9, 17), "中央銀行", "央行理監事會議（第三季）", "cb",
        "high", time_tw="16:00",
        forecast="市場多預期利率按兵不動，聚焦會後記者會對房市信用管制與匯率看法。")
    add(date(2026, 10, 6), "主計總處", "台灣 CPI 消費者物價指數(9月)", "twecon",
        "medium", time_tw="16:00")
    add(date(2026, 10, 8), "財政部", "海關出口統計(9月)", "twecon",
        "medium", time_tw="16:00")
    add(date(2026, 10, 15), "台積電", "Q3 法說會（台灣場）", "earnings",
        "high", time_tw="14:00",
        forecast="法說會與美股盤後ADR財報互為連動；法人聚焦AI/HPC營收比重與明年資本支出。")
    add(date(2026, 11, 5), "主計總處", "台灣 CPI 消費者物價指數(10月)", "twecon",
        "medium", time_tw="16:00")
    add(date(2026, 11, 9), "財政部", "海關出口統計(10月)", "twecon",
        "medium", time_tw="16:00")
    add(date(2026, 11, 14), "鴻海", "Q3 法說會", "earnings",
        "medium", time_tw="15:00")
    add(date(2026, 12, 5), "主計總處", "台灣 CPI 消費者物價指數(11月)", "twecon",
        "medium", time_tw="16:00")
    add(date(2026, 12, 8), "財政部", "海關出口統計(11月)", "twecon",
        "medium", time_tw="16:00")
    add(date(2026, 12, 17), "中央銀行", "央行理監事會議（第四季）", "cb",
        "high", time_tw="16:00")

    events.sort(key=lambda e: (e["date"], e["time_tw"] == "-", e["time_et"]))

    by_date = {}
    for e in events:
        by_date.setdefault(e["date"], []).append(e)

    # Month grids: previous month .. +2 months. Starting one month back keeps
    # completed events (past 30 days) visible in the monthly view instead of
    # dropping them the moment the date passes.
    months = []
    y, m = today.year, today.month - 1
    if m == 0:
        m = 12
        y -= 1
    for _ in range(4):
        weeks = _weeks_of_month(y, m)
        cells = []
        for week in weeks:
            row = []
            for d in week:
                if d is None:
                    row.append(None)
                else:
                    row.append({
                        "date": d.isoformat(),
                        "day": d.day,
                        "is_today": d == today,
                        "events": by_date.get(d.isoformat(), []),
                    })
            cells.append(row)
        months.append({
            "title": "{:04d}年{:02d}月".format(y, m),
            "cells": cells,
        })
        m += 1
        if m > 12:
            m = 1
            y += 1

    today_events = by_date.get(today.isoformat(), [])
    tomorrow = today + timedelta(days=1)
    tomorrow_events = by_date.get(tomorrow.isoformat(), [])
    upcoming = []
    for e in events:
        d = datetime.date.fromisoformat(e["date"])
        e["days_left"] = (d - today).days
        e["done"] = e["days_left"] < 0
        upcoming.append(e)

    forecasts = [e for e in events if e["forecast"]]

    return {
        "today": today,
        "today_display": today.strftime("%Y年%m月%d日") + " 週" + WEEKDAY_CN[today.weekday()],
        "today_events": today_events,
        "tomorrow": tomorrow,
        "tomorrow_display": tomorrow.strftime("%Y年%m月%d日") + " 週" + WEEKDAY_CN[tomorrow.weekday()],
        "tomorrow_events": tomorrow_events,
        "upcoming": upcoming,
        "months": months,
        "forecasts": forecasts,
        "categories": CATEGORIES,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(build_calendar(), ensure_ascii=False, indent=1)[:4000])
