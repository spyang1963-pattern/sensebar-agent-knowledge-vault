"""make_dialog.py - 對話劇渲染器 v3（合成動態強化，全免費）

v2 → v3 改良重點（不花一毛錢，全靠 PIL 逐格合成）：
  1) 多層視差背景：遠景大色塊、近景中色塊、漂浮光斑（bokeh）各自不同速度漂移，
     每格重繪 → 畫面有縱深、有生命。
  2) 彈性進場：發言者 pop-in 帶「超彈（overshoot）」＋輕微旋轉 + 呼吸 + 驚嚇抖動。
  3) 氣泡超彈：氣泡 pop-in 帶彈性回彈；情緒符號有爆發放大。
  4) 轉場多樣化：不再是單一 fade，改用 smoothleft/smoothup/circleclose/radial/… 輪替。
  5) 免費合成音效：氣泡出現「啵」、鏡頭轉場「咻」——用 ffmpeg 現場合成，無需素材。
  6) 配音有戲（沿用 v2）：依角色＋情緒調語速/音高。

用法：
  python make_dialog.py --script scripts/x.json --out output/x --bgm assets/bgm_playful.wav
  python make_dialog.py --script scripts/x.json --out output/x --reuse --no-sfx
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import subprocess
import sys
from pathlib import Path

LEZHI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "D:/AI-Agent-Workspace")

import make_short as ms  # noqa: E402
import edge_tts  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

W, H = 1080, 1920
FONT = r"C:\Windows\Fonts\msjh.ttc"
FONTB = r"C:\Windows\Fonts\msjhbd.ttc"
SAGE = (117, 137, 133)
INK = (21, 26, 27)
PAPER = (252, 252, 252)

NAME = {"ren": "阿忍", "le": "小樂"}
SIDE = {"ren": "left", "le": "right"}
XC = {"ren": 300, "le": 800}
VOICE = {"ren": "zh-TW-YunJheNeural", "le": "zh-TW-HsiaoYuNeural"}
EXPRS = ("normal", "surprise", "happy", "worry", "smug")

VOICE_BASE = {"ren": (0, -8), "le": (6, 8)}  # (rate%, pitch Hz)
EXPR_MOD = {"normal": (0, 0), "surprise": (16, 16), "happy": (12, 12),
            "worry": (-10, -6), "smug": (-4, -2)}
EMOTE = {"surprise": ("！", (232, 106, 92)), "worry": ("…", (96, 150, 190)),
         "happy": ("♪", (232, 176, 72)), "smug": ("★", (214, 168, 90)),
         "normal": (None, None)}
BG = [(238, 242, 240), (236, 233, 226), (232, 240, 236), (240, 236, 231), (235, 238, 243)]
BANDS = [(226, 234, 230), (232, 226, 216), (222, 236, 228), (236, 230, 222), (228, 232, 240)]
TRANSITIONS = ["fade", "smoothleft", "smoothup", "circleclose", "radial",
               "smoothright", "circleopen", "slideup"]


def _font(sz, bold=False):
    try:
        return ImageFont.truetype(FONTB if bold else FONT, sz)
    except Exception:
        return ImageFont.load_default()


_cache: dict = {}


def _sprite(char_dir: Path, who, expr, height):
    key = (str(char_dir), who, expr, height)
    if key in _cache:
        return _cache[key]
    img = None
    for e in (expr, "normal"):
        p = char_dir / f"{who}_{e}.png"
        if p.exists():
            img = Image.open(p).convert("RGBA")
            break
    if img is None:
        return None
    r = height / img.height
    img = img.resize((max(1, int(img.width * r)), height), Image.LANCZOS)
    _cache[key] = img
    return img


def _dim(img):
    key = ("dim", id(img))
    if key in _cache:
        return _cache[key]
    out = img.copy()
    a = out.getchannel("A").point(lambda v: int(v * 0.45))
    out.putalpha(a)
    _cache[key] = out
    return out


def _wrap(draw, text, font, maxw):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= maxw:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def _bg(idx):
    """靜態底圖：柔漸層 + 頂部色帶（視差色塊另外每格向量繪製）。"""
    base = BG[idx % len(BG)]
    img = Image.new("RGB", (W, H), base)
    d = ImageDraw.Draw(img)
    top = tuple(min(255, c + 12) for c in base)
    bot = tuple(max(0, c - 14) for c in base)
    for y in range(0, H, 6):
        t = y / H
        d.rectangle([0, y, W, y + 6],
                    fill=tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)))
    d.rectangle([0, 0, W, 300], fill=BANDS[idx % len(BANDS)])
    return img


def _bg_shapes(idx):
    """回傳這一鏡的背景色塊規格（供每格依時間做視差位移）。"""
    base = BG[idx % len(BG)]
    seed = (idx * 2654435761) % (2 ** 31)
    rng = (seed or 1)

    def rnd():
        nonlocal rng
        rng = (1103515245 * rng + 12345) % (2 ** 31)
        return rng / (2 ** 31)

    shapes = []
    # 遠景：大而淡
    for _ in range(6):
        col = tuple(int(c * 0.97 + 6) for c in base)
        shapes.append({"kind": "far", "x": rnd() * W, "y": 200 + rnd() * (H - 500),
                       "r": 180 + rnd() * 260, "col": col + (46,),
                       "pf": 0.35, "amp": 34, "sp": 0.05 + rnd() * 0.05, "ph": rnd()})
    # 近景：中等透度
    for _ in range(5):
        col = BANDS[(idx + 1) % len(BANDS)]
        shapes.append({"kind": "near", "x": rnd() * W, "y": 260 + rnd() * (H - 560),
                       "r": 90 + rnd() * 130, "col": col + (78,),
                       "pf": 0.8, "amp": 48, "sp": 0.08 + rnd() * 0.08, "ph": rnd()})
    # 漂浮光斑
    for _ in range(14):
        col = (255, 255, 255) if rnd() > 0.5 else SAGE
        shapes.append({"kind": "bokeh", "x": rnd() * W, "y": 120 + rnd() * (H - 320),
                       "r": 8 + rnd() * 26, "col": col + (60 + int(rnd() * 70),),
                       "pf": 1.25, "amp": 70, "sp": 0.12 + rnd() * 0.14, "ph": rnd()})
    return shapes


def _chrome(title):
    key = ("chrome", title)
    if key in _cache:
        return _cache[key]
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    f_title = _font(34, True)
    tw = d.textlength(title[:16], font=f_title)
    d.rounded_rectangle([44, 44, 44 + tw + 44, 44 + f_title.size + 40], radius=36, fill=INK)
    d.text((66, 62), title[:16], font=f_title, fill=PAPER)
    d.rectangle([0, H - 118, W, H], fill=INK)
    d.text((44, H - 94), "押忍室內裝修設計有限公司", font=_font(40, True), fill=PAPER)
    d.text((W - 306, H - 94), "LE Interior", font=_font(40, True), fill=SAGE)
    _cache[key] = lay
    return lay


def _ease(t):
    return 1 - (1 - t) ** 3


def _ease_back(t):
    """帶超彈的緩動（0→1，中途超過 1 再回落）。"""
    c1, c3 = 1.70158, 2.70158
    x = t - 1
    return 1 + c3 * x * x * x + c1 * x * x


def render_scene(title, speaker, text, expr, char_dir, dur, fps, idx):
    """Render one scene into a list of RGB frames（含視差背景動態）。"""
    other = "le" if speaker == "ren" else "ren"
    sx = XC[speaker]
    ox = XC[other]
    ah = 860 if expr == "surprise" else (830 if expr == "happy" else 800)
    sp_act = _sprite(char_dir, speaker, expr, ah)
    sp_ina = _sprite(char_dir, other, "normal", 660)
    sp_ina = _dim(sp_ina) if sp_ina else None

    base = _bg(idx)
    chrome = _chrome(title)
    shapes = _bg_shapes(idx)

    # 氣泡先離屏畫好，之後只做縮放合成
    bubble_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bubble_layer)
    f = _font(50)
    lines = _wrap(bd, text, f, 690)
    lh = int(f.size * 1.42)
    bw, bh = 760, len(lines) * lh + 74
    bx = 60 if SIDE[speaker] == "left" else W - bw - 60
    by = 1010 - bh
    bd.rounded_rectangle([bx, by, bx + bw, by + bh], radius=46, fill=PAPER, outline=INK, width=6)
    ty = by + 37
    for ln in lines:
        bd.text((bx + 48, ty), ln, font=f, fill=INK)
        ty += lh
    tx = sx + (66 if SIDE[speaker] == "left" else -66)
    bd.polygon([(tx - 44, by + bh - 6), (tx + 44, by + bh - 6), (tx, by + bh + 64)],
               fill=PAPER, outline=INK)
    bbox = (bx - 14, by - 14, bx + bw + 14, by + bh + 80)
    bubble_src = bubble_layer.crop(bbox)

    glyph, gcol = EMOTE.get(expr, (None, None))

    n = max(1, round(dur * fps))
    for fi in range(n):
        t = fi / fps
        fr = base.convert("RGBA")
        # ---- 多層視差背景 ----
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        for sh in shapes:
            ang = 2 * math.pi * (t * sh["sp"] + sh["ph"])
            dx = sh["amp"] * sh["pf"] * math.sin(ang)
            dy = sh["amp"] * sh["pf"] * math.cos(ang * 0.8)
            cx, cy, r = sh["x"] + dx, sh["y"] + dy, sh["r"]
            ld.ellipse([cx - r, cy - r, cx + r, cy + r], fill=sh["col"])
        fr.alpha_composite(lay)
        fr.alpha_composite(chrome)
        # ---- 非發言者：輕微搖擺 + 微旋 ----
        oy = int(6 * math.sin(2 * math.pi * t * 0.7))
        if sp_ina:
            ina = sp_ina.rotate(1.2 * math.sin(2 * math.pi * t * 0.6),
                                resample=Image.BILINEAR)
            fr.alpha_composite(ina, (int(ox - ina.width / 2), int(1745 - ina.height + oy)))
        # ---- 發言者：彈性進場 + 呼吸 + 抖動 ----
        pop = _ease_back(min(1.0, t / 0.34))
        hgt = int(ah * (0.84 + 0.16 * pop))
        bob = -int(9 * math.sin(2 * math.pi * t * 1.8)) - int(3 * math.sin(2 * math.pi * t * 4.6))
        shx = 0
        if expr == "surprise" and t < 0.5:
            shx = int(8 * math.sin(2 * math.pi * t * 13) * (1 - t / 0.5))
        sp = _sprite(char_dir, speaker, expr, max(1, hgt))
        if sp:
            rot = 1.6 * math.sin(2 * math.pi * t * 1.1)
            spr = sp.rotate(rot, resample=Image.BILINEAR)
            fr.alpha_composite(spr, (int(sx - spr.width / 2 + shx),
                                     int(1745 - spr.height + bob)))
        # ---- 氣泡：超彈 pop-in ----
        bc = min(1.0, t / 0.24)
        if bc < 0.999:
            sc = 0.80 + 0.20 * _ease_back(bc)
            sc = max(0.2, sc)
            src = bubble_src.resize((max(1, int(bubble_src.width * sc)),
                                     max(1, int(bubble_src.height * sc))), Image.LANCZOS)
            fr.alpha_composite(src, (int(bbox[0] + bubble_src.width * (1 - sc) / 2),
                                     int(bbox[1] + bubble_src.height * (1 - sc) / 2)))
        else:
            fr.alpha_composite(bubble_layer, (0, 0))
        # ---- 情緒符號：爆發放大 + 漂浮 ----
        if glyph:
            burst = _ease_back(min(1.0, t / 0.3))
            r = int(46 * (0.6 + 0.4 * burst) + 4 * math.sin(2 * math.pi * t * 2))
            ex = sx + (180 if SIDE[speaker] == "left" else -180)
            ey = 820 - int(min(1.0, t / 0.25) * 36) + int(5 * math.sin(2 * math.pi * t * 2))
            bd_ = ImageDraw.Draw(fr)
            bd_.ellipse([ex - r, ey - r, ex + r, ey + r], fill=gcol)
            gf = _font(52, True)
            gw = bd_.textlength(glyph, font=gf)
            bd_.text((ex - gw / 2, ey - gf.size / 2 - 6), glyph, font=gf, fill=PAPER)
        yield fr.convert("RGB")


async def _tts(text, voice, path, rate="+0%", pitch="+0Hz", volume="+0%"):
    c = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
    bounds = []
    with open(path, "wb") as fh:
        async for ch in c.stream():
            if ch["type"] == "audio":
                fh.write(ch["data"])
            elif ch["type"] in ("SentenceBoundary", "WordBoundary"):
                bounds.append({"start": ch["offset"] / 1e7, "dur": ch["duration"] / 1e7,
                               "text": ch["text"]})
    return bounds


def voice_params(speaker, expr):
    br, bp = VOICE_BASE.get(speaker, (0, 0))
    er, ep = EXPR_MOD.get(expr, (0, 0))
    return f"{br + er:+d}%", f"{bp + ep:+d}Hz"


def gen_sfx(assets: Path):
    """現場合成免費音效：氣泡『啵』＋轉場『咻』。回傳 (pop, swish)。"""
    pop = assets / "sfx_pop.wav"
    swish = assets / "sfx_swish.wav"
    if not pop.exists():
        ms.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                "aevalsrc=0.55*sin(2*PI*(360+560*t/0.14)*t)*exp(-22*t):d=0.16",
                "-af", "afade=t=out:st=0.11:d=0.05", str(pop)])
    if not swish.exists():
        ms.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=d=0.32:c=pink:a=0.5",
                "-af", "highpass=f=400,lowpass=f=3200,"
                       "afade=t=in:st=0:d=0.05,afade=t=out:st=0.10:d=0.22,volume=0.6",
                str(swish)])
    return pop, swish


def build_audio_sfx(mp3, out_m4a, dur, sfx, pop_at=0.12):
    pop, swish = sfx
    d = int(pop_at * 1000)
    ms.run(["ffmpeg", "-y", "-i", str(mp3), "-i", str(pop), "-i", str(swish),
            "-filter_complex",
            f"[1:a]adelay={d}|{d},volume=0.5[p];"
            f"[2:a]volume=0.22[s];"
            f"[0:a]apad[a0];"
            f"[a0][p][s]amix=inputs=3:duration=longest:normalize=0[out]",
            "-map", "[out]", "-t", f"{dur:.3f}", "-c:a", "aac", "-b:a", "128k",
            str(out_m4a)])


def encode_frames(frames, out_mp4, fps, total=None, cover_png=None):
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-an",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           str(out_mp4)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pick = (total // 4) if total else -1
    for fi, fr in enumerate(frames):
        if fi == pick and cover_png is not None:
            fr.save(cover_png)
        p.stdin.write(fr.tobytes())
    p.stdin.close()
    p.wait()


def main():
    ap = argparse.ArgumentParser(description="押忍對話劇渲染器 v3（合成動態強化）")
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--chars", default=None)
    ap.add_argument("--bgm", default=None)
    ap.add_argument("--bgm-volume", type=float, default=0.16)
    ap.add_argument("--tail", type=float, default=0.35)
    ap.add_argument("--transition", type=float, default=0.35)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--subs", action="store_true")
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--sfx", dest="sfx", action="store_true", default=True, help="合成音效（預設開）")
    ap.add_argument("--no-sfx", dest="sfx", action="store_false")
    args = ap.parse_args()

    script = json.loads(Path(args.script).read_text(encoding="utf-8"))
    title = script.get("title", "對話劇")
    scenes = script["scenes"]
    char_dir = Path(args.chars or script.get("char_dir") or (LEZHI / "assets" / "characters"))
    vmap = {**VOICE, **script.get("voice_map", {})}

    out = Path(args.out)
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    sfx = gen_sfx(assets) if args.sfx else None
    ms.log(f"對話劇 v3：{title}｜{len(scenes)} 句｜角色：{char_dir.name}｜音效：{'開' if sfx else '關'}")

    clips, audios, metas = [], [], []
    for i, sc in enumerate(scenes):
        who = sc.get("speaker", "ren")
        text = sc["text"]
        expr = sc.get("expr", "normal")
        if expr not in EXPRS:
            expr = "normal"
        voice = sc.get("voice") or vmap.get(who, VOICE["ren"])
        rate, pitch = voice_params(who, expr)
        ms.log(f"[{i+1}/{len(scenes)}] {NAME.get(who,who)}（{expr}, {rate}/{pitch}）：{text[:18]}")

        mp3 = assets / f"tts_{i}.mp3"
        bjson = assets / f"bounds_{i}.json"
        if args.reuse and mp3.exists() and bjson.exists():
            bounds = json.loads(bjson.read_text(encoding="utf-8"))
        else:
            bounds = None
            for attempt in range(4):
                try:
                    bounds = asyncio.run(_tts(text, voice, mp3, rate, pitch))
                    if bounds:
                        break
                except Exception as e:
                    ms.log(f"  TTS 重試 {attempt}：{str(e)[:50]}")
                    import time
                    time.sleep(3)
            if not bounds:
                bounds = asyncio.run(_tts(text, "zh-TW-HsiaoChenNeural", mp3, rate, pitch))
            bjson.write_text(json.dumps(bounds, ensure_ascii=False), encoding="utf-8")
        dur = ms.probe_duration(mp3)
        scene_dur = round((dur + args.tail) * args.fps) / args.fps

        clip = assets / f"clip_{i}.mp4"
        frames = render_scene(title, who, text, expr, char_dir, scene_dur, args.fps, i)
        encode_frames(frames, clip, args.fps,
                      total=max(1, round(scene_dur * args.fps)),
                      cover_png=(assets / "cover0.png") if i == 0 else None)
        aud = assets / f"aud_{i}.m4a"
        if sfx:
            build_audio_sfx(mp3, aud, scene_dur, sfx)
        else:
            ms.build_audio(mp3, aud, scene_dur)
        clips.append(clip)
        audios.append(aud)
        metas.append({"dur": ms.probe_duration(clip), "bounds": bounds, "text": text})

    ms.log("串接 + 多樣轉場...")
    silent = assets / "timeline.mp4"
    ms.concat_scenes(clips, audios, silent, args.fps, args.transition,
                     transitions=TRANSITIONS)

    video = silent
    if args.bgm:
        ms.log(f"混入 BGM（{args.bgm_volume}）...")
        mixed = assets / "timeline_mix.mp4"
        ms.mix_bgm(silent, Path(args.bgm), mixed, args.bgm_volume)
        video = mixed

    final = out / f"{title}.mp4"
    if args.subs:
        srt = out / f"{title}.srt"
        ms.build_srt(metas, srt, args.transition)
        ms.burn_subtitles(video, srt.name, final, out)
        subs = out / "subs"
        subs.mkdir(exist_ok=True)
        srt.replace(subs / srt.name)
    else:
        ms.run(["ffmpeg", "-y", "-i", str(video), "-c", "copy", str(final)])

    cover = out / "封面.png"
    if (assets / "cover0.png").exists():
        cover.write_bytes((assets / "cover0.png").read_bytes())
    (out / "metadata.json").write_text(json.dumps({
        "title": title, "format": "dialog", "size": f"{W}x{H}",
        "duration_sec": round(ms.probe_duration(final), 1), "lines": len(scenes),
        "char_dir": str(char_dir), "video": final.name,
        "cover": cover.name if cover.exists() else None,
        "subtitle": f"subs/{title}.srt" if args.subs else None,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    ms.log(f"完成！{final}（{round(ms.probe_duration(final),1)}s）")


if __name__ == "__main__":
    main()
