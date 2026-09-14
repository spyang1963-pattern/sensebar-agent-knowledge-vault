"""
胚騰 AI Agent - 排程執行器守護程式
確保 message_scheduler.py 持續運行，崩潰自動重啟
支援 PID 檔防重複啟動
"""
import subprocess
import sys
import os
import time
import logging
from datetime import datetime

SCHEDULER_SCRIPT = "message_scheduler.py"
RESTART_DELAY = 10  # 秒
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(BASE_DIR, "scheduler.pid")
LOG_FILE = os.path.join(BASE_DIR, "logs", "watchdog.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("watchdog")


def is_already_running():
    """檢查是否有其他 watchdog 正在運行"""
    if not os.path.exists(PID_FILE):
        return False
    try:
        with open(PID_FILE, "r") as f:
            old_pid = int(f.read().strip())
        # 檢查該 PID 是否還活著
        os.kill(old_pid, 0)
        logger.info(f"另一個守護程式正在運行 (PID: {old_pid})，跳過")
        return True
    except (ProcessLookupError, PermissionError, OSError, ValueError):
        # PID 不存在或無效，清除舊的 PID 檔
        try:
            os.remove(PID_FILE)
        except:
            pass
        return False
    except PermissionError:
        # PID 存在且有權限，表示真的在跑
        logger.info(f"另一個守護程式正在運行 (PID: {old_pid})，跳過")
        return True


def write_pid():
    """寫入目前 PID"""
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_pid():
    """移除 PID 檔"""
    try:
        os.remove(PID_FILE)
    except:
        pass


def run_scheduler():
    """持續運行 scheduler，崩潰自動重啟"""
    if is_already_running():
        return

    write_pid()
    logger.info("=" * 50)
    logger.info("排程守護程式啟動")
    logger.info(f"PID: {os.getpid()}")
    logger.info("=" * 50)

    try:
        while True:
            logger.info(f"啟動 scheduler ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
            try:
                process = subprocess.Popen(
                    [sys.executable, SCHEDULER_SCRIPT],
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                    cwd=BASE_DIR,
                )
                return_code = process.wait()
                logger.warning(f"Scheduler 已停止 (return code: {return_code})")
            except Exception as e:
                logger.error(f"Scheduler 執行異常: {e}")

            logger.info(f"{RESTART_DELAY} 秒後重啟...")
            time.sleep(RESTART_DELAY)
    finally:
        remove_pid()
        logger.info("守護程式結束")


if __name__ == "__main__":
    run_scheduler()
