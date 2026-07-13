#!/usr/bin/env python3
"""
@sensebar 自動更新腳本
- 偵測新影片
- 優先下載 YouTube 字幕
- 無字幕時下載音訊用 Whisper 辨識
- 自動清理暫存檔
- 同步到 knowledge-base
"""

import os
import sys
import re
import json
import shutil
import subprocess
import yt_dlp
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

BASE = Path(__file__).parent
CLIPPING = BASE / "Clipping"
KB = BASE / "knowledge-base" / "youtube-clips"
WORKING = BASE / "working"
LOG_DIR = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 設定
CHANNEL_URL = "https://www.youtube.com/@sensebar"
KEYWORDS = ["claude", "codex", "antigravity", "opencode", "agent", "googlea"]
SUBTITLE_LANGS = ["zh-Hant", "zh-TW", "zh", "zh-Hans", "en"]

def log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}")

def safe_filename(name):
    """移除 Windows 非法字元"""
    illegal = r'[\\/:*?"<>|]'
    return re.sub(illegal, '_', name)

def notify(title, message, url=None):
    """Windows 桌面通知（使用 tkinter 彈出視窗）"""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        messagebox.showinfo(title, message, parent=root)
        root.destroy()
    except Exception as e:
        log(f"通知失敗: {e}")

def scan_channel():
    """掃描頻道取得所有影片"""
    log("掃描 @sensebar 頻道...")
    all_entries = []
    
    url = f"{CHANNEL_URL}/videos"
    ydl_opts = {'extract_flat': True, 'skip_download': True, 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        entries = info.get('entries', [])
        all_entries.extend(entries)
        log(f"  videos: {len(entries)} 支")
    except Exception as e:
        log(f"  videos 失敗: {e}")
    
    # 去重
    seen = set()
    unique = []
    for e in all_entries:
        vid = e.get('id', '')
        if vid and vid not in seen:
            seen.add(vid)
            unique.append(e)
    
    log(f"去重後共 {len(unique)} 支影片")
    return unique

def filter_ai_videos(entries):
    """篩選 AI 相關影片"""
    matches = []
    for entry in entries:
        title = entry.get('title', '').lower()
        if any(kw in title for kw in KEYWORDS):
            matches.append(entry)
    log(f"AI 相關: {len(matches)} 支")
    return matches

def get_existing_videos():
    """取得已處理的影片 ID（從 Clipping 目錄）"""
    existing = set()
    for md in CLIPPING.glob("*.md"):
        text = md.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'youtube\.com/watch\?v=([A-Za-z0-9_-]{11})', text)
        if m:
            existing.add(m.group(1))
    log(f"已處理: {len(existing)} 支")
    return existing

def try_download_youtube_sub(video_id):
    """嘗試下載 YouTube 字幕"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    temp_dir = WORKING / "yt-subs-temp"
    temp_dir.mkdir(exist_ok=True)
    
    out_template = str(temp_dir / f"{video_id}_%(lang)s.%(ext)s")
    
    cmd = [
        "yt-dlp",
        "--write-auto-sub",
        "--write-sub",
        "--sub-lang", ",".join(SUBTITLE_LANGS),
        "--sub-format", "srt",
        "--skip-download",
        "-o", out_template,
        "--no-overwrites",
        "--ignore-errors",
        url
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        # 找到下載的 SRT
        for srt in temp_dir.glob(f"{video_id}_*.srt"):
            return srt
    except Exception as e:
        log(f"  YouTube 字幕下載失敗: {e}")
    
    return None

def download_audio(video_id):
    """下載音訊（比影片小10倍）"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    temp_dir = WORKING / video_id
    temp_dir.mkdir(exist_ok=True)
    
    audio_path = temp_dir / "audio.mp3"
    
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "5",
        "-o", str(audio_path),
        "--no-playlist",
        url
    ]
    
    try:
        log("  下載音訊...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        # 找到下載的音訊
        for f in temp_dir.glob("audio.*"):
            if f.suffix in ['.mp3', '.m4a', '.webm', '.opus']:
                return f
    except Exception as e:
        log(f"  音訊下載失敗: {e}")
    
    return None

def transcribe_with_whisper(audio_path, video_id):
    """用 Whisper 辨識字幕"""
    temp_dir = WORKING / video_id
    
    # 先用 smart_cut 去靜音
    trimmed = temp_dir / "trimmed.mp4"
    try:
        log("  去靜音...")
        cmd = [
            sys.executable,
            str(BASE / ".opencode" / "skills" / "smart-cut" / "scripts" / "smart_cut.py"),
            str(audio_path),
            "--out", str(trimmed)
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception as e:
        log(f"  去靜音失敗: {e}")
        trimmed = audio_path
    
    # 用 Groq Whisper 辨識
    raw_json = temp_dir / "raw.json"
    try:
        log("  Whisper 辨識...")
        cmd = [
            sys.executable,
            str(BASE / ".opencode" / "skills" / "audio-to-srt" / "scripts" / "transcribe_groq.py"),
            str(trimmed),
            "--out", str(raw_json)
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except Exception as e:
        log(f"  Whisper 辨識失敗: {e}")
        return None
    
    # 重新分段
    reseg_srt = temp_dir / "resegmented.srt"
    try:
        log("  重新分段...")
        cmd = [
            sys.executable,
            str(BASE / ".opencode" / "skills" / "audio-to-srt" / "scripts" / "resegment.py"),
            str(raw_json),
            "--out", str(reseg_srt),
            "--audio", str(trimmed)
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception as e:
        log(f"  重新分段失敗: {e}")
        return None
    
    # 術語校正
    corrected_srt = temp_dir / "corrected.srt"
    try:
        log("  術語校正...")
        cmd = [
            sys.executable,
            str(BASE / ".opencode" / "skills" / "audio-to-srt" / "scripts" / "apply_vocab.py"),
            str(reseg_srt),
            "--out", str(corrected_srt)
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        log(f"  術語校正失敗: {e}")
        corrected_srt = reseg_srt
    
    if corrected_srt.exists():
        return corrected_srt
    
    return None

def create_clippling_md(video_id, title, srt_path):
    """建立 Clipping MD 檔案"""
    md_path = CLIPPING / f"{safe_filename(title)}.md"
    
    # 從 SRT 提取純文字
    srt_content = srt_path.read_text(encoding="utf-8", errors="replace")
    lines = srt_content.strip().split("\n")
    text_lines = []
    for line in lines:
        line = line.strip()
        if not line or re.match(r'^\d+$', line) or re.match(r'\d{2}:\d{2}:\d{2}', line):
            continue
        text_lines.append(line)
    
    transcript = "\n".join(text_lines)
    
    md_content = f"""# {title}

- 影片網址: [YouTube](https://www.youtube.com/watch?v={video_id})

---

{transcript}
"""
    
    md_path.write_text(md_content, encoding="utf-8")
    log(f"  建立 MD: {md_path.name}")
    return md_path

def cleanup_temp(video_id):
    """清理暫存檔"""
    temp_dir = WORKING / video_id
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
        log(f"  清理: {temp_dir.name}")
    
    # 清理 yt-subs-temp 中的該影片檔案
    yt_temp = WORKING / "yt-subs-temp"
    if yt_temp.exists():
        for f in yt_temp.glob(f"{video_id}_*"):
            f.unlink()

def sync_to_kb():
    """同步到 knowledge-base"""
    log("同步到 knowledge-base...")
    
    KB.mkdir(parents=True, exist_ok=True)
    
    # 清除舊的 SRT
    for f in KB.glob("*.srt"):
        f.unlink()
    
    # 複製新的 SRT
    copied = 0
    for srt in CLIPPING.glob("*.srt"):
        shutil.copy2(srt, KB / srt.name)
        copied += 1
    
    log(f"同步 {copied} 個 SRT")

def main():
    log("=" * 50)
    log("@sensebar 自動更新開始")
    log("=" * 50)
    
    # 1. 掃描頻道
    entries = scan_channel()
    ai_videos = filter_ai_videos(entries)
    
    # 2. 取得已處理的影片
    existing = get_existing_videos()
    
    # 3. 找出新影片
    new_videos = []
    for entry in ai_videos:
        vid = entry.get('id', '')
        if vid not in existing:
            new_videos.append(entry)
    
    log(f"新影片: {len(new_videos)} 支")
    
    if not new_videos:
        log("沒有新影片，結束")
        return
    
    # 通知有新影片
    notify(
        f"@sensebar 有 {len(new_videos)} 支新影片",
        "開始自動處理字幕...",
    )
    
    # 4. 處理新影片
    success = 0
    fail = 0
    
    for i, entry in enumerate(new_videos, 1):
        vid = entry.get('id', '')
        title = entry.get('title', vid)
        
        log(f"\n[{i}/{len(new_videos)}] {title}")
        log(f"  Video ID: {vid}")
        
        try:
            # 嘗試下載 YouTube 字幕
            srt_path = try_download_youtube_sub(vid)
            
            if srt_path:
                log(f"  使用 YouTube 字幕: {srt_path.name}")
                # 複製到 Clipping
                target_srt = CLIPPING / f"{safe_filename(title)}.srt"
                shutil.copy2(srt_path, target_srt)
                # 建立 MD
                create_clippling_md(vid, title, srt_path)
                # 清理
                srt_path.unlink()
                success += 1
            else:
                log("  無 YouTube 字幕，嘗試 Whisper...")
                # 下載音訊
                audio_path = download_audio(vid)
                if audio_path:
                    # Whisper 辨識
                    srt_path = transcribe_with_whisper(audio_path, vid)
                    if srt_path:
                        # 複製到 Clipping
                        target_srt = CLIPPING / f"{safe_filename(title)}.srt"
                        shutil.copy2(srt_path, target_srt)
                        # 建立 MD
                        create_clippling_md(vid, title, srt_path)
                        success += 1
                    else:
                        log("  Whisper 辨識失敗")
                        fail += 1
                else:
                    log("  音訊下載失敗")
                    fail += 1
                
                # 清理暫存
                cleanup_temp(vid)
        
        except Exception as e:
            log(f"  錯誤: {e}")
            fail += 1
            cleanup_temp(vid)
    
    # 5. 同步到 knowledge-base
    sync_to_kb()
    
    # 6. 通知完成
    if success > 0:
        # 取得第一支新影片的 URL 用於通知
        first_vid = new_videos[0].get('id', '')
        first_url = f"https://www.youtube.com/watch?v={first_vid}" if first_vid else None
        
        notify(
            f"@sensebar 更新完成",
            f"新增 {success} 支影片字幕已同步到知識庫",
            url=first_url
        )
    
    # 7. 產生報告
    log("\n" + "=" * 50)
    log("更新完成")
    log(f"  成功: {success}")
    log(f"  失敗: {fail}")
    log("=" * 50)
    
    # 寫入日誌
    log_file = LOG_DIR / f"update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(f"更新時間: {datetime.now()}\n")
        f.write(f"新影片: {len(new_videos)}\n")
        f.write(f"成功: {success}\n")
        f.write(f"失敗: {fail}\n")

if __name__ == "__main__":
    main()
