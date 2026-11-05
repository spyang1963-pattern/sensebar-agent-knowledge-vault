#!/usr/bin/env python3
"""
run_pipeline.py — YouTube 影片自動化生產線（一鍵搞定）
用法：
  python run_pipeline.py raw/某課程/原始.mp4
  python run_pipeline.py raw/某課程/原始.mp4 --title "自訂標題"
"""
import argparse
import os
import subprocess
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8") if getattr(sys.stdout, "buffer", None) is not None else sys.stdout

# 子行程（smart_cut／transcribe_groq／ffmpeg）也要說 UTF-8，否則父行程
# 用 encoding="utf-8" 讀管線會得到亂碼（詳見 config.py 的說明）。
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = Path(__file__).parent
SKILLS = ROOT / ".opencode" / "skills"
GROQ_KEY_FILE = Path.home() / ".groq_api_key"
VLC_PATH = r"C:\Program Files\VideoLAN\VLC\vlc.exe"


def run(cmd: list, desc: str, timeout: int = 600) -> bool:
    """執行指令，回傳是否成功。"""
    print(f"\n{'='*50}")
    print(f"[STEP] {desc}")
    print(f"[CMD] {' '.join(str(c) for c in cmd)}")
    print(f"{'='*50}")
    try:
        r = subprocess.run(cmd, timeout=timeout, cwd=str(ROOT))
        if r.returncode != 0:
            print(f"[ERR] {desc} 失敗（退出碼 {r.returncode}）")
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"[ERR] {desc} 逾時")
        return False
    except Exception as e:
        print(f"[ERR] {desc} 異常：{e}")
        return False


def load_groq_key() -> str:
    """載入 Groq API Key。"""
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key.strip()
    if GROQ_KEY_FILE.exists():
        return GROQ_KEY_FILE.read_text(encoding="utf-8").strip()
    print("[ERR] 找不到 Groq API Key")
    print("  請設定環境變數 GROQ_API_KEY")
    print("  或建立檔案 ~/.groq_api_key")
    sys.exit(1)


def _mean_volume_db(path) -> float | None:
    """ffmpeg volumedetect 平均音量（dB）；失敗回傳 None。"""
    import re
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
             "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=False)
        txt = (r.stderr or b"").decode("utf-8", errors="replace")
        m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", txt)
        return float(m.group(1)) if m else None
    except Exception:
        return None


def guard_audio(path) -> None:
    """轉錄前檢查音訊是否為靜音/壞檔。

    2026-11-02 事故：靜音 mp3 被送去 Whisper，產生日文與 AI 工具幻覺字幕。
    平均音量低於 -60 dB 一律中止（寧可失敗，也不要污染知識庫）。
    """
    mean = _mean_volume_db(path)
    print(f"[CHECK] 音訊平均音量：{mean if mean is not None else '未知'} dB")
    if mean is not None and mean < -60:
        sys.exit(f"[ERR] 音訊幾乎無聲（mean {mean:.1f} dB），中止轉錄；"
                 "請確認來源影片音軌或刪除 working/compressed 的壞快取")


def guard_transcript(raw_json: Path, duration_hint: float | None = None) -> None:
    """轉錄後檢查是否為幻覺/錯誤語言，避免錯誤逐字稿進入 KB。"""
    import json as _json
    try:
        data = _json.loads(raw_json.read_text(encoding="utf-8"))
    except Exception as e:
        sys.exit(f"[ERR] 無法讀取轉錄結果：{e}")
    text = data.get("text") or ""
    segs = data.get("segments") or []
    if not text.strip() or not segs:
        sys.exit("[ERR] 轉錄結果為空，中止")
    kana = sum(1 for ch in text if "\u3040" <= ch <= "\u30ff")
    han = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    ratio = kana / max(1, kana + han)
    print(f"[CHECK] 轉錄語言檢查：漢字 {han}、日文假名 {kana}（{ratio:.2%}）")
    if ratio > 0.02 or text.count("ご視聴ありがとうございました") >= 3:
        sys.exit("[ERR] 轉錄結果含大量日文/幻覺字串，判定失敗（不寫入知識庫）")
    dur = data.get("duration") or duration_hint
    if dur and len(segs) < dur / 120:
        print(f"[WARN] 轉錄段數偏少（{len(segs)} 段 / {dur:.0f} 秒），請人工抽查")



def main():
    ap = argparse.ArgumentParser(description="YouTube 影片自動化生產線")
    ap.add_argument("video", type=Path, help="原始影片路徑（如 raw/課程/原始.mp4）")
    ap.add_argument("--title", type=str, default=None, help="自訂標題（不指定則自動生成）")
    ap.add_argument("--slug", type=str, default=None, help="自訂資料夾代號（不指定則自動從路徑推斷）")
    ap.add_argument("--skip-cut", action="store_true", help="跳過智能剪輯")
    ap.add_argument("--skip-cover", action="store_true", help="跳過封面生成")
    ap.add_argument("--resume", action="store_true",
                    help="來源未更新時沿用既有 corrected.srt（重試不重複轉錄）")
    args = ap.parse_args()

    # 路徑設定
    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"[ERR] 找不到影片：{video}")

    # 使用影片的父目錄作為 working 和 output 的基礎
    # 如果影片在 working/{course}/{task_slug}/ 下，則使用該目錄
    # 否則使用 video.parent.name 作為 slug
    if args.slug:
        slug = args.slug
        working = ROOT / "working" / slug
    elif "working" in str(video.parent) and video.parent.parent.name != "working":
        # 影片在 working/{course}/{task_slug}/ 下
        working = video.parent
        slug = video.parent.name
    else:
        slug = video.parent.name
        working = ROOT / "working" / slug
    
    output = ROOT / "output" / slug
    working.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    trimmed = working / "trimmed.mp4"
    raw_json = working / "raw.json"
    reseg_srt = working / "resegmented.srt"
    corrected_srt = working / "corrected.srt"
    clean_txt = working / "clean.txt"

    print(f"影片：{video}")
    print(f"代號：{slug}")
    print(f"工作目錄：{working}")
    print(f"輸出目錄：{output}")

    # Step 1: 智能剪輯
    if not args.skip_cut:
        ok = run(
            [sys.executable, "-X", "utf8", str(SKILLS / "smart-cut" / "scripts" / "smart_cut.py"),
             str(video), "--out", str(trimmed)],
            "Step 1: 智能剪輯（去靜音）"
        )
        if not ok:
            sys.exit(1)
        src_video = trimmed
    else:
        src_video = video

    # Step 2~4：重試時可沿用既有字幕（--resume，避免同一支音訊重複送 Whisper）
    # 僅在 corrected.srt 比來源音訊新時才沿用；來源被重新壓縮/更新就重跑。
    reuse_srt = False
    if args.resume and corrected_srt.exists():
        try:
            reuse_srt = corrected_srt.stat().st_mtime >= Path(src_video).stat().st_mtime
        except OSError:
            reuse_srt = False
    if reuse_srt:
        print(f"[SKIP] 沿用既有字幕（來源未更新）：{corrected_srt}")
    else:
        # Step 2: 語音轉字幕
        guard_audio(src_video)
        groq_key = load_groq_key()
        os.environ["GROQ_API_KEY"] = groq_key

        ok = run(
            [sys.executable, "-X", "utf8", str(SKILLS / "audio-to-srt" / "scripts" / "transcribe_groq.py"),
             str(src_video), "--out", str(raw_json)],
            "Step 2: Groq Whisper 語音轉字幕"
        )
        if not ok:
            sys.exit(1)
        guard_transcript(raw_json)

        # Step 3: 重新分段
        ok = run(
            [sys.executable, "-X", "utf8", str(SKILLS / "audio-to-srt" / "scripts" / "resegment.py"),
             str(raw_json), "--out", str(reseg_srt), "--audio", str(src_video)],
            "Step 3: AI 重新分段"
        )
        if not ok:
            sys.exit(1)

        # Step 4: 術語校正
        ok = run(
            [sys.executable, "-X", "utf8", str(SKILLS / "audio-to-srt" / "scripts" / "apply_vocab.py"),
             str(reseg_srt), "--out", str(corrected_srt)],
            "Step 4: 術語校正"
        )
        if not ok:
            sys.exit(1)

    # Step 5: 驗證 SRT
    ok = run(
        [sys.executable, "-X", "utf8", str(SKILLS / "audio-to-srt" / "scripts" / "validate_srt.py"),
         "--raw", str(reseg_srt), "--clean", str(corrected_srt)],
        "Step 5: 字幕驗證"
    )
    if not ok:
        sys.exit(1)

    # Step 6: 產生純文字
    ok = run(
        [sys.executable, "-X", "utf8", str(SKILLS / "audio-to-srt" / "scripts" / "srt_to_txt.py"),
         str(corrected_srt), "--out", str(clean_txt)],
        "Step 6: 產生純文字"
    )
    if not ok:
        sys.exit(1)

    # Step 7: 產生封面
    if not args.skip_cover:
        ok = run(
            [sys.executable, str(SKILLS / "cover-image" / "draw_free.py"),
             "minimalist stock market candlestick chart, soft pastel tones, clean white desk with notebook, educational aesthetic, no people, no text",
             "--width", "1280", "--height", "720",
             "--name", "cover", "--outdir", str(output)],
            "Step 7: 產生封面（Pollinations.AI 免費）"
        )

    # Step 8: 複製到輸出目錄
    print(f"\n{'='*50}")
    print("[STEP] Step 8: 輸出檔案")
    print(f"{'='*50}")

    import shutil
    final_srt = output / "字幕.srt"
    shutil.copy2(corrected_srt, final_srt)
    print(f"[OK] {final_srt}")

    # 注意：--skip-cut 時 src_video 是音訊（worker 傳入 working/compressed/*.mp3），
    # 不可再複製成 .mp4（2026-11-02 事故：輸出目錄的「剪輯後.mp4」其實是靜音 mp3）。
    src_suffix = Path(src_video).suffix.lower()
    if src_suffix in (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"):
        final_audio = output / "音訊.mp3"
        shutil.copy2(src_video, final_audio)
        print(f"[OK] {final_audio}（無剪輯，僅音訊）")
        final_media = final_audio
        media_label = "音訊"
    else:
        final_video = output / "剪輯後.mp4"
        shutil.copy2(src_video, final_video)
        print(f"[OK] {final_video}")
        final_media = final_video
        media_label = "影片"

    # 產生 metadata
    txt_content = clean_txt.read_text(encoding="utf-8")[:500]
    metadata = output / "metadata.md"
    metadata.write_text(f"# YouTube Metadata\n\n## 影片\n{slug}\n\n## 內容摘要\n{txt_content}...\n\n## 字幕\n{final_srt.name}\n", encoding="utf-8")
    print(f"[OK] {metadata}")

    # 完成
    print(f"\n{'='*50}")
    print("[DONE] 全部完成！")
    print(f"{'='*50}")
    print(f"\n輸出目錄：{output}")
    print(f"  字幕：{final_srt.name}")
    print(f"  {media_label}：{final_media.name}")
    print(f"\n查詢知識庫：")
    print(f"  python knowledge-base/kb_query.py \"關鍵字\" --srt \"{final_srt}\" --video \"{final_media}\"")


if __name__ == "__main__":
    main()
