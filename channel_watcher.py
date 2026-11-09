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
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    log, PROJECT_ROOT, SHARED_ROOT, MACHINE,
    load_channel_state, save_channel_state, get_watched_channels,
    CHANNEL_STATE_FILE, load_task_status,
)
from watchdog import notify_line_and_email

# ── 常數 ──
WORKING = PROJECT_ROOT / "working"
KB_ROOT = PROJECT_ROOT / "knowledge-base"
YT_VIDEOS = Path(r"D:\YouTube_Videos")
YT_VIDEOS.mkdir(parents=True, exist_ok=True)
# 已知 video_id 種子（notebook KB 的 id 清單；產出機 KB 從零開始時補足去重能力）
KB_VIDEO_IDS_SEED = PROJECT_ROOT / "workspace-bundle" / "infra" / "bootstrap" / "kb_video_ids.txt"

# 最近一次掃描的詳細處理明細（供通知產生）
_last_scan_details = []

# ── 工具函數 ──

def safe_filename(name):
    illegal = r'[\\/:*?"<>|]'
    return re.sub(illegal, "_", name)

def kb_basename(title, date_prefix=None):
    """KB 檔名：有日期時以「YYYY-MM-DD_標題」為前綴，否則僅用標題。
    頻道/直播等有時間序的影片進入知識庫時，日期前綴可辨識資訊時點。"""
    safe = safe_filename(title)
    return f"{date_prefix}_{safe}" if date_prefix else safe

# 影片日期快取（避免同一支重複呼叫 yt-dlp）
_VIDEO_DATE_CACHE = {}

def get_video_date(video_id):
    """取得影片日期（Asia/Taipei）→ 'YYYY-MM-DD' 或 None。
    優先順序：release_date（首播/實際發布日）→ timestamp（直播/發布時點，換算台北時區）→ upload_date。
    2026-11-02 事故：首播影片的 timestamp 仍停在原本排定的 2026-10-26，但實際首播／發布日是
    release_date=2026-11-02，導致產出檔名前綴錯誤。因此 release_date 必須優先。
    """
    if video_id in _VIDEO_DATE_CACHE:
        return _VIDEO_DATE_CACHE[video_id]
    url = f"https://www.youtube.com/watch?v={video_id}"
    date = None
    try:
        r = subprocess.run(
            ["yt-dlp", "--no-update", "--skip-download", "--no-warnings",
             *yt_cookies_args(),
             "--print", "%(timestamp)s|%(release_date)s|%(upload_date)s", url],
            capture_output=True, text=False, timeout=120,
        )
        line = r.stdout.decode("utf-8", errors="replace").strip().splitlines()
        if line:
            parts = (line[0].split("|") + ["", "", ""])[:3]
            ts, rel, up = parts
            if rel and re.match(r"^\d{8}$", rel):
                date = f"{rel[:4]}-{rel[4:6]}-{rel[6:8]}"
            elif ts and ts not in ("NA", "None"):
                tw = datetime.fromtimestamp(int(ts), timezone(timedelta(hours=8)))
                date = tw.strftime("%Y-%m-%d")
            elif up and re.match(r"^\d{8}$", up):
                date = f"{up[:4]}-{up[4:6]}-{up[6:8]}"
        log(f"  [日期] {video_id} → {date}")
    except Exception as e:
        log(f"  [日期] 取得失敗 {video_id}: {e}")
    _VIDEO_DATE_CACHE[video_id] = date
    return date

_VIDEO_TITLE_CACHE = {}

def get_video_title(video_id):
    """取得影片標題。任務由播放清單展開時，偶有 title 空白／等於 video_id 的情況，
    會讓 KB 檔名變成 `zHCBKVqdaes.md`；收成前先用這個補回來。"""
    if video_id in _VIDEO_TITLE_CACHE:
        return _VIDEO_TITLE_CACHE[video_id]
    title = ""
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        r = subprocess.run(
            ["yt-dlp", "--no-update", "--skip-download", "--no-warnings",
             *yt_cookies_args(),
             "--print", "%(title)s", url],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
        if r.returncode == 0 and (r.stdout or "").strip():
            title = r.stdout.strip().splitlines()[0].strip()
        log(f"  [標題] {video_id} → {title[:50] or '（取不到）'}")
    except Exception as e:
        log(f"  [標題] 取得失敗 {video_id}: {e}")
    _VIDEO_TITLE_CACHE[video_id] = title
    return title


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

def get_playlist_entries(source):
    """用 yt-dlp 取得播放清單所有影片
    source: 可為 playlist_id 或直接 YouTube URL（含 youtube.com）
    """
    if "youtube.com" in source or "youtu.be" in source:
        url = source
        label = source[:50]
    else:
        url = f"https://www.youtube.com/playlist?list={source}"
        label = source
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
    ydl_opts.update(_ytdlp_cookiefile())
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        entries = info.get("entries", [])
        log(f"  [清單] {label}: {len(entries)} 支")
        return entries
    except Exception as e:
        log(f"  [清單] 失敗: {e}")
        return []

def expand_youtube_entries(url, limit=None):
    """把 YouTube 網址展開成影片清單（單一影片／播放清單／頻道皆可）。

    供 GUI「新增任務」與佇列建立逐支任務使用；只回傳 {id, title}，
    不做任何下載。抓不到或非影片項目（例如頻道首頁的播放清單分類）一律略過。

    limit: 最多回傳幾支（None=全部）
    """
    u = (url or "").strip()
    if not u:
        return []
    try:
        import yt_dlp
    except ImportError:
        log("[ERR] 需要 yt-dlp 套件：pip install yt-dlp")
        return []

    opts = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }
    if limit and limit > 0:
        opts["playlistend"] = limit
    opts.update(_ytdlp_cookiefile())
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(u, download=False)
    except Exception as e:
        log(f"  [展開] 失敗: {e}")
        return []

    if not info:
        return []

    out, seen = [], set()

    def _collect(item, depth=0):
        if not item or depth > 2:
            return
        # 頻道首頁可能回傳「播放清單」項目，往下一層取影片
        if item.get("_type") == "playlist" and item.get("entries"):
            for sub in item["entries"]:
                _collect(sub, depth + 1)
            return
        vid = item.get("id") or ""
        if not re.match(r"^[A-Za-z0-9_-]{11}$", vid) or vid in seen:
            return
        seen.add(vid)
        out.append({"id": vid, "title": item.get("title") or vid})

    entries = info.get("entries") or [info]
    for e in entries:
        _collect(e)

    if limit and limit > 0:
        out = out[:limit]
    log(f"  [展開] {u}: {len(out)} 支（cookies: {'有' if yt_cookies_args() else '無'}）")
    return out


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
        *yt_cookies_args(),
        url,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        for f in temp_dir.glob(f"{video_id}_*.srt"):
            return f
    except Exception:
        pass
    return None

# 下載格式：優先 1080p H.264 mp4（字幕燒錄與播放相容最佳），不超過 1080p
# 2026-11-06：篩選條件改用「寬與高都 <=長邊上限」，而不是只看 height。
# 直式 Shorts 是 1080x1920，用 height<=1080 會把 1080p 自己排除掉 → 只抓到 360p。
YT_DL_FORMAT = ("bestvideo[width<=1920][height<=1920][ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/"
                "bestvideo[width<=1920][height<=1920][ext=mp4]+bestaudio[ext=m4a]/"
                "best[ext=mp4]/best")
# 直播等長片用 720p（檔案較小、燒字幕快）：config 該來源設 format: "720"
YT_DL_FORMAT_720 = ("bestvideo[width<=1280][height<=1280][ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/"
                    "bestvideo[width<=1280][height<=1280][ext=mp4]+bestaudio[ext=m4a]/"
                    "best[ext=mp4]/best")
FORMAT_PRESETS = {"720": YT_DL_FORMAT_720, "1080": YT_DL_FORMAT}

# ── cookies（2026-11-06 事故：17 支「私人影片」全部 404 級失敗）──
# 私人／會員專屬／年齡限制的影片必須帶登入 cookies 才抓得到。做法刻意「有檔案才生效」：
#   D:\AI-Agent-Workspace\cookies.txt（Netscape 格式，用瀏覽器擴充匯出）
# 檔案不存在時完全不影響其他影片（指令一個字都不變）。
COOKIES_FILE = PROJECT_ROOT / "cookies.txt"


def yt_cookies_args():
    """有 cookies.txt 就回 ["--cookies", 路徑]，否則回空 list（可直接 * 展開進 cmd）。"""
    try:
        if COOKIES_FILE.is_file() and COOKIES_FILE.stat().st_size > 0:
            return ["--cookies", str(COOKIES_FILE)]
    except OSError:
        pass
    return []


def _ytdlp_cookiefile():
    """給 yt_dlp Python API 用的 cookiefile 選項（沒有檔案就回空 dict）。"""
    args = yt_cookies_args()
    return {"cookiefile": args[1]} if args else {}

# ── JS runtime（2026-11-06 事故）──
# yt-dlp 需要 deno／node／bun 才能解 YouTube 的 JS 挑戰；沒有 runtime 時
# 「抓 metadata、列格式」都正常，但真正下載影片資料一律 HTTP 403 Forbidden，
# 造成 PC1 上 66 支任務全部失敗、每支只花 14 秒。錯誤訊息必須說清楚。
_JS_RUNTIME_CHECKED = False
_LAST_FAIL = {"stage": "", "detail": ""}


def _note_fail(stage, detail):
    """記下最後一次失敗的階段與原始訊息（供 process_youtube_video 回報）。"""
    _LAST_FAIL["stage"] = stage
    _LAST_FAIL["detail"] = (detail or "").strip()


def ensure_js_runtime(warn_once=True):
    """確認 yt-dlp 找得到 JS runtime；必要時把常見安裝路徑補進 PATH。

    已安裝但 PATH 還沒生效（例如 GUI 在裝 deno 之前就開著）也能救回來。
    回傳找到的 runtime 路徑（找不到回 None）。
    """
    global _JS_RUNTIME_CHECKED
    for exe in ("deno", "node", "bun", "qjs"):
        found = shutil.which(exe)
        if found:
            _JS_RUNTIME_CHECKED = True
            return found

    # PATH 沒生效：把 deno／winget 的常見安裝位置補上
    cands = [
        Path.home() / ".deno" / "bin",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links",
        Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links",
    ]
    added = []
    for d in cands:
        try:
            if d.is_dir() and str(d) not in os.environ.get("PATH", ""):
                os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + str(d)
                added.append(str(d))
        except Exception:
            pass
    if added:
        for exe in ("deno", "node", "bun", "qjs"):
            found = shutil.which(exe)
            if found:
                log(f"  [環境] 已把 JS runtime 路徑補進 PATH：{found}")
                _JS_RUNTIME_CHECKED = True
                return found

    if warn_once and not _JS_RUNTIME_CHECKED:
        log("  ⚠ 找不到 JS runtime（deno／node／bun）：yt-dlp 下載 YouTube 影片會回 403 Forbidden")
        log("     修法：winget install --id DenoLand.Deno -e   （裝完要重開 GUI／worker）")
    _JS_RUNTIME_CHECKED = True
    return None


def yt_fail_hint(text):
    """把 yt-dlp 的 stderr 濃縮成一句人看得懂的原因（寫進任務 last_error）。"""
    m = (text or "").lower()
    if "no supported javascript runtime" in m:
        return "缺少 JS runtime（deno／node），yt-dlp 被 YouTube 403 擋下"
    if "403" in m and "forbidden" in m:
        # 2026-11-07 實測：同批 42 支都成功、只有 #236 一支 403，稍後重試即正常。
        # 403 有兩種來源，不要一律說成「缺 deno」害人查錯方向。
        return "YouTube 回 403（批次下載常見的暫時性封鎖，重試即可；或本機缺 JS runtime）"
    if "confirm your age" in m or "age-restricted" in m:
        return "年齡限制影片：需要 cookies.txt"
    if "sign in to confirm" in m or "not a bot" in m:
        return "YouTube 要求驗證（bot check）"
    if "requested format is not available" in m:
        return "指定的下載格式不存在"
    # 2026-11-06：私人／會員專屬要分開講，否則只會看到「影片不可用」而誤判成下載壞了
    if "members-only" in m or "members only" in m or "join this channel" in m:
        return "會員專屬影片：需要 cookies.txt，且該帳號要有訂閱"
    if "private video" in m or "this video is private" in m:
        return "私人影片：需要 cookies.txt（若原影片本來就不公開，cookies 也無解）"
    if "video unavailable" in m or "has been removed" in m:
        return "影片不可用（已刪除／地區限制）"
    if "429" in m or "too many requests" in m:
        return "YouTube 回 429（請求過多／被限流）"
    if "timed out" in m or "timeout" in m:
        return "逾時"
    return ""



def download_yt_video(video_id, title, format_spec=YT_DL_FORMAT, date_prefix=None):
    """下載完整影片（預設最高 1080p H.264，避免最差畫質字幕讀不清）
    date_prefix：有值時檔名以「YYYY-MM-DD_標題」為前綴。"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    fname = kb_basename(title, date_prefix)
    out_path = YT_VIDEOS / f"{fname}.mp4"

    if out_path.exists() and out_path.stat().st_size > 0:
        log(f"  [下載] 已存在：{out_path.name}")
        return out_path

    cmd = [
        "yt-dlp", "--no-update",
        "-f", format_spec,
        "--merge-output-format", "mp4",
        "--no-playlist", "--ignore-errors",
        *yt_cookies_args(),
        "-o", str(out_path),
        url,
    ]
    try:
        ensure_js_runtime()
        log("  [下載] 下載影片中（最高 1080p）...")
        result = subprocess.run(cmd, capture_output=True, text=False, timeout=1800)
        if out_path.exists() and out_path.stat().st_size > 0:
            log(f"  [下載] 完成：{out_path.name}")
            return out_path
        err = result.stderr[-800:].decode("utf-8", errors="replace") if result.stderr else ""
        log(f"  [下載] yt-dlp rc={result.returncode} {err[-300:]}")
        _note_fail("下載影片", err)
    except subprocess.TimeoutExpired:
        log("  [下載] 逾時")
        _note_fail("下載影片", "yt-dlp 逾時（1800s）")
    except Exception as e:
        log(f"  [下載] 錯誤: {e}")
        _note_fail("下載影片", f"{type(e).__name__}: {e}")

    # 找目前任一既有成功檔案當作驗證後再重試一次（排除已燒字幕檔 _字幕.mp4）
    for lp in out_path.parent.glob(f"{fname}*"):
        if "_字幕" in lp.stem:
            continue
        if lp.is_file() and lp.suffix.lower() in (".mp4", ".mkv", ".webm"):
            log(f"  [下載] 已存在副檔名版本：{lp.name}")
            return lp
    return None

def run_pipeline(video_path, title, video_id, skip_cut=True):
    """執行 run_pipeline.py 完整流程（壓縮→轉錄→收成）

    skip_cut=True（預設）：略過 smart-cut 剪輯，字幕時間軸對齊原片，
    避免「燒在原片但 SRT 來自剪輯版」的時間軸錯位。
    """
    log("  [Pipeline] 開始...")
    slug = safe_filename(f"{title[:30]}_{video_id}")
    cmd = [
        sys.executable, "-X", "utf8",
        str(PROJECT_ROOT / "run_pipeline.py"),
        str(video_path),
        "--slug", slug,
    ]
    if skip_cut:
        cmd.append("--skip-cut")
    try:
        result = subprocess.run(cmd, capture_output=True, text=False, timeout=1800)
        if result.returncode != 0:
            log(f"  [Pipeline] 失敗（rc={result.returncode}）")
            err_text = result.stderr[-800:].decode("utf-8", errors="replace") if result.stderr else ""
            log(err_text)
            _note_fail("Pipeline", err_text)
            return None
        log("  [Pipeline] 成功")
        output_dir = PROJECT_ROOT / "output" / slug
        if output_dir.exists():
            return output_dir
        log(f"  [Pipeline] 找不到輸出: {output_dir}")
        _note_fail("Pipeline", f"找不到輸出目錄 {output_dir}")
    except subprocess.TimeoutExpired:
        log("  [Pipeline] 逾時（1800s）")
        _note_fail("Pipeline", "run_pipeline.py 逾時（1800s）")
    except Exception as e:
        log(f"  [Pipeline] 異常: {e}")
        _note_fail("Pipeline", f"{type(e).__name__}: {e}")
    return None

def burn_subtitles(video_path, srt_path, output_path, font_size=18, margin_v=15, position="bottom",
                   font_family="微軟正黑體"):
    """用 ffmpeg + libass 燒錄字幕（與 worker.py 相同處理方式）。

    ffmpeg filter 語法中 `:` 與 `,` 有特殊意義（選項分隔符/濾鏡鏈分隔符），
    Windows 磁碟機代號 `D:` 會讓解析出錯。解法：
    1. 將 SRT 複製到不含特殊字元的暫存路徑
    2. 在 force_style 值內以跳脫字元分隔選項
    3. 使用相對路徑（不含磁碟機代號）避開 `:` 問題

    成功回傳 True，失敗回傳 False（不中斷主流程）。
    """
    if not os.path.exists(srt_path):
        log("  [燒字幕] 找不到字幕檔，跳過")
        return False

    import tempfile
    # 字幕位置樣式：libass alignment 1-9
    position_map = {
        "bottom": 2, "bottom-center": 2, "下": 2, "下中": 2,
        "bottom-left": 1, "下左": 1,
        "bottom-right": 3, "下右": 3,
        "top": 8, "top-center": 8, "上": 8, "上中": 8,
        "top-left": 7, "上左": 7,
        "top-right": 9, "上右": 9,
        "middle": 5, "mid-center": 5, "中": 5, "正中": 5,
        "middle-left": 4, "mid-left": 4, "中左": 4,
        "middle-right": 6, "mid-right": 6, "中右": 6,
    }
    alignment = position_map.get(position, 2)

    work_dir = os.path.join(tempfile.gettempdir(), "opencode_subtitle")
    os.makedirs(work_dir, exist_ok=True)
    tmp_srt = os.path.join(work_dir, "subtitle.srt")
    try:
        shutil.copy2(srt_path, tmp_srt)
    except Exception:
        tmp_srt = srt_path
        work_dir = os.path.dirname(srt_path)

    style = "FontSize={}\\,MarginV={}\\,Alignment={}".format(font_size, margin_v, alignment)
    if font_family:
        style += "\\,FontName={}".format(font_family)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", "subtitles={}:force_style={}".format(os.path.basename(tmp_srt), style),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "copy",
        str(output_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=False, timeout=7200, cwd=work_dir)
    except Exception as e:
        log(f"  [燒字幕] 執行失敗: {e}")
        return False
    finally:
        if tmp_srt != srt_path and os.path.isfile(tmp_srt):
            try:
                os.unlink(tmp_srt)
            except Exception:
                pass
    if result.returncode != 0:
        err = result.stderr[-300:].decode("utf-8", errors="replace") if result.stderr else ""
        log(f"  [燒字幕] ffmpeg 失敗: {err}")
        return False
    log(f"  [燒字幕] 完成：{output_path}")
    return os.path.exists(output_path)


# ── 去重索引：video_id → KB 條目路徑（日後掃描遇同支影片不重複收成）──
# 只以「影片 ID 精確比對」去重（不用標題模糊比對，避免誤判）。
_VIDEO_ID_RE = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})")
_KB_VIDEO_INDEX = None


def _build_kb_video_index(kb_root=None):
    """掃描 KB 建立 {video_id: md路徑}。來源：.md 開頭 8KB（連結寫在表頭）＋ .link.txt 全文。
    .link.txt 若對應 .md 存在則記 md 路徑（較易辨識），否則記連結檔。

    另載入「已知 video_id 種子」（`workspace-bundle/infra/bootstrap/kb_video_ids.txt`）：
    產出機的 knowledge-base 不進 git（從零開始），光靠掃描游標去重不夠——游標一旦
    遺失（直播下架、清單改動），`scan_playlist` 會抓 `max_initial` 支重處理，
    而沒有索引就擋不住（重複下載＋重複轉錄＋重複燒字幕）。種子檔只提供 id、
    不建立任何條目，值一律標成 `seed(notebook)`（僅供 log 顯示）。
    """
    root = Path(kb_root) if kb_root else KB_ROOT
    idx = {}
    for p in root.rglob("*.md"):
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(8192)
        except Exception:
            continue
        m = _VIDEO_ID_RE.search(head)
        if m:
            idx.setdefault(m.group(1), str(p))
    for p in root.rglob("*.link.txt"):
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")[:400]
        except Exception:
            continue
        m = _VIDEO_ID_RE.search(txt)
        if m and m.group(1) not in idx:
            md = p.with_name(p.name[:-len(".link.txt")] + ".md")
            idx[m.group(1)] = str(md if md.exists() else p)
    try:
        if KB_VIDEO_IDS_SEED.exists():
            for line in KB_VIDEO_IDS_SEED.read_text(encoding="utf-8", errors="replace").splitlines():
                vid = line.strip()
                if len(vid) == 11 and re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                    idx.setdefault(vid, "seed(notebook)")
    except OSError:
        pass
    return idx


def kb_video_index(kb_root=None, refresh=False, update=None):
    """回傳（必要時才建立）KB video_id 索引；update= 可即時補入剛建好的條目。"""
    global _KB_VIDEO_INDEX
    if _KB_VIDEO_INDEX is None or refresh:
        _KB_VIDEO_INDEX = _build_kb_video_index(kb_root)
    if update:
        _KB_VIDEO_INDEX.update(update)
    return _KB_VIDEO_INDEX


def create_kb_entry(video_id, title, transcript, srt_path, video_path, kb_dir, burned_path=None, date_prefix=None):
    """建立知識庫條目
    - kb_dir/{date_prefix_}{title}.md：逐字稿 + 連結（含燒字幕影片路徑，若有產出）
    - kb_dir/{date_prefix_}{title}.srt：字幕檔
    date_prefix：有值時（YYYY-MM-DD）作為檔名前綴，維持知識時序可辨識。
    """
    base = kb_basename(title, date_prefix)
    md_path = kb_dir / f"{base}.md"
    srt_dst = kb_dir / f"{base}.srt"
    link_dst = kb_dir / f"{base}.link.txt"

    kb_dir.mkdir(parents=True, exist_ok=True)

    # .md：逐字稿 + 連結
    md_content = f"""# {title}

## 影片資訊
- YouTube 連結：https://www.youtube.com/watch?v={video_id}
"""
    if date_prefix:
        md_content += f"- 日期：{date_prefix}\n"
    if video_path and os.path.exists(video_path):
        md_content += f"- 本機影片：{video_path}\n"
    if burned_path and os.path.exists(burned_path):
        md_content += f"- 燒字幕影片：{burned_path}\n"
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


# ── 課程筆記（自動產出，預設關；由呼叫端 note=True 觸發）──
NOTE_TEMPLATE = KB_ROOT / "金融交易" / "理周學院" / "林教授" / "_preview_林教授 量價時間角度的三道菜 課程筆記.docx"
NOTE_CHUNK_CHARS = 8000
MAX_NOTES_PER_RUN = 3          # 單批上限（決策⑦）
MAX_NOTES_PER_DAY = 20         # 每日上限（決策⑦；Gemini 免費層 500/日，留安全邊際）
_NOTE_QUOTA_FILE = KB_ROOT / ".note_quota.json"
_NOTE_QUOTA_LOG_FILE = KB_ROOT / ".note_quota_log.tsv"


def _note_quota_take(tag: str = ""):
    """檢查並扣用今日筆記額度。回傳 True=可產、False=已達當日上限（決策⑦）。"""
    today = datetime.now().strftime("%Y-%m-%d")
    data = {}
    try:
        if _NOTE_QUOTA_FILE.exists():
            data = json.loads(_NOTE_QUOTA_FILE.read_text(encoding="utf-8-sig"))
    except Exception:
        data = {}
    if data.get("date") != today:
        data = {"date": today, "count": 0}
    if data.get("count", 0) >= MAX_NOTES_PER_DAY:
        return False
    data["count"] = data.get("count", 0) + 1
    try:
        _NOTE_QUOTA_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    try:
        with open(_NOTE_QUOTA_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')}\t{data['count']}\t{tag}\n")
    except Exception:
        pass
    return True


def make_note_for_md(title, md_path, out_dir=None):
    """為 KB 逐字稿 md 產生課程筆記（.md+.docx，放同目錄）。
    已存在同名「課程筆記」則略過（決策⑥）；達每日上限則略過並記待辦（決策⑦）。
    回傳 (md_out, docx_out) 或 None。
    """
    md_path = Path(md_path)
    title = title or md_path.stem
    out_dir = Path(out_dir) if out_dir else md_path.parent
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)
    md_out = out_dir / f"{safe_title} 課程筆記.md"
    if md_out.exists():
        log(f"  [筆記] 略過（已存在）：{md_out.name}")
        return md_out, md_out.with_suffix(".docx")
    if not _note_quota_take(f"channel note:{title}"):
        log(f"  [筆記] 今日已達上限 {MAX_NOTES_PER_DAY} 份，記待辦略過：{title}")
        return None
    from make_course_note import generate_note
    tpl = NOTE_TEMPLATE if NOTE_TEMPLATE.exists() else None
    log(f"  [筆記] 產生課程筆記：{title}")
    try:
        return generate_note(title, [md_path], out_dir, template=tpl,
                             chunk_chars=NOTE_CHUNK_CHARS, progress=lambda m: log(f"    {m}"))
    except Exception as e:
        log(f"  [筆記] 產生失敗：{e}")
        return None


def make_summary_for_md(title, md_path, out_dir=None):
    """為 KB 逐字稿 md 產生摘要報告（.md+.docx，放同目錄）。
    已存在同名「摘要」則略過；達每日上限則略過。與課程筆記共用同一個產製預算。
    回傳 (md_out, docx_out) 或 None。
    """
    md_path = Path(md_path)
    title = title or md_path.stem
    out_dir = Path(out_dir) if out_dir else md_path.parent
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)
    md_out = out_dir / f"{safe_title} 摘要.md"
    if md_out.exists():
        log(f"  [摘要] 略過（已存在）：{md_out.name}")
        return md_out, md_out.with_suffix(".docx")
    if not _note_quota_take(f"channel summary:{title}"):
        log(f"  [摘要] 今日已達上限 {MAX_NOTES_PER_DAY} 份，略過：{title}")
        return None
    from make_course_note import generate_summary
    tpl = NOTE_TEMPLATE if NOTE_TEMPLATE.exists() else None
    log(f"  [摘要] 產生摘要報告：{title}")
    try:
        return generate_summary(title, [md_path], out_dir, template=tpl,
                                chunk_chars=NOTE_CHUNK_CHARS, progress=lambda m: log(f"    {m}"))
    except Exception as e:
        log(f"  [摘要] 產生失敗：{e}")
        return None


# ── 核心邏輯 ──

def process_has_subs(video_id, title, langs, kb_dir, burn_subs=False, format_spec=None, save_to_kb=True):
    """有字幕路徑：下載字幕 → KB 條目。成功回傳 md_path，失敗回傳 None。
    burn_subs=True：即使有官方字幕，也下載影片並把字幕燒進去（依頻道規則）。
    format_spec：燒字幕時的下載格式（None=預設 1080p）。
    save_to_kb=False：只處理（必要時燒字幕）不寫入 KB，成功回傳 True。"""
    temp_dir = WORKING / "channel-watcher-temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    srt_path = download_yt_sub(video_id, langs, temp_dir)
    if not srt_path:
        return None

    log(f"  [字幕] YouTube 字幕：{srt_path.name}")
    transcript = srt_to_transcript(srt_path)

    date_prefix = get_video_date(video_id)

    burned_path = None
    if burn_subs:
        log("  [燒字幕] 依規則下載搭配影片並燒字幕...")
        video_path = download_yt_video(video_id, title, format_spec=format_spec or YT_DL_FORMAT, date_prefix=date_prefix)
        if video_path:
            bp = Path(video_path).with_name(Path(video_path).stem + "_字幕.mp4")
            if burn_subtitles(video_path, srt_path, bp):
                burned_path = bp

    if not save_to_kb:
        try:
            srt_path.unlink()
        except Exception:
            pass
        return True

    md_path = create_kb_entry(video_id, title, transcript, srt_path, None, kb_dir, burned_path=burned_path, date_prefix=date_prefix)

    # 清理
    srt_path.unlink()
    return md_path


def process_no_subs(video_id, title, langs, kb_dir, format_spec=None, save_to_kb=True):
    """無字幕路徑：下載影片 → Pipeline → 燒字幕 → KB 條目。成功回傳 md_path，失敗回傳 None
    save_to_kb=False：只處理（下載＋轉錄＋燒字幕）不寫入 KB，成功回傳影片路徑。"""
    log("  [轉錄] 無 YouTube 字幕，啟動離線 Pipeline...")

    date_prefix = get_video_date(video_id)
    video_path = download_yt_video(video_id, title, format_spec=format_spec or YT_DL_FORMAT, date_prefix=date_prefix)
    if not video_path:
        log("  [轉錄] 影片下載失敗")
        return None

    output_dir = run_pipeline(video_path, title, video_id)
    if not output_dir:
        log("  [轉錄] Pipeline 失敗")
        return None

    # 找到產出的 SRT
    srt_src = output_dir / "字幕.srt"
    if not srt_src.exists():
        log("  [轉錄] 找不到 Pipeline 產出的 SRT")
        _note_fail("Pipeline", f"找不到 {srt_src}")
        return None

    transcript = srt_to_transcript(srt_src)

    # 燒字幕：輸出到影片同資料夾（ffmpeg），成功才寫入 KB 連結
    burned_path = Path(video_path).with_name(Path(video_path).stem + "_字幕.mp4")
    if not burn_subtitles(video_path, srt_src, burned_path):
        burned_path = None

    if not save_to_kb:
        return video_path

    md_path = create_kb_entry(video_id, title, transcript, srt_src, video_path, kb_dir, burned_path=burned_path, date_prefix=date_prefix)

    return md_path


def kb_subdir_of(md_path):
    """KB 條目所在子目錄（相對 knowledge-base，用 / 分隔）；算不出來就回空字串。

    一律先 resolve()：呼叫端若傳相對路徑，`relative_to` 會拋 ValueError →
    退回空字串 → publish_outbox 只會在 youtube-clips／KB 根找，條目就收不到
    （2026-11-09 PC2 實測踩到：手動登記時的相對路徑）。正式掃描是絕對路徑，
    但不該讓「傳相對路徑」變成靜默失敗。
    """
    try:
        p = Path(md_path)
        if not p.is_absolute():
            p = (Path.cwd() / p)
        rel = p.resolve().parent.relative_to(Path(KB_ROOT).resolve())
        return str(rel).replace("\\", "/")
    except (ValueError, OSError):
        return ""


def record_harvest_task(video_id, title, md_path, channel_name=""):
    """把掃描收成的條目登記成一筆「已完成」任務，讓收割鏈看得到。

    為什麼需要（2026-11-09 實查）：`publish_outbox.py` 是**任務驅動**的（`iter_tasks()`），
    只打包 task_status／shared\\tasks 裡有紀錄的條目。`channel_watcher` 自己產生的 KB 條目
    以前不需要登記，是因為掃描就跑在 notebook（收割的正本機）上；掃描搬到產出機之後
    沒有這筆紀錄 → 產出永遠不會被 publish／harvest，等於白做。

    寫入 `shared\\tasks\\task_<id>.json`（status=**completed**，worker 不會撿），
    不動 `task_status.json` 以免和 GUI／scheduler 的 mirror 打架。
    `publish_outbox.iter_tasks()` 只認 `status == "completed"`，所以不能用 "done"。
    失敗只警告，不影響收成。
    """
    try:
        tasks_dir = Path(SHARED_ROOT) / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        used = []
        for f in tasks_dir.glob("task_*.json"):
            try:
                used.append(int(f.stem.split("_", 1)[1]))
            except (IndexError, ValueError):
                pass
        try:
            for k in ((load_task_status() or {}).get("tasks") or {}):
                if str(k).isdigit():
                    used.append(int(k))
        except Exception:
            pass
        tid = str((max(used) if used else 0) + 1)
        now = datetime.now().isoformat()
        info = {
            "type": "youtube",
            "status": "completed",
            "assigned_to": MACHINE,
            "priority": 0,
            "name": title,
            "title": title,
            "video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "source_url": f"channel_watcher:{channel_name}"[:300],
            "kb_subdir": kb_subdir_of(md_path),
            "harvest_to_kb": True,
            "auto_note": False,
            "auto_summary": False,
            "burn_subs": False,
            "note": "頻道掃描收成（自動登記，供 publish_outbox 收割）",
            "discovered_at": now,
            "started_at": now,
            "completed_at": now,
            "last_error": None,
            "machine": MACHINE,
            "output_keys": [],
        }
        payload = {"task_id": tid, "task_info": info, "status": "completed",
                   "assigned_to": MACHINE}
        target = tasks_dir / f"task_{tid}.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, target)
        log(f"  📤 已登記收割任務 #{tid}（publish_outbox 會打包這筆）")
    except Exception as e:
        log(f"  ⚠️ 登記收割任務失敗（收成不受影響）：{e}")


def scan_playlist(source, kb_dir, langs, state, max_initial=3, channel_name="未知頻道", burn_subs=False, note=False, summary=False, format_spec=None, dedup=True):
    """掃描單一播放清單，處理新影片
    source: playlist_id 或 YouTube URL
    max_initial: 初次掃描最多處理幾支
    channel_name: 頻道名稱（供通知明細使用）
    burn_subs: 即使有官方字幕也下載影片並燒字幕
    note: 收成後自動產生課程筆記（預設關）
    summary: 收成後自動產生摘要報告（預設關；摘要優先，需要時再補詳細筆記）
    format_spec: 燒字幕影片下載格式（None=預設 1080p）
    dedup: 同一 video_id 已在 KB 任一目錄即略過（防止直播/清單重複收成，預設開）
    """
    global _last_scan_details
    label = source[:40] if "youtube.com" in source else source
    log(f"[掃描] 清單：{label}")
    log(f"  KB 目錄：{kb_dir}")

    entries = get_playlist_entries(source)
    if not entries:
        return 0

    state_key = source  # 用 source 字串當狀態鍵
    index = kb_video_index() if dedup else {}

    last_id = state.get(state_key, {}).get("last_video_id", "")
    is_first_scan = not last_id

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

    # 初次掃描：只取前 max_initial 支
    if is_first_scan:
        new_entries = entries[:max_initial]
        log(f"  [新片] 初次掃描，取最新 {len(new_entries)} 支")
    elif not found_last:
        new_entries = entries[:max_initial]
        log(f"  [新片] 上次 ID 未找到，取最新 {len(new_entries)} 支")
    elif new_entries:
        new_entries.reverse()
        log(f"  [新片] {len(new_entries)} 支新影片")

    if not new_entries:
        state[state_key] = {
            "last_video_id": entries[0].get("id", ""),
            "last_check": datetime.now().isoformat(),
        }
        return 0

    # 處理新影片
    processed = 0
    notes_made = 0
    for entry in new_entries:
        vid = entry.get("id", "")
        title = entry.get("title", vid)
        log(f"\n  ── {title[:50]}")
        log(f"      https://www.youtube.com/watch?v={vid}")

        md_path = None

        # 精準去重：同一 video_id 已在 KB 任一目錄 → 略過（直播／播放清單重複收成）
        existing = index.get(vid)
        if existing:
            log(f"  ⏭️ 去重：同支影片已在知識庫，略過 → {existing}")
            _last_scan_details.append({
                "channel": channel_name,
                "title": title,
                "video_id": vid,
                "result": "⏭️ 已在知識庫，略過（去重）",
                "kb": existing,
            })
            # 仍須推進游標並存檔（不可用 continue 略過存檔，否則下次又當新片掃）
            state[state_key] = {
                "last_video_id": vid,
                "last_check": datetime.now().isoformat(),
                "last_process_time": datetime.now().isoformat(),
            }
            save_channel_state(state)
            continue

        md_path = process_has_subs(vid, title, langs, kb_dir, burn_subs=burn_subs, format_spec=format_spec)
        if md_path:
            processed += 1
            index[vid] = str(md_path)  # 即時更新索引：同批其他清單也遇同支即去重
            record_harvest_task(vid, title, md_path, channel_name)
            log(f"  ✅ 有字幕處理完成")
            _last_scan_details.append({
                "channel": channel_name,
                "title": title,
                "video_id": vid,
                "result": "✅ 已下載字幕並存入知識庫",
                "kb": str(md_path),
            })
        else:
            md_path = process_no_subs(vid, title, langs, kb_dir, format_spec=format_spec)
            if md_path:
                processed += 1
                record_harvest_task(vid, title, md_path, channel_name)
                log(f"  ✅ 離線轉錄完成")
                _last_scan_details.append({
                    "channel": channel_name,
                    "title": title,
                    "video_id": vid,
                    "result": "✅ 已離線轉錄並存入知識庫",
                    "kb": str(md_path),
                })
            else:
                log(f"  ❌ 處理失敗")
                _last_scan_details.append({
                    "channel": channel_name,
                    "title": title,
                    "video_id": vid,
                    "result": "❌ 處理失敗",
                    "kb": "",
                })

        # 每完成一支立即保存狀態進度，被中斷時不致全部重跑
        state[state_key] = {
            "last_video_id": vid,
            "last_check": datetime.now().isoformat(),
            "last_process_time": datetime.now().isoformat(),
        }
        save_channel_state(state)

        # 20VTA 直播 → 自動產生 AI 重點摘要報告（存「直播報告」資料夾）
        if md_path and (kb_dir.name == "直播" or channel_name == "20VTA 波段王子"):
            try:
                from make_live_report import make_report as _make_live_report
                _make_live_report(Path(md_path))
            except Exception as e:
                log(f"  ⚠️ 直播報告產生失敗: {e}")

        # 自動產生課程筆記（預設關；達單批/每日上限即停）
        if note and md_path and notes_made < MAX_NOTES_PER_RUN:
            try:
                title_for_note = Path(md_path).stem
                r = make_note_for_md(title_for_note, md_path)
                if r:
                    notes_made += 1
                    _last_scan_details[-1]["result"] += "（含課程筆記）"
            except Exception as e:
                log(f"  ⚠️ 課程筆記產生失敗: {e}")

        # 自動產生摘要報告（與課程筆記共用「摘要優先」策略；經 MAX_NOTES_PER_RUN 併計）
        if summary and md_path and notes_made < MAX_NOTES_PER_RUN:
            try:
                title_for_sum = Path(md_path).stem
                r = make_summary_for_md(title_for_sum, md_path)
                if r:
                    notes_made += 1
                    _last_scan_details[-1]["result"] += "（含摘要）"
            except Exception as e:
                log(f"  ⚠️ 摘要產生失敗: {e}")

    state[state_key] = {
        "last_video_id": entries[0].get("id", ""),
        "last_check": datetime.now().isoformat(),
        "last_process_time": datetime.now().isoformat(),
    }

    return processed


def format_scan_details(details):
    """把本次掃描明細做成通知文字（email/Line）
    details: [{channel, title, video_id, result, kb}]
    """
    if not details:
        return ""
    lines = [f"共處理 {len(details)} 支新影片", ""]
    for d in details:
        lines.append(f"■ 頻道：{d['channel']}")
        lines.append(f"  影片：{d['title']}")
        lines.append(f"  連結：https://www.youtube.com/watch?v={d['video_id']}")
        lines.append(f"  結果：{d['result']}")
        if d.get("kb"):
            lines.append(f"  存於：{d['kb']}")
        lines.append("")
    return "\n".join(lines)


def notify(title, message):
    """發送 Line + Email 通知"""
    log(f"[通知] {title}: {message[:60]}")
    try:
        notify_line_and_email(f"[{title}]", message)
    except Exception as e:
        log(f"[通知] 發送失敗: {e}")


def scan_all_channels():
    """掃描所有設定中的頻道與播放清單"""
    global _last_scan_details
    _last_scan_details = []
    state = load_channel_state()
    channels = get_watched_channels()
    total = 0
    kb_video_index(refresh=True)  # 重建 video_id 索引（含外部工具新建的條目），供本次去重

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
            source = pl.get("url", "") or pl.get("id", "")
            kb_rel = pl.get("kb_dir", "")
            kb_dir = KB_ROOT / kb_rel
            max_init = pl.get("max_initial", 3)
            fmt = FORMAT_PRESETS.get(str(pl.get("format", "")), None)

            if not source:
                continue
            try:
                n = scan_playlist(source, kb_dir, langs, state, max_initial=max_init, channel_name=name,
                                   burn_subs=pl.get("burn_subs", ch.get("burn_subs", False)),
                                   note=pl.get("note", ch.get("note", False)),
                                   summary=pl.get("summary", ch.get("summary", False)),
                                   format_spec=fmt)
                total += n
            except Exception as e:
                log(f"  [錯誤] {source[:30]}: {e}")

        # 家目錄下的 .link.txt 檔案連結也可以作為快捷方式
        ch_links = KB_ROOT / "youtube-clips"
        ch_links.mkdir(parents=True, exist_ok=True)

    save_channel_state(state)
    return total


def seed_channel_state(seed_path):
    """把另一台機器的掃描游標匯入本機（接手掃描／新機上線用）。

    seed 檔格式與 `shared/watched_channels_state.json` 相同：
    `{來源: {"last_video_id": ..., "last_check": ...}}`。
    沒有游標的新機若直接 `--once`，會把每個清單最新 `max_initial` 支當新片重抓
    （重複下載、重複轉錄、重複燒字幕）；先匯入游標就不會。

    規則：
    - 來源不在 config.yaml 的 watched_channels → 只警告，不寫入（多半是清單已改）
    - 本機沒有該來源 → 寫入
    - 本機有、seed 的 last_check 較新 → 覆蓋（游標只往前，不倒退）
    - 本機較新 → 保留本機
    """
    seed_file = Path(seed_path)
    if not seed_file.exists():
        log(f"❌ 找不到 seed 檔：{seed_file}")
        return 1
    try:
        seed = json.loads(seed_file.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"❌ seed 檔不是合法 JSON：{e}")
        return 1

    valid = set()
    for ch in get_watched_channels():
        for pl in ch.get("playlists", []):
            src = pl.get("url", "") or pl.get("id", "")
            if src:
                valid.add(src)

    state = load_channel_state()
    added, updated, kept, ignored = [], [], [], []
    for src, s in seed.items():
        if not isinstance(s, dict) or not s.get("last_video_id"):
            continue
        if valid and src not in valid:
            ignored.append(src)
            continue
        cur = state.get(src) or {}
        new = {
            "last_video_id": s["last_video_id"],
            "last_check": s.get("last_check", ""),
        }
        if not cur.get("last_video_id"):
            state[src] = new
            added.append(src)
        elif str(s.get("last_check", "")) > str(cur.get("last_check", "")):
            state[src] = new
            updated.append(src)
        else:
            kept.append(src)

    if added or updated:
        save_channel_state(state)

    log(f"匯入游標 {seed_file.name}：新增 {len(added)}｜更新 {len(updated)}｜"
        f"保留本機 {len(kept)}｜略過(不在設定) {len(ignored)}")
    if ignored:
        for src in ignored:
            log(f"  ⚠️ 不在 config.yaml watched_channels，略過：{src}")
    if not added and not updated:
        log("  ℹ️ 沒有寫入任何游標（本機已是最新，或 seed 不含有效來源）")
    log(f"  狀態檔案：{CHANNEL_STATE_FILE}")
    log("  下一步：`--status` 確認，再 `--once` 實際掃描")
    return 0


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
            source = pl.get("url", "") or pl.get("id", "")
            kb_rel = pl.get("kb_dir", "")
            s = state.get(source, {})
            last_id = s.get("last_video_id", "—")
            last_check = s.get("last_check", "未掃描")
            last_process = s.get("last_process_time", "—")
            lbl = source[:30] + "..." if len(source) > 30 else source
            print(f"   來源 {lbl} → {kb_rel}")
            print(f"     最近 ID: {last_id}")
            print(f"     上次掃描: {last_check}")
            print(f"     上次處理: {last_process}")

    print(f"\n  設定頻道數: {len(channels)}")
    print(f"  狀態檔案: {SHARED_ROOT}\\watched_channels_state.json")
    print()


def process_youtube_video(video_id, title, langs=None, kb_dir=None, burn_subs=False,
                          save_to_kb=True, format_spec=None):
    """處理單一 YouTube 影片（供佇列 worker／GUI 使用）。

    優先使用 YouTube 字幕；無字幕則下載影片跑離線 Pipeline（皆會依需求燒字幕）。
    save_to_kb=True 時寫入 KB 條目（kb_dir 預設 knowledge-base/youtube-clips）。

    Returns:
        dict: {"success": bool, "kb_md": str|None, "kb_path": str, "error": str}
    """
    if langs is None:
        langs = ["zh-Hant", "zh-TW", "zh", "en"]
    kb_dir = Path(kb_dir) if kb_dir else (KB_ROOT / "youtube-clips")

    # 任務標題空白或等於 video_id（播放清單展開失敗時會這樣）→ 收成前補抓，
    # 否則 KB 檔名會變成 video_id。
    if not str(title or "").strip() or str(title).strip() == video_id:
        real_title = get_video_title(video_id)
        if real_title:
            title = real_title

    result = {"success": False, "kb_md": None, "kb_path": "", "error": ""}
    _note_fail("", "")
    try:
        md_path = process_has_subs(
            video_id, title, langs, kb_dir,
            burn_subs=burn_subs, format_spec=format_spec, save_to_kb=save_to_kb,
        )
        if md_path is None:
            md_path = process_no_subs(
                video_id, title, langs, kb_dir,
                format_spec=format_spec, save_to_kb=save_to_kb,
            )
    except Exception as e:
        result["error"] = f"處理異常: {e}"
        log(f"[ERROR] process_youtube_video {video_id}: {e}")
        return result

    if not md_path:
        # 2026-11-06 事故：所有原因都收斂成同一句話，導致查不出真正死因。
        # 現在把「哪個階段 + 原因 + stderr 尾巴」一起寫進 last_error。
        err = "下載或轉錄失敗（無字幕且 Pipeline 未產出）"
        stage = _LAST_FAIL.get("stage")
        detail = _LAST_FAIL.get("detail") or ""
        if stage:
            err += f"：{stage} 失敗"
            hint = yt_fail_hint(detail)
            if hint:
                err += f"（{hint}）"
            tail = " ".join(detail.split())
            # 去掉 yt-dlp 的說明連結（會把 240 字吃光、還從中間被切斷成「ttps://…」）
            tail = re.sub(r"https?://\S+", "", tail).strip()
            tail = tail[-240:]
            if tail:
                err += f"｜{tail}"
        result["error"] = err
        return result

    result["success"] = True
    if save_to_kb and isinstance(md_path, Path):
        result["kb_md"] = str(md_path)
        result["kb_path"] = str(md_path)
    return result


def process_youtube_url(url, burn_sub=False, save_to_kb=True, langs=None, note=False, summary=False):
    """處理單一 YouTube 網址（舊介面；GUI 已改為建立逐支佇列任務）

    支援格式：
      - 單一影片: https://www.youtube.com/watch?v=xxx
      - 播放清單: https://www.youtube.com/playlist?list=xxx
      - 頻道: https://www.youtube.com/@channel

    Returns:
        dict: { "status": "ok"/"error", "message": str, "videos": [{...}] }
    """
    result = {"status": "ok", "message": "", "videos": []}
    entries = expand_youtube_entries(url, limit=5)
    if not entries:
        result["status"] = "error"
        result["message"] = "找不到任何影片（網址無效、未公開或清單為空）"
        return result

    processed_count = 0
    for i, entry in enumerate(entries):
        vid = entry.get("id", "")
        title = entry.get("title", vid)
        log(f"  [{i+1}] {title}")
        video_info = {"id": vid, "title": title, "success": False, "kb_path": ""}
        r = process_youtube_video(vid, title, langs=langs, burn_subs=burn_sub,
                                  save_to_kb=save_to_kb)
        video_info["success"] = r["success"]
        video_info["kb_path"] = r["kb_path"]
        if r["success"]:
            processed_count += 1
            if save_to_kb and r["kb_md"]:
                md_path = Path(r["kb_md"])
                if note:
                    make_note_for_md(md_path.stem, md_path)
                if summary:
                    make_summary_for_md(md_path.stem, md_path)
        else:
            log(f"  ❌ {r['error']}")
        result["videos"].append(video_info)

    if processed_count == 0:
        result["status"] = "error"
        result["message"] = "所有影片處理失敗"
    else:
        result["message"] = f"成功處理 {processed_count}/{len(entries)} 支影片"
        result["status"] = "ok"
    return result


# ── CLI ──

def _setup_schedule():
    """建立 Windows 排程工作：每週一晚上10點執行 --once"""
    script = sys.executable
    cmd = f'"{script}" "{__file__}" --once'
    task_name = "ChannelWatcherWeekly"
    schtask_cmd = [
        "schtasks", "/Create", "/TN", task_name,
        "/TR", cmd,
        "/SC", "WEEKLY", "/D", "MON", "/ST", "22:00",
        "/F", "/RL", "HIGHEST",
    ]
    try:
        log("建立 Windows 排程工作 (每週一 22:00)...")
        r = subprocess.run(
            schtask_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if r.returncode == 0:
            log(f"✅ 排程工作 '{task_name}' 建立成功")
            log(f"   每週一 22:00 執行：{cmd}")
        else:
            log(f"❌ 建立失敗: {r.stderr or r.stdout}")
    except Exception as e:
        log(f"❌ 建立排程異常: {e}")


def main():
    ap = argparse.ArgumentParser(description="YouTube 頻道自動監控與收成")
    ap.add_argument("--once", action="store_true", help="立即掃描一次")
    ap.add_argument("--watch", action="store_true", help="持續監控模式")
    ap.add_argument("--status", action="store_true", help="顯示監控狀態")
    ap.add_argument("--interval", type=int, default=3600, help="掃描間隔秒數（預設 3600）")
    ap.add_argument("--setup-schedule", action="store_true", help="建立 Windows 排程（每週一 22:00）")
    ap.add_argument("--seed-state", metavar="FILE",
                    help="匯入另一台機器的掃描游標後結束（接手掃描／新機上線用）")
    args = ap.parse_args()

    if args.seed_state:
        return seed_channel_state(args.seed_state)

    if args.setup_schedule:
        _setup_schedule()
        return

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
                notify("頻道監控", format_scan_details(_last_scan_details))
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
    if n > 0:
        notify("頻道監控", format_scan_details(_last_scan_details))


if __name__ == "__main__":
    main()
