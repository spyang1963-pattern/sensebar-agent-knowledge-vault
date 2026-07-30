#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
channel_watcher.py — YouTube 頻道自動監控與收成
================================================
鎖定頻道/播放清單，有新影片時自動處理：

  有字幕 → 下載字幕 → 建立 KB 逐字稿 + 影片連結
  無字幕 → 下載影片 → Pipeline 轉錄 → 燒字幕 → 收成 KB

用法:
  python channel_watcher.py --once       # 立即掃描一次
  python channel_watcher.py --watch      # 持續監控（每 3600 秒）
  python channel_watcher.py --status     # 顯示監控狀態
  python channel_watcher.py --add URL    # 新增頻道（待實作）

設定：config.yaml → watched_channels
狀態：shared/watched_channels_state.json
"""
import os, sys, re, json, shutil, subprocess, time, argparse
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    log, PROJECT_ROOT, SHARED_ROOT,
    load_channel_state, save_channel_state, get_watched_channels,
)

# ── 常數 ──
WORKING = PROJECT_ROOT / "working"
KB_ROOT = PROJECT_ROOT / "knowledge-base"
YT_VIDEOS = Path(r"D:\YouTube_Videos")
YT_VIDEOS.mkdir(parents=True, exist_ok=True)

# ── 工具函數 ──

def safe_filename(name):
    illegal = r'[\\/:*?"<>|]'
    return re.sub(illegal, "_", name)

def srt_to_transcript(srt_path):
    """從 .srt 提取純文字逐字稿"""
    text = srt_path.read_text(encoding="utf-8", errors="replace")
    lines = text.strip().split("\n")
    out = []
    for line in lines:
        line = line.strip()
        if not line or re.match(r'^\d+$', line) or re.match(r'\d{2}:\d{2}:\d{2}', line):
            continue
        out.append(line)
    return "\n".join(out)

def get_playlist_entries(playlist_id):
    """用 yt-dlp 取得播放清單所有影片"""
    url = f"https://www.youtube.com/playlist?list={playlist_id}"
    try:
        import yt_dlp
    except ImportError:
        log("[ERR] 需要 yt-dlp 套件：pip install yt-dlp")
        return []
    ydl_opts = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        entries = info.get("entries", [])
        log(f"  [清單] {playlist_id}: {len(entries)} 支")
        return entries
    except Exception as e:
        log(f"  [清單] 失敗: {e}")
        return []

def download_yt_sub(video_id, langs, temp_dir):
    """下載 YouTube 自動字幕"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    out_tpl = str(temp_dir / f"{video_id}_%(lang)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--write-auto-sub", "--write-sub",
        "--sub-lang", ",".join(langs),
        "--sub-format", "srt",
        "--skip-download",
        "-o", out_tpl,
        "--no-overwrites", "--ignore-errors",
        url,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        for f in temp_dir.glob(f"{video_id}_*.srt"):
            return f
    except Exception:
        pass
    return None

def download_yt_video(video_id, title):
    """下載完整影片（較低品質以節省時間）"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    fname = safe_filename(title)
    out_path = YT_VIDEOS / f"{fname}.mp4"

    if out_path.exists():
        log(f"  [下載] 已存在：{out_path.name}")
        return out_path

    cmd = [
        "yt-dlp",
        "-f", "worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst[ext=mp4]/worst",
        "-o", str(out_path),
        "--no-playlist", "--ignore-errors",
        url,
    ]
    try:
        log("  [下載] 下載影片中（較低畫質）...")
        subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if out_path.exists():
            log(f"  [下載] 完成：{out_path.name}")
            return out_path
    except subprocess.TimeoutExpired:
        log("  [下載] 逾時")
    except Exception as e:
        log(f"  [下載] 錯誤: {e}")

    # 嘗試用普通品質
    cmd[3] = "best[ext=mp4]/best"
    try:
        log("  [下載] 重試（最佳品質）...")
        subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if out_path.exists():
            return out_path
    except Exception:
        pass
    return None

def run_pipeline(video_path, title, video_id):
    """執行 run_pipeline.py 完整流程（壓縮→轉錄→收成）"""
    log("  [Pipeline] 開始...")
    cmd = [
        sys.executable, "-X", "utf8",
        str(PROJECT_ROOT / "run_pipeline.py"),
        str(video_path),
        "--title", f"{title} [{video_id}]",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            log(f"  [Pipeline] 失敗（rc={result.returncode}）")
            log(result.stderr[-500:] if result.stderr else "")
            return None
        log("  [Pipeline] 成功")
        # pipeline output 在 output/<slug>/
        slug = safe_filename(title)
        output_dir = PROJECT_ROOT / "output" / slug
        if output_dir.exists():
            return output_dir
    except subprocess.TimeoutExpired:
        log("  [Pipeline] 逾時（1800s）")
    except Exception as e:
        log(f"  [Pipeline] 異常: {e}")
    return None

def burn_subtitles(video_path, srt_path, output_path, font_size=24, margin_v=30, position="bottom"):
    """用 VLC 燒錄字幕"""
    if not os.path.exists(srt_path):
        log("  [燒字幕] 找不到字幕檔，跳過")
        return False

    vlc = r"C:\Program Files\VideoLAN\VLC\vlc.exe"
    if not os.path.exists(vlc):
        log("  [燒字幕] 找不到 VLC")
        return False

    # 位置對應
    pos_map = {
        "top-left": 4, "top-center": 5, "top-right": 6,
        "center-left": 7, "center": 8, "center-right": 9,
        "bottom-left": 1, "bottom": 2, "bottom-right": 3,
    }
    alignment = pos_map.get(position, 2)

    cmd = [
        vlc, str(video_path),
        f"--sub-file={srt_path}",
        f"--sub-text-scale={font_size * 10}",
        f"--sub-margin={margin_v}",
        f"--sub-alignment={alignment}",
        "--sout", (
            f"#transcode{{soverlay}}:"
            f"std{{access=file,mux=mp4,dst={output_path}}}"
        ),
        "--no-sout-all", "--sout-keep", "--stop-time=5",
        "vlk://quit",
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception:
        log("  [燒字幕] 失敗，但主流程繼續")
    return os.path.exists(output_path)


def create_kb_entry(video_id, title, transcript, srt_path, video_path, kb_dir):
    """建立知識庫條目
    - kb_dir/kb_dir.md：逐字稿 + 連結
    - kb_dir/kb_dir.srt：字幕檔
    """
    safe = safe_filename(title)
    md_path = kb_dir / f"{safe}.md"
    srt_dst = kb_dir / f"{safe}.srt"
    link_dst = kb_dir / f"{safe}.link.txt"

    kb_dir.mkdir(parents=True, exist_ok=True)

    # .md：逐字稿 + 連結
    md_content = f"""# {title}

## 影片資訊
- YouTube 連結：https://www.youtube.com/watch?v={video_id}
"""
    if video_path and os.path.exists(video_path):
        md_content += f"- 本機影片：{video_path}\n"
    md_content += f"""
---

## 逐字稿

{transcript}
"""
    md_path.write_text(md_content, encoding="utf-8")
    log(f"  [KB] 建立 {md_path.name}")

    # .srt：字幕檔
    if srt_path and os.path.exists(srt_path):
        shutil.copy2(srt_path, srt_dst)
        log(f"  [KB] 複製 {srt_dst.name}")

    # .link.txt：純連結檔
    link_dst.write_text(
        f"https://www.youtube.com/watch?v={video_id}\n",
        encoding="utf-8",
    )

    return md_path


# ── 核心邏輯 ──

def process_has_subs(video_id, title, langs, kb_dir):
    """有字幕路徑：下載字幕 → KB 條目"""
    temp_dir = WORKING / "channel-watcher-temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    srt_path = download_yt_sub(video_id, langs, temp_dir)
    if not srt_path:
        return False

    log(f"  [字幕] YouTube 字幕：{srt_path.name}")
    transcript = srt_to_transcript(srt_path)
    create_kb_entry(video_id, title, transcript, srt_path, None, kb_dir)

    # 清理
    srt_path.unlink()
    return True


def process_no_subs(video_id, title, langs, kb_dir):
    """無字幕路徑：下載影片 → Pipeline → 燒字幕 → KB 條目"""
    log("  [轉錄] 無 YouTube 字幕，啟動離線 Pipeline...")

    video_path = download_yt_video(video_id, title)
    if not video_path:
        log("  [轉錄] 影片下載失敗")
        return False

    output_dir = run_pipeline(video_path, title, video_id)
    if not output_dir:
        log("  [轉錄] Pipeline 失敗")
        return False

    # 找到產出的 SRT
    srt_src = output_dir / "字幕.srt"
    if not srt_src.exists():
        log("  [轉錄] 找不到 Pipeline 產出的 SRT")
        return False

    transcript = srt_to_transcript(srt_src)
    create_kb_entry(video_id, title, transcript, srt_src, video_path, kb_dir)

    # 燒字幕
    burned_path = output_dir / f"{safe_filename(title)}_burned.mp4"
    burn_subtitles(video_path, srt_src, burned_path)

    return True


def scan_playlist(playlist_id, kb_dir, langs, state):
    """掃描單一播放清單，處理新影片"""
    log(f"[掃描] 清單：{playlist_id}")
    log(f"  KB 目錄：{kb_dir}")

    entries = get_playlist_entries(playlist_id)
    if not entries:
        return 0

    # 找出新影片
    last_id = state.get(playlist_id, {}).get("last_video_id", "")
    last_check = state.get(playlist_id, {}).get("last_check", "")

    new_entries = []
    found_last = False
    for entry in entries:
        vid = entry.get("id", "")
        if not vid:
            continue
        if vid == last_id:
            found_last = True
            break
        new_entries.append(entry)

    # 如果沒找到 last_id（第一次掃描或全部都是新的）
    if not found_last and last_id:
        # 只取最新的 5 支（避免一次處理太多）
        new_entries = entries[:5]
        log(f"  [新片] 上次 ID ({last_id}) 未找到，取最新 {len(new_entries)} 支")
    elif new_entries:
        new_entries.reverse()
        log(f"  [新片] {len(new_entries)} 支新影片")

    if not new_entries:
        # 更新 check 時間即可
        state[playlist_id] = {
            "last_video_id": entries[0].get("id", ""),
            "last_check": datetime.now().isoformat(),
        }
        return 0

    # 處理新影片（可一次處理多支）
    processed = 0
    for entry in new_entries:
        vid = entry.get("id", "")
        title = entry.get("title", vid)
        log(f"\n  ── {title}")
        log(f"      https://www.youtube.com/watch?v={vid}")

        # 嘗試有字幕路徑
        if process_has_subs(vid, title, langs, kb_dir):
            processed += 1
            log(f"  ✅ 有字幕處理完成")
            continue

        # 無字幕 → 離線轉錄
        if process_no_subs(vid, title, langs, kb_dir):
            processed += 1
            log(f"  ✅ 離線轉錄完成")
        else:
            log(f"  ❌ 處理失敗")

    # 更新狀態
    state[playlist_id] = {
        "last_video_id": entries[0].get("id", ""),
        "last_check": datetime.now().isoformat(),
        "last_process_time": datetime.now().isoformat(),
    }

    return processed


def scan_all_channels():
    """掃描所有設定中的頻道與播放清單"""
    state = load_channel_state()
    channels = get_watched_channels()
    total = 0

    if not channels:
        log("[WARN] config.yaml 中未設定 watched_channels")
        return 0

    for ch in channels:
        name = ch.get("name", "未知頻道")
        langs = ch.get("subtitle_langs", ["zh-Hant", "zh-TW", "zh", "en"])

        log(f"\n{'='*50}")
        log(f"[頻道] {name}")
        log(f"  URL: {ch.get('channel_url', 'N/A')}")

        for pl in ch.get("playlists", []):
            pl_id = pl.get("id", "")
            kb_rel = pl.get("kb_dir", "")
            kb_dir = KB_ROOT / kb_rel

            try:
                n = scan_playlist(pl_id, kb_dir, langs, state)
                total += n
            except Exception as e:
                log(f"  [錯誤] {pl_id}: {e}")

        # 家目錄下的 .link.txt 檔案連結也可以作為快捷方式
        ch_links = KB_ROOT / "youtube-clips"
        ch_links.mkdir(parents=True, exist_ok=True)

    save_channel_state(state)
    return total


def show_status():
    """顯示監控狀態"""
    state = load_channel_state()
    channels = get_watched_channels()

    print(f"\n{'='*50}")
    print(f"  頻道監控狀態")
    print(f"{'='*50}")

    for ch in channels:
        name = ch.get("name", "未知頻道")
        print(f"\n📺 {name}")
        print(f"   URL: {ch.get('channel_url', 'N/A')}")
        for pl in ch.get("playlists", []):
            pl_id = pl.get("id", "")
            kb_rel = pl.get("kb_dir", "")
            s = state.get(pl_id, {})
            last_id = s.get("last_video_id", "—")
            last_check = s.get("last_check", "未掃描")
            last_process = s.get("last_process_time", "—")
            print(f"   清單 {pl_id[:8]}... → {kb_rel}")
            print(f"     最近 ID: {last_id}")
            print(f"     上次掃描: {last_check}")
            print(f"     上次處理: {last_process}")

    print(f"\n  設定頻道數: {len(channels)}")
    print(f"  狀態檔案: {SHARED_ROOT}\\watched_channels_state.json")
    print()


# ── CLI ──

def main():
    ap = argparse.ArgumentParser(description="YouTube 頻道自動監控與收成")
    ap.add_argument("--once", action="store_true", help="立即掃描一次")
    ap.add_argument("--watch", action="store_true", help="持續監控模式")
    ap.add_argument("--status", action="store_true", help="顯示監控狀態")
    ap.add_argument("--interval", type=int, default=3600, help="掃描間隔秒數（預設 3600）")
    args = ap.parse_args()

    if args.status:
        show_status()
        return

    if args.watch:
        log(f"啟動持續監控模式，間隔 {args.interval}s")
        log("按 Ctrl+C 停止")
        while True:
            n = scan_all_channels()
            log(f"本輪處理 {n} 支新影片")
            if n > 0:
                log(f"等待 {args.interval}s 後再次掃描...")
            else:
                log(f"無新影片，{args.interval}s 後再檢查")
            try:
                time.sleep(args.interval)
            except KeyboardInterrupt:
                log("使用者中斷")
                break
        return

    # --once 或無參數預設為 --once
    n = scan_all_channels()
    log(f"\n處理完成，共 {n} 支新影片")


if __name__ == "__main__":
    main()
