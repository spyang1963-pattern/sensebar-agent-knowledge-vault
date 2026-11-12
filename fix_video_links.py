#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_video_links.py — 相容入口，實際工作已統一由 video_links.py 執行。

2026-11-12 起，「影片在哪一台／哪個路徑」只有一個權威：video_links.py。
本檔保留給舊排程、舊文件、肌肉記憶使用，參數原樣轉交：

    python -X utf8 fix_video_links.py            # = video_links.py
    python -X utf8 fix_video_links.py --dry-run  # 只盤點
    python -X utf8 fix_video_links.py --force    # 無條件重建 .lnk

它會做的不只是「把 file:// 換成 .lnk」，還包括：
- 補「（在 哪一台）」機器標記（本機／PC1／PC2／PC3／未確認）
- 把 `## 影片` 的裸路徑改成標準影片行
- 產品（` 摘要.md`／` 課程筆記.md`）補 `> 影片位置：…`
- 跳過備份／內部目錄（_harvest_overwritten、_harvest_conflicts、backup_* …）
"""
import sys

import video_links

if __name__ == "__main__":
    sys.exit(video_links.main())
