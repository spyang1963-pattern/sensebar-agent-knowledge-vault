"""
個股+期貨即時監控排程器
每 5 分鐘執行一次，監控自選股+期貨即時行情
"""
import os
import sys
import yaml
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.stock_monitor import StockMonitor, format_alert_message
from src.futures_monitor import FuturesMonitor, format_futures_alert_message
from src.notifier import LineNotifier
from src.alert_history import AlertHistory

# 設定 logging
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "realtime_monitor.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    logger.info("=" * 50)
    logger.info("個股即時監控 - 開始執行")
    logger.info(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 50)
    
    # 載入設定
    config = load_config()
    monitor_config = config.get("realtime_monitor", {})
    line_config = config.get("channels", {}).get("line", {})
    
    if not monitor_config.get("enabled", False):
        logger.info("即時監控未啟用，跳過")
        return
    
    # 建立監控器
    monitor = StockMonitor(monitor_config)
    futures_monitor = FuturesMonitor(monitor_config)
    
    # 建立歷史紀錄器
    history = AlertHistory(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
    
    # 檢查是否在監控時間（個股或期貨）
    stock_time = monitor.is_monitor_time()
    futures_time = futures_monitor.is_monitor_time()
    
    if not stock_time and not futures_time:
        logger.info("不在監控時間，跳過")
        return
    
    # 執行個股檢查
    all_alerts = []
    if stock_time:
        logger.info("執行個股即時行情檢查...")
        stock_alerts = monitor.check()
        all_alerts.extend(stock_alerts)
    
    # 執行期貨檢查
    if futures_time:
        logger.info("執行期貨即時行情檢查...")
        futures_alerts = futures_monitor.check()
        all_alerts.extend(futures_alerts)
    
    if all_alerts:
        logger.info(f"發現 {len(all_alerts)} 個警報！")
        
        # 記錄到歷史
        history.add_alerts(all_alerts)
        
        # 格式化警報訊息
        alert_msg = format_alert_message(all_alerts)
        futures_alert_msg = format_futures_alert_message(all_alerts)
        full_msg = alert_msg + "\n" + futures_alert_msg if futures_alert_msg else alert_msg
        
        logger.info(f"\n{full_msg}")
        
        # 發送 LINE 通知
        line = LineNotifier(line_config)
        if line.enabled:
            base_url = "https://spyang1963-pattern.github.io/sensebar-agent-knowledge-vault"
            line.send(full_msg, dashboard_url=base_url)
            logger.info("已發送 LINE 通知")
        else:
            logger.info("LINE 未啟用，僅記錄日誌")
    else:
        logger.info("無警報，一切正常")
    
    # 輸出自選股狀態
    if stock_time:
        status = monitor.get_watchlist_status()
        if status:
            logger.info("\n股票狀態:")
            for s in status:
                logger.info(f"  {s['code']} {s['name']}: {s['price']:,.1f} ({s['change_pct']:+.2f}%)")
    
    # 輸出期貨狀態
    if futures_time:
        futures_status = futures_monitor.get_futures_status()
        if futures_status:
            logger.info("\n期貨狀態:")
            for s in futures_status:
                logger.info(f"  {s['code']} {s['name']}: {s['price']:,.0f} ({s['change_pct']:+.2f}%)")
    
    logger.info("=" * 50)
    logger.info("即時監控 - 執行完成")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
