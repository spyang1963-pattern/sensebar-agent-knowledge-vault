#!/usr/bin/env python3
"""透過 Groq API 做 STT，產出 word-level 時間碼 JSON。"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import urllib.request
import urllib.error

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
SIZE_LIMIT_MB = 24.0


def compress_audio(src: Path) -> Path:
    if not shutil.which("ffmpeg"):
        sys.exit("[ERR] 檔案太大需要 ffmpeg 壓縮，但找不到 ffmpeg")
    tmp = Path(tempfile.gettempdir()) / f"audio-to-srt-{os.getpid()}.mp3"
    cmd = [
        "ffmpeg", "-i", str(src),
        "-ac", "1", "-ar", "16000", "-b:a", "32k",
        "-y", str(tmp),
    ]
    print("[INFO] 壓縮中（16kHz mono 32kbps）...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"[ERR] ffmpeg 壓縮失敗：\n{result.stderr[-500:]}")
    new_mb = tmp.stat().st_size / 1024 / 1024
    print(f"[INFO] 壓縮完成：{new_mb:.1f} MB")
    return tmp


def load_api_key() -> str:
    env_key = os.environ.get("GROQ_API_KEY")
    if env_key:
        return env_key.strip()
    key_file = Path.home() / ".groq_api_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    sys.exit("[ERR] 找不到 Groq API Key（環境變數 GROQ_API_KEY 或 ~/.groq_api_key）")


def build_multipart(audio_path: Path, model: str, prompt: str) -> tuple[bytes, str]:
    boundary = "----GroqBoundary7MA4YWxkTrZu0gW"
    crlf = b"\r\n"
    parts: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        parts.append(f"--{boundary}".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        parts.append(b"")
        parts.append(value.encode("utf-8"))

    add_field("model", model)
    add_field("response_format", "verbose_json")
    add_field("timestamp_granularities[]", "word")
    add_field("timestamp_granularities[]", "segment")
    add_field("language", "zh")
    if prompt:
        add_field("prompt", prompt)

    safe_name = "audio" + audio_path.suffix.lower()
    parts.append(f"--{boundary}".encode())
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{safe_name}"'.encode("utf-8")
    )
    parts.append(b"Content-Type: audio/mpeg")
    parts.append(b"")
    parts.append(audio_path.read_bytes())

    parts.append(f"--{boundary}--".encode())
    parts.append(b"")

    body = crlf.join(parts)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--model", default="whisper-large-v3-turbo")
    ap.add_argument(
        "--prompt",
        default=(
            "以下為繁體中文口語內容。專有名詞：Claude、Claude Code、"
            "NotebookLM、GPT-Image 2、ChatGPT、OpenAI、Gemini、Groq、"
            "Whisper、GitHub、Obsidian。"
        ),
    )
    ap.add_argument("--chunk-min", type=float, default=15.0,
                    help="超過 24MB 時每段切 N 分鐘（預設 15）")
    args = ap.parse_args()

    if not args.audio.exists():
        sys.exit(f"[ERR] 找不到音訊檔：{args.audio}")

    out = args.out or args.audio.with_suffix(".groq.json")
    api_key = load_api_key()

    size_mb = args.audio.stat().st_size / 1024 / 1024
    print(f"[INFO] 檔案大小 {size_mb:.1f} MB，模型 {args.model}")

    upload_path = args.audio
    tmp_compressed: Path | None = None
    if size_mb > SIZE_LIMIT_MB:
        tmp_compressed = compress_audio(args.audio)
        upload_path = tmp_compressed
        new_mb = tmp_compressed.stat().st_size / 1024 / 1024
        if new_mb > SIZE_LIMIT_MB:
            upload_path = None  # 標記需要切段
        else:
            print(f"[INFO] 壓縮後 {new_mb:.1f} MB")

    # 切段轉錄：超過 24MB 且單次無法縮至上限內 → 分段上傳後合併
    if upload_path is None:
        final = transcribe_in_chunks(tmp_compressed, args.model, args.prompt,
                                     api_key, args.chunk_min)
    else:
        body, content_type = build_multipart(upload_path, args.model, args.prompt)
        final = transcribe_once(body, content_type, api_key)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")

    n_words = len(final.get("words", []))
    n_segs = len(final.get("segments", []))
    dur = final.get("duration", 0)
    print(f"[OK] 輸出 {out}（{n_words} 詞 / {n_segs} 段 / {dur:.1f}s）")

    if tmp_compressed is not None and tmp_compressed.exists():
        try:
            tmp_compressed.unlink()
        except OSError:
            pass
    return 0


def transcribe_once(body: bytes, content_type: str, api_key: str) -> dict:
    req = urllib.request.Request(
        GROQ_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": content_type,
            "User-Agent": "audio-to-srt/1.0 (+python-urllib)",
            "Accept": "application/json",
        },
        method="POST",
    )

    print("[INFO] 上傳中...")
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        sys.exit(f"[ERR] Groq API 錯誤 {e.code}：{err_body}")
    except urllib.error.URLError as e:
        sys.exit(f"[ERR] 網路錯誤：{e}")
    return data


def transcribe_in_chunks(src: Path, model: str, prompt: str, api_key: str,
                         chunk_min: float) -> dict:
    """超過 24MB 的音訊：用 ffmpeg 切成 N 分鐘一段，逐段轉錄後合併"""
    if not shutil.which("ffmpeg"):
        sys.exit("[ERR] 切段需要 ffmpeg，但找不到")
    duration = probe_duration(src)
    chunk_sec = chunk_min * 60
    if duration <= 0:
        sys.exit("[ERR] 無法取得音訊時長")
    n_chunks = max(1, int(duration // chunk_sec) + (1 if duration % chunk_sec else 0))
    print(f"[INFO] 音訊 {duration:.0f}s → 切 {n_chunks} 段（每段 {chunk_min} 分鐘）")

    results: dict | None = None
    for i in range(n_chunks):
        start = i * chunk_sec
        seg = Path(tempfile.gettempdir()) / f"audio-to-srt-seg-{os.getpid()}-{i}.mp3"
        cmd = [
            "ffmpeg", "-y", "-ss", f"{start}", "-i", str(src),
            "-t", str(min(chunk_sec, duration - start)),
            "-ac", "1", "-ar", "16000", "-b:a", "32k", str(seg),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"[ERR] ffmpeg 切段失敗：\n{r.stderr[-500:]}")
        seg_mb = seg.stat().st_size / 1024 / 1024
        if seg_mb > SIZE_LIMIT_MB:
            sys.exit(f"[ERR] 第 {i+1} 段仍 {seg_mb:.1f} MB，請縮短 --chunk-min")
        print(f"[INFO] 轉錄段 {i+1}/{n_chunks}（{start:.0f}s 起，{seg_mb:.1f} MB）...")
        body, ct = build_multipart(seg, model, prompt)
        data = transcribe_once(body, ct, api_key)
        seg.unlink(missing_ok=True)
        results = merge_results(results, data, offset=start)
    return results


def probe_duration(path: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return 0.0
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def merge_results(base: dict | None, new: dict, offset: float) -> dict:
    """合併分段轉錄結果；時序碼平移 offset 秒"""
    if base is None:
        return new
    out = dict(base)
    out["text"] = (out.get("text", "") + " " + new.get("text", "")).strip()
    shifted_words = [dict(w, start=w.get("start", 0) + offset, end=w.get("end", 0) + offset)
                     for w in new.get("words", [])]
    out["words"] = list(out.get("words", [])) + shifted_words
    shifted_segs = [dict(s, start=s.get("start", 0) + offset, end=s.get("end", 0) + offset)
                    for s in new.get("segments", [])]
    out["segments"] = list(out.get("segments", [])) + shifted_segs
    out["duration"] = offset + new.get("duration", 0)
    return out


if __name__ == "__main__":
    sys.exit(main())
