"""
TWSE 資料監控腳本 - 即時偵測融資融券資料更新
每15分鐘檢查一次，發現新資料立即觸發分析並通知
"""
import os
import sys
import yaml
import json
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.twse_fetcher import TWSEFetcher
from src.margin_cache import load_cache, get_cache_info

# 監控狀態檔
STATUS_FILE = os.path.join(os.path.dirname(__file__), "output", "monitor_status.json")


def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_status():
    """載入監控狀態"""
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_known_date": None, "last_check": None}


def save_status(status):
    """儲存監控狀態"""
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def check_for_update():
    """檢查 TWSE 是否有新資料"""
    print("=" * 60)
    print("  TWSE 資料監控 - 檢查更新")
    print(f"  時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 載入狀態
    status = load_status()
    last_known_date = status.get("last_known_date")
    print(f"\n  上次已知日期: {last_known_date or '無'}")

    # 抓取最新資料（不指定日期，API 會回傳最新）
    fetcher = TWSEFetcher()
    print("\n[1] 檢查 TWSE 最新資料...")
    margin_data, actual_date = fetcher.fetch_margin_data_twse()

    if margin_data is None or margin_data.empty or not actual_date:
        print("  [結果] 無法取得資料或無新資料")
        status["last_check"] = datetime.now().isoformat()
        save_status(status)
        return False

    print(f"  [結果] TWSE 最新日期: {actual_date}")
    print(f"  [結果] 資料筆數: {len(margin_data)}")

    # 比對是否為新資料
    if actual_date == last_known_date:
        print(f"\n  [結論] 資料無更新（仍為 {actual_date}）")
        status["last_check"] = datetime.now().isoformat()
        save_status(status)
        return False

    # 有新資料！
    print(f"\n  [結論] ★ 發現新資料！{last_known_date} → {actual_date}")

    # 更新狀態
    status["last_known_date"] = actual_date
    status["last_check"] = datetime.now().isoformat()
    status["last_update_time"] = datetime.now().isoformat()
    save_status(status)

    # 觸發完整分析
    print("\n[2] 觸發完整分析流程...")
    trigger_analysis(actual_date, margin_data)

    return True


def trigger_analysis(trading_day, margin_data):
    """觸發完整分析流程"""
    try:
        # 執行主分析腳本
        import subprocess
        script_path = os.path.join(os.path.dirname(__file__), "run_stock_analysis.py")
        
        print(f"  執行分析腳本: {script_path}")
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=os.path.dirname(__file__),
            capture_output=True,
            text=True,
            timeout=300  # 5分鐘逾時
        )

        if result.returncode == 0:
            print("  [成功] 分析完成！")
            # 顯示最後幾行輸出
            lines = result.stdout.strip().split("\n")
            for line in lines[-10:]:
                print(f"    {line}")
        else:
            print(f"  [錯誤] 分析失敗 (returncode: {result.returncode})")
            if result.stderr:
                print(f"  錯誤訊息: {result.stderr[:500]}")

    except subprocess.TimeoutExpired:
        print("  [錯誤] 分析逾時（超過5分鐘）")
    except Exception as e:
        print(f"  [錯誤] 執行失敗: {e}")


def run_monitor(interval_minutes=15):
    """持續監控模式"""
    print("=" * 60)
    print("  TWSE 資料監控模式啟動")
    print(f"  檢查間隔: {interval_minutes} 分鐘")
    print(f"  按 Ctrl+C 停止")
    print("=" * 60)

    while True:
        try:
            check_for_update()
            print(f"\n  下次檢查: {(datetime.now() + timedelta(minutes=interval_minutes)).strftime('%H:%M:%S')}")
            print("-" * 60)
            time.sleep(interval_minutes * 60)
        except KeyboardInterrupt:
            print("\n\n  監控已停止")
            break
        except Exception as e:
            print(f"\n  [錯誤] 監控異常: {e}")
            print("  30 秒後重試...")
            time.sleep(30)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        # 持續監控模式
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        run_monitor(interval)
    else:
        # 單次檢查模式
        check_for_update()
