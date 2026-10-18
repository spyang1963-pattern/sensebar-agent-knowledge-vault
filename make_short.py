#!/usr/bin/env python3
"""make_short.py - 免費 AI 自動生成影片工作流（圈 2 一鍵版）

一條指令，把一份「分鏡腳本 JSON」變成一支可上架的直式短片：
  腳本 -> Edge-TTS 配音 -> Pollinations 生圖 -> ffmpeg 運鏡組裝
       -> 自動字幕 -> 上架包（影片 / 字幕 / 封面 / metadata）

完全免費、可腳本化、可批次。不依賴任何付費 API。

用法：
  python make_short.py --script shorts/ai-video.json --out output/shorts/ai-video

分鏡腳本 JSON 格式：
{
  "title": "影片標題",
  "voice": "zh-TW-HsiaoChenNeural",
  "style": "flat vector illustration, dark navy background",   // 可選，附加到每張圖 prompt
  "scenes": [
    {"narration": "旁白台詞", "image": "english image prompt", "zoom": "in"},
    {"narration": "...", "image_file": "real/photo.jpg", "zoom": "out"}   // 用實拍照取代生圖
  ]
}
"""
import argparse
import asyncio
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import edge_tts
from PIL import Image

DEFAULT_VOICE = "zh-TW-HsiaoChenNeural"
DEFAULT_STYLE = "flat vector illustration, clean minimal design, dark navy background, soft neon accents"


def log(msg):
    print(f"[make_short] {msg}", flush=True)


def run(cmd, cwd=None):
    """Run a command, raise on failure with the last stderr lines."""
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        out = p.stdout.decode("utf-8", errors="replace")
        tail = "\n".join(out.strip().splitlines()[-12:])
        raise RuntimeError(f"命令失敗 ({p.returncode}): {' '.join(cmd[:3])} ...\n{tail}")
    return p.stdout.decode("utf-8", errors="replace")


def probe_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(path)])
    return float(out.strip())


async def tts_scene(text, voice, mp3_path):
    """Generate narration mp3 + return sentence-boundary timings (seconds)."""
    communicate = edge_tts.Communicate(text, voice)
    bounds = []
    with open(mp3_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] in ("SentenceBoundary", "WordBoundary"):
                bounds.append({
                    "start": chunk["offset"] / 1e7,
                    "dur": chunk["duration"] / 1e7,
                    "text": chunk["text"],
                })
    return bounds


def fetch_image(prompt, w, h, out_png, seed=None):
    """Pollinations.AI 免費生圖；含重試退避（匿名有速率限制）。失敗回傳 None。"""
    import time
    encoded = urllib.parse.quote(prompt)
    base = (f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={w}&height={h}&model=flux")
    if seed is not None:
        base += f"&seed={seed}"
    delays = [8, 15, 25, 40, 60]
    for attempt, wait in enumerate([0] + delays):
        if wait:
            log(f"  生圖被限流，{wait}s 後重試（第 {attempt} 次）...")
            time.sleep(wait)
        try:
            req = urllib.request.Request(base, headers={"User-Agent": "make-short/1.0"})
            with urllib.request.urlopen(req, timeout=150) as resp:
                data = resp.read()
            if len(data) < 5000:
                continue
            out_png.write_bytes(data)
            return out_png
        except Exception as e:
            log(f"  生圖嘗試 {attempt} 失敗：{e}")
    log("  生圖最終失敗（改用後備圖）")
    return None


def fallback_image(title, subtitle, w, h, out_png):
    """無網路時的後備：用 PIL 畫一張漸層資訊卡。"""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (w, h), (16, 22, 43))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(16 + 30 * t), int(22 + 20 * t), int(43 + 60 * t)))
    font_path = r"C:\Windows\Fonts\msjh.ttc"
    try:
        f_title = ImageFont.truetype(font_path, int(h * 0.055))
        f_sub = ImageFont.truetype(font_path, int(h * 0.036))
    except Exception:
        f_title = f_sub = ImageFont.load_default()
    for i, line in enumerate(_wrap(title, 12)):
        d.text((w * 0.08, h * 0.30 + i * h * 0.08), line, font=f_title, fill=(255, 255, 255))
    for i, line in enumerate(_wrap(subtitle, 18)):
        d.text((w * 0.08, h * 0.62 + i * h * 0.055), line, font=f_sub, fill=(160, 210, 255))
    img.save(out_png)
    return out_png


def _wrap(text, n):
    return [text[i:i + n] for i in range(0, len(text), n)] or [""]


def build_clip(image, out_mp4, dur, fps, w, h, zoom):
    """單一鏡頭：靜圖 + Ken Burns 運鏡，輸出無聲影片。"""
    frames = max(1, round(dur * fps))
    if zoom == "out":
        zexpr = f"{'1.22'}-0.22*on/{frames}"
    else:
        zexpr = f"1.0+0.22*on/{frames}"
    vf = (
        f"scale={2*w}:{2*h}:force_original_aspect_ratio=increase,"
        f"crop={2*w}:{2*h},"
        f"zoompan=z='{zexpr}':d={frames}"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps},"
        f"format=yuv420p"
    )
    run(["ffmpeg", "-y", "-i", str(image), "-vf", vf, "-frames:v", str(frames),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", str(out_mp4)])


def build_audio(src_mp3, out_m4a, dur):
    run(["ffmpeg", "-y", "-i", str(src_mp3),
         "-af", f"apad", "-t", f"{dur:.3f}",
         "-c:a", "aac", "-b:a", "128k", str(out_m4a)])


def mix_bgm(video, bgm, out_mp4, vol):
    """把背景音樂（循環）混入影片音軌，旁白維持原音量。"""
    run(["ffmpeg", "-y", "-i", str(video), "-stream_loop", "-1", "-i", str(bgm),
         "-filter_complex",
         f"[1:a]volume=1.0[bg];[0:a][bg]amix=inputs=2:duration=first:"
         f"weights='1 {vol}':normalize=0[a]",
         "-map", "0:v", "-map", "[a]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(out_mp4)])


def concat_scenes(clips, audios, out_mp4, fps, transition, transitions=None):
    """xfade 串接影片 + acrossfade 串接音訊（兩者同步縮短）。

    transitions: 可選，轉場清單或單一字串（如 ["fade","smoothleft",...]），
                 逐一輪替使用；預設 "fade"。
    """
    n = len(clips)
    durs = [probe_duration(c) for c in clips]
    if transitions is None:
        trans_list = ["fade"]
    elif isinstance(transitions, str):
        trans_list = [transitions]
    else:
        trans_list = list(transitions) or ["fade"]
    cmd = ["ffmpeg", "-y"]
    for c in clips:
        cmd += ["-i", str(c)]
    for a in audios:
        cmd += ["-i", str(a)]

    parts = []
    # video xfade chain
    if n == 1:
        vlab = "0:v"
    else:
        prev = "0:v"
        acc = durs[0]
        for k in range(1, n):
            offset = acc - transition
            lab = f"v{k}"
            tr = trans_list[(k - 1) % len(trans_list)]
            parts.append(f"[{prev}][{k}:v]xfade=transition={tr}:duration={transition}"
                         f":offset={offset:.3f}[{lab}]")
            acc = offset + durs[k]
            prev = lab
        vlab = prev
    # audio acrossfade chain
    if n == 1:
        alab = f"{n}:a"
    else:
        prev = f"{n}:a"
        for k in range(1, n):
            lab = f"a{k}"
            parts.append(f"[{prev}][{n + k}:a]acrossfade=d={transition}:c1=tri:c2=tri[{lab}]")
            prev = lab
        alab = prev

    filter_complex = ";".join(parts)
    cmd += ["-filter_complex", filter_complex, "-map", f"[{vlab}]", "-map", f"[{alab}]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-r", str(fps), "-c:a", "aac", "-b:a", "128k", str(out_mp4)]
    run(cmd)


def build_srt(scenes_meta, srt_path, transition):
    """依句級時間碼 + 各鏡頭在成品時間軸的起點，輸出 SRT。"""
    def ts(sec):
        ms = int(round(sec * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines, idx = [], 1
    timeline_start = 0.0
    for si, meta in enumerate(scenes_meta):
        bounds = meta["bounds"] or [{"start": 0.0, "dur": meta["dur"], "text": meta["text"]}]
        scene_end = timeline_start + meta["dur"]
        for b in bounds:
            start = timeline_start + b["start"]
            end = min(scene_end, start + max(b["dur"], 0.6))
            txt = re.sub(r"\s+", " ", b["text"]).strip()
            if not txt:
                continue
            lines += [str(idx), f"{ts(start)} --> {ts(end)}", txt, ""]
            idx += 1
        timeline_start += meta["dur"] - transition
    srt_path.write_text("\n".join(lines), encoding="utf-8")
    return srt_path


def burn_subtitles(video, srt_name, out_mp4, workdir):
    style = ("FontName=Microsoft JhengHei,FontSize=12,PrimaryColour=&H00FFFFFF,"
             "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
             "MarginV=40,Alignment=2")
    run(["ffmpeg", "-y", "-i", str(Path(video).resolve()),
         "-vf", f"subtitles={srt_name}:force_style='{style}'",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "copy", str(Path(out_mp4).resolve())], cwd=workdir)


def _film_meta(script, script_path, title):
    """Indexable output info (metadata spine).

    Returns {stem, pack, topic_id, style, version, date, title}. Finds
    engine/core/naming.py in an ancestor (or its immediate subdirs);
    falls back to the plain title when unavailable.
    """
    import sys
    for parent in Path(__file__).resolve().parents:
        cands = [parent / "engine" / "core" / "naming.py"]
        cands += list(parent.glob("*/engine/core/naming.py"))
        for cand in cands:
            if cand.exists():
                sys.path.insert(0, str(cand.parent.parent))
                try:
                    from core import naming as ename
                    meta = ename.parse(Path(script_path).stem)
                    ver = meta["version"] if meta else (script.get("version") or 1)
                    tid = meta["id"] if meta else (script.get("topic_id") or Path(script_path).stem)
                    stl = meta["style"] if meta else (script.get("style") or None)
                    return ename.film_fields(stl, tid, title, ver, pack=script.get("pack"))
                except Exception:
                    pass
    return {"stem": title, "pack": script.get("pack"), "topic_id": script.get("topic_id"),
            "style": script.get("style"), "version": script.get("version") or 1,
            "date": None, "title": title}

def main():
    ap = argparse.ArgumentParser(description="免費 AI 自動生成影片（一鍵）")
    ap.add_argument("--script", required=True, help="分鏡腳本 JSON 路徑")
    ap.add_argument("--out", required=True, help="輸出目錄")
    ap.add_argument("--voice", default=None, help="Edge-TTS 語音（預設讀 JSON 或 zh-TW-HsiaoChenNeural）")
    ap.add_argument("--w", type=int, default=1080, help="寬度（預設 1080）")
    ap.add_argument("--h", type=int, default=1920, help="高度（預設 1920）")
    ap.add_argument("--fps", type=int, default=30, help="影格率（預設 30）")
    ap.add_argument("--transition", type=float, default=0.5, help="轉場秒數（預設 0.5）")
    ap.add_argument("--tail", type=float, default=0.6, help="每鏡頭結尾留白秒數（預設 0.6）")
    ap.add_argument("--no-subs", action="store_true", help="不燒字幕")
    ap.add_argument("--bgm", default=None, help="背景音樂檔（wav/mp3），提供即混入")
    ap.add_argument("--bgm-volume", type=float, default=0.18, help="背景音樂音量比例（預設 0.18）")
    ap.add_argument("--reuse", action="store_true", help="重用已存在的語音/圖片素材（加速迭代）")
    args = ap.parse_args()

    script = json.loads(Path(args.script).read_text(encoding="utf-8"))
    title = script.get("title", "未命名短片")
    info = _film_meta(script, args.script, title)
    stem = info["stem"]
    voice = args.voice or script.get("voice", DEFAULT_VOICE)
    style = script.get("style", DEFAULT_STYLE)
    scenes = script["scenes"]

    out = Path(args.out)
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    log(f"標題：{title}｜鏡頭數：{len(scenes)}｜語音：{voice}")

    clips, audios, metas = [], [], []
    for i, sc in enumerate(scenes):
        narration = sc["narration"]
        img_prompt = sc.get("image", title)
        full_prompt = f"{img_prompt}, {style}" if style else img_prompt
        zoom = sc.get("zoom", "in" if i % 2 == 0 else "out")
        log(f"[{i+1}/{len(scenes)}] {narration[:24]}...")

        mp3 = assets / f"tts_{i}.mp3"
        bjson = assets / f"bounds_{i}.json"
        if args.reuse and mp3.exists() and bjson.exists():
            bounds = json.loads(bjson.read_text(encoding="utf-8"))
        else:
            bounds = asyncio.run(tts_scene(narration, voice, mp3))
            bjson.write_text(json.dumps(bounds, ensure_ascii=False), encoding="utf-8")
        d = probe_duration(mp3)

        frames = max(1, round((d + args.tail) * args.fps))
        scene_dur = frames / args.fps

        img = assets / f"img_{i}.png"
        if not (args.reuse and img.exists()):
            src_file = sc.get("image_file")
            if src_file:
                src = Path(src_file)
                if not src.is_absolute():
                    src = Path(args.script).resolve().parent / src
                if src.exists():
                    log(f"  使用實拍照：{src.name}")
                    Image.open(src).convert("RGB").save(img)
                else:
                    log(f"  實拍照不存在，改生成：{src}")
                    if not fetch_image(full_prompt, args.w, args.h, img):
                        fallback_image(title, narration, args.w, args.h, img)
            else:
                log("  生圖中...")
                if not fetch_image(full_prompt, args.w, args.h, img):
                    fallback_image(title, narration, args.w, args.h, img)

        clip = assets / f"clip_{i}.mp4"
        build_clip(img, clip, scene_dur, args.fps, args.w, args.h, zoom)
        aud = assets / f"aud_{i}.m4a"
        build_audio(mp3, aud, scene_dur)

        clips.append(clip)
        audios.append(aud)
        metas.append({"dur": probe_duration(clip), "bounds": bounds, "text": narration})

    log("串接鏡頭 + 轉場...")
    silent = assets / "timeline.mp4"
    concat_scenes(clips, audios, silent, args.fps, args.transition)

    video_for_subs = silent
    if args.bgm:
        log(f"混入背景音樂（音量 {args.bgm_volume}）...")
        mixed = assets / "timeline_mix.mp4"
        mix_bgm(silent, Path(args.bgm), mixed, args.bgm_volume)
        video_for_subs = mixed

    srt = out / f"{stem}.srt"
    build_srt(metas, srt, args.transition)

    final = out / f"{stem}.mp4"
    if args.no_subs:
        run(["ffmpeg", "-y", "-i", str(video_for_subs), "-c", "copy", str(final)])
    else:
        log("燒字幕...")
        burn_subtitles(video_for_subs, srt.name, final, out)

    # 字幕已燒進影片；把外掛 .srt 移到子資料夾，避免播放器自動載入造成「雙字幕」
    subs_dir = out / "subs"
    subs_dir.mkdir(exist_ok=True)
    published_srt = subs_dir / srt.name
    if srt.exists():
        srt.replace(published_srt)

    cover = out / "封面.png"
    try:
        cover.write_bytes((assets / "img_0.png").read_bytes())
    except Exception:
        pass

    meta = {
        "pack": info.get("pack"), "topic_id": info.get("topic_id"),
        "style": info.get("style"), "version": info.get("version"),
        "date": info.get("date"), "title": title,
        "voice": voice,
        "size": f"{args.w}x{args.h}",
        "duration_sec": round(probe_duration(final), 1),
        "scenes": len(scenes),
        "video": final.name,
        "subtitle": f"subs/{srt.name}",
        "cover": cover.name if cover.exists() else None,
    }
    (out / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    log(f"完成！成品：{final}")
    log(f"  時長 {meta['duration_sec']}s｜{meta['size']}｜字幕 {srt.name}｜封面 {meta['cover']}")


if __name__ == "__main__":
    main()
