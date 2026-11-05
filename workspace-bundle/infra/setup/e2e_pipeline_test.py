#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
e2e_pipeline_test.py — 影片產線端到端自測（會真的跑一次 run_pipeline）
======================================================================
目的：驗證「音訊分支」的實際行為，而不是只靠編譯通過。

涵蓋的三個歷史事故：
  1. 任務 1921/1923：`--skip-cut` 走音訊分支時，結尾仍印 `final_video.name`
     → `UnboundLocalError`，所有步驟都成功卻在最後一行崩掉、worker 重試 3 次。
  2. 重試時重複送 Whisper：`--resume` 必須在來源未更新時直接沿用 `corrected.srt`。
  3. 音訊被誤命名成 `剪輯後.mp4`：`--skip-cut` 的輸出一律只能是 `音訊.mp3`。

用法（在任一已部署的機器）：
  python -X utf8 workspace-bundle\\infra\\setup\\e2e_pipeline_test.py
  python -X utf8 ... --keep      # 保留測試檔（可人工看 output 內容）

成本：Groq Whisper 一次（約數秒音訊）＋本機 CPU。不會呼叫 Gemini。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SLUG = "_e2e_pipeline_test"
SPEECH = ("This is the pipeline self test. One two three four five six seven. "
          "Checking the audio branch of the run pipeline.")

results: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> bool:
    results.append((ok, name, detail))
    mark = "✅" if ok else "❌"
    print(f"  {mark} {name}" + (f"  — {detail}" if detail else ""))
    return ok


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    p = subprocess.run(cmd, cwd=str(cwd or ROOT), capture_output=True, env=env)
    out = (p.stdout + p.stderr).decode("utf-8", errors="replace")
    return p.returncode, out


def make_audio(dst: Path) -> bool:
    """用 ffmpeg 內建的 flite TTS 產生一段真人語音（免 API、免網路）。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    rc, out = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                   "-f", "lavfi", "-i", f"flite=text='{SPEECH}':voice=slt",
                   str(dst)])
    if rc != 0 or not dst.exists():
        print(f"[ERR] ffmpeg flite 產生語音失敗：{out[-400:]}")
        return False
    # 靜音檔會被 guard_audio 攔下，先自己確認音量
    rc, out = run(["ffmpeg", "-hide_banner", "-i", str(dst),
                   "-af", "volumedetect", "-f", "null", "NUL"])
    mean = ""
    for line in out.splitlines():
        if "mean_volume" in line:
            mean = line.split("mean_volume:")[-1].strip()
    print(f"  測試音訊：{dst.name}（{dst.stat().st_size // 1024} KB，mean_volume {mean or '?'}）")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="影片產線端到端自測")
    ap.add_argument("--keep", action="store_true", help="保留測試檔不清理")
    ap.add_argument("--slug", default=SLUG)
    args = ap.parse_args()

    src_dir = ROOT / "working" / "_e2e_src"
    work = ROOT / "working" / args.slug
    outp = ROOT / "output" / args.slug
    audio = src_dir / "e2e_voice.mp3"

    print("=" * 56)
    print("  影片產線端到端自測（會真的跑一次 run_pipeline）")
    print("=" * 56)

    # 清掉上次殘留，確保是全新一輪
    for d in (src_dir, work, outp):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)

    print("\n[1/3] 產生測試音訊（ffmpeg flite）")
    if not make_audio(audio):
        return 1

    print("\n[2/3] 第一次跑：--skip-cut（走音訊分支 = 任務 1921/1923 崩潰的那條路）")
    t0 = time.time()
    rc, out = run([sys.executable, "-X", "utf8", "run_pipeline.py", str(audio),
                   "--skip-cut", "--skip-cover", "--slug", args.slug])
    took = time.time() - t0
    tail = "\n".join(out.strip().splitlines()[-12:])
    check(rc == 0, "run_pipeline 結束碼 0", f"{took:.0f}s")
    if rc != 0:
        print("\n--- 最後 12 行輸出 ---")
        print(tail)
        print("\n（UnboundLocalError: final_video 就是任務 1921/1923 的 bug）")

    srt = outp / "字幕.srt"
    mp3 = outp / "音訊.mp3"
    mp4 = outp / "剪輯後.mp4"
    meta = outp / "metadata.md"

    ok_srt = srt.exists() and srt.stat().st_size > 20
    check(ok_srt, "輸出 字幕.srt", f"{srt.stat().st_size} bytes" if srt.exists() else "缺少")
    check(mp3.exists(), "輸出 音訊.mp3", f"{mp3.stat().st_size // 1024} KB" if mp3.exists() else "缺少")
    check(not mp4.exists(), "沒有誤命的 剪輯後.mp4", "音訊分支不應產生 mp4" if mp4.exists() else "正確")
    check(meta.exists(), "輸出 metadata.md")

    if ok_srt:
        body = srt.read_text(encoding="utf-8", errors="replace")
        text_lines = [ln for ln in body.splitlines()
                      if ln.strip() and not ln.strip().isdigit() and "-->" not in ln]
        check(bool(text_lines), "字幕有實際文字", f"{len(text_lines)} 行")
        preview = " / ".join(text_lines[:2])[:110]
        print(f"      字幕預覽：{preview}")

    print("\n[3/3] 第二次跑：加上 --resume（模擬 worker 失敗重試）")
    raw_json = work / "raw.json"
    srt_before = srt.stat().st_mtime if srt.exists() else 0
    raw_before = raw_json.stat().st_mtime if raw_json.exists() else 0

    t0 = time.time()
    rc2, out2 = run([sys.executable, "-X", "utf8", "run_pipeline.py", str(audio),
                     "--skip-cut", "--skip-cover", "--resume", "--slug", args.slug])
    took2 = time.time() - t0

    skip_msg = "[SKIP] 沿用既有字幕" in out2
    check(rc2 == 0, "重試結束碼 0", f"{took2:.0f}s")
    check(skip_msg, "--resume 跳過轉錄", "[SKIP] 沿用既有字幕")
    check(not raw_json.exists() or raw_json.stat().st_mtime == raw_before,
          "沒有重送 Whisper（raw.json 未變）",
          f"{raw_before:.0f} → {raw_json.stat().st_mtime:.0f}" if raw_json.exists() else "無 raw.json")
    check(not (outp / "剪輯後.mp4").exists(), "重跑後仍沒有 剪輯後.mp4")
    if srt.exists() and srt_before and srt.stat().st_mtime < srt_before:
        check(False, "字幕檔未被回退", "mtime 比第一次舊")

    if not args.keep:
        for d in (src_dir, work, outp):
            shutil.rmtree(d, ignore_errors=True)
        print("\n  已清理測試檔（--keep 可保留）")
    else:
        print(f"\n  測試檔保留：{work} / {outp}")

    failed = [r for r in results if not r[0]]
    print("\n" + "=" * 56)
    print(f"  結果：{len(results) - len(failed)}/{len(results)} 通過")
    if failed:
        for _, name, detail in failed:
            print(f"    ❌ {name}  {detail}")
    print("=" * 56)
    return len(failed)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
