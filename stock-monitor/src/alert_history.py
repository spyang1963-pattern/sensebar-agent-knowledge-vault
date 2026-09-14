# alert_history.py
"""
歷史警報紀錄模組
記錄所有警報歷史，支援查詢和統計
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

ALERT_HISTORY_FILE = "alert_history.json"


class AlertHistory:
    """警報歷史管理器"""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.file_path = os.path.join(data_dir, ALERT_HISTORY_FILE)
        self._ensure_dir()
        self.alerts = self._load()
    
    def _ensure_dir(self):
        """確保資料目錄存在"""
        os.makedirs(self.data_dir, exist_ok=True)
    
    def _load(self) -> List[Dict[str, Any]]:
        """載入歷史資料"""
        if not os.path.exists(self.file_path):
            return []
        
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"[AlertHistory] 載入歷史資料失敗: {e}")
            return []
    
    def _save(self):
        """儲存歷史資料"""
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.alerts, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"[AlertHistory] 儲存歷史資料失敗: {e}")
    
    def add_alert(self, alert: Dict[str, Any]):
        """
        新增警報紀錄
        
        Args:
            alert: 警報資料
                {
                    "code": "2330",
                    "name": "台積電",
                    "alert_type": "price_drop",
                    "alert_level": "danger",
                    "price": 1012.5,
                    "change_pct": -3.5,
                    "message": "...",
                    "time": "2026-07-23 14:30:00"
                }
        """
        # 確保有時間戳記
        if "time" not in alert:
            alert["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 確保有日期
        if "date" not in alert:
            alert["date"] = datetime.now().strftime("%Y-%m-%d")
        
        # 加入唯一 ID
        alert["id"] = f"{alert.get('code', '')}_{alert.get('time', '').replace(':', '').replace(' ', '')}"
        
        self.alerts.append(alert)
        self._save()
        
        logger.info(f"[AlertHistory] 新增警報: {alert.get('code')} {alert.get('name')} - {alert.get('alert_type')}")
    
    def add_alerts(self, alerts: List[Dict[str, Any]]):
        """批次新增警報"""
        for alert in alerts:
            self.add_alert(alert)
    
    def get_alerts(self, 
                   days: Optional[int] = None,
                   code: Optional[str] = None,
                   alert_type: Optional[str] = None,
                   limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        查詢警報紀錄
        
        Args:
            days: 最近幾天
            code: 股票代號
            alert_type: 警報類型
            limit: 限制筆數
            
        Returns:
            警報列表
        """
        result = self.alerts.copy()
        
        # 篩選日期
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            result = [a for a in result if a.get("date", "") >= cutoff_date]
        
        # 篩選股票
        if code:
            result = [a for a in result if a.get("code") == code]
        
        # 篩選類型
        if alert_type:
            result = [a for a in result if a.get("alert_type") == alert_type]
        
        # 按時間排序（最新在前）
        result.sort(key=lambda x: x.get("time", ""), reverse=True)
        
        # 限制筆數
        if limit:
            result = result[:limit]
        
        return result
    
    def get_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        取得警報統計
        
        Args:
            days: 統計最近幾天
            
        Returns:
            {
                "total": 15,
                "by_type": {"price_drop": 10, "volume_surge": 5},
                "by_stock": {"2330": 5, "2317": 3},
                "by_level": {"danger": 8, "warning": 7}
            }
        """
        recent_alerts = self.get_alerts(days=days)
        
        stats = {
            "total": len(recent_alerts),
            "by_type": {},
            "by_stock": {},
            "by_level": {},
            "period_days": days
        }
        
        for alert in recent_alerts:
            # 統計類型
            alert_type = alert.get("alert_type", "unknown")
            stats["by_type"][alert_type] = stats["by_type"].get(alert_type, 0) + 1
            
            # 統計股票
            code = alert.get("code", "unknown")
            stats["by_stock"][code] = stats["by_stock"].get(code, 0) + 1
            
            # 統計等級
            level = alert.get("alert_level", "unknown")
            stats["by_level"][level] = stats["by_level"].get(level, 0) + 1
        
        return stats
    
    def get_daily_summary(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        取得某日警報摘要
        
        Args:
            date: 日期 (YYYY-MM-DD)，None 則為今日
            
        Returns:
            {
                "date": "2026-07-23",
                "total": 5,
                "alerts": [...]
            }
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        daily_alerts = [a for a in self.alerts if a.get("date") == date]
        
        return {
            "date": date,
            "total": len(daily_alerts),
            "alerts": daily_alerts
        }
    
    def clear_old_alerts(self, keep_days: int = 30):
        """清除舊警報（保留最近 N 天）"""
        cutoff_date = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
        before_count = len(self.alerts)
        
        self.alerts = [a for a in self.alerts if a.get("date", "") >= cutoff_date]
        after_count = len(self.alerts)
        
        if before_count > after_count:
            self._save()
            logger.info(f"[AlertHistory] 清除 {before_count - after_count} 筆舊警報（保留 {keep_days} 天）")
    
    def export_to_csv(self, filepath: Optional[str] = None) -> str:
        """
        匯出警報紀錄為 CSV
        
        Args:
            filepath: 匯出路徑，None 則自動命名
            
        Returns:
            匯出的檔案路徑
        """
        import csv
        
        if filepath is None:
            filepath = os.path.join(self.data_dir, f"alert_history_{datetime.now().strftime('%Y%m%d')}.csv")
        
        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                if not self.alerts:
                    return filepath
                
                # 寫入標題
                headers = ["時間", "日期", "股票代號", "股票名稱", "警報類型", "警報等級", 
                          "現價", "漲跌幅%", "訊息"]
                writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
                writer.writeheader()
                
                # 寫入資料
                for alert in self.alerts:
                    row = {
                        "時間": alert.get("time", ""),
                        "日期": alert.get("date", ""),
                        "股票代號": alert.get("code", ""),
                        "股票名稱": alert.get("name", ""),
                        "警報類型": alert.get("alert_type", ""),
                        "警報等級": alert.get("alert_level", ""),
                        "現價": alert.get("price", ""),
                        "漲跌幅%": alert.get("change_pct", ""),
                        "訊息": alert.get("message", "")
                    }
                    writer.writerow(row)
            
            logger.info(f"[AlertHistory] 匯出 {len(self.alerts)} 筆警報到 {filepath}")
            return filepath
            
        except IOError as e:
            logger.error(f"[AlertHistory] 匯出失敗: {e}")
            return ""


if __name__ == "__main__":
    # 測試用
    history = AlertHistory()
    
    # 模擬新增警報
    test_alert = {
        "code": "2330",
        "name": "台積電",
        "alert_type": "price_drop",
        "alert_level": "danger",
        "price": 1012.5,
        "change_pct": -3.5,
        "message": "台積電 (2330) 股價跌幅 -3.5%，超過警戒值 -3.0%"
    }
    
    history.add_alert(test_alert)
    
    # 查詢警報
    recent = history.get_alerts(days=7)
    print(f"最近 7 天警報: {len(recent)} 筆")
    
    # 統計
    stats = history.get_statistics(days=7)
    print(f"統計: {stats}")
