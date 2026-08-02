#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notifier - sends alerts via Telegram and LINE.

Telegram requires a bot token + chat id (see setup instructions).
LINE reuses the token already configured in stock-monitor/config.yaml.

Usage:
  python notifier.py --test-tg          # test Telegram
  python notifier.py --test-line        # test LINE
  python notifier.py --digest           # send today's report summary
"""
import os
import sys
import argparse
from datetime import datetime, timezone, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

# --- config ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
TG_API = "https://api.telegram.org/bot{token}/sendMessage"

LINE_API = "https://api.line.me/v2/bot/message/push"


def _line_config():
    import yaml

    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stock-monitor", "config.yaml")
    if not os.path.exists(cfg_path):
        return None
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("channels", {}).get("line", {})
    except Exception:
        return None


def send_telegram(text, token=None, chat_id=None):
    token = token or TELEGRAM_TOKEN
    chat_id = chat_id or TELEGRAM_CHAT_ID
    if not token or not chat_id:
        print("[Telegram] 未設定 token/chat_id，跳過")
        return False
    try:
        resp = requests.post(
            TG_API.format(token=token),
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=15,
        )
        ok = resp.status_code == 200
        if not ok:
            print(f"[Telegram] 失敗: {resp.status_code} {resp.text[:200]}")
        else:
            print(f"[Telegram] 已發送 ({len(text)} 字)")
        return ok
    except Exception as e:
        print(f"[Telegram] 錯誤: {e}")
        return False


def send_line(text):
    cfg = _line_config()
    if not cfg or not cfg.get("enabled") or not cfg.get("channel_access_token"):
        print("[LINE] 未設定，跳過")
        return False
    token = cfg["channel_access_token"]
    ok = True
    for user in cfg.get("user_ids", []):
        uid = user.get("user_id") if isinstance(user, dict) else user
        if not uid:
            continue
        try:
            resp = requests.post(
                LINE_API,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                json={"to": uid, "messages": [{"type": "text", "text": text}]},
                timeout=10,
            )
            if resp.status_code != 200:
                print(f"[LINE] 發送失敗 {resp.status_code}: {resp.text[:120]}")
                ok = False
            else:
                print(f"[LINE] 已發送給 {user.get('name', uid[:8]) if isinstance(user, dict) else uid[:8]}")
        except Exception as e:
            print(f"[LINE] 錯誤: {e}")
            ok = False
    return ok


def build_digest(limit=8):
    """Build a short digest of today's important analyzed events."""
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    events = db.recent_events(limit=100, severity_min=1)
    lines = []
    lines.append(f"【金融重點摘要】{now.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    # market snapshot top few
    try:
        import market_data

        for row in market_data.latest_table()[:6]:
            lines.append(row)
        lines.append("")
    except Exception:
        pass
    important = [e for e in events if e["severity"] >= 2]
    lines.append(f"重大事件: {len(important)} 則")
    for e in important[:limit]:
        senti = "▲" if e["sentiment"] == "positive" else ("▼" if e["sentiment"] == "negative" else "―")
        lines.append(f"{senti}[{e['category']}] {e['title'][:60]}")
    lines.append("")
    lines.append("更多請看知識庫『金融/每日報告』")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Financial news notifier")
    parser.add_argument("--test-tg", action="store_true", help="test Telegram")
    parser.add_argument("--test-line", action="store_true", help="test LINE")
    parser.add_argument("--digest", action="store_true", help="send digest")
    args = parser.parse_args()

    if args.test_tg:
        send_telegram("【測試】金融新聞系統 Telegram 通知已上線！")
    elif args.test_line:
        send_line("【測試】金融新聞系統 LINE 通知已上線！")
    elif args.digest:
        text = build_digest()
        print(text)
        send_telegram(text)
        send_line(text)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
