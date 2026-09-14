# futures_monitor.py
"""
期貨即時監控模組
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


def check_futures_alerts(futures_data: Dict[str, Any], futures_watchlist: List[Dict], default_thresholds: Dict) -> List[Dict[str, Any]]:
    """
    檢查期貨是否觸發警報
    """
    alerts = []
    
    for futures in futures_watchlist:
        code = futures.get("code", "")
        name = futures.get("name", "")
        thresholds = futures.get("thresholds", default_thresholds)
        
        if code not in futures_data:
            continue
        
        data = futures_data[code]
        price = data.get("price", 0)
        change_pct = data.get("change_pct", 0)
        yesterday_settle = data.get("yesterday_settle", 0)
        volume = data.get("volume", 0)
        
        # 檢查跌幅
        price_drop_threshold = thresholds.get("price_drop_pct", -1.0)
        if change_pct <= price_drop_threshold:
            alerts.append({
                "code": code,
                "name": name,
                "price": price,
                "yesterday_settle": yesterday_settle,
                "change_pct": change_pct,
                "volume": volume,
                "alert_type": "futures_drop",
                "alert_level": "danger",
                "market_type": "futures",
                "message": f"{name} ({code}) 跌幅 {change_pct:+.2f}%，超過警戒值 {price_drop_threshold}%"
            })
        
        # 檢查漲幅
        price_rise_threshold = thresholds.get("price_rise_pct", 2.0)
        if change_pct >= price_rise_threshold:
            alerts.append({
                "code": code,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "alert_type": "futures_rise",
                "alert_level": "warning",
                "market_type": "futures",
                "message": f"{name} ({code}) 漲幅 {change_pct:+.2f}%，注意反轉"
            })
    
    return alerts


def format_futures_alert_message(alerts: List[Dict[str, Any]], check_time: Optional[datetime] = None) -> str:
    """
    格式化期貨警報訊息
    """
    if check_time is None:
        check_time = datetime.now()
    
    if not alerts:
        return ""
    
    msg = f"期貨即時警報 ({check_time.strftime('%H:%M')})\n"
    msg += "=" * 30 + "\n"
    
    danger_alerts = [a for a in alerts if a.get("alert_level") == "danger"]
    warning_alerts = [a for a in alerts if a.get("alert_level") != "danger"]
    
    if danger_alerts:
        msg += "\n[危險] 跌幅警報:\n"
        for a in danger_alerts:
            msg += f"  {a['message']}\n"
            msg += f"  現價: {a['price']:,.0f} (昨結: {a.get('yesterday_settle', 0):,.0f})\n"
            msg += f"  成交量: {a['volume']:,} 口\n"
    
    if warning_alerts:
        msg += "\n[注意] 漲幅警報:\n"
        for a in warning_alerts:
            msg += f"  {a['message']}\n"
    
    msg += "\n" + "=" * 30 + "\n"
    msg += "胚騰 AI Agent 期貨監控"
    
    return msg


class FuturesMonitor:
    """期貨即時監控器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get("enabled", False)
        self.futures_watchlist = config.get("futures_watchlist", [])
        self.default_thresholds = config.get("default_thresholds", {})
        self.monitor_hours = config.get("monitor_hours", {"start": "08:45", "end": "05:00"})
        self.check_interval = config.get("check_interval_minutes", 5)
        self._last_check_time = None
    
    def is_monitor_time(self) -> bool:
        """檢查現在是否在監控時間內（含夜盤）"""
        if not self.enabled or not self.futures_watchlist:
            return False
        
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        start_time = self.monitor_hours.get("start", "08:45")
        end_time = self.monitor_hours.get("end", "05:00")
        
        # 處理跨日（夜盤：15:00 - 05:00）
        if start_time > end_time:
            # 跨日情況：08:45-05:00 表示日盤+夜盤
            return current_time >= start_time or current_time <= end_time
        else:
            return start_time <= current_time <= end_time
    
    def should_check(self) -> bool:
        if not self.is_monitor_time():
            return False
        if self._last_check_time is None:
            return True
        elapsed = (datetime.now() - self._last_check_time).total_seconds() / 60
        return elapsed >= self.check_interval
    
    def check(self) -> List[Dict[str, Any]]:
        """執行一次檢查"""
        if not self.enabled or not self.futures_watchlist:
            return []
        
        if not self.should_check():
            return []
        
        self._last_check_time = datetime.now()
        
        from src.futures_fetcher import fetch_futures_data
        
        codes = [f.get("code", "") for f in self.futures_watchlist if f.get("code")]
        if not codes:
            return []
        
        futures_data = fetch_futures_data(codes)
        if not futures_data:
            logger.warning("[FuturesMonitor] 無法取得期貨行情")
            return []
        
        alerts = check_futures_alerts(futures_data, self.futures_watchlist, self.default_thresholds)
        return alerts
    
    def get_futures_status(self) -> List[Dict[str, Any]]:
        """取得期貨目前狀態"""
        codes = [f.get("code", "") for f in self.futures_watchlist if f.get("code")]
        if not codes:
            return []
        
        from src.futures_fetcher import fetch_futures_data
        futures_data = fetch_futures_data(codes)
        if not futures_data:
            return []
        
        result = []
        for futures in self.futures_watchlist:
            code = futures.get("code", "")
            name = futures.get("name", "")
            
            if code in futures_data:
                data = futures_data[code]
                change_pct = data.get("change_pct", 0)
                
                if change_pct <= -1:
                    status = "danger"
                elif change_pct <= -0.5:
                    status = "warning"
                elif change_pct >= 1:
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
