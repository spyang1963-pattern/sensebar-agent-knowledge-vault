"""make_scene.py - 場景式對話劇（3D 相機投影版）

用「3D→2D 透視投影」取代手畫透視：房間/家具/人物都定義成 3D 座標，
由相機投影到螢幕，透視（消失點、收斂、近大遠小）自動正確，焦點可控。

🔑 設計原則：特殊、非標準眼光的設計才是賣點（怪奇人物保留）。

用法：
  python make_scene.py --out working/poc_scene_3d --debug
"""
from __future__ import annotations

import argparse
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
INK = (21, 26, 27)
PAPER = (252, 252, 252)

FONT = r"C:\Windows\Fonts\msjh.ttc"
FONTB = r"C:\Windows\Fonts\msjhbd.ttc"

WALL = (236, 239, 237)
WALL_SIDE = (222, 228, 225)
FLOOR = (206, 190, 172)
FLOOR_LINE = (186, 170, 152)
WOOD = (176, 138, 104)
SOFA_A = (150, 170, 166)
SOFA_B = (120, 132, 150)
TABLE = (120, 96, 70)
SKIN = (247, 219, 196)

REN = {"hair": (38, 42, 45), "top": (117, 137, 133), "accent": PAPER,
       "pants": (58, 62, 68), "glasses": True, "cap": False}
LE = {"hair": (94, 66, 51), "top": (224, 158, 106), "accent": PAPER,
      "pants": (70, 82, 96), "glasses": False, "cap": True}


def _font(sz, bold=False):
    try:
        return ImageFont.truetype(FONTB if bold else FONT, sz)
    except Exception:
        return ImageFont.load_default()


# ------------------------------------------------------------------ 向量＋相機
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm(a):
    m = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / m, a[1] / m, a[2] / m)


class Camera:
    def __init__(self, eye, target, fov=46):
        self.eye = eye
        fwd = _norm(_sub(target, eye))
        right = _norm(_cross(fwd, (0, 1, 0)))
        up = _cross(right, fwd)
        self.fwd, self.right, self.up = fwd, right, up
        self.f = (H / 2) / math.tan(math.radians(fov) / 2)

    def project(self, p):
        d = _sub(p, self.eye)
        zc = _dot(d, self.fwd)
        if zc <= 0.05:
            return None
        xc = _dot(d, self.right)
        yc = _dot(d, self.up)
        return (W / 2 + self.f * xc / zc, H / 2 - self.f * yc / zc, zc)


def _shade(c, k):
    return tuple(max(0, min(255, int(x * k))) for x in c)


def _p2(cam, p):
    r = cam.project(p)
    return (r[0], r[1]) if r else None


def draw_sofa(cam, d, cx, cz, w, dep, h, color, yaw=0.0):
    """雙人座：底座＋椅背（椅背在「背後」）。yaw=0 面朝 +z。"""
    draw_box(cam, d, cx, 0, cz, w, dep, h, color, yaw)
    # 椅背在面向的反方向（-facing）
    bx = cx - dep * 0.45 * math.sin(yaw)
    bz = cz - dep * 0.45 * math.cos(yaw)
    draw_box(cam, d, bx, 0, bz, w * 0.94, dep * 0.35, h * 1.5, _shade(color, 0.9), yaw)


# ------------------------------------------------------------------ 3D 箱子
def _box_corners(cx, cy, cz, w, d, h):
    x0, x1 = cx - w / 2, cx + w / 2
    y0, y1 = cy, cy + h
    z0, z1 = cz - d / 2, cz + d / 2
    return [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1),
            (x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)]


FACES = [(0, 1, 5, 4), (2, 3, 7, 6), (0, 3, 7, 4), (1, 2, 6, 5), (0, 1, 2, 3), (4, 5, 6, 7)]
FACE_NORM = [(0, 0, -1), (0, 0, 1), (-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0)]


def _rot_y(p, cx, cz, ang):
    dx, dz = p[0] - cx, p[2] - cz
    c, s = math.cos(ang), math.sin(ang)
    return (cx + dx * c - dz * s, p[1], cz + dx * s + dz * c)


def draw_box(cam, d, cx, cy, cz, w, dep, h, color, yaw=0.0):
    """畫 3D 箱子（可繞 Y 軸轉 yaw，背向面剔除），回傳投影中心 (sx, sy, zc)。"""
    corners = _box_corners(cx, cy, cz, w, dep, h)
    if yaw:
        corners = [_rot_y(c, cx, cz, yaw) for c in corners]
    proj = [cam.project(c) for c in corners]
    center = cam.project((cx, cy + h / 2, cz))
    if center is None or any(p is None for p in proj):
        return center
    order = []
    for fi, (face, nrm) in enumerate(zip(FACES, FACE_NORM)):
        # 面法向量也要隨 yaw 轉
        n3 = (nrm[0], nrm[1], nrm[2])
        if yaw:
            n3 = _rot_y((cx + n3[0], 0, cz + n3[2]), cx, cz, yaw)
            n3 = (n3[0] - cx, n3[1], n3[2] - cz)
        center3 = tuple(sum(corners[i][k] for i in face) / 4 for k in range(3))
        view = _sub(center3, cam.eye)
        if _dot(n3, view) < 0:
            zavg = sum(proj[i][2] for i in face) / 4
            order.append((zavg, fi))
    order.sort(reverse=True)
    for _, fi in order:
        face = FACES[fi]
        pts = [(proj[i][0], proj[i][1]) for i in face]
        shade_k = 1.0 - 0.12 * max(0, FACE_NORM[fi][2])
        d.polygon(pts, fill=_shade(color, shade_k), outline=INK)
    return center


# ------------------------------------------------------------------ 背景（2D 貼在投影牆上）
def _window_on_wall(cam, d, t):
    wx0 = cam.project((1.6, 1.1, 0))
    wx1 = cam.project((3.4, 1.1, 0))
    wy0 = cam.project((1.6, 2.6, 0))
    wy1 = cam.project((3.4, 2.6, 0))
    if not all([wx0, wx1, wy0, wy1]):
        return
    x0, y0 = wx0[0], wy0[1]
    x1, y1 = wx1[0], wy1[1]
    ww, wh = int(x1 - x0), int(y0 - y1)
    if ww <= 0 or wh <= 0:
        return
    sky = Image.new("RGB", (ww, wh), (176, 214, 232))
    sd = ImageDraw.Draw(sky)
    for i, (cx0, cy, rw) in enumerate([(ww * 0.3, wh * 0.2, ww * 0.13), (ww * 0.7, wh * 0.15, ww * 0.11)]):
        cx = (cx0 + t * ww * 0.03) % (ww * 1.3) - ww * 0.15
        sd.ellipse([cx - rw, cy - rw * 0.6, cx + rw, cy + rw * 0.6], fill=(250, 250, 248))
    # 樹
    tx = ww * 0.8
    sd.rectangle([tx - ww * 0.03, wh * 0.7, tx + ww * 0.03, wh], fill=(110, 88, 66))
    for k, (lx, ly, r) in enumerate([(tx - ww * 0.1, wh * 0.5, ww * 0.13), (tx + ww * 0.08, wh * 0.45, ww * 0.11)]):
        sw = math.sin(t * 1.6 + k) * ww * 0.02
        sd.ellipse([lx + sw - r, ly - r * 0.7, lx + sw + r, ly + r * 0.7],
                   fill=(120, 168, 118), outline=(86, 128, 84), width=3)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.paste(sky, (int(x0), int(y1)))
    dd = ImageDraw.Draw(img)
    dd.rectangle([int(x0), int(y1), int(x1), int(y0)], outline=INK, width=8)
    dd.line([(int((x0 + x1) / 2), int(y1)), (int((x0 + x1) / 2), int(y0))], fill=INK, width=6)
    dd.line([(int(x0), int((y0 + y1) / 2)), (int(x1), int((y0 + y1) / 2))], fill=INK, width=6)
    return img


def _clock_on_wall(cam, d, t):
    c = cam.project((3.6, 2.5, 0))
    if not c:
        return
    cx, cy = int(c[0]), int(c[1])
    r = int(c[2] and 80 * (5.0 / c[2]) * 2 or 40)
    r = max(24, min(90, r))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PAPER, outline=INK, width=6)
    sa = math.radians((t * 60) % 360)
    d.line([(cx, cy), (cx + (r - 8) * math.sin(sa), cy - (r - 8) * math.cos(sa))],
           fill=(200, 80, 60), width=3)
    d.line([(cx, cy), (cx - r * 0.3, cy - r * 0.4)], fill=INK, width=5)
    d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=INK)


# ------------------------------------------------------------------ 怪奇角色（坐姿，有手腳）
def _limb(d, x0, y0, x1, y1, w, color):
    d.line([(x0, y0), (x1, y1)], fill=color, width=w)
    r = w // 2
    d.ellipse([x0 - r, y0 - r, x0 + r, y0 + r], fill=color)
    d.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], fill=color)


def _char(who, d, sx, sy, scale, facing, t, brow, eye, mouth, view="front"):
    c = REN if who == "ren" else LE
    r = int(58 * scale)
    bw = int(r * 1.7)

    # 腿（大腿往前＋小腿往下），畫在身體後方
    thigh_y = sy + int(r * 2.7)
    d.rounded_rectangle([sx - int(r * 1.6), thigh_y, sx + int(r * 1.6), thigh_y + int(r * 0.9)],
                        radius=int(r * 0.3), fill=c["pants"], outline=INK, width=4)
    for lx in (sx - int(r * 0.95), sx + int(r * 0.95)):
        _limb(d, lx, thigh_y + int(r * 0.7), lx, thigh_y + int(r * 1.7), int(18 * scale), c["pants"])

    # 身體（上身）
    d.rounded_rectangle([sx - bw, sy + r, sx + bw, sy + int(r * 3.0)], radius=int(r * 0.7),
                        fill=c["top"], outline=INK, width=5)
    d.rectangle([sx + bw - int(r * 0.5), sy + r, sx + bw, sy + int(r * 3.0)], fill=_shade(c["top"], 0.82))
    if view == "front":
        d.polygon([(sx - int(r * 0.7), sy + r), (sx + int(r * 0.7), sy + r),
                   (sx, sy + int(r * 1.4))], fill=c["accent"], outline=INK)

    # 手臂（搭在腿上）
    for ax, dirv in ((sx - bw, -1), (sx + bw, 1)):
        _limb(d, ax, sy + int(r * 1.3), sx + dirv * int(r * 0.5), thigh_y + int(r * 0.4),
              int(16 * scale), c["top"])

    # 頭
    if view == "back":
        d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=c["hair"], outline=INK, width=5)
        for k in (-0.3, 0.0, 0.3):
            d.arc([sx - int(r * 0.85), sy - int(r * (0.85 + k * 0.3)),
                   sx + int(r * 0.85), sy + int(r * (0.85 + k * 0.3))], 10, 170,
                  fill=_shade(c["hair"], 1.15), width=3)
        return
    d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=SKIN, outline=INK, width=5)
    if c["cap"]:
        d.pieslice([sx - r - 3, sy - r - 3, sx + r + 3, sy + r + 3], 180, 320, fill=c["hair"], outline=INK, width=5)
        d.rounded_rectangle([sx - r - 8, sy - r + 2, sx + r * 0.5, sy - r + 24], radius=10,
                            fill=(196, 92, 82), outline=INK, width=4)
    else:
        d.pieslice([sx - r - 2, sy - r - 2, sx + r + 2, sy + r + 2], 180, 330, fill=c["hair"], outline=INK, width=5)
    # 臉（3/4 偏移）
    ox = facing * r * 0.4
    ey = sy - r * 0.05
    for ex, k in ((sx + ox + r * 0.5, 1.0), (sx + ox - r * 0.5, 0.55)):
        w2 = r * 0.32 * k
        if eye == "blink":
            d.line([(ex - w2, ey), (ex + w2, ey)], fill=INK, width=4)
        elif eye == "wide":
            d.ellipse([ex - w2, ey - w2 * 0.9, ex + w2, ey + w2 * 0.9], outline=INK, width=4)
            d.ellipse([ex - w2 * 0.3, ey - w2 * 0.3, ex + w2 * 0.15, ey + w2 * 0.4], fill=INK)
        else:
            d.ellipse([ex - w2 * 0.7, ey - w2 * 0.6, ex + w2 * 0.7, ey + w2 * 0.6], outline=INK, width=4)
            d.ellipse([ex - w2 * 0.25, ey - w2 * 0.2, ex + w2 * 0.15, ey + w2 * 0.35], fill=INK)
    for ex, k in ((sx + ox + r * 0.5, 1.0), (sx + ox - r * 0.5, 0.6)):
        by = ey - r * 0.42
        w = r * 0.3 * k
        d.line([(ex - w, by - (r * 0.2 if brow == "up" else 0)), (ex + w, by - (r * 0.3 if brow == "up" else 0))],
               fill=INK, width=4)
    my = sy + r * 0.55
    if mouth == "o":
        d.ellipse([sx + ox - r * 0.2, my - r * 0.1, sx + ox + r * 0.2, my + r * 0.3],
                  fill=(122, 60, 60), outline=INK, width=3)
    else:
        d.line([(sx + ox - r * 0.2, my), (sx + ox + r * 0.2, my)], fill=INK, width=4)
    if c["glasses"]:
        for gx in (sx + ox + r * 0.5, sx + ox - r * 0.5):
            d.ellipse([gx - r * 0.32, ey - r * 0.3, gx + r * 0.32, ey + r * 0.12], outline=INK, width=4)


def _talk_face(t, seed):
    e = (math.sin(t * 5) + 1) / 2
    mouth = "o" if e > 0.75 else "closed"
    ph = math.sin(t * 0.7 + seed)
    brow = "up" if ph > 0.6 else "flat"
    eye = "wide" if ph > 0.6 else "normal"
    if (t * 1.0) % 4.2 < 0.12:
        eye = "blink"
    return brow, eye, mouth


def _draw_debug(d, cam, horizon_pt):
    if not horizon_pt:
        return
    cx, cy = int(horizon_pt[0]), int(horizon_pt[1])
    d.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], outline=(230, 60, 60), width=4)
    d.line([(cx - 30, cy), (cx + 30, cy)], fill=(230, 60, 60), width=3)
    d.line([(cx, cy - 30), (cx, cy + 30)], fill=(230, 60, 60), width=3)
    d.text((cx + 22, cy + 22), "焦點", fill=(230, 60, 60), font=_font(30, True))


# ------------------------------------------------------------------ 渲染
def render(outdir, fps=12, dur=8.0, debug=False):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    n = int(dur * fps)

    cam = Camera(eye=(2.5, 2.7, 8.0), target=(2.5, 1.4, 2.0), fov=50)
    focus = cam.project((2.5, 1.4, 2.0))  # 焦點＝相機看向的點（兩人之間）

    frames = []
    for fi in range(n):
        t = fi / fps
        img = Image.new("RGB", (W, H), WALL)
        d = ImageDraw.Draw(img)

        # 地板（x∈[1,4], z∈[0,4.5]）
        fp = [_p2(cam, (1, 0, 0)), _p2(cam, (4, 0, 0)), _p2(cam, (4, 0, 4.5)), _p2(cam, (1, 0, 4.5))]
        if all(fp):
            d.polygon(fp, fill=FLOOR)
        # 地板格線（3D 投影）
        for x in range(1, 5):
            p0 = cam.project((x, 0, 0))
            p1 = cam.project((x, 0, 4.5))
            if p0 and p1:
                d.line([(p0[0], p0[1]), (p1[0], p1[1])], fill=FLOOR_LINE, width=2)
        for z in range(0, 5):
            p0 = cam.project((1, 0, z))
            p1 = cam.project((4, 0, z))
            if p0 and p1:
                d.line([(p0[0], p0[1]), (p1[0], p1[1])], fill=FLOOR_LINE, width=2)

        # 後牆（z=0）
        bw = [_p2(cam, (1, 0, 0)), _p2(cam, (4, 0, 0)), _p2(cam, (4, 3.2, 0)), _p2(cam, (1, 3.2, 0))]
        if all(bw):
            d.polygon(bw, fill=WALL)
        # 左牆（x=1）
        lw = [_p2(cam, (1, 0, 0)), _p2(cam, (1, 0, 4.5)), _p2(cam, (1, 3.2, 4.5)), _p2(cam, (1, 3.2, 0))]
        if all(lw):
            d.polygon(lw, fill=WALL_SIDE)

        # 窗＋鐘（貼在後牆）
        wim = _window_on_wall(cam, d, t)
        if wim:
            img.paste(wim, (0, 0), wim)
        _clock_on_wall(cam, d, t)

        # 家具：小樂椅（後，面朝 +z）→ 茶几 → 阿忍椅（前，面朝 -z），椅子轉邊對坐
        draw_sofa(cam, d, 2.0, 1.4, 1.6, 0.75, 0.7, SOFA_A, yaw=0.0)
        draw_box(cam, d, 2.5, 0, 2.3, 0.9, 0.55, 0.4, TABLE)
        draw_sofa(cam, d, 3.0, 3.2, 1.6, 0.75, 0.7, SOFA_B, yaw=math.pi)

        # 人物：小樂面朝相機（正面）、阿忍背對相機（背面）
        p_le = cam.project((2.0, 0.7, 1.4))
        p_ren = cam.project((3.0, 0.7, 3.2))
        if p_le:
            sc_le = 5.0 / p_le[2]
            r_le = int(58 * sc_le)
            lb, le_, lm = _talk_face(t, 1) if t > 1.0 else ("flat", "normal", "closed")
            _char("le", d, int(p_le[0]), int(p_le[1] - r_le * 3.0), sc_le, 1, t, lb, le_, lm, view="front")
        if p_ren:
            sc_ren = 5.0 / p_ren[2]
            r_ren = int(58 * sc_ren)
            rb, re_, rm = _talk_face(t, 2) if t > 1.0 else ("flat", "normal", "closed")
            _char("ren", d, int(p_ren[0]), int(p_ren[1] - r_ren * 3.0), sc_ren, -1, t, rb, re_, rm, view="back")

        if debug:
            _draw_debug(d, cam, focus)
        frames.append(img)

    mp4 = outdir / "poc.mp4"
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "20", "-pix_fmt", "yuv420p", str(mp4)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for i, frm in enumerate(frames):
        p.stdin.write(frm.tobytes())
        if i in (int(n * 0.12), int(n * 0.4), int(n * 0.65)):
            frm.save(outdir / f"frame_{i:03d}.png")
    p.stdin.close()
    p.wait()
    if debug:
        frames[max(0, int(n * 0.6))].save(outdir / "debug_focus.png")
    print(f"POC 完成：{mp4}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="working/poc_scene_3d")
    ap.add_argument("--fps", type=int, default=12)
    ap.add_argument("--dur", type=float, default=8.0)
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    render(a.out, a.fps, a.dur, debug=a.debug)
