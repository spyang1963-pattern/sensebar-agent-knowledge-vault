"""char_parts.py - 零件式角色（頭/身/腿/手/髮/帽…組合）

角色 = 一份「配方」(recipe) 選零件＋顏色，通用渲染器組出角色。
零件全部參數化，與背景無關；表情/對嘴/眨眼/視線對齊由 state 傳入。

設計：畫風由「零件 + 配方」決定；「構圖（站/坐/半身）」由 char_modes 決定。
    char_parts（長相）  ⟂  char_modes（姿勢構圖）
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

INK = (21, 26, 27)
SKIN = (247, 219, 196)

# ---------------------------------------------------------------- 零件：頭

def head_round(ld, cx, cy, r, skin, ink):
    ld.ellipse([cx - r, cy - r, cx + r, cy + r], fill=skin, outline=ink, width=5)


def head_square(ld, cx, cy, r, skin, ink):
    ld.rounded_rectangle([cx - r, cy - r, cx + r, cy + r], radius=int(r * 0.3),
                         fill=skin, outline=ink, width=5)


HEADS = {"round": head_round, "square": head_square}

# ---------------------------------------------------------------- 零件：頭髮

def hair_chord(ld, cx, cy, r, color, ink):
    ld.chord([cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2], 217, 323,
             fill=color, outline=ink, width=5)


def hair_none(ld, cx, cy, r, color, ink):
    return


HAIRS = {"chord": hair_chord, "none": hair_none}

# ---------------------------------------------------------------- 零件：帽子

def hat_cap(ld, cx, cy, r, color, ink):
    ld.rounded_rectangle([cx - int(r * 0.85), cy - r + 2, cx + int(r * 0.5), cy - r + int(r * 0.42)],
                         radius=10, fill=color, outline=ink, width=4)


HATS = {"cap": hat_cap}

# ---------------------------------------------------------------- 零件：眼睛

def eye_dot(ld, cx, cy, r, dir, gaze, state, ink, dx=0.0, dy=0.0):
    eye_x = cx + dir * int(r * 0.42) + int(dx * r)
    ey = cy + int(r * 0.12) + int(gaze * r) + int(dy * r)
    if state == "blink":
        ld.line([(eye_x - int(r * 0.26), ey), (eye_x + int(r * 0.26), ey)], fill=ink, width=5)
    elif state == "wide":
        ld.ellipse([eye_x - int(r * 0.28), ey - int(r * 0.24), eye_x + int(r * 0.28), ey + int(r * 0.24)],
                   fill=(255, 255, 255), outline=ink, width=4)
        ld.ellipse([eye_x - int(r * 0.1), ey - int(r * 0.08), eye_x + int(r * 0.1), ey + int(r * 0.12)], fill=ink)
    else:
        ld.ellipse([eye_x - int(r * 0.17), ey - int(r * 0.17), eye_x + int(r * 0.17), ey + int(r * 0.17)], fill=ink)
    return eye_x, ey


EYES = {"dot": eye_dot}


def eye_big(ld, cx, cy, r, dir, gaze, state, ink, dx=0.0, dy=0.0):
    """大圓眼（青蛙/貓用），依 state：normal/blink/wide。"""
    eye_x = cx + dir * int(r * 0.42) + int(dx * r)
    ey = cy + int(r * 0.10) + int(gaze * r) + int(dy * r)
    if state == "blink":
        ld.line([(eye_x - int(r * 0.30), ey), (eye_x + int(r * 0.30), ey)], fill=ink, width=5)
    elif state == "wide":
        ld.ellipse([eye_x - int(r * 0.36), ey - int(r * 0.36), eye_x + int(r * 0.36), ey + int(r * 0.36)],
                   fill=(255, 255, 255), outline=ink, width=4)
        ld.ellipse([eye_x - int(r * 0.14), ey - int(r * 0.14), eye_x + int(r * 0.14), ey + int(r * 0.14)], fill=ink)
    else:
        ld.ellipse([eye_x - int(r * 0.30), ey - int(r * 0.30), eye_x + int(r * 0.30), ey + int(r * 0.30)],
                   fill=(255, 255, 255), outline=ink, width=4)
        ld.ellipse([eye_x - int(r * 0.12), ey - int(r * 0.12), eye_x + int(r * 0.12), ey + int(r * 0.12)], fill=ink)
    return eye_x, ey


EYES["big"] = eye_big

# ---------------------------------------------------------------- 零件：眉毛

def brow_flat(ld, cx, cy, r, dir, eye_x, ey, ink):
    by = ey - int(r * 0.42)
    ld.line([(eye_x - int(r * 0.26), by), (eye_x + int(r * 0.26), by)], fill=ink, width=5)


def brow_up(ld, cx, cy, r, dir, eye_x, ey, ink):
    by = ey - int(r * 0.42)
    ld.line([(eye_x - int(r * 0.26), by - int(r * 0.1)), (eye_x + int(r * 0.26), by - int(r * 0.32))], fill=ink, width=5)


def brow_in(ld, cx, cy, r, dir, eye_x, ey, ink):
    by = ey - int(r * 0.42)
    ld.line([(eye_x - int(r * 0.26), by - int(r * 0.32)), (eye_x + int(r * 0.26), by - int(r * 0.1))], fill=ink, width=5)


BROWS = {"flat": brow_flat, "up": brow_up, "in": brow_in}

# ---------------------------------------------------------------- 零件：嘴巴

def mouth_line(ld, cx, cy, r, dir, state, ink, dx=0.0, dy=0.0):
    my = cy + int(r * 0.5) + int(dy * r)
    if state == "open":
        mx = cx + dir * int(r * 0.4) + int(dx * r)
        ld.ellipse([mx - int(r * 0.14), my - int(r * 0.06), mx + int(r * 0.18), my + int(r * 0.26)],
                   fill=(122, 60, 60), outline=ink, width=4)
    elif state == "half":
        mx = cx + dir * int(r * 0.4) + int(dx * r)
        ld.ellipse([mx - int(r * 0.1), my - int(r * 0.03), mx + int(r * 0.14), my + int(r * 0.14)],
                   fill=(122, 60, 60), outline=ink, width=4)
    else:
        ld.line([(cx + dir * int(r * 0.24) + int(dx * r), my), (cx + dir * int(r * 0.62) + int(dx * r), my)], fill=ink, width=5)


MOUTHS = {"line": mouth_line}


def mouth_wide(ld, cx, cy, r, dir, state, ink, dx=0.0, dy=0.0):
    """寬嘴（大咧嘴），依 state 對嘴：closed=微笑弧、half=半開、open=張大。"""
    my = cy + int(r * 0.45) + int(dy * r)
    mx = cx + dir * int(r * 0.3) + int(dx * r)
    if state == "open":
        ld.ellipse([mx - int(r * 0.4), my - int(r * 0.05), mx + int(r * 0.4), my + int(r * 0.35)],
                   fill=(122, 60, 60), outline=ink, width=4)
    elif state == "half":
        ld.ellipse([mx - int(r * 0.4), my - int(r * 0.02), mx + int(r * 0.4), my + int(r * 0.18)],
                   fill=(122, 60, 60), outline=ink, width=4)
    else:
        ld.arc([mx - int(r * 0.45), my - int(r * 0.35), mx + int(r * 0.45), my + int(r * 0.35)],
               start=20, end=160, fill=ink, width=5)


MOUTHS["wide"] = mouth_wide

# ---------------------------------------------------------------- 零件：眼鏡

def glasses_round(ld, cx, cy, r, dir, eye_x, ey, ink):
    ld.ellipse([eye_x - int(r * 0.34), ey - int(r * 0.44), eye_x + int(r * 0.34), ey + int(r * 0.2)],
               outline=ink, width=4)
    ld.line([(eye_x - int(r * 0.34), ey - int(r * 0.12)), (cx - dir * int(r * 0.45), ey - int(r * 0.12))],
            fill=ink, width=4)


# ---------------------------------------------------------------- 配方

REN_RECIPE = {
    "name": "阿忍",
    "skin": SKIN, "ink": INK,
    "head": "round", "eyes": "dot",
    "hair": {"style": "chord", "color": (38, 42, 45)},
    "hat": None, "glasses": True,
    "top": (117, 137, 133), "pants": (58, 62, 68),
}

LE_RECIPE = {
    "name": "小樂",
    "skin": SKIN, "ink": INK,
    "head": "round", "eyes": "dot",
    "hair": {"style": "chord", "color": (94, 66, 51)},
    "hat": {"style": "cap", "color": (196, 92, 82)}, "glasses": False,
    "top": (224, 158, 106), "pants": (70, 82, 96),
}

FROG_RECIPE = {
    "name": "青蛙",
    "skin": (150, 200, 120), "ink": INK,
    "head": "round", "eyes": "big", "mouth": "wide",
    "hair": {"style": "none"}, "hat": None, "glasses": False,
    "top": (110, 170, 100), "pants": (90, 150, 90),
}

RECIPES = {"ren": REN_RECIPE, "le": LE_RECIPE, "frog": FROG_RECIPE}

_OVERRIDE = {}
_POSE_OVERRIDE = {}


def set_override(mapping):
    """覆寫 who→recipe 對應（GUI 選長相用）。mapping = {'le': 'frog', 'ren': 'ren'}"""
    global _OVERRIDE
    _OVERRIDE = mapping or {}


def set_pose_override(mapping):
    """覆寫 who→姿勢（11 錨點 offset），供場景預覽拖曳。mapping = {'le': {neck_dx:..}, 'ren': {..}}"""
    global _POSE_OVERRIDE
    _POSE_OVERRIDE = mapping or {}


def apply_pose(recipe, pose):
    """回傳套用姿勢覆寫的配方副本（11 錨點 offset 替換）。"""
    if not pose:
        return recipe
    r = dict(recipe)
    r.update(pose)
    return r


def get_recipe(who):
    key = _OVERRIDE.get(who, who)
    recipe = RECIPES.get(key, REN_RECIPE)
    pose = _POSE_OVERRIDE.get(who)
    if pose:
        recipe = apply_pose(recipe, pose)
    return recipe


def list_recipes():
    return [{"key": k, "name": RECIPES[k]["name"]} for k in RECIPES]


# ---------------------------------------------------------------- 零件目錄＋自訂角色

PART_CATALOG = {
    "heads": [{"key": "round", "name": "圓頭"}, {"key": "square", "name": "方頭"}],
    "hairs": [{"key": "chord", "name": "短髮"}, {"key": "none", "name": "無"}],
    "hats": [{"key": "none", "name": "無"}, {"key": "cap", "name": "帽子"}],
    "eyes": [{"key": "dot", "name": "點眼"}, {"key": "big", "name": "大眼"}],
    "mouths": [{"key": "line", "name": "線嘴"}, {"key": "wide", "name": "寬嘴"}],
    "ears": [{"key": "none", "name": "無"}, {"key": "round", "name": "圓耳"}, {"key": "pointy", "name": "尖耳"}],
    "brows": [{"key": "line", "name": "細眉"}, {"key": "thick", "name": "粗眉"}, {"key": "none", "name": "無"}],
}

DEFAULT_SPEC = {
    "name": "新角色",
    "head": "round", "hair": "chord", "hat": "none", "eyes": "dot", "mouth": "line",
    "ears": "none", "brow": "line", "glasses": False, "facing": "auto",
    "eye_dx": 0, "eye_dy": 0, "mouth_dx": 0, "mouth_dy": 0,
    "neck_dx": 0, "neck_dy": 0.7, "hip_dx": 0, "hip_dy": 2.0,
    "elbow_lx": -0.4, "elbow_ly": 0.15, "elbow_rx": 0.4, "elbow_ry": 0.15,
    "hand_lx": -0.2, "hand_ly": 0.15, "hand_rx": 0.2, "hand_ry": 0.15,
    "knee_lx": -0.3, "knee_ly": 0.95, "knee_rx": 0.3, "knee_ry": 0.95,
    "foot_lx": -0.08, "foot_ly": 0.95, "foot_rx": 0.08, "foot_ry": 0.95,
    "head_dx": 0, "head_dy": 0,
    "skin": "#f7dbc4", "hair_color": "#262a2d", "hat_color": "#c45c52",
    "top": "#758985", "pants": "#3a3e44",
}

_CUSTOM_FILE = Path(__file__).resolve().parents[2] / "working" / "custom_recipes.json"


def _hex_to_rgb(h):
    h = (h or "").lstrip("#")
    if len(h) != 6:
        return (200, 200, 200)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return (200, 200, 200)


def build_recipe(spec):
    """從 spec（零件選擇＋顏色）建一份配方 dict。"""
    spec = {**DEFAULT_SPEC, **(spec or {})}
    hat = None
    if spec.get("hat") and spec["hat"] != "none":
        hat = {"style": spec["hat"], "color": _hex_to_rgb(spec.get("hat_color"))}
    return {
        "name": spec.get("name", "新角色"),
        "skin": _hex_to_rgb(spec.get("skin")), "ink": INK,
        "head": spec.get("head", "round"),
        "eyes": spec.get("eyes", "dot"),
        "mouth": spec.get("mouth", "line"),
        "ears": spec.get("ears", "none"),
        "brow": spec.get("brow", "line"),
        "hair": {"style": spec.get("hair", "none"), "color": _hex_to_rgb(spec.get("hair_color"))},
        "hat": hat,
        "glasses": bool(spec.get("glasses")),
        "facing": spec.get("facing", "auto"),
        "eye_dx": float(spec.get("eye_dx") or 0), "eye_dy": float(spec.get("eye_dy") or 0),
        "mouth_dx": float(spec.get("mouth_dx") or 0), "mouth_dy": float(spec.get("mouth_dy") or 0),
        "neck_dx": float(spec.get("neck_dx", 0) or 0), "neck_dy": float(spec.get("neck_dy", 0.7) if spec.get("neck_dy") is not None else 0.7),
        "hip_dx": float(spec.get("hip_dx", 0) or 0), "hip_dy": float(spec.get("hip_dy", 2.0) if spec.get("hip_dy") is not None else 2.0),
        "elbow_lx": float(spec.get("elbow_lx") if spec.get("elbow_lx") is not None else -0.4),
        "elbow_ly": float(spec.get("elbow_ly") if spec.get("elbow_ly") is not None else 0.15),
        "elbow_rx": float(spec.get("elbow_rx") if spec.get("elbow_rx") is not None else 0.4),
        "elbow_ry": float(spec.get("elbow_ry") if spec.get("elbow_ry") is not None else 0.15),
        "hand_lx": float(spec.get("hand_lx") if spec.get("hand_lx") is not None else -0.2),
        "hand_ly": float(spec.get("hand_ly") if spec.get("hand_ly") is not None else 0.15),
        "hand_rx": float(spec.get("hand_rx") if spec.get("hand_rx") is not None else 0.2),
        "hand_ry": float(spec.get("hand_ry") if spec.get("hand_ry") is not None else 0.15),
        "knee_lx": float(spec.get("knee_lx") if spec.get("knee_lx") is not None else -0.3),
        "knee_ly": float(spec.get("knee_ly") if spec.get("knee_ly") is not None else 0.95),
        "knee_rx": float(spec.get("knee_rx") if spec.get("knee_rx") is not None else 0.3),
        "knee_ry": float(spec.get("knee_ry") if spec.get("knee_ry") is not None else 0.95),
        "foot_lx": float(spec.get("foot_lx") if spec.get("foot_lx") is not None else -0.08),
        "foot_ly": float(spec.get("foot_ly") if spec.get("foot_ly") is not None else 0.95),
        "foot_rx": float(spec.get("foot_rx") if spec.get("foot_rx") is not None else 0.08),
        "foot_ry": float(spec.get("foot_ry") if spec.get("foot_ry") is not None else 0.95),
        "head_dx": float(spec.get("head_dx", 0) or 0), "head_dy": float(spec.get("head_dy", 0) or 0),
        "top": _hex_to_rgb(spec.get("top")), "pants": _hex_to_rgb(spec.get("pants")),
    }


def render_head_image(recipe, r=70, facing=None):
    """渲染單獨的頭（供編輯器即時預覽），回傳 RGB Image。"""
    if facing is None:
        facing = recipe.get("facing", "auto")
    if facing in ("auto", "side"):
        facing = "right"
    layer, _cx, _cy = render_head_layer(recipe, r, facing, "flat", "normal", "closed", 0)
    bg = Image.new("RGBA", layer.size, (255, 255, 255, 255))
    bg.paste(layer, (0, 0), layer)
    return bg.convert("RGB")


def anchors_from(recipe, hx, hy, r):
    """從頭中心 (hx,hy) 算出 11 錨點座標（場景/編輯器通用）。"""
    ndx = int(recipe.get("neck_dx", 0.0) * r)
    ndy = int(recipe.get("neck_dy", 0.7) * r)
    pdx = int(recipe.get("hip_dx", 0.0) * r)
    pdy = int(recipe.get("hip_dy", 2.0) * r)
    nx = hx + ndx
    ny = hy + ndy
    px = nx + pdx
    py = ny + pdy
    el = (nx + int(recipe.get("elbow_lx", -0.4) * r), ny + int(recipe.get("elbow_ly", 0.15) * r))
    er = (nx + int(recipe.get("elbow_rx", 0.4) * r), ny + int(recipe.get("elbow_ry", 0.15) * r))
    hl = (el[0] + int(recipe.get("hand_lx", -0.2) * r), el[1] + int(recipe.get("hand_ly", 0.15) * r))
    hr = (er[0] + int(recipe.get("hand_rx", 0.2) * r), er[1] + int(recipe.get("hand_ry", 0.15) * r))
    kl = (px + int(recipe.get("knee_lx", -0.3) * r), py + int(recipe.get("knee_ly", 0.95) * r))
    kr = (px + int(recipe.get("knee_rx", 0.3) * r), py + int(recipe.get("knee_ry", 0.95) * r))
    fl = (kl[0] + int(recipe.get("foot_lx", -0.08) * r), kl[1] + int(recipe.get("foot_ly", 0.95) * r))
    fr = (kr[0] + int(recipe.get("foot_rx", 0.08) * r), kr[1] + int(recipe.get("foot_ry", 0.95) * r))
    return {"head": (hx, hy), "neck": (nx, ny), "hip": (px, py),
            "elbowL": el, "elbowR": er, "handL": hl, "handR": hr,
            "kneeL": kl, "kneeR": kr, "footL": fl, "footR": fr}


def character_geometry(recipe, r=50):
    """計算全身角色（站姿）的十一個錨點與畫布尺寸（供編輯器拖曳）。"""
    hdx = int(recipe.get("head_dx", 0.0) * r)
    hdy = int(recipe.get("head_dy", 0.0) * r)
    W = int(r * 5)
    H = int(r * 7)
    hx = W // 2 + hdx
    hy = int(r * 1.5) + hdy
    return (W, H), anchors_from(recipe, hx, hy, r)


def render_character_image(recipe, r=50, facing=None):
    """渲染全身角色（站姿，供編輯器預覽），回傳 RGB Image。"""
    facing = resolve_facing(recipe, 1, facing)
    (W, H), a = character_geometry(recipe, r)
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    hx, hy = a["head"]
    nx, ny = a["neck"]
    px, py = a["hip"]
    dir = -1 if facing == "left" else 1
    render_legs_stand(d, recipe, px, py, a["kneeL"][0], a["kneeL"][1], a["kneeR"][0], a["kneeR"][1],
                      a["footL"][0], a["footL"][1], a["footR"][0], a["footR"][1], r)
    render_arms(d, recipe, nx, ny, a["elbowL"][0], a["elbowL"][1], a["elbowR"][0], a["elbowR"][1],
                a["handL"][0], a["handL"][1], a["handR"][0], a["handR"][1], r)
    render_torso(d, recipe, nx, ny, px, py, r, int(r * 0.7))
    render_head(d, recipe, hx, hy, r, dir, "flat", "normal", "closed", 0, 0, (0, 0), facing)
    return img


def _tuplify(x):
    """把 JSON 讀回的 list 顏色轉回 tuple（PIL 只吃 tuple，不吃 list）。"""
    if isinstance(x, list):
        return tuple(_tuplify(i) for i in x)
    if isinstance(x, dict):
        return {k: _tuplify(v) for k, v in x.items()}
    return x


def _load_custom():
    try:
        data = json.loads(_CUSTOM_FILE.read_text(encoding="utf-8-sig"))
        for k, v in data.items():
            RECIPES[k] = _tuplify(v)
    except Exception:
        pass


def register_recipe(key, recipe):
    """註冊一個自訂角色，並存到 working/custom_recipes.json（供子行程渲染也讀得到）。"""
    RECIPES[key] = recipe
    try:
        data = {}
        try:
            data = json.loads(_CUSTOM_FILE.read_text(encoding="utf-8-sig"))
        except Exception:
            data = {}
        data[key] = recipe
        _CUSTOM_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CUSTOM_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


_load_custom()


# ---------------------------------------------------------------- 組合：頭

def _ears_round(ld, cx, cy, r, skin, ink, facing):
    """人類圓耳（頭兩側）。側視只看得到後腦那隻耳。"""
    sides = (-1, 1)
    if facing in ("left", "right"):
        sides = (1,) if facing == "left" else (-1,)
    for s in sides:
        ex = cx + s * int(r * 0.82)
        ey = cy + int(r * 0.08)
        ld.ellipse([ex - int(r * 0.15), ey - int(r * 0.2), ex + int(r * 0.15), ey + int(r * 0.2)],
                   fill=skin, outline=ink, width=4)


def _ears_pointy(ld, cx, cy, r, skin, ink, facing):
    """尖耳（頭頂兩側，貓/蛙用）。側視只看得到一耳。"""
    sides = (-1, 1)
    if facing in ("left", "right"):
        sides = (1,) if facing == "left" else (-1,)
    for s in sides:
        ld.polygon([(cx + s * int(r * 0.6), cy - int(r * 1.12)),
                    (cx + s * int(r * 0.12), cy - int(r * 0.3)),
                    (cx + s * int(r * 0.82), cy - int(r * 0.3))], fill=skin, outline=ink)


EARS = {"none": None, "round": _ears_round, "pointy": _ears_pointy}


def _draw_brow_side(ld, eye_x, ey, r, state, ink, width):
    by = ey - int(r * 0.42)
    if state == "up":
        ld.line([(eye_x - int(r * 0.26), by - int(r * 0.1)), (eye_x + int(r * 0.26), by - int(r * 0.32))], fill=ink, width=width)
    elif state == "in":
        ld.line([(eye_x - int(r * 0.26), by - int(r * 0.32)), (eye_x + int(r * 0.26), by - int(r * 0.1))], fill=ink, width=width)
    else:
        ld.line([(eye_x - int(r * 0.26), by), (eye_x + int(r * 0.26), by)], fill=ink, width=width)


def _draw_brow_front(ld, cx, cy, r, state, ink, width):
    ey = cy + int(r * 0.12)
    by = ey - int(r * 0.4)
    for s in (-1, 1):
        ex = cx + s * int(r * 0.32)
        if state == "up":
            ld.line([(ex - int(r * 0.22), by - int(r * 0.08)), (ex + int(r * 0.22), by - int(r * 0.28))], fill=ink, width=width)
        elif state == "in":
            ld.line([(ex - int(r * 0.22), by - int(r * 0.28)), (ex + int(r * 0.22), by - int(r * 0.08))], fill=ink, width=width)
        else:
            ld.line([(ex - int(r * 0.22), by), (ex + int(r * 0.22), by)], fill=ink, width=width)


def _eyes_front(ld, cx, cy, r, gaze, state, ink, style="dot", dx=0.0, dy=0.0):
    """正視：左右對稱雙眼（style=dot/big）。"""
    ey = cy + int(r * 0.12) + int(gaze * r) + int(dy * r)
    for s in (-1, 1):
        ex = cx + s * int(r * 0.32) + int(dx * r)
        if style == "big":
            if state == "blink":
                ld.line([(ex - int(r * 0.26), ey), (ex + int(r * 0.26), ey)], fill=ink, width=5)
            elif state == "wide":
                ld.ellipse([ex - int(r * 0.3), ey - int(r * 0.3), ex + int(r * 0.3), ey + int(r * 0.3)],
                           fill=(255, 255, 255), outline=ink, width=4)
                ld.ellipse([ex - int(r * 0.13), ey - int(r * 0.13), ex + int(r * 0.13), ey + int(r * 0.13)], fill=ink)
            else:
                ld.ellipse([ex - int(r * 0.24), ey - int(r * 0.24), ex + int(r * 0.24), ey + int(r * 0.24)],
                           fill=(255, 255, 255), outline=ink, width=4)
                ld.ellipse([ex - int(r * 0.1), ey - int(r * 0.1), ex + int(r * 0.1), ey + int(r * 0.1)], fill=ink)
        else:
            if state == "blink":
                ld.line([(ex - int(r * 0.22), ey), (ex + int(r * 0.22), ey)], fill=ink, width=5)
            elif state == "wide":
                ld.ellipse([ex - int(r * 0.22), ey - int(r * 0.2), ex + int(r * 0.22), ey + int(r * 0.2)],
                           fill=(255, 255, 255), outline=ink, width=4)
                ld.ellipse([ex - int(r * 0.08), ey - int(r * 0.06), ex + int(r * 0.08), ey + int(r * 0.1)], fill=ink)
            else:
                ld.ellipse([ex - int(r * 0.14), ey - int(r * 0.14), ex + int(r * 0.14), ey + int(r * 0.14)], fill=ink)


def _brow_front(ld, cx, cy, r, state, ink, width):
    ey = cy + int(r * 0.12)
    by = ey - int(r * 0.4)
    for s in (-1, 1):
        ex = cx + s * int(r * 0.32)
        if state == "up":
            ld.line([(ex - int(r * 0.22), by - int(r * 0.08)), (ex + int(r * 0.22), by - int(r * 0.28))], fill=ink, width=width)
        elif state == "in":
            ld.line([(ex - int(r * 0.22), by - int(r * 0.28)), (ex + int(r * 0.22), by - int(r * 0.08))], fill=ink, width=width)
        else:
            ld.line([(ex - int(r * 0.22), by), (ex + int(r * 0.22), by)], fill=ink, width=width)


def _mouth_front(ld, cx, cy, r, state, ink, style="line", dx=0.0, dy=0.0):
    my = cy + int(r * 0.5) + int(dy * r)
    mx = cx + int(dx * r)
    if style == "wide":
        if state == "open":
            ld.ellipse([mx - int(r * 0.4), my - int(r * 0.05), mx + int(r * 0.4), my + int(r * 0.35)],
                       fill=(122, 60, 60), outline=ink, width=4)
        elif state == "half":
            ld.ellipse([mx - int(r * 0.4), my - int(r * 0.02), mx + int(r * 0.4), my + int(r * 0.18)],
                       fill=(122, 60, 60), outline=ink, width=4)
        else:
            ld.arc([mx - int(r * 0.45), my - int(r * 0.35), mx + int(r * 0.45), my + int(r * 0.35)],
                   start=20, end=160, fill=ink, width=5)
    elif state == "open":
        ld.ellipse([mx - int(r * 0.16), my - int(r * 0.04), mx + int(r * 0.16), my + int(r * 0.22)],
                   fill=(122, 60, 60), outline=ink, width=4)
    elif state == "half":
        ld.ellipse([mx - int(r * 0.11), my - int(r * 0.02), mx + int(r * 0.11), my + int(r * 0.12)],
                   fill=(122, 60, 60), outline=ink, width=4)
    else:
        ld.line([(mx - int(r * 0.22), my), (mx + int(r * 0.22), my)], fill=ink, width=5)


def render_head_layer(recipe, r, facing, brow, eye, mouth, gaze):
    """在獨立層上畫頭（回傳 RGBA layer + 中心座標）。
    facing ∈ {"front","left","right","back"}：正視/側左/側右/後視。"""
    skin = recipe.get("skin", SKIN)
    ink = recipe.get("ink", INK)
    pad = int(r)
    size = 2 * (r + pad)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    cx = cy = r + pad
    HEADS.get(recipe.get("head", "round"), head_round)(ld, cx, cy, r, skin, ink)
    hair = recipe.get("hair") or {}
    if facing == "back":
        # 後視：頭髮蓋滿整個頭（無五官）
        ld.ellipse([cx - r, cy - r, cx + r, cy + r], fill=hair.get("color", (38, 42, 45)), outline=ink, width=5)
    else:
        HAIRS.get(hair.get("style", "none"), hair_none)(ld, cx, cy, r, hair.get("color", (38, 42, 45)), ink)
    ear_fn = EARS.get(recipe.get("ears", "none"))
    if ear_fn:
        ear_fn(ld, cx, cy, r, skin, ink, facing)
    hat = recipe.get("hat")
    if hat:
        HATS.get(hat.get("style", "cap"), hat_cap)(ld, cx, cy, r, hat.get("color", (196, 92, 82)), ink)
    brow_style = recipe.get("brow", "line")
    brow_w = 0 if brow_style == "none" else (9 if brow_style == "thick" else 5)
    eye_dx = recipe.get("eye_dx", 0.0)
    eye_dy = recipe.get("eye_dy", 0.0)
    mouth_dx = recipe.get("mouth_dx", 0.0)
    mouth_dy = recipe.get("mouth_dy", 0.0)
    if facing == "back":
        return layer, cx, cy
    if facing == "front":
        _eyes_front(ld, cx, cy, r, gaze, eye, ink, recipe.get("eyes", "dot"), eye_dx, eye_dy)
        if brow_w:
            _draw_brow_front(ld, cx, cy, r, brow, ink, brow_w)
        # 正視小圓鼻
        ld.ellipse([cx - int(r * 0.08), cy + int(r * 0.24) - int(r * 0.08),
                    cx + int(r * 0.08), cy + int(r * 0.24) + int(r * 0.08)], fill=skin, outline=ink, width=3)
        _mouth_front(ld, cx, cy, r, mouth, ink, recipe.get("mouth", "line"), mouth_dx, mouth_dy)
        if recipe.get("glasses"):
            # 正視眼鏡：左右兩片鏡片（明顯大於眼睛）＋鼻橋
            ey = cy + int(r * 0.12) + int(eye_dy * r)
            for s in (-1, 1):
                ex = cx + s * int(r * 0.32) + int(eye_dx * r)
                ld.ellipse([ex - int(r * 0.36), ey - int(r * 0.32), ex + int(r * 0.36), ey + int(r * 0.30)],
                           outline=ink, width=4)
            ld.line([(cx - int(r * 0.04), ey), (cx + int(r * 0.04), ey)], fill=ink, width=4)
        return layer, cx, cy
    dir = -1 if facing == "left" else 1
    eye_x, ey = EYES.get(recipe.get("eyes", "dot"), eye_dot)(ld, cx, cy, r, dir, gaze, eye, ink, eye_dx, eye_dy)
    if brow_w:
        _draw_brow_side(ld, eye_x, ey, r, brow, ink, brow_w)
    # 鼻子/臉頰（側臉的突起）
    ld.ellipse([cx + dir * int(r * 0.72) - int(r * 0.13), cy + int(r * 0.12) - int(r * 0.13),
                cx + dir * int(r * 0.72) + int(r * 0.13), cy + int(r * 0.12) + int(r * 0.13)],
               fill=skin, outline=ink, width=4)
    MOUTHS.get(recipe.get("mouth", "line"), mouth_line)(ld, cx, cy, r, dir, mouth, ink, mouth_dx, mouth_dy)
    if recipe.get("glasses"):
        glasses_round(ld, cx, cy, r, dir, eye_x, ey, ink)
    return layer, cx, cy


def resolve_facing(recipe, dir, facing=None):
    """把 facing（None/auto/left/right/front/back）正規化成 left/right/front/back。"""
    if facing is None:
        facing = recipe.get("facing", "auto")
    if facing in ("auto", "side"):
        facing = "left" if dir < 0 else "right"
    return facing


def render_head(d, recipe, sx, sy, r, dir, brow, eye, mouth, gaze=0, tilt=0, shift=(0, 0), facing=None):
    """畫頭（可旋轉 tilt 度），貼到主畫布 (sx,sy)。"""
    facing = resolve_facing(recipe, dir, facing)
    layer, cx, cy = render_head_layer(recipe, r, facing, brow, eye, mouth, gaze)
    if tilt and facing in ("left", "right"):
        layer = layer.rotate(tilt, resample=Image.BICUBIC, center=(cx, cy + r))
    d._image.paste(layer, (int(sx - cx + shift[0]), int(sy - cy + shift[1])), layer)


# ---------------------------------------------------------------- 組合：身體

def render_torso(d, recipe, nx, ny, px, py, r, top_w, bot_w=None, lean=0):
    """上半身（軀幹），從頸(nx,ny)畫到髖(px,py)。lean 額外水平偏移頸部（前傾）。"""
    fill = recipe.get("top", (117, 137, 133))
    ink = recipe.get("ink", INK)
    bot_w = top_w if bot_w is None else bot_w
    nx2 = nx + int(lean)
    d.polygon([(nx2 - top_w, ny), (nx2 + top_w, ny),
               (px + bot_w, py), (px - bot_w, py)], fill=fill, outline=ink)
    d.line([(nx2 - top_w, ny), (nx2 + top_w, ny)], fill=ink, width=4)
    d.line([(px - bot_w, py), (px + bot_w, py)], fill=ink, width=4)


def render_legs_stand(d, recipe, px, py, klx, kly, krx, kry, flx, fly, frx, fry, r):
    """站姿雙腿（兩段），髖→膝→腳。"""
    pants = recipe.get("pants", (58, 62, 68))
    ink = recipe.get("ink", INK)
    for (kx, ky, fx, fy) in ((klx, kly, flx, fly), (krx, kry, frx, fry)):
        d.line([(px, py), (kx, ky)], fill=pants, width=int(r * 0.5))
        d.line([(kx, ky), (fx, fy)], fill=pants, width=int(r * 0.45))
        d.ellipse([fx - int(r * 0.3), fy - int(r * 0.12), fx + int(r * 0.3), fy + int(r * 0.28)],
                  fill=(40, 40, 44), outline=ink, width=3)


def render_arms(d, recipe, nx, ny, elx, ely, erx, ery, hlx, hly, hrx, hry, r):
    """雙臂（兩段），肩→肘→手。"""
    top = recipe.get("top", (117, 137, 133))
    ink = recipe.get("ink", INK)
    skin = recipe.get("skin", SKIN)
    shy = ny + int(r * 0.2)
    for (ex, ey, hx, hy) in ((elx, ely, hlx, hly), (erx, ery, hrx, hry)):
        shx = nx + int((ex - nx) * 0.2)
        d.line([(shx, shy), (ex, ey)], fill=ink, width=int(r * 0.42) + 4)
        d.line([(shx, shy), (ex, ey)], fill=top, width=int(r * 0.42))
        d.line([(ex, ey), (hx, hy)], fill=ink, width=int(r * 0.4) + 4)
        d.line([(ex, ey), (hx, hy)], fill=top, width=int(r * 0.4))
        d.ellipse([hx - int(r * 0.2), hy - int(r * 0.2), hx + int(r * 0.2), hy + int(r * 0.2)],
                  fill=skin, outline=ink, width=3)


def render_hip_seated(d, recipe, px, py, r, dir, symmetric=False):
    """盤腿坐的下半身（單一形狀）＋腳，畫在髖(px,py)處。symmetric=True 正視/後視。"""
    pants = recipe.get("pants", (58, 62, 68))
    ink = recipe.get("ink", INK)
    if symmetric:
        hx0, hx1 = px - int(r * 1.2), px + int(r * 1.2)
        foot_x = px
    else:
        hip_back = px - dir * int(r * 0.9)
        hip_front = px + dir * int(r * 1.6)
        hx0, hx1 = min(hip_back, hip_front), max(hip_back, hip_front)
        foot_x = px + dir * int(r * 1.4)
    d.rounded_rectangle([hx0, py, hx1, py + int(r * 1.1)], radius=int(r * 0.55),
                        fill=pants, outline=ink, width=4)
    d.ellipse([foot_x - int(r * 0.3), py + int(r * 0.4), foot_x + int(r * 0.3), py + int(r * 1.2)],
              fill=(40, 40, 44), outline=ink, width=3)


def render_arm(d, recipe, nx, ny, ex, ey, hx, hy, r, t, wave):
    """單臂（兩段），肩（頸略下）→肘(ex,ey)→手(hx,hy)。wave 時手舉起。"""
    import math
    top = recipe.get("top", (117, 137, 133))
    ink = recipe.get("ink", INK)
    skin = recipe.get("skin", SKIN)
    shy = ny + int(r * 0.2)
    shx = nx + int((ex - nx) * 0.2)
    if wave:
        wa = math.sin(t * 8) * 16
        hx = shx + int(r * 0.4) + wa
        hy = shy - int(r * 2.0)
    d.line([(shx, shy), (ex, ey)], fill=ink, width=int(r * 0.42) + 4)
    d.line([(shx, shy), (ex, ey)], fill=top, width=int(r * 0.42))
    d.line([(ex, ey), (hx, hy)], fill=ink, width=int(r * 0.4) + 4)
    d.line([(ex, ey), (hx, hy)], fill=top, width=int(r * 0.4))
    d.ellipse([hx - int(r * 0.2), hy - int(r * 0.2), hx + int(r * 0.2), hy + int(r * 0.2)],
              fill=skin, outline=ink, width=3)
