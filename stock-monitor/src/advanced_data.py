"""
進階籌碼資料模組 v1
- 回補近 N 天歷史：融資/融券餘額（今日值）、三大法人買賣超、個股收盤價、
  大盤融資金額與整體維持率估算
- 增量更新：每日只抓缺失的交易日，避免重複浪費請求
- 個股 K 線快取：TWSE STOCK_DAY 歷史走勢

資料源（均使用 TWSE 官方 API）：
  MI_MARGN   -> 融資融券明細（今日餘額）+ 大盤信用交易統計
  MI_INDEX   -> 每日收盤行情（全部） + 加權指數
  T86        -> 三大法人買賣超
  STOCK_DAY  -> 個股日 K 線
"""
import os
import csv
import json
import time
import requests
from datetime import datetime, timedelta

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_BASE, "output", "cache")
MARGIN_CSV = os.path.join(CACHE_DIR, "margin_history.csv")
INST_CSV = os.path.join(CACHE_DIR, "institutional_history.csv")
MARKET_CSV = os.path.join(CACHE_DIR, "market_daily.csv")
KLINE_DIR = os.path.join(CACHE_DIR, "kline")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "zh-TW,zh;q=0.9",
}


def _parse_num(s):
    try:
        if s is None:
            return 0
        return int(float(str(s).replace(",", "").replace("--", "0").strip() or 0))
    except (ValueError, TypeError):
        return 0


def _get(session, url, params, timeout=30, retries=3):
    for i in range(retries):
        try:
            resp = session.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if i == retries - 1:
                print(f"    [HTTP] 失敗 {url} {params} : {e}")
                return None
            time.sleep(1.5)
    return None


class HistoryData:
    """回補 + 讀取歷史籌碼資料"""

    def __init__(self, calendar_days=60):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.calendar_days = calendar_days
        os.makedirs(CACHE_DIR, exist_ok=True)
        os.makedirs(KLINE_DIR, exist_ok=True)

    # ---------- 對外主要方法 ----------

    def refresh(self, force=False):
        """增量回補歷史資料到最新交易日，並確保窗口內日期齊全；force=True 強制重建全部"""
        latest = self.latest_trading_day()
        if not latest:
            print("  [ADV] 無法取得最新交易日，跳過回補")
            return False

        known_dates = self._read_market_dates()
        inst_cov = self._read_inst_coverage()
        start = (datetime.strptime(latest, "%Y-%m-%d") - timedelta(days=self.calendar_days)).strftime("%Y-%m-%d")

        # 窗口內缺少的日期（只算平日，避免週末/例假日無限重試）
        # market_daily 缺該日，或法人資料缺失/異常少（T86 曾失敗）都需回補
        missing = []
        d = datetime.strptime(start, "%Y-%m-%d")
        end = datetime.strptime(latest, "%Y-%m-%d")
        while d <= end:
            if d.weekday() < 5:
                ds = d.strftime("%Y-%m-%d")
                if ds not in known_dates or inst_cov.get(ds, 0) < 500:
                    missing.append(ds)
            d += timedelta(days=1)

        if not missing:
            print(f"  [ADV] 歷史資料已涵蓋窗口（{start} ~ {latest}），無需回補")
            return True

        # 全新回補（無 market_daily.csv）才整建 margin_history.csv
        rebuild_margin = not known_dates or not os.path.exists(MARGIN_CSV)

        print(f"  [ADV] 需回補 {len(missing)} 個日期 ({start} ~ {latest})")
        fetched_days = []
        for i, ds in enumerate(missing):
            day = self.fetch_one_day(ds)
            if day:
                fetched_days.append(day)
                print(f"  [ADV]   {ds}: {len(day['stocks'])} 檔 維持率 {day['market'].get('maintenance', 0):.1f}%")
            if i % 5 == 4:
                time.sleep(0.5)

        if fetched_days:
            self._write_market(fetched_days)
            self._write_inst(fetched_days)
            if rebuild_margin:
                self._rebuild_margin(fetched_days)
            else:
                self._append_margin(fetched_days)
            print(f"  [ADV] 回補完成，共 {len(fetched_days)} 個交易日")
            return True
        print("  [ADV] 本次沒有抓到新資料")
        return False

    # ---------- 資料抓取 ----------

    def latest_trading_day(self):
        d = _get(self.session, "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN",
                 {"response": "json", "selectType": "ALL"})
        if d and d.get("stat") == "OK" and d.get("date"):
            s = str(d["date"])
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return None

    def fetch_one_day(self, date_str):
        """抓取單一交易日的完整籌碼資料"""
        param_date = date_str.replace("-", "")
        margin = self._fetch_margin(param_date)
        if margin is None:
            return None
        prices, index = self._fetch_prices(param_date)
        inst = self._fetch_inst(param_date)

        # 計算整體維持率估算 = 融資擔保品市值 / 融資金額
        mkt = margin["market"]
        numerator = 0.0
        for s in margin["stocks"]:
            close = prices.get(s["stock_id"], 0)
            if close > 0 and s["margin_balance"] > 0:
                numerator += close * s["margin_balance"] * 1000
        denominator = mkt.get("margin_amount_k", 0) * 1000
        mkt["maintenance"] = round(numerator / denominator * 100, 2) if denominator > 0 else 0
        mkt["index"] = index.get("index", 0) if index else 0
        mkt["index_change"] = index.get("change", 0) if index else 0
        mkt["index_pct"] = index.get("pct", 0) if index else 0

        return {"date": date_str, "stocks": margin["stocks"], "market": mkt, "inst": inst}

    def _fetch_margin(self, param_date):
        d = _get(self.session, "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN",
                 {"response": "json", "date": param_date, "selectType": "ALL"})
        if not d or d.get("stat") != "OK":
            return None
        tables = d.get("tables", [])
        if len(tables) < 2:
            return None
        # tables[0] 大盤信用交易統計
        market = {"margin_qty": 0, "margin_qty_prev": 0, "margin_amount_k": 0,
                  "margin_amount_k_prev": 0, "short_qty": 0, "short_qty_prev": 0,
                  "margin_buy": 0, "margin_sell": 0, "margin_repay": 0,
                  "short_sell": 0, "short_buy": 0, "short_repay": 0}
        for row in tables[0].get("data", []):
            key = str(row[0]).strip()
            if key == "融資(交易單位)":
                market["margin_qty"] = _parse_num(row[5])
                market["margin_qty_prev"] = _parse_num(row[4])
            elif key == "融資金額(仟元)":
                market["margin_amount_k"] = _parse_num(row[5])
                market["margin_amount_k_prev"] = _parse_num(row[4])
            elif key == "融券(交易單位)":
                market["short_qty"] = _parse_num(row[5])
                market["short_qty_prev"] = _parse_num(row[4])
        # 買進/賣出/償還 從明細加總（tables[1]）
        stocks = []
        for row in tables[1].get("data", []):
            try:
                stock_id = str(row[0]).strip()
                if not stock_id.isdigit():
                    continue
                stocks.append({
                    "stock_id": stock_id,
                    "stock_name": str(row[1]).strip(),
                    "margin_balance": _parse_num(row[6]),
                    "short_balance": _parse_num(row[12]),
                    "margin_buy": _parse_num(row[2]),
                    "margin_sell": _parse_num(row[3]),
                    "margin_repay": _parse_num(row[4]),
                    "short_sell": _parse_num(row[9]),
                    "short_buy": _parse_num(row[8]),
                    "short_repay": _parse_num(row[10]),
                    "offset": _parse_num(row[14]),
                })
            except (IndexError, ValueError):
                continue
        for s in stocks:
            market["margin_buy"] += s["margin_buy"]
            market["margin_sell"] += s["margin_sell"]
            market["margin_repay"] += s["margin_repay"]
            market["short_sell"] += s["short_sell"]
            market["short_buy"] += s["short_buy"]
            market["short_repay"] += s["short_repay"]
        return {"stocks": stocks, "market": market}

    def _fetch_prices(self, param_date):
        d = _get(self.session, "https://www.twse.com.tw/exchangeReport/MI_INDEX",
                 {"response": "json", "date": param_date, "type": "ALL"})
        if not d or d.get("stat") != "OK":
            return {}, None
        prices = {}
        index = None
        for t in d.get("tables", []):
            title = str(t.get("title") or "")
            if "每日收盤行情" in title:
                for row in t.get("data", []):
                    try:
                        code = str(row[0]).strip()
                        if not code.isdigit():
                            continue
                        close = _parse_num(row[8])
                        if close > 0:
                            prices[code] = close
                    except (IndexError, ValueError):
                        continue
            elif "價格指數" in title and "臺灣證券交易所" in title:
                for row in t.get("data", []):
                    if str(row[0]).strip() == "發行量加權股價指數":
                        index = {
                            "index": _parse_num(row[1]),
                            "change": _parse_num(row[3]),
                            "pct": _parse_num(row[4]),
                        }
                        break
        return prices, index

    def _fetch_inst(self, param_date):
        d = _get(self.session, "https://www.twse.com.tw/fund/T86",
                 {"response": "json", "date": param_date, "selectType": "ALL"})
        if not d or d.get("stat") != "OK":
            return {}
        result = {}
        for row in d.get("data", []):
            try:
                code = str(row[0]).strip()
                if not code.isdigit():
                    continue
                result[code] = {
                    "name": str(row[1]).strip(),
                    "foreign_net": _parse_num(row[4]),
                    "trust_net": _parse_num(row[10]),
                    "dealer_net": _parse_num(row[11]),
                    "total_net": _parse_num(row[18]),
                }
            except (IndexError, ValueError):
                continue
        return result

    # ---------- 寫檔 ----------

    def _write_market(self, days):
        path = MARKET_CSV
        existing = self._read_market_dates()
        keep = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                for r in csv.DictReader(f):
                    if r.get("date") not in {day["date"] for day in days}:
                        keep.append(r)
        fieldnames = ["date", "index", "index_change", "index_pct",
                      "margin_qty", "margin_qty_prev", "margin_amount_k", "margin_amount_k_prev",
                      "short_qty", "short_qty_prev",
                      "margin_buy", "margin_sell", "margin_repay",
                      "short_sell", "short_buy", "short_repay", "maintenance"]
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in keep:
                w.writerow({k: r.get(k, "") for k in fieldnames})
            for day in days:
                m = day["market"]
                w.writerow({
                    "date": day["date"], "index": m.get("index", 0), "index_change": m.get("index_change", 0),
                    "index_pct": m.get("index_pct", 0), "margin_qty": m.get("margin_qty", 0),
                    "margin_qty_prev": m.get("margin_qty_prev", 0), "margin_amount_k": m.get("margin_amount_k", 0),
                    "margin_amount_k_prev": m.get("margin_amount_k_prev", 0), "short_qty": m.get("short_qty", 0),
                    "short_qty_prev": m.get("short_qty_prev", 0), "margin_buy": m.get("margin_buy", 0),
                    "margin_sell": m.get("margin_sell", 0), "margin_repay": m.get("margin_repay", 0),
                    "short_sell": m.get("short_sell", 0), "short_buy": m.get("short_buy", 0),
                    "short_repay": m.get("short_repay", 0), "maintenance": m.get("maintenance", 0),
                })

    def _write_inst(self, days):
        path = INST_CSV
        keep = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                for r in csv.DictReader(f):
                    if r.get("date") not in {day["date"] for day in days}:
                        keep.append(r)
        fieldnames = ["date", "stock_id", "stock_name", "foreign_net", "trust_net", "dealer_net", "total_net"]
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in keep:
                w.writerow({k: r.get(k, "") for k in fieldnames})
            for day in days:
                for code, v in day["inst"].items():
                    w.writerow({
                        "date": day["date"], "stock_id": code, "stock_name": v.get("name", ""),
                        "foreign_net": v.get("foreign_net", 0), "trust_net": v.get("trust_net", 0),
                        "dealer_net": v.get("dealer_net", 0), "total_net": v.get("total_net", 0),
                    })

    def _rebuild_margin(self, days):
        fieldnames = ["date", "stock_id", "stock_name", "margin_balance", "short_balance"]
        with open(MARGIN_CSV, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for day in days:
                for s in day["stocks"]:
                    w.writerow({
                        "date": day["date"], "stock_id": s["stock_id"], "stock_name": s["stock_name"],
                        "margin_balance": s["margin_balance"], "short_balance": s["short_balance"],
                    })

    def _append_margin(self, days):
        fieldnames = ["date", "stock_id", "stock_name", "margin_balance", "short_balance"]
        existing_dates = set()
        keep = []
        if os.path.exists(MARGIN_CSV):
            with open(MARGIN_CSV, "r", encoding="utf-8-sig", errors="replace") as f:
                for r in csv.DictReader(f):
                    existing_dates.add(r.get("date"))
                    keep.append(r)
        # 移除要重抓的日期，避免重複
        new_dates = {day["date"] for day in days}
        keep = [r for r in keep if r.get("date") not in new_dates]
        with open(MARGIN_CSV, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(keep)
            for day in days:
                for s in day["stocks"]:
                    w.writerow({
                        "date": day["date"], "stock_id": s["stock_id"], "stock_name": s["stock_name"],
                        "margin_balance": s["margin_balance"], "short_balance": s["short_balance"],
                    })

    def _read_market_dates(self):
        if not os.path.exists(MARKET_CSV):
            return set()
        with open(MARKET_CSV, "r", encoding="utf-8-sig", errors="replace") as f:
            return {r.get("date") for r in csv.DictReader(f) if r.get("date")}

    def _read_inst_coverage(self):
        """統計 institutional_history.csv 各日期列數，用於偵測法人資料缺失"""
        cov = {}
        if os.path.exists(INST_CSV):
            with open(INST_CSV, "r", encoding="utf-8-sig", errors="replace") as f:
                for r in csv.DictReader(f):
                    d = r.get("date")
                    if d:
                        cov[d] = cov.get(d, 0) + 1
        return cov

    # ---------- 讀取圖表資料 ----------

    def load_market_series(self):
        """大盤每日序列，依日期排序"""
        rows = []
        if os.path.exists(MARKET_CSV):
            with open(MARKET_CSV, "r", encoding="utf-8-sig", errors="replace") as f:
                rows = [r for r in csv.DictReader(f) if r.get("date")]
        rows.sort(key=lambda r: r["date"])
        return rows

    def load_inst_series(self, stock_id):
        rows = []
        if os.path.exists(INST_CSV):
            with open(INST_CSV, "r", encoding="utf-8-sig", errors="replace") as f:
                for r in csv.DictReader(f):
                    if r.get("stock_id") == stock_id:
                        rows.append(r)
        rows.sort(key=lambda r: r["date"])
        return rows

    def load_margin_series(self, stock_id):
        rows = []
        if os.path.exists(MARGIN_CSV):
            with open(MARGIN_CSV, "r", encoding="utf-8-sig", errors="replace") as f:
                for r in csv.DictReader(f):
                    if r.get("stock_id") == stock_id:
                        rows.append(r)
        rows.sort(key=lambda r: r["date"])
        return rows

# ---------- 個股 K 線 ----------

    def get_kline(self, code, months=3, yahoo_months=6, min_days=100):
        """取得個股 K 線（有快取），回傳 [{date, open, high, low, close, volume}, ...]

        TWSE STOCK_DAY 有時會忽略 date 參數只回傳當月，故不足 min_days 根時改用
        Yahoo Finance 補足（可取得整季/整年日 K）。
        """
        cache_path = os.path.join(KLINE_DIR, f"{code}.json")
        data = None
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = None
        # 檢查快取是否需要更新：僅當快取最後日期已是「今天」才直接用，否則重抓
        if data and data.get("data"):
            latest_cache_date = data["data"][-1]["date"].replace("/", "-")
            today_str = datetime.now().strftime("%Y-%m-%d")
            if latest_cache_date >= today_str and len(data["data"]) >= min_days:
                return data["data"]
        old_data = (data.get("data") if data else None) or []
        data = self._fetch_kline(code, months)
        # 合併舊快取，避免覆蓋掉更早歷史
        if data:
            merged = {r["date"]: r for r in old_data}
            for r in data:
                merged[r["date"]] = r
            data = sorted(merged.values(), key=lambda x: x["date"])
        if not data or len(data) < min_days:
            yahoo = self._fetch_kline_yahoo(code, yahoo_months)
            if yahoo and (not data or len(yahoo) > len(data)):
                data = yahoo
        if data:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({"data": data}, f, ensure_ascii=False)
        return data

    def _fetch_kline(self, code, months=3):
        all_data = []
        today = datetime.now()
        for i in range(months):
            target = today - timedelta(days=30 * i)
            # TWSE STOCK_DAY 需用西元 8 位數（YYYYMM01），民國格式會回錯誤頁
            params = {"response": "json", "date": f"{target.year:04d}{target.month:02d}01", "stockNo": code}
            d = _get(self.session, "https://www.twse.com.tw/exchangeReport/STOCK_DAY", params, timeout=30)
            if d and d.get("stat") == "OK":
                for row in d.get("data", []):
                    try:
                        parts = str(row[0]).strip().split("/")
                        full_date = f"{int(parts[0]) + 1911}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                        all_data.append({
                            "date": full_date,
                            "open": _parse_num(row[3]),
                            "high": _parse_num(row[4]),
                            "low": _parse_num(row[5]),
                            "close": _parse_num(row[6]),
                            "volume": _parse_num(row[1]),
                        })
                    except (IndexError, ValueError):
                        continue
            time.sleep(0.4)
        all_data.sort(key=lambda x: x["date"])
        # 去重（跨月可能重複當月1日）
        seen = set()
        out = []
        for r in all_data:
            if r["date"] not in seen:
                seen.add(r["date"])
                out.append(r)
        return out

    def _fetch_kline_yahoo(self, code, months=3):
        """從 Yahoo Finance 抓取個股日 K 線（可完整取得整季資料）"""
        rng = "3mo" if months <= 3 else "6mo" if months <= 6 else "1y"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{code}.TW"
        d = _get(self.session, url, {"range": rng, "interval": "1d"}, timeout=30)
        if not d:
            return None
        try:
            res = d["chart"]["result"][0]
            ts = res.get("timestamp") or []
            q = (res.get("indicators", {}).get("quote") or [{}])[0]
        except (KeyError, IndexError, TypeError):
            return None
        out = []
        for i, t in enumerate(ts):
            try:
                close = q["close"][i]
                if close is None:
                    continue
                day = datetime.fromtimestamp(t).date()
                out.append({
                    "date": day.strftime("%Y-%m-%d"),
                    "open": round(float(q["open"][i] or close), 2),
                    "high": round(float(q["high"][i] or close), 2),
                    "low": round(float(q["low"][i] or close), 2),
                    "close": round(float(close), 2),
                    "volume": int(q["volume"][i] or 0),
                })
            except (TypeError, ValueError, IndexError):
                continue
        out.sort(key=lambda x: x["date"])
        seen = set()
        dedup = []
        for r in out:
            if r["date"] not in seen:
                seen.add(r["date"])
                dedup.append(r)
        return dedup or None

    def fetch_index_daily(self, months=3):
        """從 Yahoo Finance 抓大盤指數(^TWII)每日 OHLCV，回傳 {date: {o,h,l,c,v}}"""
        rng = "3mo" if months <= 3 else "6mo" if months <= 6 else "1y"
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII"
        d = _get(self.session, url, {"range": rng, "interval": "1d"}, timeout=30)
        if not d:
            return {}
        try:
            res = d["chart"]["result"][0]
            ts = res.get("timestamp") or []
            q = (res.get("indicators", {}).get("quote") or [{}])[0]
        except (KeyError, IndexError, TypeError):
            return {}
        out = {}
        for i, t in enumerate(ts):
            try:
                close = q["close"][i]
                if close is None:
                    continue
                day = datetime.fromtimestamp(t).date().strftime("%Y-%m-%d")
                vol = int(q["volume"][i] or 0)
                out[day] = {
                    "o": round(float(q["open"][i] or close), 2),
                    "h": round(float(q["high"][i] or close), 2),
                    "l": round(float(q["low"][i] or close), 2),
                    "c": round(float(close), 2),
                    "v": vol,
                }
            except (TypeError, ValueError, IndexError):
                continue
        return out


    def load_inst_market(self):
        """大盤三大法人合計（每日彙總全體上市股票）"""
        agg = {}
        if os.path.exists(INST_CSV):
            with open(INST_CSV, "r", encoding="utf-8-sig", errors="replace") as f:
                for r in csv.DictReader(f):
                    d = r.get("date")
                    if not d:
                        continue
                    a = agg.setdefault(d, {"foreign_net": 0, "trust_net": 0, "dealer_net": 0, "total_net": 0})
                    for k in a:
                        try:
                            a[k] += int(r[k] or 0)
                        except (TypeError, ValueError):
                            a[k] += 0
        return [{"date": d, **a} for d, a in sorted(agg.items())]


# =========================================================
# 圖表資料建置 + 四象限
# =========================================================

QUADRANT_INFO = {
    "Q1": {"label": "警訊", "desc": "資增價跌", "advice": "散戶逢低攤平、承接賣壓，短線不宜追進，觀望或分批減碼",
           "color": "#ef4444", "emoji": "警訊"},
    "Q2": {"label": "多頭", "desc": "資減價漲", "advice": "融資洗清、籌碼轉佳，可留意低檔布局或續抱",
           "color": "#10b981", "emoji": "多頭"},
    "Q3": {"label": "波段末端", "desc": "資增價漲", "advice": "散戶追高、短線過熱，注意回檔風險，持股者可獲利了結",
           "color": "#f59e0b", "emoji": "過熱"},
    "Q4": {"label": "打底階段", "desc": "資減價跌", "advice": "散戶退場、籌碼沉澱，等待止跌訊號後可留意落底布局",
           "color": "#60a5fa", "emoji": "打底"},
}

QUADRANT_ORDER = ["Q1", "Q2", "Q3", "Q4"]


def _quadrant_of(price_up, margin_change):
    """依 價 與 資 方向給四象限 key；margin_change==0 回傳 None"""
    if margin_change > 0 and not price_up:
        return "Q1"
    if margin_change < 0 and price_up:
        return "Q2"
    if margin_change > 0 and price_up:
        return "Q3"
    if margin_change < 0 and not price_up:
        return "Q4"
    return None


def compute_quadrants(all_stocks_df, market_summary):
    """計算四象限分布 + 大盤狀態

    all_stocks_df: analyzer 合併後的 DataFrame（含 pct_change、margin_change）
    market_summary: market_summary dict（含 index_change_pct、margin_change_total）
    """
    quad_stocks = {q: [] for q in QUADRANT_ORDER}
    counts = {QUADRANT_INFO[q]["label"]: 0 for q in QUADRANT_ORDER}
    total = 0

    if all_stocks_df is not None and not all_stocks_df.empty:
        for _, row in all_stocks_df.iterrows():
            try:
                pct = float(row.get("pct_change", 0))
                m_chg = int(row.get("margin_change", 0))
                if float(row.get("close", 0)) <= 0:
                    continue
            except (TypeError, ValueError):
                continue
            q = _quadrant_of(pct > 0, m_chg)
            if q is None:
                continue
            total += 1
            counts[QUADRANT_INFO[q]["label"]] += 1
            quad_stocks[q].append({
                "code": str(row.get("stock_id", "")),
                "name": str(row.get("stock_name", "")),
                "pct": round(float(row.get("pct_change", 0)), 2),
                "margin_change": int(row.get("margin_change", 0)),
                "close": round(float(row.get("close", 0)), 2),
            })
        for q in quad_stocks:
            quad_stocks[q].sort(key=lambda x: abs(x["margin_change"]), reverse=True)

    # 大盤狀態（四象限）
    idx_pct = float(market_summary.get("index_change_pct", 0))
    margin_chg = int(market_summary.get("margin_change_total", 0))
    mq = _quadrant_of(idx_pct > 0, margin_chg)
    market = None
    if mq:
        info = QUADRANT_INFO[mq]
        market = {
            "code": mq,
            "label": f"【{info['label']}】{info['desc']}",
            "desc": info["desc"],
            "advice": info["advice"],
            "color": info["color"],
            "index_pct": round(idx_pct, 2),
            "margin_change": margin_chg,
        }
    return {"quadrants": quad_stocks, "counts": counts, "total": total, "market": market}


def collect_focus_stocks(config, analysis_result, quad=None, max_stocks=150):
    """收集個股圖下拉選單股票：watchlist + 0050 + 警示 + 觸發 + 法人名單 + 四象限個股

    目的：分頁中列出的所有個股（三大觸發/法人前5/個股篩選/四象限）都必須能在 K線分頁查看。
    回傳 [(code, name, [分類標籤, ...]), ...]
    """
    seen = {}
    order = []

    def add(code, name, cat):
        code = str(code).strip()
        if not code.isdigit():
            return
        if code not in seen:
            seen[code] = {"name": (name or "").strip(), "cats": []}
            order.append(code)
        if cat and cat not in seen[code]["cats"]:
            seen[code]["cats"].append(cat)

    for w in config.get("realtime_monitor", {}).get("watchlist", []):
        add(w.get("code"), w.get("name"), "自選")
    add("0050", "元大台灣50", "0050")

    alerts = analysis_result.get("alerts")
    if alerts is not None and not alerts.empty:
        for _, row in alerts.iterrows():
            add(row.get("stock_id"), row.get("stock_name"), "警示股")

    for key, label in [("margin_call", "融資斷頭"), ("panic_sell", "恐慌停損"), ("institutional_buy", "主力換手")]:
        for s in analysis_result.get("triggers", {}).get(key, []):
            add(s.get("stock_id"), s.get("stock_name"), label)

    inst = analysis_result.get("institutional_summary", {})
    for s in inst.get("top_buyers", []):
        add(s.get("code"), s.get("name"), "法人買超前5")
    for s in inst.get("top_sellers", []):
        add(s.get("code"), s.get("name"), "法人賣超前5")

    # 四象限顯示的個股（每象限取前 8 檔，與看板 chips 一致）
    if quad:
        for q in QUADRANT_ORDER:
            for s in quad.get("quadrants", {}).get(q, [])[:8]:
                add(s.get("code"), s.get("name"), f"四象限{q}·{QUADRANT_INFO[q]['label']}")

    return [(c, seen[c]["name"], seen[c]["cats"]) for c in order[:max_stocks]]


def build_stock_chart(hd, code, name):
    """建置單一個股的圖表資料"""
    kline = hd.get_kline(code) or []
    margin_rows = hd.load_margin_series(code)
    short_rows = hd.load_margin_series(code)
    inst_rows = hd.load_inst_series(code)

    m_dates, m_balance, m_change, m_prev = [], [], [], []
    for i, r in enumerate(margin_rows):
        m_dates.append(r["date"])
        bal = int(r["margin_balance"])
        m_balance.append(bal)
        m_change.append(bal - m_prev[-1] if m_prev else 0)
        m_prev.append(bal)

    s_dates, s_balance, s_change, s_prev = [], [], [], []
    for i, r in enumerate(short_rows):
        s_dates.append(r["date"])
        bal = int(r["short_balance"])
        s_balance.append(bal)
        s_change.append(bal - s_prev[-1] if s_prev else 0)
        s_prev.append(bal)

    i_dates, i_f, i_t, i_d, i_tot = [], [], [], [], []
    for r in inst_rows:
        i_dates.append(r["date"])
        i_f.append(int(r["foreign_net"]))
        i_t.append(int(r["trust_net"]))
        i_d.append(int(r["dealer_net"]))
        i_tot.append(int(r["total_net"]))

    # K 線為主軸（至少一季）；融資/融券/法人資料較短，依日期對齊並以 null 填空
    master = [x["date"] for x in kline]
    m_map = {d: i for i, d in enumerate(m_dates)}
    s_map = {d: i for i, d in enumerate(s_dates)}
    i_map = {d: i for i, d in enumerate(i_dates)}

    def _align(vals, mapping):
        return [vals[mapping[d]] if d in mapping else None for d in master]

    return {
        "name": name,
        "kline": {"dates": master,
                  "o": [x["open"] for x in kline], "h": [x["high"] for x in kline],
                  "l": [x["low"] for x in kline], "c": [x["close"] for x in kline],
                  "v": [x["volume"] for x in kline]},
        "margin": {"dates": master, "balance": _align(m_balance, m_map), "change": _align(m_change, m_map)},
        "short": {"dates": master, "balance": _align(s_balance, s_map), "change": _align(s_change, s_map)},
        "inst": {"dates": master, "foreign": _align(i_f, i_map), "trust": _align(i_t, i_map),
                 "dealer": _align(i_d, i_map), "total": _align(i_tot, i_map)},
    }


def build_chart_payload(config, analysis_result):
    """組合完整圖表 payload（供看板 JS 使用）"""
    hd = HistoryData()

    # 大盤序列（K線主軸為 Yahoo ^TWII，約半年；融資/維持率/指數較短，依日期對齊填空）
    market_rows = hd.load_market_series()
    mar_dates = [r["date"] for r in market_rows]
    mar_total = [int(r.get("margin_qty", 0)) for r in market_rows]
    mar_change = [mar_total[i] - mar_total[i - 1] if i > 0 else 0 for i in range(len(mar_total))]
    mar_short = [int(r.get("short_qty", 0)) for r in market_rows]
    mar_maint = [float(r.get("maintenance", 0)) for r in market_rows]
    mar_index = [int(float(r.get("index", 0))) for r in market_rows]

    try:
        idx_daily = hd.fetch_index_daily(6)
    except Exception:
        idx_daily = {}

    def _mk_amap(master_dates, src_dates):
        m = {d: i for i, d in enumerate(src_dates)}
        return lambda vals: [vals[m[d]] if d in m else None for d in master_dates]

    if idx_daily:
        master = sorted(idx_daily.keys())
        amap = _mk_amap(master, mar_dates)
        mkt = {
            "dates": master,
            "margin_total": amap(mar_total),
            "margin_change": amap(mar_change),
            "short_total": amap(mar_short),
            "maintenance": amap(mar_maint),
            "index": [idx_daily[d]["c"] for d in master],
            "o": [idx_daily[d]["o"] for d in master],
            "h": [idx_daily[d]["h"] for d in master],
            "l": [idx_daily[d]["l"] for d in master],
            "c": [idx_daily[d]["c"] for d in master],
        }
        vol_raw = [idx_daily[d]["v"] for d in master]
        # Yahoo ^TWII 成交量單位為千股，正規化為「股」（台股日成交約數十億股）
        if vol_raw and max(vol_raw) < 1e7:
            vol_raw = [v * 1000 for v in vol_raw]
        mkt["volume"] = vol_raw
    else:
        mkt = {
            "dates": mar_dates,
            "margin_total": mar_total,
            "margin_change": mar_change,
            "short_total": mar_short,
            "maintenance": mar_maint,
            "index": mar_index,
            "o": [None] * len(mar_dates), "h": [None] * len(mar_dates),
            "l": [None] * len(mar_dates), "c": mar_index, "volume": [0] * len(mar_dates),
        }

    # 大盤法人合計序列
    inst_mkt = hd.load_inst_market()
    mkt["inst_dates"] = [r["date"] for r in inst_mkt]
    mkt["inst_foreign"] = [r["foreign_net"] for r in inst_mkt]
    mkt["inst_trust"] = [r["trust_net"] for r in inst_mkt]
    mkt["inst_dealer"] = [r["dealer_net"] for r in inst_mkt]
    mkt["inst_total"] = [r["total_net"] for r in inst_mkt]

    # 四象限（先計算，供 focus 收集四象限個股）
    quad = compute_quadrants(analysis_result.get("all_stocks"), analysis_result.get("market_summary", {}))

    # 個股
    focus = collect_focus_stocks(config, analysis_result, quad=quad)
    stocks = {}
    stock_cats = {}
    for code, name, cats in focus:
        data = build_stock_chart(hd, code, name)
        if data["kline"]["dates"] or data["margin"]["dates"]:
            stocks[code] = data
            stock_cats[code] = cats

    return {
        "market": mkt,
        "stocks": stocks,
        "stockCats": stock_cats,
        "stockOrder": [c for c, _, _ in focus if c in stocks],
        "quadrant": quad,
    }


TDCC_JSON = os.path.join(CACHE_DIR, "tdcc_shareholding.json")
TDCC_URL = "https://openapi.tdcc.com.tw/v1/opendata/1-5"


def get_tdcc_shareholding():
    """
    集保戶股權分散表（千張大戶）：每週抓一次全市場 JSON 並快取。

    - 千張大戶占比 = 持股分級 15（1,000,001 股以上）占集保庫存比例
    - 每週僅在資料週（資料日期）改變時刷新；prev 為前一週占比，供前端算當週增減
    - 回傳: {"week": "YYYY-MM-DD", "cur": {code: pct}, "prev": {code: pct}}
    """
    state = {"week": "", "cur": {}, "prev": {}}
    if os.path.exists(TDCC_JSON):
        try:
            with open(TDCC_JSON, encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass
    cur_map = {}
    data_date = None
    try:
        resp = requests.get(TDCC_URL, headers=HEADERS, timeout=180)
        resp.raise_for_status()
        rows = resp.json()
        for x in rows:
            x = {(k.lstrip("\ufeff")): v for k, v in x.items()}
            if str(x.get("持股分級") or "").strip() != "15":
                continue
            code = str(x.get("證券代號") or "").strip()
            if len(code) < 4:
                continue
            if data_date is None:
                data_date = str(x.get("資料日期") or "").strip()
            try:
                pct = float(str(x.get("占集保庫存數比例%") or 0).replace(",", ""))
            except (ValueError, TypeError):
                continue
            cur_map[code] = round(pct, 2)
    except Exception as e:
        print(f"    [TDCC] 抓取失敗: {e}")
        return state  # 沿用舊快取
    if not cur_map or not data_date:
        return state
    # 資料週未變：沿用既有 cur/prev（不刷新 prev）
    if state.get("week") == data_date and state.get("cur"):
        return state
    new_state = {"week": data_date, "cur": cur_map, "prev": state.get("cur", {}) if state.get("week") else {}}
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(TDCC_JSON, "w", encoding="utf-8") as f:
            json.dump(new_state, f, ensure_ascii=False)
    except Exception as e:
        print(f"    [TDCC] 寫入快取失敗: {e}")
    return new_state


if __name__ == "__main__":
    print("=== 歷史資料回補測試（12 天）===")
    h = HistoryData(calendar_days=12)
    ok = h.refresh(force=False)
    print(f"refresh ok = {ok}")
    rows = h.load_market_series()
    print(f"市場日數: {len(rows)}")
    if rows:
        last = rows[-1]
        print(f"最新: {last['date']} 指數={last['index']} 融資={int(last['margin_qty']):,}張 維持率={last['maintenance']}%")
