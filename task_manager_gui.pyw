#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任務管理 GUI —— 給 pythonw 用的啟動殼。

2026-11-09 PC2 實踩：這個檔案原本是 2026-07 的舊版 GUI 副本（22 KB，單一 class），
而且第 13 行是沒有防護的 `sys.stdout.reconfigure(...)`。用 pythonw 啟動時
`sys.stdout` 是 None → 一啟動就 AttributeError，但 pythonw 沒有主控台，
所以症狀是「雙擊完全沒反應、沒有視窗、沒有錯誤訊息」。notebook／PC1 沒事
只是因為它們用的是 `管理介面.bat`／`.lnk`（直接跑 task_manager_gui.py）。

現在改成薄殼：唯一的實作在 `task_manager_gui.py`，這裡只負責轉過去，
讓「雙擊 .pyw」跟「跑 .py」行為完全一致，以後不會再有兩份分歧的 GUI。
"""

import os
import sys
import runpy

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "task_manager_gui.py")

if not os.path.exists(TARGET):
    # pythonw 下沒有 stdout，只能用 MessageBox 講話
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None,
            f"找不到 {TARGET}\n\n請確認 D:\\AI-Agent-Workspace 是否完整（git pull）。",
            "任務管理 GUI", 0x10)
    except Exception:
        pass
    sys.exit(1)

sys.path.insert(0, HERE)
runpy.run_path(TARGET, run_name="__main__")
