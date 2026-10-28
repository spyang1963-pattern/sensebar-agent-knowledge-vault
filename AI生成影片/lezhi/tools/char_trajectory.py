"""char_trajectory.py - 自動移動軌跡（11 錨點隨時間變化）

把「姿勢（11 錨點 offset）＋位置（頭中心座標）＋時間」串成軌跡，做出
走路／跑步／跳躍／滑步／蹲下／坐下／靠近／退後等戲劇動作。

姿勢 pose 是 dict，鍵與 recipe 的 pose 欄位相同（單位＝頭半徑 r 的比例）：
  neck_dx/dy、hip_dx/dy、elbow_lx/ly/rx/ry、hand_lx/ly/rx/ry、
  knee_lx/ly/rx/ry、foot_lx/ly/rx/ry、head_dx/dy
位置 pos＝角色頭中心在場景座標 (x, y)。骨架各錨點由 (x, y) + 各 offset 推算，
故「姿勢」只動相對偏移、「位置」只動全身平移，兩者正交。

模型（2026-10-26 定案，區分「點動作」與「段動作」）：
  - 路徑點 waypoint：{x, y, pose(stand/sit/squat), wave(bool), hold(秒)}
    代表「點位置動作」（站/坐/蹲＋可選揮手，停留 hold 秒）。
  - 動作段 segment：{motion(walk/slide/run/jump), dur, steps_per_sec, amp, facing}
    代表「點與點之間」的移動動作。
  - compile_path(waypoints, segments) 會自動插入過渡：
    * 移動→坐／蹲　自動「站→坐(sit_down)／站→蹲(squat_in)」再維持坐/蹲。
    * 坐／蹲→移動　自動「坐→站(sit_up)／蹲→站(squat_out)」再走/滑/跑/跳。
  - 朝向（視角）依路徑方向：與水平夾角 >70° 自動轉 正視/後視；否則側視。
    爬高/爬低（維持原轉向）用 facing="side" 手動指定。

設計：
  - 動作原語 walk_pose/run_pose/jump_pose 是「時間的連續函數」。
  - Trajectory 由若干「動作段」(dur, fn, facing) 依序組成，
    fn(u) -> (pose, x, y, mode, wave)；sample(t) -> (pose, x, y, mode, wave, facing)。
"""
from __future__ import annotations

import math

POSE_KEYS = [
    "neck_dx", "neck_dy", "hip_dx", "hip_dy",
    "elbow_lx", "elbow_ly", "elbow_rx", "elbow_ry",
    "hand_lx", "hand_ly", "hand_rx", "hand_ry",
    "knee_lx", "knee_ly", "knee_rx", "knee_ry",
    "foot_lx", "foot_ly", "foot_rx", "foot_ry",
    "head_dx", "head_dy",
]

STAND = {
    "neck_dx": 0.0, "neck_dy": 0.7, "hip_dx": 0.0, "hip_dy": 2.0,
    "elbow_lx": 0.2, "elbow_ly": 0.7, "elbow_rx": -0.2, "elbow_ry": 0.7,
    "hand_lx": -0.25, "hand_ly": 1.0, "hand_rx": 0.25, "hand_ry": 1.0,
    "knee_lx": -0.2, "knee_ly": 1.1, "knee_rx": 0.2, "knee_ry": 1.1,
    "foot_lx": 0.25, "foot_ly": 1.0, "foot_rx": -0.25, "foot_ry": 1.0,
    "head_dx": 0.0, "head_dy": 0.0,
}

# 過渡（站↔坐、站↔蹲）預設參數
TRANS_SIT = 0.4        # 站↔坐過渡秒數
TRANS_SQUAT = 0.5      # 站↔蹲過渡秒數
SIT_DROP = 26.0        # 坐姿下沉（頭部 y 位移）
SQUAT_DROP = 42.0      # 蹲姿下沉（頭部 y 位移）


# 全域基底姿勢（供 set_base_pose 覆寫，讓時間軸尊重角色的身體比例）
_BASE = dict(STAND)


def set_base_pose(pose):
    """設定基底姿勢（角色身體比例），姿勢原語會在此基底上做動畫。"""
    global _BASE
    _BASE = dict(STAND)
    if pose:
        for k in POSE_KEYS:
            if pose.get(k) is not None:
                _BASE[k] = pose[k]


def base_pose():
    return dict(_BASE)


def interp_pose(a, b, k):
    """線性內插兩份姿勢。k 會被夾在 0..1。"""
    k = max(0.0, min(1.0, k))
    out = {}
    for key in POSE_KEYS:
        out[key] = a.get(key, 0.0) * (1.0 - k) + b.get(key, 0.0) * k
    return out


def _lerp(a, b, k):
    return a + (b - a) * k


def _smoothstep(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def _ease_in_out(k):
    k = max(0.0, min(1.0, k))
    return 0.5 - 0.5 * math.cos(math.pi * k)


def _flip_x(p):
    """鏡像姿勢（面朝左用）：x 軸左右鏡像＋交換抬腿 + 前傾反向。

    面朝右（forward=+x）是基準；面朝左要把「膝 V／腳尖 V」的方向一起鏡像，
    否則腳仍留在膝的 +x 側（面朝左＝後方）。做法：
      * 膝/腳的 x：左右交換並反向（lx↔-rx）。
      * 膝/腳的 y（升降 ly/ry）：左右交換（抬哪隻腿不變，但左右對調）。
      * 前傾 neck_dx/hip_dx 反向。手臂不動（本已對稱）。
    """
    q = dict(p)
    for base in ("knee", "foot"):
        ly, ry = base + "_ly", base + "_ry"
        q[ly], q[ry] = q[ry], q[ly]
        lx, rx = base + "_lx", base + "_rx"
        q[lx], q[rx] = -q[rx], -q[lx]
    q["neck_dx"] = -q.get("neck_dx", 0.0)
    q["hip_dx"] = -q.get("hip_dx", 0.0)
    return q


# ---------------------------------------------------------------- 動作原語

def walk_pose(t, amp=1.0):
    """走路姿勢：膝蓋輪流彎、雙腳前後踏＋抬腳、手臂反向擺動、身體微起伏。"""
    a = t * 2.0 * math.pi
    sL = math.sin(a)
    sR = -sL
    cL = math.cos(a)
    # 腳在空中（recovery 向前盪）＝ cos>0；落地（向前/向後極點）＝ cos=0
    swingL = _smoothstep(max(0.0, cL))
    swingR = _smoothstep(max(0.0, -cL))
    p = base_pose()
    # 腿：大腿前後擺；腳往前伸（落地腳尖在膝前方、不向後倒退）、recovery 時抬腳屈膝
    p["knee_lx"] = 0.50 * sL * amp
    p["knee_rx"] = 0.50 * sR * amp
    p["knee_ly"] = 1.10 - 0.30 * swingL * amp
    p["knee_ry"] = 1.10 - 0.30 * swingR * amp
    p["foot_lx"] = (0.30 * sL - 0.15 * swingL) * amp
    p["foot_rx"] = (0.30 * sR - 0.15 * swingR) * amp
    p["foot_ly"] = 1.00 - 0.60 * swingL * amp
    p["foot_ry"] = 1.00 - 0.60 * swingR * amp
    # 手臂：肘尖 V 永遠朝後（手恆在肘前方）、上臂向前擺 > 向後擺
    p["elbow_lx"] = -0.10 - 0.20 * sL * amp
    p["elbow_rx"] = 0.10 + 0.20 * sL * amp
    p["hand_lx"] = -0.30 - 0.15 * sL * amp
    p["hand_rx"] = 0.30 + 0.15 * sL * amp
    p["head_dy"] = -abs(sL) * 0.06 * amp
    p["neck_dx"] = 0.12 * amp
    return p


def run_pose(t, amp=1.0):
    """跑步姿勢：步幅更大、抬腿更高、手臂擺更大、身體起伏更明顯。"""
    a = t * 2.0 * math.pi
    sL = math.sin(a)
    sR = -sL
    cL = math.cos(a)
    swingL = _smoothstep(max(0.0, cL))
    swingR = _smoothstep(max(0.0, -cL))
    p = base_pose()
    # 腿：大腿前後擺；腳往前伸（落地腳尖在膝前方、不向後倒退）、recovery 時抬腳屈膝
    p["knee_lx"] = 0.60 * sL * amp
    p["knee_rx"] = 0.60 * sR * amp
    p["knee_ly"] = 1.10 - 0.40 * swingL * amp
    p["knee_ry"] = 1.10 - 0.40 * swingR * amp
    p["foot_lx"] = (0.40 * sL - 0.15 * swingL) * amp
    p["foot_rx"] = (0.40 * sR - 0.15 * swingR) * amp
    p["foot_ly"] = 1.00 - 0.75 * swingL * amp
    p["foot_ry"] = 1.00 - 0.75 * swingR * amp
    # 跑步手臂：肘尖 V 永遠朝後（手恆在肘前方）、上臂向前擺 > 向後擺、手抬高
    p["elbow_lx"] = -0.10 - 0.30 * sL * amp
    p["elbow_rx"] = 0.10 + 0.30 * sL * amp
    p["hand_ly"] = 1.0 - 0.55 * amp
    p["hand_ry"] = 1.0 - 0.55 * amp
    p["hand_lx"] = -0.35 - 0.20 * sL * amp
    p["hand_rx"] = 0.35 + 0.20 * sL * amp
    p["head_dy"] = -abs(sL) * 0.12 * amp
    p["neck_dx"] = 0.18 * amp
    return p


def jump_pose(t, amp=1.0):
    """跳躍式走路姿勢：週期性離地（雙腿收縮、雙臂上舉）。位置高度由 jump 建造器在 y 疊加。"""
    a = t * 2.0 * math.pi
    hop = max(0.0, math.sin(a))
    p = base_pose()
    p["knee_ly"] = 0.95 - hop * 0.55 * amp
    p["knee_ry"] = 0.95 - hop * 0.55 * amp
    p["foot_ly"] = 0.95 - hop * 0.8 * amp
    p["foot_ry"] = 0.95 - hop * 0.8 * amp
    p["foot_lx"] = -0.08 + 0.22 * math.sin(a) * amp
    p["foot_rx"] = 0.08 - 0.22 * math.sin(a) * amp
    p["hand_ly"] = 1.0 - hop * 1.0 * amp
    p["hand_ry"] = 1.0 - hop * 1.0 * amp
    return p


def squat_pose(depth=1.0):
    """蹲下姿勢：雙膝大幅外張彎曲、髖下沉、雙臂往前放。depth 0（站）～1（深蹲）。"""
    p = base_pose()
    p["hip_dy"] = 2.0 - 0.35 * depth
    p["knee_lx"] = -0.30 - 0.40 * depth
    p["knee_rx"] = 0.30 + 0.40 * depth
    p["knee_ly"] = 0.95 - 0.30 * depth
    p["knee_ry"] = 0.95 - 0.30 * depth
    p["foot_lx"] = -0.08 - 0.30 * depth
    p["foot_rx"] = 0.08 + 0.30 * depth
    p["foot_ly"] = 0.95 + 0.15 * depth
    p["foot_ry"] = 0.95 + 0.15 * depth
    p["elbow_lx"] = -0.4 - 0.10 * depth
    p["elbow_rx"] = 0.4 + 0.10 * depth
    p["elbow_ly"] = 0.15 + 0.25 * depth
    p["elbow_ry"] = 0.15 + 0.25 * depth
    p["hand_ly"] = 0.15 + 0.55 * depth
    p["hand_ry"] = 0.15 + 0.55 * depth
    return p


def sit_pose():
    """盤腿坐姿勢（近似）。實際渲染盤腿坐由 mode 的 render_hip_seated 單一形狀完成，
    這裡僅供「站→坐」過渡時把雙腿摺疊到貼地，做視覺收腿。"""
    p = base_pose()
    p["hip_dy"] = 2.0 - 0.55
    p["knee_lx"] = -0.30 - 0.55
    p["knee_rx"] = 0.30 + 0.55
    p["knee_ly"] = 0.95 - 0.45
    p["knee_ry"] = 0.95 - 0.45
    p["foot_lx"] = -0.08 - 0.30
    p["foot_rx"] = 0.08 + 0.30
    p["foot_ly"] = 0.95 + 0.30
    p["foot_ry"] = 0.95 + 0.30
    return p


# ---------------------------------------------------------------- 軌跡（分段取樣）

class Trajectory:
    """軌跡＝若干「動作段」(dur, fn, facing) 依序組成。

    fn(u) -> (pose, x, y, mode, wave)；sample(t) -> (pose, x, y, mode, wave, facing)。
    facing ∈ {"left","right","front","back"}。
    """

    def __init__(self):
        self.segments = []  # [(dur, fn, facing)]

    def append(self, dur, fn, facing="right"):
        self.segments.append((dur, fn, facing))
        return self

    def duration(self):
        return sum(d for d, _, _ in self.segments)

    def sample(self, t):
        """回傳 (pose, x, y, mode, wave, facing)。t 超出範圍時夾到最後一段結尾。"""
        if not self.segments:
            return base_pose(), 0.0, 0.0, "stand", False, "right"
        tt = max(0.0, min(t, self.duration()))
        for dur, fn, facing in self.segments:
            if tt <= dur:
                pose, x, y, mode, wave = fn(tt)
                return pose, x, y, mode, wave, facing
            tt -= dur
        dur, fn, facing = self.segments[-1]
        pose, x, y, mode, wave = fn(dur)
        return pose, x, y, mode, wave, facing


# ---------------------------------------------------------------- 動作段建造器
# 每個建造器回傳 (duration, fn)；fn(u) -> (pose, x, y, mode, wave)。

def hold(x, y, dur, pose=None, mode="stand", wave=False):
    """靜止（或持某姿勢）。wave=True 時該段揮手。"""
    p = pose or base_pose()

    def fn(u):
        return p, x, y, mode, wave
    return dur, fn


def walk(x0, y0, x1, y1, dur, steps_per_sec=2.0, amp=1.0, wave=False, flip=1):
    """走路：從 (x0,y0) 走到 (x1,y1)，dur 秒，帶步態。wave=True 邊走邊揮手（近手）。flip=-1 面朝左。"""
    def fn(u):
        k = u / dur if dur > 0 else 1.0
        pose = walk_pose(u * steps_per_sec, amp)
        if flip < 0:
            pose = _flip_x(pose)
        return pose, _lerp(x0, x1, k), _lerp(y0, y1, k), "stand", wave
    return dur, fn


def run(x0, y0, x1, y1, dur, steps_per_sec=3.0, amp=1.0, wave=False, flip=1):
    """跑步：從 (x0,y0) 到 (x1,y1)。"""
    def fn(u):
        k = u / dur if dur > 0 else 1.0
        pose = run_pose(u * steps_per_sec, amp)
        if flip < 0:
            pose = _flip_x(pose)
        return pose, _lerp(x0, x1, k), _lerp(y0, y1, k), "stand", wave
    return dur, fn


def jump(x0, y0, x1, y1, dur, steps_per_sec=2.0, amp=1.0, wave=False, flip=1):
    """跳躍式走路：從 (x0,y0) 到 (x1,y1)，週期性離地跳起（y 往上疊加）。"""
    def fn(u):
        k = u / dur if dur > 0 else 1.0
        pose = jump_pose(u * steps_per_sec, amp)
        if flip < 0:
            pose = _flip_x(pose)
        hop = max(0.0, math.sin(u * steps_per_sec * 2.0 * math.pi)) * 20.0 * amp
        return pose, _lerp(x0, x1, k), _lerp(y0, y1, k) - hop, "stand", wave
    return dur, fn


def slide(x0, y0, x1, y1, dur, pose=None, wave=False):
    """平移（無步態，如靠近/退後/滑步）。從 (x0,y0) 到 (x1,y1)。"""
    p = pose or base_pose()

    def fn(u):
        k = u / dur if dur > 0 else 1.0
        return p, _lerp(x0, x1, k), _lerp(y0, y1, k), "stand", wave
    return dur, fn


def squat_in(x, y, dur, drop=0.0, depth=1.0):
    """站→蹲：姿勢漸蹲＋頭部（位置 y）下沉 drop 像素。"""
    def fn(u):
        k = _ease_in_out(u / dur if dur > 0 else 1.0)
        return squat_pose(depth * k), x, y + drop * k, "stand", False
    return dur, fn


def squat_out(x, y, dur, drop=0.0, depth=1.0):
    """蹲→站：由蹲姿回到站立。"""
    def fn(u):
        k = _ease_in_out(u / dur if dur > 0 else 1.0)
        return squat_pose(depth * (1.0 - k)), x, y + drop * (1.0 - k), "stand", False
    return dur, fn


def squat_bob(x, y, dur, depth=1.0, rate=2.0):
    """蹲姿動態（上下動作）：蹲姿深度隨時間上下起伏（蹲起蹲起）。"""
    def fn(u):
        k = 0.5 + 0.5 * math.sin(u * rate * 2.0 * math.pi)   # 0..1
        d = 0.5 + 0.5 * k                                    # 0.5..1.0，保持在蹲姿內
        return squat_pose(d), x, y + SQUAT_DROP * d, "stand", False
    return dur, fn


def sit_down(x, y, dur, drop=0.0):
    """站→坐過渡（姿勢收腿＋頭下沉）。此段仍用站姿骨架（雙腿摺疊）。"""
    def fn(u):
        k = _ease_in_out(u / dur if dur > 0 else 1.0)
        pose = interp_pose(base_pose(), sit_pose(), k)
        return pose, x, y + drop * k, "stand", False
    return dur, fn


def sit_up(x, y, dur, drop=0.0):
    """坐→站過渡（姿勢收腿反向展開＋頭上升）。"""
    def fn(u):
        k = _ease_in_out(u / dur if dur > 0 else 1.0)
        pose = interp_pose(sit_pose(), base_pose(), k)
        return pose, x, y + drop * (1.0 - k), "stand", False
    return dur, fn


# ---------------------------------------------------------------- 朝向（視角）

def resolve_facing(dx, dy, manual="auto"):
    """依路徑方向決定朝向（視角）。

    manual ∈ {auto, side, left, right, front, back}：
      auto  ＝與水平夾角 >70° → 正視/後視；否則側視（左/右）。
      side  ＝維持側視（爬高/爬低用，不轉正/後視）。
      其餘  ＝直接指定。
    """
    if manual == "left":
        return "left"
    if manual == "right":
        return "right"
    if manual == "front":
        return "front"
    if manual == "back":
        return "back"
    adx = abs(dx)
    if manual == "side":
        return "right" if dx >= 0 else "left"
    # auto
    angle = math.degrees(math.atan2(abs(dy), adx)) if adx > 1e-6 else 90.0
    if angle >= 70.0:
        return "back" if dy < 0 else "front"
    return "right" if dx >= 0 else "left"


def _pose_of(wp):
    return (wp or {}).get("pose", "stand")


def _is_squat(p):
    return p in ("squat", "squat_bob")


def _hold_seg(wp):
    """回傳 waypoint 的停留段 (dur, fn)（含姿勢＋揮手），hold<=0 回 None。"""
    dur = float((wp or {}).get("hold", 0) or 0)
    if dur <= 0:
        return None
    pose = _pose_of(wp)
    wave = bool((wp or {}).get("wave", False))
    x = wp.get("x", 0)
    y = wp.get("y", 0)
    if pose == "sit":
        return hold(x, y, dur, mode="sit", wave=wave)
    if pose == "squat":
        return hold(x, y, dur, squat_pose(), wave=wave)
    if pose == "squat_bob":
        return squat_bob(x, y, dur, depth=1.0, rate=2.0)
    return hold(x, y, dur, wave=wave)


def compile_path(waypoints, segments):
    """把「路徑點＋動作段」編譯成 Trajectory（自動插入 站↔坐、站↔蹲 過渡）。

    waypoints: [{x, y, pose(stand/sit/squat), wave(bool), hold(秒)}, ...]
    segments:  [{motion(walk/slide/run/jump), dur, steps_per_sec, amp, facing}, ...]
      segments[i] 對應 waypoints[i] → waypoints[i+1]。
    """
    tr = Trajectory()
    wps = [dict(w) for w in (waypoints or [])]
    segs = [dict(s) for s in (segments or [])]
    if not wps:
        return tr
    n_seg = max(0, len(wps) - 1)

    facings = []
    for i in range(n_seg):
        seg = segs[i] if i < len(segs) else {}
        p0 = wps[i]
        p1 = wps[i + 1]
        dx = p1.get("x", 0) - p0.get("x", 0)
        dy = p1.get("y", 0) - p0.get("y", 0)
        facings.append(resolve_facing(dx, dy, seg.get("facing", "auto")))

    def motion_seg(i):
        seg = segs[i] if i < len(segs) else {}
        motion = seg.get("motion", "walk")
        dur = float(seg.get("dur", 1.0))
        sps = float(seg.get("steps_per_sec", 2.0))
        amp = float(seg.get("amp", 1.0))
        wave = bool(seg.get("wave", False))
        flip = -1 if facings[i] == "left" else 1
        p0 = wps[i]
        p1 = wps[i + 1]
        x0, y0, x1, y1 = p0["x"], p0["y"], p1["x"], p1["y"]
        if motion == "run":
            return run(x0, y0, x1, y1, dur, sps, amp, wave, flip)
        if motion == "jump":
            return jump(x0, y0, x1, y1, dur, sps, amp, wave, flip)
        if motion == "slide":
            return slide(x0, y0, x1, y1, dur, wave=wave)
        return walk(x0, y0, x1, y1, dur, sps, amp, wave, flip)

    facing0 = facings[0] if facings else "right"
    hs = _hold_seg(wps[0])
    if hs:
        tr.append(*hs, facing0)
    cur_pose = _pose_of(wps[0])

    for i in range(n_seg):
        p0 = wps[i]
        p1 = wps[i + 1]
        fc = facings[i]
        # 移動前：若當前是坐/蹲，先自動站起來
        if cur_pose == "sit":
            tr.append(*sit_up(p0["x"], p0["y"], TRANS_SIT, SIT_DROP), fc)
        elif _is_squat(cur_pose):
            tr.append(*squat_out(p0["x"], p0["y"], TRANS_SQUAT, SQUAT_DROP), fc)
        cur_pose = "stand"
        # 移動
        tr.append(*motion_seg(i), fc)
        # 移動後：依目標點姿勢自動坐下/蹲下
        tpose = _pose_of(p1)
        if tpose == "sit":
            tr.append(*sit_down(p1["x"], p1["y"], TRANS_SIT, SIT_DROP), fc)
            cur_pose = "sit"
        elif _is_squat(tpose):
            tr.append(*squat_in(p1["x"], p1["y"], TRANS_SQUAT, SQUAT_DROP), fc)
            cur_pose = tpose
        else:
            cur_pose = "stand"
        # 目標點停留（姿勢＋揮手）
        hs = _hold_seg(p1)
        if hs:
            tr.append(*hs, fc)
    return tr


if __name__ == "__main__":
    # 自測：姿勢鍵齊全、取樣不拋錯、內插合理
    wps = [
        {"x": 60, "y": 760, "pose": "stand", "hold": 0.3},
        {"x": 380, "y": 760, "pose": "sit", "wave": True, "hold": 0.8},
        {"x": 60, "y": 760, "pose": "stand", "hold": 0.2},
    ]
    segs = [
        {"motion": "walk", "dur": 2.0, "steps_per_sec": 2.0, "amp": 1.0},
        {"motion": "run", "dur": 1.6, "steps_per_sec": 3.0, "amp": 1.0},
    ]
    tr = compile_path(wps, segs)
    for tt in [0.0, 0.5, 2.0, 2.4, 3.0, 4.0, tr.duration()]:
        pose, x, y, mode, wave, facing = tr.sample(tt)
        assert set(pose) == set(POSE_KEYS), f"pose 鍵不全 @t={tt}"
        print(f"t={tt:5.1f} mode={mode:5s} wave={str(wave):5s} facing={facing:5s} x={x:6.1f} y={y:6.1f}")
    print("OK: char_trajectory 自測通過，總長", tr.duration())
