"""
本地融資資料快取管理
每天抓完資料存 CSV，隔天跟前一天比對計算融資增減
"""
import os
import csv
from datetime import datetime, timedelta
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "output" / "cache"
CSV_FILE = CACHE_DIR / "margin_history.csv"


def load_cache(max_days: int = 7) -> list[dict]:
    """讀取 CSV 快取，回傳最近 N 天的資料"""
    if not CSV_FILE.exists():
        return []

    rows = []
    with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # 依照日期分組，取最近 max_days 個日期
    dates = sorted(set(r["date"] for r in rows), reverse=True)[:max_days]
    return [r for r in rows if r["date"] in dates]


def save_today(margin_data: list[dict], date_str: str):
    """
    將今天的融資資料存入 CSV
    margin_data: [{"stock_id": "2330", "margin_balance": 33293, ...}, ...]
    date_str: "2026-07-15"
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # 讀取舊資料
    existing = []
    if CSV_FILE.exists():
        with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            existing = list(reader)

    # 移除今天已有的資料（避免重複）
    existing = [r for r in existing if r.get("date") != date_str]

    # 加入今天的新資料
    for item in margin_data:
        existing.append({
            "date": date_str,
            "stock_id": item.get("stock_id", ""),
            "stock_name": item.get("stock_name", ""),
            "margin_balance": item.get("margin_balance", 0),
            "short_balance": item.get("short_balance", 0),
        })

    # 寫回 CSV
    fieldnames = ["date", "stock_id", "stock_name", "margin_balance", "short_balance"]
    with open(CSV_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing)

    print(f"  [CACHE] 已儲存 {len(margin_data)} 筆資料到 {CSV_FILE.name}")


def compute_margin_changes(today_data: list[dict], cache: list[dict]) -> dict[str, dict]:
    """
    比對今天跟昨天的資料，計算融資增減

    回傳: {
        "2330": {
            "margin_balance_today": 33293,
            "margin_change": -500,       # 跟昨天比
            "margin_change_pct": -1.48,  # 變動百分比
            "margin_change_3d": -1200,   # 跟3天前比（如果有的話）
        },
        ...
    }
    """
    # 取得所有日期，排序
    all_dates = sorted(set(r["date"] for r in cache))

    if len(all_dates) < 1:
        print("  [CACHE] 沒有歷史資料，融資增減全部為 0")
        return {}

    # 建立每天的資料索引
    daily = {}
    for d in all_dates:
        daily[d] = {r["stock_id"]: r for r in cache if r["date"] == d}

    # 今天的日期（從今天資料推斷）
    today_date = today_data[0].get("date", "") if today_data else ""

    # 取得今天的前一個交易日
    prev_dates = [d for d in all_dates if d < today_date]
    prev_date = prev_dates[-1] if prev_dates else None

    # 取得3天前的日期
    dates_3d = [d for d in all_dates if d < today_date]
    date_3d = dates_3d[-3] if len(dates_3d) >= 3 else (dates_3d[0] if dates_3d else None)

    result = {}

    for item in today_data:
        sid = item.get("stock_id", "")
        margin_today = item.get("margin_balance", 0)

        margin_prev = int(daily.get(prev_date, {}).get(sid, {}).get("margin_balance", 0)) if prev_date else 0
        margin_3d = int(daily.get(date_3d, {}).get(sid, {}).get("margin_balance", 0)) if date_3d else 0

        change = margin_today - margin_prev if margin_prev else 0
        change_pct = (change / margin_prev * 100) if margin_prev else 0
        change_3d = margin_today - margin_3d if margin_3d else 0

        result[sid] = {
            "margin_balance_today": margin_today,
            "margin_change": change,
            "margin_change_pct": round(change_pct, 2),
            "margin_change_3d": change_3d,
        }

    if prev_date:
        print(f"  [CACHE] 比對日期: {today_date} vs {prev_date}")
    else:
        print(f"  [CACHE] 無歷史比對資料，融資增減為 0")

    return result


def get_cache_info() -> dict:
    """回傳快取狀態摘要"""
    result = {"raw": "快取：無資料", "最新日期": None, "天數": 0}
    if not CSV_FILE.exists():
        return result

    cache = load_cache()
    dates = sorted(set(r["date"] for r in cache))
    result["raw"] = f"快取：{len(dates)} 天資料 ({', '.join(dates)})"
    result["天數"] = len(dates)
    if dates:
        result["最新日期"] = dates[-1]
    return result


if __name__ == "__main__":
    print(get_cache_info())
    cache = load_cache()
    if cache:
        print(f"  共 {len(cache)} 筆記錄")
        dates = sorted(set(r["date"] for r in cache))
        print(f"  日期範圍: {dates[0]} ~ {dates[-1]}")
