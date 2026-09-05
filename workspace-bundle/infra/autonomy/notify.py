#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# notify.py - manual notification helper (used for tests and one-off alerts).
import argparse

import common


def main():
    ap = argparse.ArgumentParser(description="Send a Telegram alert")
    ap.add_argument("--test", action="store_true", help="send a test message")
    ap.add_argument("--text", default="", help="text to send")
    args = ap.parse_args()
    if args.test:
        ok = common.send_telegram("【Autonomy】測試訊息 — 自主任務層已在線 ✅")
        print("成功" if ok else "未送出（請檢查 ~\\.telegram_env）")
    elif args.text:
        common.send_telegram(args.text)
    else:
        token, chat = common.telegram_token_chat()
        print("token 已設定" if token else "token 未設定")


if __name__ == "__main__":
    main()