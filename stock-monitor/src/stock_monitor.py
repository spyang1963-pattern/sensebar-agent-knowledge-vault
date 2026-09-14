# stock_monitor.py
"""
個股即時監控模組
監控自選股的即時股價，並在觸發條件時發送警報
"""
import requests
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

TWSE_REALTIME_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"


def fetch_realtime_data(codes: List[str]) -> Optional[Dict[str, Any]]:
    """
    抓取多檔股票的即時行情
    
    Args:
        codes: 股票代號列表，如 ["2330", "2317"]
        
    Returns:
        {
            "2330": {
                "code": "2330",
                "name": "台積電",
                "price": 1050.0,
                "yesterday_close": 1045.0,
                "open": 1048.0,
                "high": 1055.0,
                "low": 1045.0,
                "volume": 25000000,
                "change": 5.0,
                "change_pct": 0.48,
                "time": "14:30:00"
            },
            ...
        }
    """
    if not codes:
        return None
    
    # 建立查詢參數
    ex_ch = "|".join([f"tse_{code}.tw" for code in codes])
    params = {
        "ex_ch": ex_ch,
        "json": "1",
        "delay": "0"
    }
    
    try:
        logger.info(f"[Realtime] 抓取即時行情: {', '.join(codes)}")
        resp = requests.get(TWSE_REALTIME_URL, params=params, timeout=10)
        resp.raise_for_status()
        
        raw = resp.json()
        
        if raw.get("rtcode") != "0000":
            logger.warning(f"[Realtime] API 回傳異常: {raw.get('rtcode')}")
            return None
        
        msg_array = raw.get("msgArray", [])
        if not msg_array:
            logger.warning("[Realtime] 無即時行情資料")
            return None
        
        result = {}
        for item in msg_array:
            code = item.get("c", "")
            if not code:
                continue
            
            try:
                # 解析即時行情（處理 '-' 或空值）
                def safe_float(val, default=0):
                    if val is None or val == '-' or val == '':
                        return default
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return default
                
                def safe_int(val, default=0):
                    if val is None or val == '-' or val == '':
                        return default
                    try:
                        return int(val)
                    except (ValueError, TypeError):
                        return default
                
                price = safe_float(item.get("z"))  # 當前成交價
                yesterday_close = safe_float(item.get("y"))  # 昨收
                open_price = safe_float(item.get("o"))  # 開盤
                high = safe_float(item.get("h"))  # 最高
                low = safe_float(item.get("l"))  # 最低
                volume = safe_int(item.get("v"))  # 成交量（張）
                
                # 計算漲跌
                change = price - yesterday_close if price > 0 and yesterday_close > 0 else 0
                change_pct = (change / yesterday_close * 100) if yesterday_close > 0 else 0
                
                result[code] = {
                    "code": code,
                    "name": item.get("n", ""),
                    "price": price,
                    "yesterday_close": yesterday_close,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "volume": volume,
                    "change": change,
                    "change_pct": change_pct,
                    "time": item.get("t", ""),
                    "date": item.get("d", "")
                }
            except (ValueError, TypeError) as e:
                logger.warning(f"[Realtime] 解析 {code} 資料錯誤: {e}")
                continue
        
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"[Realtime] 抓取即時行情失敗: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"[Realtime] 解析 JSON 失敗: {e}")
        return None


def check_alerts(realtime_data: Dict[str, Any], watchlist: List[Dict], default_thresholds: Dict) -> List[Dict[str, Any]]:
    """
    檢查是否觸發警報
    
    Args:
        realtime_data: 即時行情資料
        watchlist: 自選股清單
        default_thresholds: 預設警報門檻
        
    Returns:
        [
            {
                "code": "2330",
                "name": "台積電",
                "price": 1050.0,
                "change_pct": -3.5,
                "alert_type": "price_drop",
                "message": "台積電 (2330) 股價跌幅 -3.5%，超過警戒值 -3.0%"
            },
            ...
        ]
    """
    alerts = []
    
    for stock in watchlist:
        code = stock.get("code", "")
        name = stock.get("name", "")
        thresholds = stock.get("thresholds", default_thresholds)
        
        if code not in realtime_data:
            continue
        
        data = realtime_data[code]
        price = data.get("price", 0)
        change_pct = data.get("change_pct", 0)
        volume = data.get("volume", 0)
        yesterday_close = data.get("yesterday_close", 0)
        open_price = data.get("open", 0)
        high = data.get("high", 0)
        low = data.get("low", 0)
        
        # 1. 檢查股價跌幅
        price_drop_threshold = thresholds.get("price_drop_pct", default_thresholds.get("price_drop_pct", -3.0))
        if change_pct <= price_drop_threshold:
            alerts.append({
                "code": code,
                "name": name,
                "price": price,
                "yesterday_close": yesterday_close,
                "change_pct": change_pct,
                "volume": volume,
                "alert_type": "price_drop",
                "alert_level": "danger",
                "message": f"{name} ({code}) 股價跌幅 {change_pct:+.2f}%，超過警戒值 {price_drop_threshold}%"
            })
        
        # 2. 檢查股價漲幅（可能獲利了結警報）
        price_rise_threshold = thresholds.get("price_rise_pct", 5.0)
        if change_pct >= price_rise_threshold:
            alerts.append({
                "code": code,
                "name": name,
                "price": price,
                "yesterday_close": yesterday_close,
                "change_pct": change_pct,
                "volume": volume,
                "alert_type": "price_rise",
                "alert_level": "warning",
                "message": f"{name} ({code}) 股價漲幅 {change_pct:+.2f}%，注意獲利了結"
            })
        
        # 3. 檢查成交量異常放大
        volume_surge_threshold = thresholds.get("volume_surge_ratio", default_thresholds.get("volume_surge_ratio", 2.0))
        # 這裡先用簡化版：檢查成交量是否異常高
        # TODO: 之後可以加入歷史平均成交量比較
        avg_volume = stock.get("avg_volume", 0)
        if avg_volume > 0 and volume > avg_volume * volume_surge_threshold:
            alerts.append({
                "code": code,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "volume": volume,
                "avg_volume": avg_volume,
                "alert_type": "volume_surge",
                "alert_level": "warning",
                "message": f"{name} ({code}) 成交量異常放大 {volume/avg_volume:.1f} 倍"
            })
        
        # 4. 檢查上下影線（可能反轉訊號）
        body = abs(price - open_price)
        upper_shadow = high - max(price, open_price)
        lower_shadow = min(price, open_price) - low
        
        # 長上影線（可能反轉下跌）
        if body > 0 and upper_shadow > body * 2:
            alerts.append({
                "code": code,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "alert_type": "long_upper_shadow",
                "alert_level": "warning",
                "message": f"{name} ({code}) 出現長上影線，可能反轉下跌"
            })
        
        # 長下影線（可能反轉上漲）
        if body > 0 and lower_shadow > body * 2:
            alerts.append({
                "code": code,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "alert_type": "long_lower_shadow",
                "alert_level": "info",
                "message": f"{name} ({code}) 出現長下影線，可能反轉上漲"
            })
        
        # 5. 檢查跳空缺口
        gap_threshold = thresholds.get("gap_pct", 2.0)
        if open_price > 0 and yesterday_close > 0:
            gap_pct = ((open_price - yesterday_close) / yesterday_close) * 100
            if abs(gap_pct) >= gap_threshold:
                gap_type = "向上" if gap_pct > 0 else "向下"
                alerts.append({
                    "code": code,
                    "name": name,
                    "price": price,
                    "change_pct": change_pct,
                    "alert_type": "gap",
                    "alert_level": "warning",
                    "message": f"{name} ({code}) 出現{gap_type}跳空缺口 {gap_pct:+.2f}%"
                })
    
    return alerts


def format_alert_message(alerts: List[Dict[str, Any]], check_time: Optional[datetime] = None) -> str:
    """
    格式化警報訊息
    
    Args:
        alerts: 警報列表
        check_time: 檢查時間
        
    Returns:
        格式化的訊息字串
    """
    if check_time is None:
        check_time = datetime.now()
    
    if not alerts:
        return ""
    
    msg = f"⚠️ 個股即時警報 ({check_time.strftime('%H:%M')})\n"
    msg += "=" * 30 + "\n"
    
    danger_alerts = [a for a in alerts if a.get("alert_level") == "danger"]
    warning_alerts = [a for a in alerts if a.get("alert_level") != "danger"]
    
    if danger_alerts:
        msg += "\n🔴 危險警報:\n"
        for a in danger_alerts:
            msg += f"• {a['message']}\n"
            msg += f"  現價: {a['price']:,.1f} (昨收: {a['yesterday_close']:,.1f})\n"
            msg += f"  成交量: {a['volume']:,} 張\n"
    
    if warning_alerts:
        msg += "\n🟡 注意事項:\n"
        for a in warning_alerts:
            msg += f"• {a['message']}\n"
    
    msg += "\n" + "=" * 30 + "\n"
    msg += "胚騰 AI Agent 即時監控"
    
    return msg


class StockMonitor:
    """個股即時監控器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get("enabled", False)
        self.watchlist = config.get("watchlist", [])
        self.default_thresholds = config.get("default_thresholds", {})
        self.monitor_hours = config.get("monitor_hours", {"start": "09:00", "end": "13:30"})
        self.check_interval = config.get("check_interval_minutes", 5)
        self._last_check_time = None
        self._last_prices = {}  # 記錄上次價格，用於判斷變動
    
    def is_monitor_time(self) -> bool:
        """檢查現在是否在監控時間內"""
        if not self.enabled:
            return False
        
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        start_time = self.monitor_hours.get("start", "09:00")
        end_time = self.monitor_hours.get("end", "13:30")
        
        return start_time <= current_time <= end_time
    
    def should_check(self) -> bool:
        """檢查是否應該執行檢查"""
        if not self.is_monitor_time():
            return False
        
        if self._last_check_time is None:
            return True
        
        elapsed = (datetime.now() - self._last_check_time).total_seconds() / 60
        return elapsed >= self.check_interval
    
    def check(self) -> List[Dict[str, Any]]:
        """
        執行一次檢查
        
        Returns:
            警報列表
        """
        if not self.enabled or not self.watchlist:
            return []
        
        if not self.should_check():
            return []
        
        self._last_check_time = datetime.now()
        
        # 取得所有自選股代號
        codes = [stock.get("code", "") for stock in self.watchlist if stock.get("code")]
        
        if not codes:
            return []
        
        # 抓取即時行情
        realtime_data = fetch_realtime_data(codes)
        if not realtime_data:
            logger.warning("[Monitor] 無法取得即時行情")
            return []
        
        # 檢查警報
        alerts = check_alerts(realtime_data, self.watchlist, self.default_thresholds)
        
        # 記錄價格
        for code, data in realtime_data.items():
            self._last_prices[code] = {
                "price": data.get("price", 0),
                "time": datetime.now()
            }
        
        return alerts
    
    def get_watchlist_status(self) -> List[Dict[str, Any]]:
        """
        取得自選股目前狀態
        
        Returns:
            [
                {
                    "code": "2330",
                    "name": "台積電",
                    "price": 1050.0,
                    "change_pct": 0.5,
                    "status": "normal"
                },
                ...
            ]
        """
        codes = [stock.get("code", "") for stock in self.watchlist if stock.get("code")]
        if not codes:
            return []
        
        realtime_data = fetch_realtime_data(codes)
        if not realtime_data:
            return []
        
        result = []
        for stock in self.watchlist:
            code = stock.get("code", "")
            name = stock.get("name", "")
            
            if code in realtime_data:
                data = realtime_data[code]
                change_pct = data.get("change_pct", 0)
                
                # 判斷狀態
                if change_pct <= -3:
                    status = "danger"
                elif change_pct <= -1:
                    status = "warning"
                elif change_pct >= 3:
                    status = "strong"
                else:
                    status = "normal"
                
                result.append({
                    "code": code,
                    "name": name,
                    "price": data.get("price", 0),
                    "change_pct": change_pct,
                    "volume": data.get("volume", 0),
                    "status": status
                })
        
        return result


if __name__ == "__main__":
    # 測試用
    config = {
        "enabled": True,
        "watchlist": [
            {"code": "2330", "name": "台積電", "thresholds": {"price_drop_pct": -3.0}},
            {"code": "2317", "name": "鴻海", "thresholds": {"price_drop_pct": -3.0}},
        ],
        "default_thresholds": {"price_drop_pct": -3.0, "volume_surge_ratio": 2.0},
        "monitor_hours": {"start": "09:00", "end": "13:30"},
        "check_interval_minutes": 5
    }
    
    monitor = StockMonitor(config)
    
    if monitor.is_monitor_time():
        print("現在是監控時間，執行檢查...")
        alerts = monitor.check()
        if alerts:
            print("\n警報:")
            for alert in alerts:
                print(f"  - {alert['message']}")
        else:
            print("無警報")
    else:
        print("現在不是監控時間")
    
    print("\n自選股狀態:")
    status = monitor.get_watchlist_status()
    for s in status:
        print(f"  {s['code']} {s['name']}: {s['price']:,.1f} ({s['change_pct']:+.2f}%) [{s['status']}]")
