"""
胚騰 AI Agent - 排程執行器
根據 config.yaml 中的訊息設定，自動發送通知
"""
import os
import sys
import yaml
import json
import time
import subprocess
import logging
from datetime import datetime, timedelta

# === 日誌設定 ===
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "scheduler.log")

LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduler.lock")

def acquire_lock():
    """PID lock 避免重複啟動，回傳 True 表示取得鎖"""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)
            return False  # 已有實例在跑
        except (ProcessLookupError, PermissionError, OSError, ValueError):
            pass
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True

def release_lock():
    try:
        os.remove(LOCK_FILE)
    except:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("scheduler")

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
SENT_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sent_log.json")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sent_log():
    """載入已發送記錄"""
    if os.path.exists(SENT_LOG_PATH):
        with open(SENT_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_sent_log(log):
    """儲存已發送記錄"""
    with open(SENT_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def _is_stock_msg(msg):
    """判斷是否為股票分析類訊息"""
    msg_id = msg.get("id", "")
    msg_name = msg.get("name", "")
    return msg_id == "stock_alert" or "股票" in msg_name or "融資" in msg_name


def should_send_now(msg, memory_sent_log=None):
    """檢查這則訊息現在是否應該發送
    memory_sent_log: run_scheduler 內的記憶體去重 dict，用於週六補發判斷
    """
    if not msg.get("enabled"):
        return False
    
    status = msg.get("status", "編輯中")
    if status != "運作中":
        return False
    
    sched = msg.get("schedule", {})
    repeat = sched.get("repeat", "daily")
    time_str = sched.get("time", "18:00")
    start = sched.get("start", "immediately")
    end = sched.get("end", "never")
    
    now = datetime.now()
    hour, minute = map(int, time_str.split(":"))

    # 檢查是否已到設定時間（同小時且分數已達，確保 21:30 不會在 21:00 就觸發）
    if now.hour != hour or now.minute < minute:
        return False
    
    # 檢查開始時間
    if start != "immediately":
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M")
            if now < start_dt:
                return False
        except:
            pass
    
    # 檢查結束時間
    if end != "never":
        try:
            end_dt = datetime.strptime(end, "%Y-%m-%d %H:%M")
            if now > end_dt:
                return False
        except:
            pass
    
    # 檢查週期
    if repeat == "once":
        # 單次：檢查是否已發送過
        sent_log = load_sent_log()
        msg_id = msg.get("id", "")
        today = now.strftime("%Y-%m-%d")
        if sent_log.get(msg_id) == today:
            return False
    elif repeat == "weekly":
        # 每週：檢查是否為週一
        if now.weekday() != 0:
            return False
    elif repeat == "monthly":
        # 每月：檢查是否為1號
        if now.day != 1:
            return False
    elif repeat == "hourly":
        # 每小時：在整點發送
        pass
    
    # 股票分析類：週末過濾（週一～五正常，週六補發，週日不發）
    if repeat == "daily" and _is_stock_msg(msg):
        weekday = now.weekday()  # 0=週一, 5=週六, 6=週日
        if weekday == 6:  # 週日
            return False
        elif weekday == 5:  # 週六：檢查週五是否有發過，有則跳過
            msg_id = msg.get("id", "")
            friday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            # 用記憶體去重 dict 比對（run_scheduler 內的即時記錄）
            sent_key = memory_sent_log.get(msg_id) if memory_sent_log else None
            if sent_key == friday:
                logger.info(f"週六補發跳過：{msg_id} 週五({friday})已發送")
                return False
    
    return True


def get_active_recipients(msg):
    """取得可發送的接收者（排除暫停和錯誤的）"""
    recipients = msg.get("recipients", [])
    return [r for r in recipients if r.get("status") == "運作中"]


def send_line_message(recipients, message):
    """發送 LINE 訊息"""
    config = load_config()
    token = config.get("channels", {}).get("line", {}).get("channel_access_token", "")
    
    if not token:
        logger.warning("[LINE] Token 未設定")
        return False
    
    import requests
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    
    success = True
    for r in recipients:
        if r.get("channel") != "line":
            continue
        target = r.get("target", "")
        if not target:
            continue
        
        payload = {"to": target, "messages": [{"type": "text", "text": message}]}
        try:
            resp = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info(f"[LINE] 已發送給 {r.get('name', target[:8])}")
            else:
                logger.error(f"[LINE] 發送失敗: {resp.status_code} {resp.text[:200]}")
                success = False
        except Exception as e:
            logger.error(f"[LINE] 錯誤: {e}")
            success = False
    
    return success


def send_email(recipients, subject, content):
    """發送 Email"""
    config = load_config()
    email_config = config.get("channels", {}).get("email", {})
    
    if not email_config.get("enabled"):
        logger.info("[Email] 未啟用")
        return False
    
    email_list = [r.get("target") for r in recipients if r.get("channel") == "email" and r.get("target")]
    if not email_list:
        logger.info("[Email] 無收件者")
        return False
    
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    try:
        msg = MIMEMultipart()
        msg["From"] = email_config.get("sender_email", "")
        msg["To"] = ", ".join(email_list)
        msg["Subject"] = subject
        msg.attach(MIMEText(content, "html", "utf-8"))
        
        server = smtplib.SMTP(email_config.get("smtp_server", "smtp.gmail.com"), email_config.get("smtp_port", 587))
        server.starttls()
        server.login(email_config.get("sender_email", ""), email_config.get("sender_password", ""))
        server.sendmail(email_config.get("sender_email", ""), email_list, msg.as_string())
        server.quit()
        logger.info(f"[Email] 已發送給 {len(email_list)} 人")
        return True
    except Exception as e:
        logger.error(f"[Email] 錯誤: {e}")
        return False


def execute_stock_analysis():
    """執行股票分析，回傳 (success, stdout, stderr)"""
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_stock_analysis.py")
    try:
        logger.info(f"啟動分析腳本: {script_path}")
        result = subprocess.run(
            [sys.executable, "-u", script_path, "--no-notify"],
            capture_output=True,
            timeout=600,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            encoding="utf-8",
            errors="replace",
        )
        logger.info(f"分析腳本輸出:\n{result.stdout}")
        if result.returncode != 0:
            logger.error(f"分析失敗 (code={result.returncode}): {result.stderr}")
        return result.returncode == 0, result.stdout or "", result.stderr or ""
    except subprocess.TimeoutExpired:
        logger.error("分析腳本逾時（600 秒）")
        return False, "", "timeout"
    except Exception as e:
        logger.error(f"分析腳本例外: {e}")
        return False, "", str(e)


def send_stock_analysis_message(msg):
    """發送股票分析訊息
    邏輯：嘗試抓取今日資料
    - 有今日資料 → 發送完整分析
    - 無今日資料 → 發送「今日證交所未發布」
    """
    logger.info("=" * 50)
    logger.info("執行台股融資券分析")
    logger.info("=" * 50)

    # 嘗試抓取資料
    success, stdout, stderr = execute_stock_analysis()
    
    if success:
        # 從 stdout 解析明確標記（避免亂碼比對問題）
        today_str = datetime.now().strftime("%Y-%m-%d")
        got_today_data = False
        data_date = ""
        alert_count = 0
        margin_call = 0
        panic_sell = 0
        institutional_buy = 0
        quadrant_line = ""
        
        for line_text in stdout.split("\n"):
            line_text = line_text.strip()
            if line_text.startswith("DATA_DATE:"):
                data_date = line_text.split("DATA_DATE:", 1)[1].strip()
                if data_date == today_str:
                    got_today_data = True
            elif line_text.startswith("ALERT_COUNT:"):
                try:
                    alert_count = int(line_text.split("ALERT_COUNT:", 1)[1].strip())
                except:
                    pass
            elif line_text.startswith("MARGIN_CALL:"):
                try:
                    margin_call = int(line_text.split("MARGIN_CALL:", 1)[1].strip())
                except:
                    pass
            elif line_text.startswith("PANIC_SELL:"):
                try:
                    panic_sell = int(line_text.split("PANIC_SELL:", 1)[1].strip())
                except:
                    pass
            elif line_text.startswith("INSTITUTIONAL_BUY:"):
                try:
                    institutional_buy = int(line_text.split("INSTITUTIONAL_BUY:", 1)[1].strip())
                except:
                    pass
            elif line_text.startswith("QUADRANT:"):
                quadrant_line = line_text.split("QUADRANT:", 1)[1].strip()
        
        logger.info(f"資料日期: {data_date}, 今日: {today_str}, 符合: {got_today_data}")
        
        if got_today_data:
            # 有今日資料 → 發送完整分析
            logger.info(f"抓到今日({today_str})資料，發送完整分析")
            recipients = get_active_recipients(msg)
            if not recipients:
                logger.warning("無可發送的接收者")
                return True

            config = load_config()
            base_url = "https://spyang1963-pattern.github.io/sensebar-agent-knowledge-vault"
            # 帶日期版本參數強制跳過 CDN/瀏覽器快取（新參數 = 新快取鍵）
            ver = today_str.replace("-", "")
            dashboard_url = f"{base_url}/?d={ver}"
            history_url = f"{base_url}/history.html?d={ver}"

            # 週六補發：加上【補發】標記
            is_catchup = datetime.now().weekday() == 5
            prefix = "【補發】" if is_catchup else ""
            if is_catchup:
                logger.info("週六補發模式：加上【補發】標記")

            message = f"【胚騰 AI 台股融資券分析 {prefix}{today_str}】\n\n"
            message += f"今日警示股: {alert_count} 檔\n"
            message += f"融資斷頭: {margin_call} 檔\n"
            message += f"恐慌停損: {panic_sell} 檔\n"
            message += f"主力換手: {institutional_buy} 檔\n"
            if quadrant_line:
                parts = quadrant_line.split("|")
                if len(parts) >= 3:
                    q_code, q_label, q_advice = parts[0], parts[1], parts[2]
                    message += f"\n【大盤四象限】{q_label}\n"
                    message += f"建議: {q_advice}\n"
            message += f"\n看板: {dashboard_url}\n"
            message += f"歷史紀錄: {history_url}\n"
            message += "---\n"
            message += "胚騰 AI Agent"

            send_line_message(recipients, message)
            email_recipients = [r for r in recipients if r.get("channel") == "email"]
            if email_recipients:
                send_email(email_recipients, f"台股融資券分析 {today_str}", message)
            logger.info("分析通知已發送")
            return True
        else:
            # 有資料但不是今日 → 發送「今日證交所未發布」
            logger.info(f"抓到的資料非今日({today_str})，視為未發布")
    else:
        logger.warning("分析腳本執行失敗")

    # 無今日資料 → 發送「今日證交所未發布」
    logger.info("今日證交所未發布資料")
    recipients = get_active_recipients(msg)

    history_url = "https://spyang1963-pattern.github.io/sensebar-agent-knowledge-vault/history.html"
    fallback_msg = f"【胚騰 AI 股票警報 {today_str}】\n\n"
    fallback_msg += f"今日({today_str})證交所未發布融資融券資料\n"
    fallback_msg += "請留意明日更新\n\n"
    fallback_msg += f"歷史紀錄: {history_url}\n"
    fallback_msg += "---\n"
    fallback_msg += "胚騰 AI Agent"

    send_line_message(recipients, fallback_msg)
    email_recipients = [r for r in recipients if r.get("channel") == "email"]
    if email_recipients:
        send_email(email_recipients, "台股融資券分析 - 今日未發布", fallback_msg)
    return True


def process_message(msg):
    """處理單一訊息"""
    msg_name = msg.get("name", "")
    msg_id = msg.get("id", "")
    
    logger.info(f"處理訊息: {msg_name}")
    
    # 特殊處理：股票分析
    if msg_id == "stock_alert" or "股票" in msg_name or "融資" in msg_name:
        return send_stock_analysis_message(msg)
    
    # 一般訊息
    recipients = get_active_recipients(msg)
    if not recipients:
        logger.warning(f"  無可發送的接收者")
        return False
    
    content = msg.get("content", "")
    if not content:
        logger.warning(f"  訊息內容為空")
        return False
    
    # 發送
    send_line_message(recipients, content)
    
    # 如果有 Email 收件者
    email_recipients = [r for r in recipients if r.get("channel") == "email"]
    if email_recipients:
        send_email(email_recipients, msg_name, content)
    
    return True


def run_scheduler():
    """排程執行器主迴圈"""
    if not acquire_lock():
        logger.info("另一個排程器正在運行，跳過")
        return

    logger.info("=" * 50)
    logger.info("胚騰 AI Agent - 排程執行器啟動")
    logger.info(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 50)
    
    config = load_config()
    messages = config.get("messages", [])
    
    logger.info(f"共 {len(messages)} 則訊息")
    for msg in messages:
        status = "運作中" if msg.get("status") == "運作中" else "停止"
        logger.info(f"  - {msg.get('name', '')}: {status} (enabled={msg.get('enabled')})")
    
    logger.info("等待排程時間... 按 Ctrl+C 停止")
    
    sent_log = {}  # 記錄已發送的訊息，避免重複 (msg_id -> date_string)
    
    try:
        while True:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            current_hour = now.strftime("%Y-%m-%d %H")
            
            # 重新載入設定（支援即時修改）
            try:
                config = load_config()
                messages = config.get("messages", [])
            except Exception as e:
                logger.warning(f"重新載入設定失敗: {e}")
            
            # 檢查每則訊息
            for msg in messages:
                msg_id = msg.get("id", "")
                if should_send_now(msg, memory_sent_log=sent_log):
                    # 去重：根據 repeat 類型決定去重週期
                    repeat = msg.get("schedule", {}).get("repeat", "daily")
                    if repeat == "hourly":
                        dedup_key = current_hour  # 每小時去重
                    else:
                        dedup_key = today_str  # 每日去重（daily/weekly/monthly/once）
                    
                    if sent_log.get(msg_id) == dedup_key:
                        continue
                    
                    logger.info(f"[{now.strftime('%H:%M:%S')}] 觸發: {msg.get('name', '')}")
                    process_message(msg)
                    sent_log[msg_id] = dedup_key
                    
                    # 如果是單次訊息，記錄已發送
                    if repeat == "once":
                        permanent_log = load_sent_log()
                        permanent_log[msg_id] = today_str
                        save_sent_log(permanent_log)
            
            # 清除舊的記錄（保留最近 2 天）
            two_days_ago = (now - timedelta(days=2)).strftime("%Y-%m-%d")
            sent_log = {k: v for k, v in sent_log.items() if v >= two_days_ago}
            
            # 每30秒檢查一次
            time.sleep(30)
    finally:
        release_lock()


if __name__ == "__main__":
    run_scheduler()
