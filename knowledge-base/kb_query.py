#!/usr/bin/env python3
"""
知識庫查詢工具 — 傳統K線型態（含影片時間碼 + VLC 一鍵跳轉）
用法：
  python kb_query.py "紅黑紅"
  python kb_query.py "停損" --video "影片路徑"
  python kb_query.py --list
  python kb_query.py --topic 01
"""
import argparse
import re
import subprocess
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

KB_DIR = Path(__file__).parent / "traditional-kline"
VLC_PATH = r"C:\Program Files\VideoLAN\VLC\vlc.exe"


def parse_srt(srt_path: Path) -> list[dict]:
    """解析 SRT 檔，回傳 [{index, start, end, start_sec, text}]。"""
    content = srt_path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\n+", content.strip())
    entries = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        time_match = re.match(
            r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})",
            lines[1],
        )
        if not time_match:
            continue
        g = time_match.groups()
        start_sec = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000
        end_sec = int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000
        text = " ".join(lines[2:]).strip()
        entries.append({
            "index": int(lines[0]),
            "start": lines[1].split("-->")[0].strip(),
            "end": lines[1].split("-->")[1].strip(),
            "start_sec": start_sec,
            "end_sec": end_sec,
            "text": text,
        })
    return entries


def fmt_time(seconds: float) -> str:
    """秒數格式化為 HH:MM:SS。"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def find_timestamp(keyword: str, entries: list[dict]) -> list[dict]:
    """在 SRT 中搜尋關鍵字，回傳匹配的時間範圍（合併相鄰段落）。"""
    matches = []
    for e in entries:
        if keyword.lower() in e["text"].lower():
            matches.append(e)
    if not matches:
        return []
    # 合併相鄰段落（間隔 < 3秒）
    merged = [matches[0]]
    for m in matches[1:]:
        prev = merged[-1]
        if m["start_sec"] - prev["end_sec"] < 3:
            merged[-1] = {
                "start": prev["start"],
                "end": m["end"],
                "start_sec": prev["start_sec"],
                "end_sec": m["end_sec"],
                "text": prev["text"] + " " + m["text"],
            }
        else:
            merged.append(m)
    return merged


def open_in_vlc(video_path: Path, start_sec: float):
    """用 VLC 開啟影片，跳到指定時間。按空白鍵暫停。"""
    if not Path(VLC_PATH).exists():
        print(f"[ERR] VLC 未安裝：{VLC_PATH}")
        return
    cmd = [
        VLC_PATH,
        str(video_path),
        f"--start-time={int(start_sec)}",
        "--no-video-title-show",
    ]
    print(f"[CMD] {' '.join(cmd)}")
    subprocess.Popen(cmd)
    print("[INFO] 影片播放中，按空白鍵暫停")


def list_topics():
    for f in sorted(KB_DIR.glob("*.md")):
        if f.name == "README.md":
            continue
        first_line = f.read_text(encoding="utf-8").split("\n")[0].replace("# ", "")
        print(f"  {f.stem}  {first_line}")


def show_topic(topic_id: str):
    matches = list(KB_DIR.glob(f"{topic_id}*.md"))
    if not matches:
        print(f"[ERR] 找不到主題：{topic_id}")
        return
    for f in matches:
        print(f.read_text(encoding="utf-8"))


def search(keyword: str, srt_entries: list[dict] | None = None, video_path: Path | None = None):
    """搜尋關鍵字，顯示內容 + 時間碼 + VLC 跳轉。"""
    results = []
    seen_contexts = set()
    for f in sorted(KB_DIR.glob("*.md")):
        if f.name == "README.md":
            continue
        content = f.read_text(encoding="utf-8")
        lines = content.split("\n")
        topic_title = lines[0].replace("# ", "")
        for i, line in enumerate(lines):
            if keyword.lower() in line.lower():
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                context = "\n".join(lines[start:end])
                ctx_key = (f.name, context.strip())
                if ctx_key not in seen_contexts:
                    seen_contexts.add(ctx_key)
                    results.append({
                        "file": f.name,
                        "topic": topic_title,
                        "context": context,
                    })

    if not results:
        print(f"找不到「{keyword}」相關內容。")
        return

    print(f"=== 搜尋「{keyword}」找到 {len(results)} 筆 ===\n")
    seen_topics = set()
    for r in results:
        if r["topic"] not in seen_topics:
            print(f"--- {r['topic']} ({r['file']}) ---")
            seen_topics.add(r["topic"])
        print(r["context"])
        print()

    # 顯示時間碼
    if srt_entries:
        ts = find_timestamp(keyword, srt_entries)
        if ts:
            print(f"影片位置：")
            for t in ts:
                time_range = f"{t['start']} ~ {t['end']}"
                print(f"  {time_range}  ({t['text'][:50]}...)")
            print()
            if video_path:
                first_start = ts[0]["start_sec"]
                print(f"想看影片？執行：python kb_query.py \"{keyword}\" --srt \"...\" --video \"...\" --open")
        else:
            print("(SRT 中未找到對應時間碼)\n")


def main():
    ap = argparse.ArgumentParser(description="傳統K線知識庫查詢工具")
    ap.add_argument("keyword", nargs="?", help="搜尋關鍵字")
    ap.add_argument("--list", action="store_true", help="列出所有主題")
    ap.add_argument("--topic", type=str, help="顯示特定主題（如 01, 02）")
    ap.add_argument("--srt", type=Path, default=None, help="SRT 字幕檔路徑")
    ap.add_argument("--video", type=Path, default=None, help="影片檔路徑")
    ap.add_argument("--open", action="store_true", help="用 VLC 開啟影片跳轉")
    args = ap.parse_args()

    if not KB_DIR.exists():
        print(f"[ERR] 知識庫目錄不存在：{KB_DIR}")
        sys.exit(1)

    if args.list:
        print("=== 傳統K線型態 知識庫主題 ===\n")
        list_topics()
        return

    if args.topic:
        show_topic(args.topic)
        return

    if not args.keyword:
        ap.print_help()
        return

    # 載入 SRT
    srt_entries = None
    if args.srt and args.srt.exists():
        srt_entries = parse_srt(args.srt)
        print(f"[INFO] 已載入 SRT：{len(srt_entries)} 段字幕\n")

    # 搜尋
    if args.open and args.video:
        # 直接開啟影片
        if srt_entries:
            ts = find_timestamp(args.keyword, srt_entries)
            if ts:
                open_in_vlc(args.video, ts[0]["start_sec"])
            else:
                print(f"SRT 中找不到「{args.keyword}」的時間碼")
        else:
            print("[ERR] 需要 --srt 參數才能跳轉")
    else:
        search(args.keyword, srt_entries, args.video)


if __name__ == "__main__":
    main()
