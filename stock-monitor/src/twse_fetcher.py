"""
TWSE/TPEx 資料抓取模組 v2
抓取融資融券（TWSE 直接API）+ 個股收盤價 + 歷史數據
"""
import requests
import pandas as pd
from datetime import datetime, timedelta
import time


class TWSEFetcher:
    """從台灣證券交易所抓取資料"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        self._price_cache = {}

    def _convert_date(self, date_str):
        """西元年轉 TWSE 格式: 2026-07-15 -> 20260715"""
        return date_str.replace("-", "")

    def fetch_margin_data_twse(self, date_str=None):
        """
        抓取融資融券資料（直接從 TWSE MI_MARGN API）
        如果不指定日期，API 會回傳最新可用的資料
        """
        if date_str:
            roc_date = self._convert_date(date_str)
            print(f"  [TWSE] 抓取融資融券: {date_str} (民國 {roc_date})")
        else:
            roc_date = None
            print(f"  [TWSE] 抓取最新融資融券資料...")
        
        try:
            url = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
            params = {"response": "json", "selectType": "ALL"}
            if roc_date:
                params["date"] = roc_date
            
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            tables = data.get("tables", [])
            if not tables or len(tables) < 2:
                print(f"  [TWSE] 無表格資料")
                return pd.DataFrame(), None

            # table[1] 是融資融券餘額明細
            table = tables[1]
            rows = table.get("data", [])
            if not rows:
                print(f"  [TWSE] 表格無資料")
                return pd.DataFrame(), None

            # 從 API 回應中取得實際日期
            api_date = data.get("date", "")
            if api_date:
                # API 回傳格式: 20260717 -> 2026-07-17
                actual_date = f"{api_date[:4]}-{api_date[4:6]}-{api_date[6:8]}"
                print(f"  [TWSE] API 回傳日期: {actual_date}")
            else:
                actual_date = date_str

            # 表格標題包含日期，例如 "115年07月15日"
            title = table.get("title", "")
            print(f"  [TWSE] 表格標題: {title}")

            # TWSE 融資融券欄位 (MI_MARGN tables[1], 16 欄):
            # [0] 代號, [1] 名稱, [2] 融資買進, [3] 融資賣出, [4] 融資現金償還,
            # [5] 融資前日餘額, [6] 融資今日餘額(張), [7] 融資次一營業日限額,
            # [8] 券買進, [9] 券賣出, [10] 券現金償還,
            # [11] 券前日餘額, [12] 券今日餘額, [13] 券次一營業日限額, [14] 資券互抵, [15] 註記
            # 依證交所說明，以「今日餘額」為當日值
            records = []
            for row in rows:
                try:
                    stock_id = str(row[0]).strip()
                    if not stock_id or not stock_id.isdigit():
                        continue
                    margin_balance = self._parse_num(row[6])
                    margin_limit = self._parse_num(row[7])
                    short_balance = self._parse_num(row[12])
                    short_limit = self._parse_num(row[13])
                    records.append({
                        "stock_id": stock_id,
                        "stock_name": str(row[1]).strip(),
                        "margin_buy": self._parse_num(row[2]),
                        "margin_sell": self._parse_num(row[3]),
                        "margin_repay": self._parse_num(row[4]),
                        "margin_balance": margin_balance,
                        "margin_limit": margin_limit,
                        "margin_usage_rate": round(margin_balance / margin_limit * 100, 2) if margin_limit > 0 else 0,
                        "short_sell": self._parse_num(row[9]),
                        "short_buy": self._parse_num(row[8]),
                        "short_repay": self._parse_num(row[10]),
                        "short_balance": short_balance,
                        "short_limit": short_limit,
                        "offset": self._parse_num(row[14]),
                    })
                except (IndexError, ValueError):
                    continue

            df = pd.DataFrame(records)
            df["date"] = actual_date
            print(f"  [TWSE] 找到 {len(df)} 檔個股")
            return df, actual_date

        except Exception as e:
            print(f"  [TWSE] 抓取失敗: {e}")
            return pd.DataFrame(), None

    def _parse_num(self, val):
        """解析數字，處理逗號和 '--'"""
        try:
            s = str(val).replace(",", "").replace("--", "0").strip()
            if not s:
                return 0
            return int(float(s))
        except (ValueError, TypeError):
            return 0

    def fetch_stock_prices(self, date_str):
        """抓取當日所有個股收盤價
        STOCK_DAY_ALL 只回最新交易日；歷史日期自動 fallback 到 MI_INDEX
        """
        df = self._fetch_prices_stock_day_all(date_str)
        if not df.empty:
            return df
        print(f"  [TWSE] STOCK_DAY_ALL 無 {date_str} 資料，改用 MI_INDEX 歷史查詢...")
        return self._fetch_prices_mi_index(date_str)

    def _fetch_prices_stock_day_all(self, date_str):
        """STOCK_DAY_ALL（只回最新一個交易日）"""
        url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        print(f"  [TWSE] 抓取個股收盤價: {date_str}")
        try:
            resp = self.session.get(url, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            if not data:
                return pd.DataFrame()
            records = []
            y, m, d = date_str.split("-")
            target_date = f"{int(y)-1911}{m}{d}"
            for item in data:
                if item.get("Date") != target_date:
                    continue
                records.append({
                    "stock_id": item.get("Code", ""),
                    "stock_name": item.get("Name", ""),
                    "volume": item.get("TradeVolume", "0"),
                    "turnover": item.get("TradeValue", "0"),
                    "open": item.get("OpeningPrice", "0"),
                    "high": item.get("HighestPrice", "0"),
                    "low": item.get("LowestPrice", "0"),
                    "close": item.get("ClosingPrice", "0"),
                    "change": item.get("Change", "0"),
                    "transactions": item.get("Transaction", "0"),
                })
            if not records:
                return pd.DataFrame()
            df = pd.DataFrame(records)
            for c in ["volume", "turnover", "open", "high", "low", "close", "change", "transactions"]:
                df[c] = pd.to_numeric(
                    df[c].astype(str).str.replace(",", "").str.replace("X", "0"),
                    errors="coerce"
                ).fillna(0)
            df["volume"] = (df["volume"] / 1000).astype(int)
            df["date"] = date_str
            df["stock_id"] = df["stock_id"].astype(str).str.strip()
            print(f"  [TWSE] 找到 {len(df)} 檔個股")
            return df
        except Exception as e:
            print(f"  [TWSE] 抓取收盤價失敗: {e}")
            return pd.DataFrame()

    def _fetch_prices_mi_index(self, date_str):
        """MI_INDEX 每日收盤行情（支援指定歷史日期）"""
        try:
            param_date = date_str.replace("-", "")
            resp = self.session.get(
                "https://www.twse.com.tw/exchangeReport/MI_INDEX",
                params={"response": "json", "date": param_date, "type": "ALL"},
                timeout=90,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("stat") != "OK":
                print(f"  [TWSE] MI_INDEX {date_str}: {data.get('stat')}")
                return pd.DataFrame()
            records = []
            for t in data.get("tables", []):
                title = str(t.get("title") or "")
                if "每日收盤行情" not in title:
                    continue
                for row in t.get("data", []):
                    try:
                        code = str(row[0]).strip()
                        if not code.isdigit():
                            continue
                        # 漲跌方向: row[9] 含 red=漲 / green=跌 / X=除權息
                        sign = str(row[9])
                        diff = str(row[10]).replace(",", "").replace("X", "0") or "0"
                        try:
                            diff_val = float(diff)
                        except ValueError:
                            diff_val = 0.0
                        if "green" in sign or "-" in sign:
                            diff_val = -abs(diff_val)
                        elif "X" in sign:
                            diff_val = 0.0
                        records.append({
                            "stock_id": code,
                            "stock_name": str(row[1]).strip(),
                            "volume": str(row[2]),
                            "turnover": str(row[4]),
                            "open": str(row[5]),
                            "high": str(row[6]),
                            "low": str(row[7]),
                            "close": str(row[8]),
                            "change": str(diff_val),
                            "transactions": str(row[3]),
                        })
                    except (IndexError, ValueError):
                        continue
                break
            if not records:
                return pd.DataFrame()
            df = pd.DataFrame(records)
            for c in ["volume", "turnover", "open", "high", "low", "close", "change", "transactions"]:
                df[c] = pd.to_numeric(
                    df[c].astype(str).str.replace(",", "").str.replace("X", "0"),
                    errors="coerce"
                ).fillna(0)
            df["volume"] = (df["volume"] / 1000).astype(int)
            df["date"] = date_str
            df["stock_id"] = df["stock_id"].astype(str).str.strip()
            print(f"  [TWSE] MI_INDEX 找到 {len(df)} 檔個股")
            return df
        except Exception as e:
            print(f"  [TWSE] MI_INDEX 抓取失敗: {e}")
            return pd.DataFrame()

    def fetch_stock_prices_multi_day(self, date_str, days=4):
        """抓取多天的收盤價（用於計算累計漲跌）"""
        cache_key = f"prices_{date_str}_{days}"
        if cache_key in self._price_cache:
            return self._price_cache[cache_key]
        all_prices = []
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        for i in range(days):
            d = (dt - timedelta(days=i)).strftime("%Y-%m-%d")
            df = self.fetch_stock_prices(d)
            if not df.empty:
                all_prices.append(df)
            time.sleep(0.3)
        if all_prices:
            result = pd.concat(all_prices, ignore_index=True)
            self._price_cache[cache_key] = result
            return result
        return pd.DataFrame()

    def fetch_twse_index(self, date_str):
        """抓取加權指數 (從 Yahoo Finance)"""
        print(f"  [TWSE] 抓取加權指數: {date_str}")
        try:
            url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII"
            params = {"range": "1d", "interval": "1d"}
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            price = meta.get("regularMarketPrice", 0)
            prev = meta.get("chartPreviousClose", 0)
            change = price - prev if prev else 0
            pct = (change / prev * 100) if prev else 0
            return {"date": date_str, "index": price, "change": change, "pct": round(pct, 2)}
        except Exception as e:
            print(f"  [TWSE] 抓取指數失敗: {e}")
            return None

    def fetch_twse_index_at(self, date_str):
        """抓取指定日期的加權指數（從 Yahoo Finance 歷史）"""
        print(f"  [TWSE] 抓取歷史指數: {date_str}")
        try:
            url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII"
            params = {"range": "1mo", "interval": "1d"}
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            result = data.get("chart", {}).get("result", [{}])[0]
            timestamps = result.get("timestamp", [])
            indicators = result.get("indicators", {}).get("quote", [{}])[0]
            closes = indicators.get("close", [])
            for i, ts in enumerate(timestamps):
                d = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                if d == date_str and closes[i] is not None:
                    # 往前找一天計算變動
                    prev = None
                    for j in range(i - 1, -1, -1):
                        if closes[j] is not None:
                            prev = closes[j]
                            break
                    change = closes[i] - prev if prev else 0
                    pct = (change / prev * 100) if prev else 0
                    return {"date": date_str, "index": round(closes[i], 2), "change": round(change, 2), "pct": round(pct, 2)}
            print(f"  [TWSE] 歷史指數找不到 {date_str}")
            return None
        except Exception as e:
            print(f"  [TWSE] 抓取歷史指數失敗: {e}")
            return None

    def fetch_index_history(self, days=30):
        """抓取加權指數歷史（近 N 天）"""
        print(f"  [TWSE] 抓取加權指數歷史（{days}天）...")
        try:
            url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII"
            params = {"range": f"{days}d", "interval": "1d"}
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            result = data.get("chart", {}).get("result", [{}])[0]
            timestamps = result.get("timestamp", [])
            indicators = result.get("indicators", {}).get("quote", [{}])[0]
            closes = indicators.get("close", [])
            history = []
            for i, ts in enumerate(timestamps):
                dt = datetime.fromtimestamp(ts)
                if closes[i] is not None:
                    history.append({
                        "date": dt.strftime("%Y-%m-%d"),
                        "index": round(closes[i], 2)
                    })
            return history
        except Exception as e:
            print(f"  [TWSE] 抓取指數歷史失敗: {e}")
            return []


if __name__ == "__main__":
    fetcher = TWSEFetcher()
    today = datetime.now().strftime("%Y-%m-%d")
    margin = fetcher.fetch_margin_data_twse(today)
    print(f"\n融資融券筆數: {len(margin)}")
    if not margin.empty:
        print(margin.head())
