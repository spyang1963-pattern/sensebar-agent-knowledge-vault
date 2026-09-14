# stock_chart.py
"""
個股歷史走勢圖模組
顯示個股歷史價格走勢
"""
import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

TWSE_HISTORY_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"


def fetch_stock_history(code: str, months: int = 6) -> Optional[List[Dict[str, Any]]]:
    """
    抓取個股歷史資料
    
    Args:
        code: 股票代號
        months: 抓取幾個月的資料
        
    Returns:
        [
            {
                "date": "2026/07/23",
                "open": 1050.0,
                "high": 1060.0,
                "low": 1045.0,
                "close": 1055.0,
                "volume": 25000000
            },
            ...
        ]
    """
    all_data = []
    today = datetime.now()
    
    for i in range(months):
        # 計算月份
        target_date = today - timedelta(days=30 * i)
        year = target_date.year
        month = target_date.month
        
        # 轉換为民國年
        roc_year = year - 1911
        
        params = {
            "response": "json",
            "date": f"{roc_year}/{month:02d}/01",
            "stockNo": code
        }
        
        try:
            logger.info(f"[StockHistory] 抓取 {code} {year}/{month:02d} 資料...")
            resp = requests.get(TWSE_HISTORY_URL, params=params, timeout=30)
            resp.raise_for_status()
            
            raw = resp.json()
            
            if raw.get("stat") != "OK":
                logger.warning(f"[StockHistory] API 回傳異常: {raw.get('stat')}")
                continue
            
            data_rows = raw.get("data", [])
            if not data_rows:
                continue
            
            # 解析資料
            for row in data_rows:
                try:
                    # 欄位順序：日期, 成交股數, 成交金額, 開盤價, 最高價, 最低價, 收盤價, 漲跌價差, 成交筆數
                    date_str = row[0].strip()
                    open_price = float(row[3].replace(",", ""))
                    high = float(row[4].replace(",", ""))
                    low = float(row[5].replace(",", ""))
                    close = float(row[6].replace(",", ""))
                    volume = int(row[1].replace(",", ""))
                    
                    # 轉換日期格式
                    # 115/07/23 -> 2026/07/23
                    parts = date_str.split("/")
                    if len(parts) == 3:
                        roc_year = int(parts[0])
                        month = int(parts[1])
                        day = int(parts[2])
                        full_date = f"{roc_year + 1911}/{month:02d}/{day:02d}"
                    else:
                        full_date = date_str
                    
                    all_data.append({
                        "date": full_date,
                        "open": open_price,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": volume
                    })
                except (ValueError, IndexError) as e:
                    logger.warning(f"[StockHistory] 解析資料錯誤: {row[:3]}, {e}")
                    continue
            
            # 避免請求太快
            import time
            time.sleep(1)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"[StockHistory] 抓取 {code} {year}/{month:02d} 失敗: {e}")
            continue
        except json.JSONDecodeError as e:
            logger.error(f"[StockHistory] 解析 JSON 失敗: {e}")
            continue
    
    # 按日期排序
    all_data.sort(key=lambda x: x["date"])
    
    return all_data if all_data else None


def generate_chart_data(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    產生圖表資料
    
    Args:
        history: 歷史資料
        
    Returns:
        {
            "dates": ["2026/07/01", ...],
            "prices": [1050.0, ...],
            "volumes": [25000000, ...],
            "ma5": [1055.0, ...],
            "ma20": [1048.0, ...]
        }
    """
    if not history:
        return {}
    
    dates = [h["date"] for h in history]
    prices = [h["close"] for h in history]
    volumes = [h["volume"] for h in history]
    
    # 計算移動平均線
    def moving_average(data, window):
        result = []
        for i in range(len(data)):
            if i < window - 1:
                result.append(None)
            else:
                avg = sum(data[i-window+1:i+1]) / window
                result.append(round(avg, 2))
        return result
    
    ma5 = moving_average(prices, 5)
    ma20 = moving_average(prices, 20)
    
    return {
        "dates": dates,
        "prices": prices,
        "volumes": volumes,
        "ma5": ma5,
        "ma20": ma20
    }


def format_history_summary(history: List[Dict[str, Any]], code: str, name: str) -> str:
    """
    格式化歷史摘要
    
    Args:
        history: 歷史資料
        code: 股票代號
        name: 股票名稱
        
    Returns:
        格式化的摘要字串
    """
    if not history:
        return f"{name} ({code}) 無歷史資料"
    
    latest = history[-1]
    earliest = history[0]
    
    # 計算漲跌幅
    start_price = earliest["close"]
    end_price = latest["close"]
    change_pct = ((end_price - start_price) / start_price * 100) if start_price > 0 else 0
    
    # 計算最高最低
    highs = [h["high"] for h in history]
    lows = [h["low"] for h in history]
    highest = max(highs)
    lowest = min(lows)
    
    # 計算平均成交量
    avg_volume = sum(h["volume"] for h in history) / len(history)
    
    summary = f"📊 {name} ({code}) 近期走勢\n"
    summary += "=" * 30 + "\n"
    summary += f"期間: {earliest['date']} ~ {latest['date']}\n"
    summary += f"最新收盤: {end_price:,.2f}\n"
    summary += f"期間漲跌: {change_pct:+.2f}%\n"
    summary += f"最高價: {highest:,.2f}\n"
    summary += f"最低價: {lowest:,.2f}\n"
    summary += f"平均成交量: {avg_volume:,.0f} 股\n"
    
    return summary


if __name__ == "__main__":
    # 測試用
    history = fetch_stock_history("2330", months=3)
    if history:
        print(f"共 {len(history)} 筆資料")
        print(f"最新: {history[-1]}")
        
        chart_data = generate_chart_data(history)
        print(f"圖表資料: {len(chart_data.get('dates', []))} 天")
        
        summary = format_history_summary(history, "2330", "台積電")
        print(summary)
    else:
        print("無法取得歷史資料")
