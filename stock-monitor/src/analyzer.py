"""
分析引擎 - 過濾「跌幅大 + 融資減」+ 三大觸發條件
"""
import pandas as pd
import numpy as np


class StockAnalyzer:
    """分析融資券數據，篩選警示股 + 觸發條件"""

    def __init__(self, config):
        self.thresholds = config.get("thresholds", {})
        self.triggers = config.get("triggers", {})
        self.price_drop_pct = self.thresholds.get("price_drop_pct", -2.0)
        self.margin_decrease_qty = self.thresholds.get("margin_decrease_qty", -50)
        self.margin_decrease_pct = self.thresholds.get("margin_decrease_pct", -5.0)
        self.min_volume = self.thresholds.get("min_volume", 100)

    def analyze(self, today_data, yesterday_data, price_history=None):
        """分析今日 vs 昨日資料"""
        today_margin = today_data["margin"]
        today_prices = today_data["prices"]
        yesterday_margin = yesterday_data["margin"] if yesterday_data else pd.DataFrame()

        if today_margin.empty:
            return self._empty_result(today_data)

        merged = self._merge_data(today_margin, today_prices, yesterday_margin, price_history)
        if merged.empty:
            return self._empty_result(today_data)

        alerts = self._filter_alerts(merged)
        market_summary = self._calc_market_summary(today_data, yesterday_data)
        industry_stats = self._calc_industry_stats(alerts)
        triggers = self._detect_triggers(merged)

        return {
            "alerts": alerts,
            "market_summary": market_summary,
            "industry_stats": industry_stats,
            "triggers": triggers,
            "all_stocks": merged,
        }

    def _empty_result(self, today_data):
        return {
            "alerts": pd.DataFrame(),
            "market_summary": {"date": today_data["date"]},
            "industry_stats": {},
            "triggers": {"margin_call": [], "panic_sell": [], "institutional_buy": []},
            "all_stocks": pd.DataFrame(),
        }

    def _merge_data(self, today_margin, today_prices, yesterday_margin, price_history):
        """合併融資券和股價資料，計算所有指標"""
        df = today_margin.copy()

        if not today_prices.empty:
            price_cols = ["stock_id", "close", "change", "volume", "open", "high", "low"]
            available = [c for c in price_cols if c in today_prices.columns]
            prices_subset = today_prices[available].copy()
            df = df.merge(prices_subset, on="stock_id", how="left", suffixes=("", "_price"))

        if not yesterday_margin.empty:
            yest = yesterday_margin[["stock_id", "margin_balance", "short_balance"]].copy()
            yest = yest.rename(columns={
                "margin_balance": "margin_balance_prev_yest",
                "short_balance": "short_balance_prev_yest",
            })
            df = df.merge(yest, on="stock_id", how="left", suffixes=("", "_yest"))

        for col in ["close", "change", "volume", "margin_balance_prev_yest", "short_balance_prev_yest"]:
            if col not in df.columns:
                df[col] = 0

        df["close"] = pd.to_numeric(df["close"], errors="coerce").fillna(0)
        df["change"] = pd.to_numeric(df["change"], errors="coerce").fillna(0)
        df["pct_change"] = np.where(
            (df["close"] - df["change"]) > 0,
            (df["change"] / (df["close"] - df["change"])) * 100,
            0
        )

        df["margin_change"] = df["margin_balance"] - df.get("margin_balance_prev_yest", df.get("margin_balance_prev", 0))

        # 計算融資使用率（如果有 margin_limit 資料）
        if "margin_limit" in df.columns:
            df["margin_usage_rate"] = np.where(
                df["margin_limit"] > 0,
                (df["margin_balance"] / df["margin_limit"]) * 100,
                0
            )
        else:
            df["margin_usage_rate"] = 0

        # 計算估計維持率
        df["est_maintenance_rate"] = np.where(
            df["margin_balance"] > 0,
            np.where(
                df.get("margin_balance_prev_yest", 0) > 0,
                (df["margin_balance"] / df.get("margin_balance_prev_yest", 1)) * 100,
                100.0
            ),
            0
        )

        if price_history is not None and not price_history.empty:
            df = self._calc_cumulative_change(df, price_history)

        return df

    def _calc_cumulative_change(self, df, price_history):
        """計算 N 天累計漲跌幅"""
        if "stock_id" not in price_history.columns or "close" not in price_history.columns:
            df["cum_3d_change"] = 0
            return df

        for _, row in df.iterrows():
            sid = row["stock_id"]
            hist = price_history[price_history["stock_id"] == sid].copy()
            if len(hist) < 2:
                continue
            hist = hist.sort_values("date")
            closes = hist["close"].values
            if len(closes) >= 2 and closes[-1] > 0:
                cum_change = ((closes[-1] - closes[0]) / closes[0]) * 100
                df.loc[df["stock_id"] == sid, "cum_3d_change"] = round(cum_change, 2)

        if "cum_3d_change" not in df.columns:
            df["cum_3d_change"] = 0

        return df

    def _filter_alerts(self, df):
        """過濾警示股"""
        if df.empty:
            return df
        filtered = df[
            (df["close"] > 0) &
            (df["volume"] >= self.min_volume) &
            (df["margin_change"] <= self.margin_decrease_qty)
        ].copy()
        if "pct_change" in filtered.columns:
            filtered = filtered[filtered["pct_change"] <= self.price_drop_pct]
        filtered = filtered.sort_values("margin_change", ascending=True)
        return filtered

    def _calc_market_summary(self, today_data, yesterday_data):
        """計算大盤摘要"""
        today_idx = today_data.get("index")
        yest_idx = yesterday_data.get("index") if yesterday_data else None
        today_margin = today_data["margin"]
        yest_margin = yesterday_data["margin"] if yesterday_data else pd.DataFrame()

        market = {
            "date": today_data["date"],
            "index_today": today_idx["index"] if today_idx else 0,
            "index_change": 0,
            "index_change_pct": 0,
            "total_margin_balance": 0,
            "margin_change_total": 0,
            "total_margin_balance_billion": 0,
            "margin_change_billion": 0,
            "est_maintenance_rate": 0,
        }

        if today_idx:
            market["index_today"] = today_idx.get("index", 0)
            market["index_change"] = today_idx.get("change", 0)
            market["index_change_pct"] = today_idx.get("pct", 0)

        if not today_margin.empty and "margin_balance" in today_margin.columns:
            total = today_margin["margin_balance"].sum()
            market["total_margin_balance"] = total
            market["total_margin_balance_billion"] = round(total * 1000 / 100000000, 2)

        if not yest_margin.empty and "margin_balance" in yest_margin.columns:
            yest_total = yest_margin["margin_balance"].sum()
            change = market["total_margin_balance"] - yest_total
            market["margin_change_total"] = change
            market["margin_change_billion"] = round(change * 1000 / 100000000, 2)
            if yest_total > 0:
                market["est_maintenance_rate"] = round((market["total_margin_balance"] / yest_total) * 100, 2)

        return market

    def _calc_industry_stats(self, alerts):
        """計算警示股產業分布"""
        if alerts.empty:
            return {}
        industry_map = {
            "23": "電子", "24": "電子", "30": "電子", "31": "電子",
            "32": "電子", "33": "電子", "34": "電子", "35": "電子",
            "36": "電子", "37": "電子", "38": "電子", "39": "電子",
            "49": "通信", "52": "通信",
            "11": "水泥", "12": "食品", "13": "塑化",
            "14": "紡織", "15": "電機", "16": "電器",
            "17": "電線", "18": "化學", "19": "生技",
            "20": "玻璃", "21": "鋼鐵", "22": "橡膠",
            "25": "汽車", "26": "運輸", "27": "觀光",
            "28": "金融", "29": "貿易百貨",
        }
        stats = {}
        for _, row in alerts.iterrows():
            prefix = str(row["stock_id"])[:2]
            industry = industry_map.get(prefix, "其他")
            stats[industry] = stats.get(industry, 0) + 1
        return dict(sorted(stats.items(), key=lambda x: x[1], reverse=True))

    def _detect_triggers(self, df):
        """偵測三大觸發條件"""
        mc_config = self.triggers.get("margin_call", {})
        ps_config = self.triggers.get("panic_sell", {})
        ib_config = self.triggers.get("institutional_buy", {})

        margin_call_stocks = []
        panic_sell_stocks = []
        institutional_buy_stocks = []

        if mc_config.get("enabled", True) and "cum_3d_change" in df.columns:
            cum_threshold = mc_config.get("cumulative_drop_pct", -10.0)
            mc_margin_threshold = mc_config.get("margin_decrease_qty", -100) if "margin_decrease_qty" in mc_config else self.margin_decrease_qty
            max_rate = mc_config.get("max_maintenance_rate", 135.0)
            mc_stocks = df[
                (df["cum_3d_change"] <= cum_threshold) &
                (df["est_maintenance_rate"] <= max_rate) &
                (df["est_maintenance_rate"] > 0)
            ].sort_values("margin_change").head(mc_config.get("top_margin_decrease", 10))
            margin_call_stocks = self._stocks_to_list(mc_stocks)

        if ps_config.get("enabled", True):
            ps_drop = ps_config.get("daily_drop_pct", -4.0)
            ps_margin = ps_config.get("margin_decrease_qty", -100)
            min_rate = ps_config.get("min_maintenance_rate", 145.0)
            ps_stocks = df[
                (df["pct_change"] <= ps_drop) &
                (df["margin_change"] <= ps_margin) &
                (df["est_maintenance_rate"] >= min_rate)
            ].sort_values("margin_change").head(10)
            panic_sell_stocks = self._stocks_to_list(ps_stocks)

        if ib_config.get("enabled", True):
            ib_rise = ib_config.get("daily_rise_pct", 2.0)
            ib_margin = ib_config.get("margin_decrease_qty", -80)
            ib_stocks = df[
                (df["pct_change"] >= ib_rise) &
                (df["margin_change"] <= ib_margin)
            ].sort_values("margin_change").head(10)
            institutional_buy_stocks = self._stocks_to_list(ib_stocks)

        return {
            "margin_call": margin_call_stocks,
            "panic_sell": panic_sell_stocks,
            "institutional_buy": institutional_buy_stocks,
        }

    def _stocks_to_list(self, df):
        """將 DataFrame 轉為 list of dicts"""
        if df.empty:
            return []
        result = []
        for _, row in df.iterrows():
            result.append({
                "stock_id": str(row.get("stock_id", "")),
                "stock_name": str(row.get("stock_name", "")),
                "close": round(float(row.get("close", 0)), 2),
                "pct_change": round(float(row.get("pct_change", 0)), 2),
                "margin_change": int(row.get("margin_change", 0)),
                "margin_balance": int(row.get("margin_balance", 0)),
                "margin_usage_rate": round(float(row.get("margin_usage_rate", 0)), 2),
                "est_maintenance_rate": round(float(row.get("est_maintenance_rate", 0)), 2),
                "cum_3d_change": round(float(row.get("cum_3d_change", 0)), 2),
            })
        return result


if __name__ == "__main__":
    import yaml
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    analyzer = StockAnalyzer(config)
    print("Analyzer initialized with thresholds:")
    print(f"  價格跌幅: {analyzer.price_drop_pct}%")
    print(f"  融資減量: {analyzer.margin_decrease_qty} 張")
    print(f"  觸發條件: {list(analyzer.triggers.keys())}")
