#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YouTube 任務失敗原因診斷（唯讀，可在任一機器跑）

用途：PC1 回報「下載或轉錄失敗很多，但也有成功的」時，一次收齊判斷所需的證據。

用法：
    python diag_youtube_fail.py            # 最近 200 筆任務
    python diag_youtube_fail.py --all      # 全部任務
    python diag_youtube_fail.py --probe 3  # 額外實測 3 支失敗影片（只抓 metadata）
    python diag_youtube_fail.py --download-probe 2 --with-pipeline
                                           # 真實下載 2 支失敗影片（抓真正的錯誤訊息），
                                           # 下載成功再跑一次 run_pipeline.py 定位問題點

輸出同時印在畫面並寫入 working/diag_youtube_YYYYMMDD_HHMMSS.txt
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKING = ROOT / "working"

LINES: list[str] = []


def put(s: str = "") -> None:
    LINES.append(s)
    try:
        print(s)
    except Exception:
        print(s.encode("utf-8", "replace").decode("ascii", "replace"))


def section(title: str) -> None:
    put("")
    put("=" * 70)
    put(title)
    put("=" * 70)


def run(cmd, timeout=60, cwd=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           cwd=cwd)
        return (r.stdout or "").strip(), (r.stderr or "").strip(), r.returncode
    except Exception as e:  # noqa: BLE001
        return "", f"{type(e).__name__}: {e}", -1


def groq_transcribe_probe(key: str) -> None:
    """真的送 1 秒靜音去 /audio/transcriptions（/models 會被 403，不能拿來判斷）。"""
    put("")
    put("Groq 轉錄實測（1 秒靜音 → whisper-large-v3-turbo）:")
    if not shutil.which("ffmpeg"):
        put("  找不到 ffmpeg，無法產生測試音檔")
        return
    import tempfile
    tdir = Path(tempfile.mkdtemp(prefix="groqprobe_"))
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
         "-t", "1", "-q:a", "9", "t.wav"], timeout=60, cwd=str(tdir))
    if not (tdir / "t.wav").exists():
        put("  產生音檔失敗")
        return
    out, err, rc = run(["curl.exe", "-sS", "-m", "60", "-o", "r.json", "-w", "%{http_code}",
                        "-X", "POST", "https://api.groq.com/openai/v1/audio/transcriptions",
                        "-H", f"Authorization: Bearer {key}",
                        "-F", "file=@t.wav",
                        "-F", "model=whisper-large-v3-turbo",
                        "-F", "response_format=json"], timeout=90, cwd=str(tdir))
    body = ""
    if (tdir / "r.json").exists():
        body = (tdir / "r.json").read_text(encoding="utf-8", errors="replace")[:200]
    put(f"  HTTP {out or rc}  {body or err[:150]}")
    shutil.rmtree(tdir, ignore_errors=True)



# ---------------------------------------------------------------- environment
def env_facts() -> None:
    section("1. 環境")
    put(f"時間       : {datetime.now():%Y-%m-%d %H:%M:%S}")
    put(f"主機       : {os.environ.get('COMPUTERNAME')}  python {sys.version.split()[0]}")
    put(f"工作區     : {ROOT}")
    for exe in ("yt-dlp", "ffmpeg", "ffprobe", "auto-editor"):
        put(f"{exe:<11}: {shutil.which(exe) or '找不到（PATH 裡沒有）'}")

    for name in ("yt-dlp", "ffmpeg", "auto-editor"):
        if shutil.which(name):
            out, err, rc = run([name, "--version"], timeout=30)
            put(f"  {name} --version -> rc={rc} {(out or err).splitlines()[0][:80] if (out or err) else ''}")

    # 磁碟
    for drive in ("D:\\", "C:\\"):
        try:
            t, u, f = shutil.disk_usage(drive)
            put(f"磁碟 {drive} 可用 {f/2**30:6.1f} GB / 共 {t/2**30:6.1f} GB")
        except Exception as e:  # noqa: BLE001
            put(f"磁碟 {drive} 讀取失敗: {e}")

    # API keys
    key_file = Path.home() / ".groq_api_key"
    env_key = os.environ.get("GROQ_API_KEY", "")
    if key_file.exists():
        txt = key_file.read_text(encoding="utf-8", errors="replace").strip()
        put(f"~/.groq_api_key : 存在，長度 {len(txt)}，前 4 碼 {txt[:4]!r}")
    else:
        put("~/.groq_api_key : **不存在**")
    put(f"env GROQ_API_KEY: {'有，長度 %d' % len(env_key) if env_key else '未設定'}")
    for f in (".gemini_api_key",):
        p = Path.home() / f
        put(f"~/{f:<14}: {'存在' if p.exists() else '不存在'}")

    # Groq 可用性：直接打轉錄端點（/models 在此網路環境固定 403，不能當判斷依據）
    key = key_file.read_text(encoding="utf-8", errors="replace").strip() if key_file.exists() else env_key
    if key:
        groq_transcribe_probe(key)
    else:
        put("")
        put("Groq 轉錄實測: 略過（沒有 key）")

    # Pipeline 能不能啟動（不連網、不下載；run_pipeline 一啟動就會 import 全部相依）
    put("")
    put("Pipeline 自我檢查（不連網）:")
    put(f"  解譯器: {sys.executable}")
    out, err, rc = run([sys.executable, "-X", "utf8", str(ROOT / "run_pipeline.py"), "--help"],
                       timeout=120, cwd=str(ROOT))
    put(f"  run_pipeline.py --help -> rc={rc}")
    if rc != 0:
        for line in (err or out).splitlines()[-12:]:
            put("    " + line[:200])
    for mod in ("groq", "yt_dlp", "docx", "PIL"):
        o, e, r = run([sys.executable, "-c", f"import {mod}"], timeout=60)
        put(f"  import {mod:<7} rc={r}" + ("" if r == 0 else "  " + (e.splitlines() or [""])[-1][:120]))
    # pythonw 啟動時 sys.stdout 可能是 None；只記錄有沒有 pythonw（run_pipeline 已加防護）
    pw = Path(sys.executable).with_name("pythonw.exe")
    put(f"  pythonw.exe 存在 = {pw.exists()}")

    # YouTube 字幕下載實測（只用 metadata，不下載檔案）
    put("")
    put("YouTube 連通性（yt-dlp --simulate，不下載）:")
    if shutil.which("yt-dlp"):
        out, err, rc = run(["yt-dlp", "--simulate", "--skip-download",
                            "--no-warnings", "--print", "%(id)s %(title)s",
                            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"], timeout=90)
        put(f"  rc={rc} out={out[:120]!r}")
        if rc != 0:
            put("  stderr 末 6 行：")
            for line in err.splitlines()[-6:]:
                put("    " + line[:160])
        # 字幕清單（判斷有沒有官方/自動字幕）
        out2, err2, rc2 = run(["yt-dlp", "--simulate", "--skip-download",
                               "--list-subs",
                               "https://www.youtube.com/watch?v=dQw4w9WgXcQ"], timeout=90)
        langs = [ln.split()[0] for ln in out2.splitlines() if ln.strip() and not ln.startswith("[")]
        put(f"  可用字幕: rc={rc2} {langs[:6]}")
    else:
        put("  找不到 yt-dlp")


# ---------------------------------------------------------------- task survey
def load_tasks() -> dict:
    tasks = {}
    p = ROOT / "task_status.json"
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            tasks.update(data.get("tasks") or {})
        except Exception as e:  # noqa: BLE001
            put(f"task_status.json 讀取失敗: {e}")
    for f in glob.glob(str(ROOT / "shared" / "tasks" / "task_*.json")):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8-sig"))
            tid = str(d.get("task_id") or Path(f).stem.split("_")[-1])
            if tid not in tasks:
                tasks[tid] = d.get("task_info") or {}
        except Exception:
            pass
    return tasks


def survey(limit: int) -> list:
    section("2. 任務統計")
    tasks = load_tasks()
    items = []
    for tid, info in tasks.items():
        items.append({
            "tid": str(tid),
            "type": info.get("type"),
            "status": info.get("status"),
            "machine": info.get("machine") or info.get("assigned_to"),
            "title": info.get("title") or info.get("name") or "",
            "video_id": info.get("video_id") or "",
            "error": (info.get("last_error") or info.get("error") or ""),
            "when": info.get("completed_at") or info.get("started_at") or info.get("discovered_at") or "",
        })
    items.sort(key=lambda x: x["when"] or "", reverse=True)
    if limit and limit > 0:
        items = items[:limit]
    put(f"筆數 {len(items)}")
    put("狀態分布：" + str(dict(collections.Counter(i["status"] for i in items))))
    put("機器分布：" + str(dict(collections.Counter(i["machine"] for i in items))))
    put("型別分布（failed）：" + str(dict(collections.Counter(
        i["type"] for i in items if i["status"] == "failed"))))

    failed = [i for i in items if i["status"] == "failed"]
    section("3. 失敗原因分類")
    if not failed:
        put("沒有 failed 任務（可能都成功了，或狀態還沒同步回本機）")
        return items

    def bucket(msg: str) -> str:
        m = msg.lower()
        if "sign in to confirm" in m or "not a bot" in m:
            return "YouTube 要求驗證（bot check／需要 cookies）"
        if "403" in m or "forbidden" in m:
            return "HTTP 403（被拒／地區限制）"
        if "429" in m or "too many requests" in m:
            return "HTTP 429（請求過多／被限流）"
        if "video unavailable" in m or "private video" in m or "removed" in m:
            return "影片不可用（私人／已刪除／地區封鎖）"
        if "timed out" in m or "timeout" in m:
            return "逾時"
        if "groq" in m or "whisper" in m or "transcri" in m or "轉錄" in m:
            return "轉錄失敗（Groq／Whisper）"
        if "no space" in m or "磁碟" in m or "disk" in m:
            return "磁碟空間不足"
        if "下載或轉錄失敗" in msg:
            return "下載或轉錄失敗（訊息未帶細節）"
        return (msg[:60] or "（沒有錯誤訊息）")

    for reason, n in collections.Counter(bucket(i["error"]) for i in failed).most_common():
        put(f"  {n:4d}  {reason}")

    section("4. 最近 15 筆失敗明細")
    for i in failed[:15]:
        put(f"#{i['tid']:<5} {i['when'][:19]:<19} {i['type'] or '':<9} {i['video_id']:<12} {i['title'][:40]}")
        put(f"        -> {i['error'][:200] or '(無訊息)'}")
    return items


# ---------------------------------------------------------------- live probe
def probe(items: list, n: int) -> None:
    section(f"5. 實測 {n} 支失敗影片（yt-dlp 只抓 metadata）")
    cand = [i for i in items if i["status"] == "failed" and i["video_id"]][:n]
    if not cand:
        put("沒有可實測的 video_id")
        return
    if not shutil.which("yt-dlp"):
        put("找不到 yt-dlp")
        return
    for i in cand:
        url = f"https://www.youtube.com/watch?v={i['video_id']}"
        put(f"--- #{i['tid']} {i['video_id']} {i['title'][:40]}")
        t0 = time.time()
        out, err, rc = run(["yt-dlp", "--simulate", "--skip-download", "--no-warnings",
                            "--print", "%(id)s|%(title)s", url], timeout=120)
        put(f"    rc={rc}  {time.time()-t0:.1f}s  out={(out or '')[:100]!r}")
        if rc != 0:
            for line in err.splitlines()[-8:]:
                put("    " + line[:180])


def _yt_format() -> str:
    """跟 channel_watcher 用同一個格式字串（優先讀模組，讀不到才退回內建值）。"""
    try:
        sys.path.insert(0, str(ROOT))
        import channel_watcher as cw  # noqa: PLC0415
        return cw.YT_DL_FORMAT
    except Exception:  # noqa: BLE001
        return ("bestvideo[height<=1080][ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/"
                "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
                "best[ext=mp4]/best")


def download_probe(items: list, n: int, with_pipeline: bool = False,
                   ids: str = "") -> None:
    """真實下載 N 支失敗影片（simulate 只驗 metadata，抓不抓得到檔案是另一回事）。

    下載成功且 --with-pipeline 時，順便跑一次 run_pipeline.py --skip-cut，
    把 Pipeline 的 rc／stderr 尾巴印出來，一次定位是「下載」還是「Pipeline」掛掉。
    """
    import tempfile

    section(f"6. 實測下載 {n} 支失敗影片（真實下載）")
    cand = [i for i in items if i["status"] == "failed" and i["video_id"]]
    if ids:
        cand = [{"tid": "-", "video_id": v.strip(), "title": ""}
                for v in ids.split(",") if v.strip()]
    if not cand:
        put("沒有可實測的 video_id")
        return
    cand = cand[:n]
    if not shutil.which("yt-dlp"):
        put("找不到 yt-dlp")
        return

    fmt = _yt_format()
    put(f"格式字串: {fmt}")

    ok = 0
    for i in cand:
        vid = i["video_id"]
        url = f"https://www.youtube.com/watch?v={vid}"
        tdir = Path(tempfile.mkdtemp(prefix="dlprobe_"))
        dest = tdir / "v.mp4"
        put("")
        put(f"--- #{i['tid']} {vid} {i['title'][:40]}")
        cmd = ["yt-dlp", "--no-update", "-f", fmt, "--merge-output-format", "mp4",
               "--no-playlist", "--ignore-errors", "-o", str(dest), url]
        t0 = time.time()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=900)
            rc, stderr = r.returncode, (r.stderr or "")
        except Exception as e:  # noqa: BLE001
            rc, stderr = -1, f"{type(e).__name__}: {e}"
        elapsed = time.time() - t0
        files = [p for p in tdir.glob("v.*") if p.is_file()]
        size = sum(p.stat().st_size for p in files)
        put(f"    rc={rc}  {elapsed:.1f}s  檔案 {len(files)} 個  {size/2**20:.1f} MB")
        if files:
            for p in files:
                put(f"      {p.name}  {p.stat().st_size/2**20:.2f} MB")

        if size > 0 and rc == 0:
            ok += 1
            put("    → 下載成功")
            if with_pipeline:
                put("    Pipeline 實測（run_pipeline.py --skip-cut）…")
                slug = f"diag_{vid}"
                t1 = time.time()
                try:
                    pr = subprocess.run(
                        [sys.executable, "-X", "utf8", str(ROOT / "run_pipeline.py"),
                         str(files[0]), "--slug", slug, "--skip-cut"],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=2400)
                    prc, pout, perr = pr.returncode, (pr.stdout or ""), (pr.stderr or "")
                except Exception as e:  # noqa: BLE001
                    prc, pout, perr = -1, "", f"{type(e).__name__}: {e}"
                put(f"    Pipeline rc={prc}  {time.time()-t1:.0f}s")
                if perr.strip():
                    put("    Pipeline stderr 末 12 行:")
                    for line in perr.strip().splitlines()[-12:]:
                        put("      " + line[:200])
                if prc != 0:
                    put("    Pipeline stdout 末 12 行:")
                    for line in pout.strip().splitlines()[-12:]:
                        put("      " + line[:200])
                else:
                    srt = ROOT / "output" / slug / "字幕.srt"
                    put(f"    output/字幕.srt 存在={srt.exists()}")
        else:
            put("    stderr 末 15 行:")
            for line in stderr.strip().splitlines()[-15:]:
                put("      " + line[:200])
            # 格式問題的話列出可用格式
            if "format" in stderr.lower():
                fo, fe, frc = run(["yt-dlp", "--no-update", "-F", url], timeout=120)
                lines = [ln for ln in (fo or fe).splitlines() if ln.strip()]
                put(f"    可用格式（-F rc={frc}，前 20 行）:")
                for line in lines[:20]:
                    put("      " + line[:160])
        shutil.rmtree(tdir, ignore_errors=True)

    put("")
    put(f"下載成功 {ok}/{len(cand)} 支")
    if ok:
        put("→ 下載沒問題：失敗點在 Pipeline（跑 --with-pipeline 看 stderr）或後續步驟")
    else:
        put("→ 下載全部失敗：看上面 stderr，多半是 bot check／403／格式選擇")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="不限制筆數")
    ap.add_argument("--probe", type=int, default=0, help="實測 N 支失敗影片（只抓 metadata）")
    ap.add_argument("--download-probe", type=int, default=0, metavar="N",
                    help="真實下載 N 支失敗影片，抓真的錯誤訊息")
    ap.add_argument("--with-pipeline", action="store_true",
                    help="搭配 --download-probe：下載成功後順便跑 run_pipeline.py")
    ap.add_argument("--ids", default="", metavar="ID,ID",
                    help="搭配 --download-probe：直接指定 video_id（不看失敗清單）")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    env_facts()
    items = survey(0 if args.all else 200)
    if args.probe:
        probe(items, args.probe)
    if args.download_probe:
        download_probe(items, args.download_probe, with_pipeline=args.with_pipeline,
                       ids=args.ids)

    WORKING.mkdir(parents=True, exist_ok=True)
    out = WORKING / f"diag_youtube_{datetime.now():%Y%m%d_%H%M%S}.txt"
    out.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    put("")
    put(f"報告已寫入: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
