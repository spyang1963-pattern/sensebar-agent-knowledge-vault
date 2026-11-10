#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backfill_burn.py — 回補燒字幕：掃 KB 條目，把「有下載影片但沒燒字幕」的補齊。

為什麼（2026-11-10）：11-09~11-10 期間 burn_subs 一度關閉，掃描收成的「無字幕」影片
只下載了原始 mp4（D:\\YouTube_Videos），沒有 _字幕.mp4，條目也沒有「燒字幕影片」行。
使用者原則：**無字幕影片一律下載＋燒字幕**（_字幕.mp4 是條目的可點播版本）。
本工具在任何一台都能跑（只處理「影片在本機」的條目；影片在別台的會列出來提示）。

做什麼：
1. 掃 knowledge-base 的 .md 條目，找 `- 本機影片：<絕對路徑>` 行。
2. 影片存在但 `_字幕.mp4` 不存在 → 用條目同名 .srt 燒字幕（channel_watcher.burn_subtitles）。
3. 燒成功（或 _字幕.mp4 已存在但條目漏寫）→ 在「本機影片」行後面補
   `- 燒字幕影片：<路徑>`，產出機自己的 KB 用本機路徑（publish 打包時會改成 UNC 點播）。

用法：
    python -X utf8 backfill_burn.py --dry-run          # 只列出會做什麼
    python -X utf8 backfill_burn.py                    # 實際燒＋回寫條目
    python -X utf8 backfill_burn.py --subtree "20VTA 頻道"
    python -X utf8 backfill_burn.py --file "2026-11-09"   # 檔名子字串過濾

冪等：已燒且有寫行的條目會跳過；重跑安全。
"""
import argparse
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).parent))

import config  # noqa: E402
from channel_watcher import burn_subtitles  # noqa: E402

KB_ROOT = config.PROJECT_ROOT / "knowledge-base"
EXCLUDE_DIRS = {"_harvest_conflicts", "_harvest_overwritten", "_archive_no_transcript"}

LOCAL_LINE = re.compile(r"^([ \t]*-[ \t]*)本機影片：(\S.*?)(\r?\n|$)", re.M)
BURNED_LINE = re.compile(r"^[ \t]*-[ \t]*燒字幕影片：", re.M)


def iter_entries(subtree=None, name_filter=None):
    """走訪 KB 的 .md 條目（略過衝突／封存目錄）。"""
    root = KB_ROOT / subtree if subtree else KB_ROOT
    if not root.exists():
        print(f"[ERR] 找不到目錄：{root}")
        return
    for md in sorted(root.rglob("*.md")):
        if any(part in EXCLUDE_DIRS for part in md.parts):
            continue
        if name_filter and name_filter not in md.stem:
            continue
        yield md


def plan_for(md_path):
    """回傳 (video_path, burned_path, action) — action: 'burn'/'add-line'/'done'/原因
    只讀檔頭 4KB（影片資訊區塊一定在最前面；全檔讀 3140 個條目要 30 秒以上）。"""
    with open(md_path, "rb") as f:
        head = f.read(4096).decode("utf-8", errors="replace")
    m = LOCAL_LINE.search(head)
    if not m:
        return None, None, "skip-no-video-line"
    if BURNED_LINE.search(head):
        return None, None, "done-has-burned-line"
    video = Path(m.group(2).strip())
    burned = video.with_name(video.stem + "_字幕.mp4")
    if not video.exists():
        return video, burned, "skip-video-not-local"
    if burned.exists():
        return video, burned, "add-line"
    srt = md_path.with_suffix(".srt")
    if not srt.exists():
        return video, burned, "skip-no-srt"
    return video, burned, "burn"


def add_burned_line(md_path, burned_path):
    """在「本機影片」行後面插入「燒字幕影片」行（保留原換行格式）。"""
    data = md_path.read_bytes().decode("utf-8", errors="replace")
    m = LOCAL_LINE.search(data)
    if not m or BURNED_LINE.search(data):
        return False
    nl = m.group(3) or "\n"
    new_line = f"{m.group(1)}燒字幕影片：{burned_path}{nl}"
    data = data[:m.end()] + new_line + data[m.end():]
    md_path.write_text(data, encoding="utf-8", newline="")
    return True


def main():
    ap = argparse.ArgumentParser(description="回補燒字幕（下載了但沒燒的影片）")
    ap.add_argument("--dry-run", action="store_true", help="只列出會做什麼，不燒不寫")
    ap.add_argument("--subtree", default="", help="只掃這個 KB 子目錄")
    ap.add_argument("--file", default="", help="條目檔名子字串過濾")
    ap.add_argument("--force-line", action="store_true",
                    help="條目已有燒字幕影片行也重新檢查/補寫（幾乎不用）")
    args = ap.parse_args()

    print(f"機器 {config.MACHINE}｜KB {KB_ROOT}")
    candidates = []
    not_local = []
    for md in iter_entries(args.subtree, args.file):
        video, burned, action = plan_for(md)
        if action == "burn":
            candidates.append((md, video, burned))
        elif action == "add-line":
            candidates.append((md, None, burned))
        elif action == "skip-video-not-local":
            not_local.append((md, video))
        # done/skip-no-video-line/skip-no-srt → 安靜略過（dry-run 才顯示）

    if not candidates and not not_local:
        print("沒有待補燒的條目（全部已燒或無影片）。")
        return 0

    for md, video, burned in candidates:
        if video is None:
            print(f"  [補行] {md.name}（_字幕.mp4 已存在，條目漏寫）")
        else:
            print(f"  [燒]   {md.name}\n         {video.name} → {burned.name}")
    for md, video in not_local:
        print(f"  [別台] {md.name}（影片不在本機：{video}）→ 到影片所在機器跑本工具")

    if args.dry_run:
        print(f"\n[DRY] 共 {len(candidates)} 筆可處理、{len(not_local)} 筆在別台；未實際執行。")
        return 0

    ok, fail = 0, 0
    for md, video, burned in candidates:
        try:
            if video is not None:
                print(f"\n▶ 燒字幕：{burned.name}")
                if not burn_subtitles(str(video), str(md.with_suffix('.srt')), str(burned)):
                    fail += 1
                    print(f"  ❌ 燒失敗：{md.name}")
                    continue
            if add_burned_line(md, burned):
                ok += 1
                print(f"  ✅ {md.name}（已補「燒字幕影片」行）")
            else:
                fail += 1
                print(f"  ❌ 回寫條目失敗：{md.name}")
        except Exception as e:
            fail += 1
            print(f"  ❌ {md.name}: {e}")

    print(f"\n完成：成功 {ok}、失敗 {fail}。")
    if ok and config.MACHINE != "notebook":
        print("提示：條目更新後 publish_outbox 會自動重包（fingerprint 已變）。")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
