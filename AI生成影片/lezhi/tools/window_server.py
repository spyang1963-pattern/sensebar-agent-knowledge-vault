#!/usr/bin/env python3
"""押忍工作室 · 內容窗口（本機小服務）

免安裝的按鈕式調整窗口：許願池 + 蓋章區 + 狀態列 + 執行排程。
只用 Python 標準函式庫。雙擊 open_window.bat 即開。

API
  GET  /                -> window.html
  GET  /api/queue       -> topics/queue.json
  POST /api/queue       -> 儲存 queue.json（並同步產生 queue.md）
  GET  /api/reviews     -> 待蓋章清單（腳本 / 成片）
  POST /api/review      -> {key, decision} 寫入 review.json
  POST /api/run         -> {ids:[...]} 背景執行 make_short.py
  GET  /api/runstatus   -> {running, log, results}
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ENGINE = Path(__file__).resolve().parents[2] / "engine"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))
try:
    from core import pack as epack             # 領域包（Manifest-first）
    LEZHI = epack.content_root(epack.load())
except Exception:
    epack = None
    LEZHI = Path(__file__).resolve().parents[1]
ROOT = LEZHI.parents[1]                       # D:\AI-Agent-Workspace
FILMS = LEZHI.parent                          # ...\AI生成影片（產出庫可存取範圍）
MAKE_SHORT = ROOT / "make_short.py"
QUEUE_JSON = LEZHI / "topics" / "queue.json"
QUEUE_MD = LEZHI / "topics" / "queue.md"
SCRIPTS = LEZHI / "scripts"
OUTPUT = LEZHI / "output"
CARDS = LEZHI / "assets" / "cards"
BGM_DIR = LEZHI / "assets"
BGM = LEZHI / "assets" / "bgm_warm.wav"
PHOTO_BG_DIR = LEZHI / "assets" / "backgrounds" / "photo"
IMG_EXTS = ("*.jpg", "*.jpeg", "*.png", "*.webp")
PROC_BG = ["plain", "living", "cafe", "site", "kitchen", "bedroom",
           "office", "restaurant", "balcony", "showroom", "outdoor"]
REVIEW_JSON = LEZHI / "review.json"
SETTINGS_JSON = LEZHI / "settings.json"
MAKE_DIALOG = LEZHI / "tools" / "make_dialog.py"
MAKE_COMIC = LEZHI / "tools" / "make_comic.py"   # 對話劇正式版型（2026-10-18 定案）
MAKE_SCENE_DIALOG = LEZHI / "tools" / "scene_dialog.py"   # 場景式對話劇（融合版）
SCENE_BG_GEN = LEZHI / "tools" / "scene_bg_gen.py"        # AI 背景生成器
SCENE_BG_DIR = LEZHI.parent / "working" / "ai_bg3"
SCENE_POS_JSON = LEZHI.parent / "working" / "scene_pos.json"
SCENE_POSE = {"living": "sit", "cafe": "sit",
              "kitchen": "sitstand", "park": "sitstand", "cafe_outdoor": "sitstand", "office": "sitstand",
              "site": "stand", "sidewalk": "stand", "park_gate": "stand", "bus_stop": "stand", "pavilion": "stand"}
SCENE_NAME = {"living": "客廳", "cafe": "咖啡廳", "kitchen": "廚房",
              "park": "公園", "cafe_outdoor": "咖啡店外", "office": "辦公室",
              "site": "工地", "sidewalk": "人行道", "park_gate": "公園門外",
              "bus_stop": "候車亭", "pavilion": "涼亭"}
try:
    import char_modes as _char_modes_mod
    CHAR_MODES = _char_modes_mod.list_modes()
except Exception:
    CHAR_MODES = [{"key": "mode_2", "name": "2人角色-2（怪奇盤腿側身）"}]
try:
    import char_parts as _char_parts_mod
    CHAR_RECIPES = _char_parts_mod.list_recipes()
except Exception:
    CHAR_RECIPES = [{"key": "ren", "name": "阿忍"}, {"key": "le", "name": "小樂"}]
try:
    import char_trajectory as _ct
except Exception:
    _ct = None
TRAJECTORY_DEMO = LEZHI / "tools" / "trajectory_demo.py"
MOTION_JSON = LEZHI.parent / "working" / "motion_timeline.json"

# 動作時間軸：點動作（姿勢）與段動作（移動）分離
MOTION_POSES = [
    {"key": "stand", "name": "站姿"},
    {"key": "sit", "name": "坐姿"},
    {"key": "squat", "name": "蹲姿（靜態）"},
    {"key": "squat_bob", "name": "蹲姿（動態上下）"},
]
MOTION_KINDS = [
    {"key": "walk", "name": "走路"},
    {"key": "slide", "name": "滑步"},
    {"key": "run", "name": "跑步"},
    {"key": "jump", "name": "跳躍走路"},
]
MOTION_FACING = [
    {"key": "auto", "name": "自動（陡坡轉正/後視）"},
    {"key": "side", "name": "維持側視（爬高/爬低）"},
    {"key": "left", "name": "朝左"},
    {"key": "right", "name": "朝右"},
    {"key": "front", "name": "正視"},
    {"key": "back", "name": "後視"},
]
MOTION_PARAMS = {
    "dur": {"label": "秒", "min": 0.1, "max": 10, "step": 0.1},
    "steps_per_sec": {"label": "步頻", "min": 0.5, "max": 6, "step": 0.1},
    "amp": {"label": "幅度", "min": 0, "max": 2, "step": 0.05},
    "hold": {"label": "停留秒", "min": 0, "max": 10, "step": 0.1},
}
DEFAULT_MOTION = {
    "who": "ren", "r": 55, "bg": "park_1", "fps": 15,
    "waypoints": [
        {"x": 60, "y": 760, "pose": "stand", "wave": False, "hold": 0.3},
        {"x": 380, "y": 760, "pose": "sit", "wave": False, "hold": 1.0},
        {"x": 60, "y": 760, "pose": "stand", "wave": False, "hold": 0.0},
    ],
    "segments": [
        {"motion": "walk", "dur": 2.0, "steps_per_sec": 2.0, "amp": 1.0, "facing": "auto"},
        {"motion": "walk", "dur": 1.6, "steps_per_sec": 2.0, "amp": 1.0, "facing": "auto"},
    ],
}
ADHOC = ENGINE / "core" / "adhoc.py"            # 即興型產片（Pack 驅動）
MAKE_BGM = ROOT / "make_bgm.py"                 # 程序化背景音樂（numpy）
ENGINE = LEZHI.parent / "engine"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))
try:
    from core import registry as reg       # 風格/插槽登錄表
    from core import naming as ename       # 版本化命名
except Exception:
    reg = ename = None
SCRIPT_ENGINE = LEZHI / "tools" / "script_engine.py"
LOCAL = LEZHI / "tools" / "window.html"
PORT = 8787

DEFAULT_SETTINGS = {"bgm_enabled": True, "bgm": "bgm_playful.wav", "bgm_volume": 0.16,
                    "char_dir": "characters"}

_RUN = {"running": False, "log": "", "results": []}
_LOCK = threading.Lock()


def _read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    s.update(_read_json(SETTINGS_JSON, {}))
    return s


BGM_EXTS = ("*.wav", "*.mp3", "*.m4a", "*.aac", "*.ogg", "*.flac")


def _safe_stem(name):
    keep = "".join(c if (c.isalnum() or c in "-_") else "_" for c in (name or "").strip())
    return keep[:40].strip("_") or "clip"


def bgm_files():
    if not BGM_DIR.exists():
        return []
    found = []
    for e in BGM_EXTS:
        found += list(BGM_DIR.glob(e))
    return sorted(p.name for p in found)


def photo_bg_files():
    if not PHOTO_BG_DIR.exists():
        return []
    found = []
    for e in IMG_EXTS:
        found += list(PHOTO_BG_DIR.glob(e))
    return sorted(p.name for p in found)


def background_list():
    return {"procedural": PROC_BG, "photo": photo_bg_files()}


def scan_scenes():
    """掃描背景目錄，列出可用場景（編號，如 kitchen_1、pavilion_2、bus_stop_1_wide 橫式）。"""
    if not SCENE_BG_DIR.exists():
        return []
    items = []
    for f in sorted(SCENE_BG_DIR.glob("*.png")):
        stem = f.stem
        wide = stem.endswith("_wide")
        base = stem[:-len("_wide")] if wide else stem
        parts = base.rsplit("_", 1)
        if len(parts) != 2 or not parts[1].isdigit():
            continue
        stype = parts[0]
        if stype not in SCENE_POSE:
            continue
        name = f"{SCENE_NAME.get(stype, stype)}{parts[1]}"
        if wide:
            name += "·橫"
        items.append({"key": stem, "name": name,
                      "type": stype, "pose": SCENE_POSE[stype], "wide": wide, "path": str(f)})
    return items


_SCENE_DIALOG = None


def _sd():
    """惰性載入 scene_dialog.py（避免開機就吃 make_short/make_comic 的重依賴）。"""
    global _SCENE_DIALOG
    if _SCENE_DIALOG is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("scene_dialog", MAKE_SCENE_DIALOG)
        _SCENE_DIALOG = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_SCENE_DIALOG)
    return _SCENE_DIALOG


def render_scene_preview(data):
    """渲染單張場景預覽圖（背景＋小樂＋阿忍）。回傳 (png_bytes, anchors, err)。"""
    from PIL import Image, ImageDraw
    import io
    bg = data.get("bg") or ""
    if not bg:
        return None, None, "請選背景"
    bg_path = SCENE_BG_DIR / f"{bg}.png"
    if not bg_path.exists():
        return None, None, f"背景 {bg} 不存在"
    try:
        sd = _sd()
    except Exception as e:
        return None, None, f"載入 scene_dialog 失敗：{e}"
    if data.get("char_mode"):
        sd.set_char_mode(data["char_mode"])
    recipe_override = {}
    if data.get("le_recipe"):
        recipe_override["le"] = data["le_recipe"]
    if data.get("ren_recipe"):
        recipe_override["ren"] = data["ren_recipe"]
    if recipe_override:
        sd.cp.set_override(recipe_override)
    le_pose_override = data.get("le_pose") or {}
    ren_pose_override = data.get("ren_pose") or {}
    if le_pose_override or ren_pose_override:
        sd.cp.set_pose_override({"le": le_pose_override, "ren": ren_pose_override})
    le = data.get("le") or {}
    ren = data.get("ren") or {}
    try:
        img = Image.open(bg_path).convert("RGB")
    except Exception as e:
        return None, None, f"讀取背景失敗：{e}"
    W, H = img.size
    r = int(data.get("r") or sd._char_r(W, H))
    d = ImageDraw.Draw(img)
    # 預設位置隨畫布（直/橫）縮放：le 坐、ren 站（sitstand），拖曳覆寫則用絕對座標
    _, _, def_le_x, def_le_y, def_ren_x, def_ren_y = sd.resolve_pose("sitstand", W, H)
    le_x = int(le.get("x", def_le_x)); le_y = int(le.get("y", def_le_y)); le_pose = le.get("pose", "sit")
    ren_x = int(ren.get("x", def_ren_x)); ren_y = int(ren.get("y", def_ren_y)); ren_pose = ren.get("pose", "stand")
    le_dir, le_tilt, le_shift, le_lean = sd.look_at_gated("le", le_x, le_y, ren_x, ren_y)
    ren_dir, ren_tilt, ren_shift, ren_lean = sd.look_at_gated("ren", ren_x, ren_y, le_x, le_y)
    seat = bool(data.get("seat", True))
    t = 0.5
    if le_pose == "stand":
        sd.draw_char_standing(d, "le", le_x, le_y, r, le_dir, t, False,
                              tilt=le_tilt, shift=le_shift, lean=le_lean)
    else:
        if seat:
            sd.draw_seat(d, le_x, le_y, r)
        sd.draw_char_seated(d, "le", le_x, le_y, r, le_dir, "flat", "normal", "closed",
                            tilt=le_tilt, shift=le_shift, lean=le_lean)
    if ren_pose == "stand":
        sd.draw_char_standing(d, "ren", ren_x, ren_y, r, ren_dir, t, bool(data.get("wave")),
                              tilt=ren_tilt, shift=ren_shift, lean=ren_lean)
    else:
        if seat:
            sd.draw_seat(d, ren_x, ren_y, r)
        sd.draw_char_seated(d, "ren", ren_x, ren_y, r, ren_dir, "flat", "normal", "closed",
                            tilt=ren_tilt, shift=ren_shift, lean=ren_lean)
    anchors = {
        "le": sd.cp.anchors_from(sd.cp.get_recipe("le"), le_x, le_y, r),
        "ren": sd.cp.anchors_from(sd.cp.get_recipe("ren"), ren_x, ren_y, r),
    }
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue(), anchors, None


def motion_config():
    """載入動作時間軸設定（MOTION_JSON，缺則用 DEFAULT_MOTION）。"""
    cfg = json.loads(json.dumps(DEFAULT_MOTION))
    saved = _read_json(MOTION_JSON, {}) or {}
    if isinstance(saved, dict):
        cfg.update(saved)
    return cfg


def _set_motion_base(who):
    """時間軸用「對稱基底」(STAND) 做動作，不繼承 ⑥ 拖曳的非對稱骨架姿勢。

    ⑥ 自訂角色把「臉/髮/帽/眼鏡/顏色」（長相）與「11 錨點」（骨架姿勢）都存進 recipe。
    長相由 draw_char_standing 的 get_recipe 取用；骨架姿勢屬「場景姿勢」，若拿來當基底，
    會讓自訂角色（如光頭把右手拖到右側）在時間軸裡永遠偏一邊、不隨朝向翻轉。
    故時間軸一律用對稱 STAND 基底，動作（走/跑/跳/蹲/坐）都在其上做。
    """
    _ct.set_base_pose(None)


def motion_frame(cfg, t):
    """渲染時間軸在 t 秒的單張畫面。回傳 (png_bytes, meta, err)，meta 含角色座標。"""
    from PIL import Image, ImageDraw
    import io
    if _ct is None:
        return None, None, "char_trajectory 載入失敗"
    bg_key = cfg.get("bg") or ""
    bg_path = SCENE_BG_DIR / f"{bg_key}.png"
    if not bg_path.exists():
        return None, None, f"背景 {bg_key} 不存在（請先生成）"
    try:
        import char_modes as cm
        mode_obj = cm.get("mode_2")
    except Exception as e:
        return None, None, f"載入 char_modes 失敗：{e}"
    # 清掉場景預覽設的全局覆寫，確保時間軸角色乾淨
    try:
        _char_parts_mod.set_override({})
        _char_parts_mod.set_pose_override({})
    except Exception:
        pass
    who = cfg.get("who") or "ren"
    _set_motion_base(who)
    r = int(cfg.get("r") or 55)
    segs = cfg.get("segments") or []
    waypoints = cfg.get("waypoints") or []
    if not waypoints:
        return None, None, "時間軸沒有路徑點"
    traj = _ct.compile_path(waypoints, segs)
    pose, x, y, mode, wave, facing = traj.sample(float(t))
    d = -1 if facing == "left" else 1
    img = Image.open(bg_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    if mode == "sit":
        mode_obj.draw_char_seated(draw, who, x, y, r, d, "flat", "normal", "closed",
                                  facing=facing, wave=wave, t=float(t))
    else:
        mode_obj.draw_char_standing(draw, who, x, y, r, d, float(t), wave, "flat", "normal", "closed",
                                    facing=facing, pose_override=pose)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue(), {"x": float(x), "y": float(y), "mode": mode, "dir": int(d), "facing": facing}, None


def run_motion_render(data):
    """把時間軸渲染成一支 MP4（背景執行，沿用 _RUN 日誌輪詢）。"""
    with _LOCK:
        _RUN["running"] = True
        _RUN["log"] = ""
        _RUN["results"] = []
    cfg = json.loads(json.dumps(data.get("config") or data or {}))
    cfg.setdefault("fps", 15)
    _write_json(MOTION_JSON, cfg)
    log_lines = []

    def emit(s):
        log_lines.append(s)
        with _LOCK:
            _RUN["log"] = "\n".join(log_lines)

    try:
        bg_key = cfg.get("bg") or ""
        bg_path = SCENE_BG_DIR / f"{bg_key}.png"
        if not bg_path.exists():
            emit(f"[錯誤] 背景 {bg_key} 不存在，請先生成（scene_bg_gen.py）")
            return
        segs = cfg.get("segments") or []
        waypoints = cfg.get("waypoints") or []
        if not waypoints:
            emit("[錯誤] 時間軸沒有路徑點")
            return
        fps = int(cfg.get("fps") or 15)
        who = cfg.get("who") or "ren"
        _set_motion_base(who)
        r = int(cfg.get("r") or 55)
        outdir = LEZHI.parent / "working" / "motion_edit"
        outdir.mkdir(parents=True, exist_ok=True)
        traj = _ct.compile_path(waypoints, segs)
        total = traj.duration()
        nframes = max(1, int(round(total * fps)))
        emit(f"[軌跡] {len(waypoints)} 點、{len(segs)} 段、{total:.1f}s、{nframes} 幀 @ {fps}fps")
        import char_modes as cm
        from PIL import Image, ImageDraw
        mode_obj = cm.get("mode_2")
        frames = []
        for fi in range(nframes):
            t = fi / fps
            pose, x, y, mode, wave, facing = traj.sample(t)
            d = -1 if facing == "left" else 1
            img = Image.open(bg_path).convert("RGB")
            draw = ImageDraw.Draw(img)
            if mode == "sit":
                mode_obj.draw_char_seated(draw, who, x, y, r, d, "flat", "normal", "closed",
                                          facing=facing, wave=wave, t=t)
            else:
                mode_obj.draw_char_standing(draw, who, x, y, r, d, t, wave, "flat", "normal", "closed",
                                            facing=facing, pose_override=pose)
            frames.append(img)
            if fi % 15 == 0:
                emit(f"  渲染 {fi}/{nframes}")
        clip = outdir / "motion.mp4"
        W, H = frames[0].size
        cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
               "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "20", "-pix_fmt", "yuv420p", str(clip)]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for f in frames:
            p.stdin.write(f.tobytes())
        p.stdin.close()
        p.wait()
        emit(f"[完成] -> {clip}")
        _RUN["results"].append({"ok": True, "video": str(clip)})
    except Exception as e:
        emit(f"[失敗] {e}")
    finally:
        with _LOCK:
            _RUN["running"] = False


def packs_list():
    """列出所有領域包（讀 packs/*/pack.json）。"""
    out = []
    if epack is None:
        return out
    for key in epack.available():
        pk = epack.load(key)
        qf = epack.resolve(pk, pk.get("topics_file", "topics/queue.json"))
        out.append({"key": key, "name": pk.get("name", key),
                    "modules": pk.get("modules", []),
                    "style_default": pk.get("style_default"),
                    "has_queue": Path(qf).exists()})
    return out


def scan_outputs():
    """List every finished film across all Packs (the 產出庫)."""
    sources = []
    if epack is not None:
        for key in epack.available():
            pk = epack.load(key)
            sources.append((key, pk.get("name", key),
                            Path(epack.resolve(pk, pk.get("output_dir", "output")))))
    else:
        sources.append(("interior_lezhi", "樂之室內設計", OUTPUT))
    items = []
    for key, name, outdir in sources:
        if not outdir.exists():
            continue
        for d in sorted(outdir.iterdir()):
            if not d.is_dir():
                continue
            mp4 = next(d.glob("*.mp4"), None)
            if not mp4:
                continue
            m = _read_json(d / "metadata.json", {}) or {}
            video_name = m.get("video")
            if video_name:
                vp = d / video_name
                if vp.is_file():
                    mp4 = vp
            pid, stl, ver = m.get("topic_id"), m.get("style"), m.get("version")
            if not pid and ename is not None:
                pm = ename.parse(d.name)
                if pm:
                    pid, stl, ver = pm["id"], pm["style"], pm["version"]
            date = m.get("date") or (mp4.stem[:10] if mp4.stem[:10].count("-") == 2 else "")
            cover = d / "封面.png"
            items.append({
                "pack": m.get("pack") or key, "pack_name": name,
                "topic_id": pid or d.name, "style": stl, "version": ver,
                "date": date, "title": m.get("title") or d.name,
                "video": str(mp4), "cover": str(cover) if cover.exists() else None,
                "duration_sec": m.get("duration_sec"), "dir": str(d),
            })
    items.sort(key=lambda x: (x.get("date") or "", x.get("title") or ""), reverse=True)
    return items


def load_queue():
    q = _read_json(QUEUE_JSON, {"pillars": [], "topics": []})
    q.setdefault("pillars", [])
    q.setdefault("topics", [])
    q.setdefault("studio", "押忍室內裝修設計有限公司")
    return q


def _topic_md(t):
    star = "★ " if t.get("star") else ""
    mat = "有實拍" if t.get("material") == "shot" else "無需實拍"
    out = [f"- {star}{t['title']}　〔{mat}〕"]
    if t.get("direction"):
        out.append(f"  - 方向：{t['direction']}")
    return out


def queue_to_md(q):
    lines = ["# 押忍工作室｜選題佇列（調整窗口）", "",
             f"> 由窗口自動產生，最後更新：{q.get('updated', '')}", ""]
    ids = {p["id"] for p in q["pillars"]}
    for p in q["pillars"]:
        lines.append(f"## {p['id']} {p['name']}（{p['funnel']}）— {p['goal']}")
        for t in q["topics"]:
            if t.get("pillar") == p["id"]:
                lines += _topic_md(t)
        lines.append("")
    loose = [t for t in q["topics"] if t.get("pillar") not in ids]
    if loose:
        lines.append("## 未分類")
        for t in loose:
            lines += _topic_md(t)
        lines.append("")
    return "\n".join(lines)


def scan_reviews():
    rev = _read_json(REVIEW_JSON, {})
    items = []
    for f in sorted(SCRIPTS.glob("*.json")) if SCRIPTS.exists() else []:
        key = f"script:{f.name}"
        items.append({"key": key, "stage": "1 腳本", "name": f.stem,
                      "path": str(f.relative_to(LEZHI)),
                      "decision": rev.get(key, {}).get("decision", "")})
    for d in sorted(OUTPUT.glob("*")) if OUTPUT.exists() else []:
        mp4 = next(d.glob("*.mp4"), None) if d.is_dir() else None
        if mp4:
            key = f"film:{d.name}"
            items.append({"key": key, "stage": "3 成片", "name": d.name,
                          "path": str(mp4.relative_to(LEZHI)),
                          "decision": rev.get(key, {}).get("decision", "")})
    return items


def scan_status(q):
    topics = q["topics"]
    starred = [t for t in topics if t.get("star")]
    done = [t for t in topics if t.get("status") == "done"]
    no_script = [t for t in starred if not t.get("script")]
    reviews = scan_reviews()
    pending = [r for r in reviews if not r["decision"]]
    gaps = [t["title"] for t in topics if t.get("material") == "shot" and t.get("status") != "done"]
    return {"starred": len(starred), "done": len(done),
            "no_script": [t["id"] for t in no_script],
            "pending_review": len(pending),
            "material_gaps": gaps[:8]}


def topic_versions(tid):
    """All script versions for a topic (versioned first, legacy last)."""
    items = []
    if SCRIPTS.exists():
        for f in SCRIPTS.glob(f"{tid}__*.json"):
            m = ename.parse(f.name) if ename else None
            items.append({"file": f.name, "style": (m or {}).get("style"),
                          "version": (m or {}).get("version", 1)})
    legacy = SCRIPTS / f"{tid}.json"
    if legacy.exists():
        items.append({"file": legacy.name, "style": None, "version": 0})
    items.sort(key=lambda x: (x["style"] or "", x["version"]))
    return items


def meta():
    styles = reg.styles() if reg else []
    prompts = reg.prompts() if reg else {"presets": [], "structure_options": []}
    versions = {t["id"]: topic_versions(t["id"]) for t in load_queue()["topics"]}
    return {"styles": styles,
            "presets": prompts.get("presets", []),
            "structures": prompts.get("structure_options", []),
            "versions": versions}


def _bgm_args(settings):
    if not settings.get("bgm_enabled"):
        return []
    name = settings.get("bgm") or ""
    p = BGM_DIR / name if name else None
    if p and p.exists():
        return ["--bgm", str(p), "--bgm-volume", str(settings.get("bgm_volume", 0.16))]
    return []


def run_scripts(ids=None, starred=False, style=None, keep_script=False):
    """Run the script engine to produce scripts for given ids / starred topics.
    keep_script=True 時只產新腳本、不更新題目的 script/format 指標（加另一風格用）。"""
    with _LOCK:
        _RUN["running"] = True
        _RUN["log"] = ""
        _RUN["results"] = []
    log_lines = []

    def emit(s):
        log_lines.append(s)
        with _LOCK:
            _RUN["log"] = "\n".join(log_lines)

    try:
        cmd = [sys.executable, "-u", "-X", "utf8", str(SCRIPT_ENGINE)]
        if ids:
            cmd += ["--topics", *ids]
        elif starred:
            cmd += ["--starred"]
        if style:
            cmd += ["--style", style]
        emit("[產腳本] " + " ".join(cmd))
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", bufsize=1)
        for line in p.stdout:
            emit(line.rstrip())
        p.wait()
        if p.returncode != 0:
            emit("[產腳本失敗] 有題目腳本未更新（Gemini 高負載，見上方「腳本未更新」），舊腳本保留，請稍後重試")
        else:
            emit("[產腳本完成] ✓ 腳本已更新")
        if keep_script:
            return
        # mark scripts produced (prefer newest versioned script; fall back to legacy)
        q = load_queue()
        for t in q["topics"]:
            matches = list(SCRIPTS.glob(f"{t['id']}__*.json")) if SCRIPTS.exists() else []
            legacy = SCRIPTS / f"{t['id']}.json"
            if matches:
                f = max(matches, key=lambda p: p.stat().st_mtime)
            elif legacy.exists():
                f = legacy
            else:
                continue
            t["script"] = f.name
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                t["format"] = d.get("format", "narr")
                if d.get("style"):
                    t["style"] = d["style"]
            except Exception:
                pass
        _write_json(QUEUE_JSON, q)
        QUEUE_MD.write_text(queue_to_md(q), encoding="utf-8")
    finally:
        with _LOCK:
            _RUN["running"] = False


def run_jobs(ids, script_map=None, scene=None, scene_mode=False, char_mode=None):
    with _LOCK:
        _RUN["running"] = True
        _RUN["log"] = ""
        _RUN["results"] = []
    q = load_queue()
    settings = load_settings()
    char_dir = LEZHI / "assets" / settings.get("char_dir", "characters")
    by_id = {t["id"]: t for t in q["topics"]}
    script_map = script_map or {}
    log_lines = []

    def emit(s):
        log_lines.append(s)
        with _LOCK:
            _RUN["log"] = "\n".join(log_lines)

    try:
        for tid in ids:
            t = by_id.get(tid)
            if not t:
                emit(f"[skip] 未知題目 {tid}")
                continue
            script = script_map.get(tid) or t.get("script")
            if not script:
                emit(f"[需腳本] {t['title']} → 尚無分鏡，先產腳本")
                _RUN["results"].append({"id": tid, "ok": False, "reason": "no_script"})
                continue
            sp = SCRIPTS / script
            if not sp.exists():
                emit(f"[缺檔] {sp}")
                _RUN["results"].append({"id": tid, "ok": False, "reason": "missing"})
                continue
            fmt = "narr"
            d = {}
            try:
                d = json.loads(sp.read_text(encoding="utf-8"))
                fmt = d.get("format", "narr")
            except Exception:
                pass
            outdir = OUTPUT / tid
            if scene_mode and fmt == "dialog":
                # 場景式：把 dialog 腳本的 scenes 轉成台詞，交給 scene_dialog.py
                lines = [{"who": s.get("speaker") or "ren", "text": s.get("text") or ""}
                         for s in d.get("scenes", []) if s.get("text")]
                if not lines:
                    emit(f"[缺台詞] {t['title']} 腳本無 scenes，跳過")
                    _RUN["results"].append({"id": tid, "ok": False, "reason": "no_lines"})
                    continue
                lines_file = OUTPUT / f"_lines_{tid}.json"
                lines_file.write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")
                scene_key = scene or "living_1"
                bg_path = SCENE_BG_DIR / f"{scene_key}.png"
                base_key = scene_key[:-len("_wide")] if scene_key.endswith("_wide") else scene_key
                stype = base_key.rsplit("_", 1)[0] if "_" in base_key else base_key
                if not bg_path.exists():
                    emit(f"[跳過] {t['title']}：場景「{scene_key}」背景不存在，請先生成背景（python lezhi/tools/scene_bg_gen.py --scene {stype}）")
                    _RUN["results"].append({"id": tid, "ok": False, "reason": "missing_bg"})
                    continue
                pose = SCENE_POSE.get(stype, "sit")
                cmd = [sys.executable, "-u", "-X", "utf8", str(MAKE_SCENE_DIALOG),
                       "--bg", str(bg_path), "--lines", str(lines_file), "--out", str(outdir),
                       "--pose", pose, "--title", t.get("title") or tid, "--topic-id", tid]
                if char_mode:
                    cmd += ["--char-mode", char_mode]
                if SCENE_POS_JSON.exists():
                    cmd += ["--pos", str(SCENE_POS_JSON)]
                    pos_data = _read_json(SCENE_POS_JSON, {}) or {}
                    if pos_data.get("le_recipe"):
                        cmd += ["--le-recipe", pos_data["le_recipe"]]
                    if pos_data.get("ren_recipe"):
                        cmd += ["--ren-recipe", pos_data["ren_recipe"]]
                    if pos_data.get("le_pose"):
                        cmd += ["--le-pose", json.dumps(pos_data["le_pose"], ensure_ascii=False)]
                    if pos_data.get("ren_pose"):
                        cmd += ["--ren-pose", json.dumps(pos_data["ren_pose"], ensure_ascii=False)]
                cmd += _bgm_args(settings)
            elif fmt == "dialog":
                cmd = [sys.executable, "-u", "-X", "utf8", str(MAKE_COMIC),
                       "--script", str(sp), "--out", str(outdir)]
                cmd += _bgm_args(settings)
            else:
                cmd = [sys.executable, "-u", "-X", "utf8", str(MAKE_SHORT),
                       "--script", str(sp), "--out", str(outdir)]
                cmd += _bgm_args(settings)
            kind = "場景式" if (scene_mode and fmt == "dialog") else ("漫畫對話劇" if fmt == "dialog" else "旁白")
            emit(f"[執行/{kind}] {t['title']}")
            emit("  " + " ".join(cmd))
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace", bufsize=1)
            for line in p.stdout:
                emit(line.rstrip())
            p.wait()
            ok = p.returncode == 0
            if ok:
                t["status"] = "done"
            _RUN["results"].append({"id": tid, "ok": ok})
            emit(f"[{'完成' if ok else '失敗'}] {t['title']}")
        _write_json(QUEUE_JSON, q)
        QUEUE_MD.write_text(queue_to_md(q), encoding="utf-8")
    finally:
        with _LOCK:
            _RUN["running"] = False


def run_scene_gen(scene, wide=False):
    """生成一個 AI 背景（呼叫 scene_bg_gen.py），沿用 _RUN 日誌輪詢。"""
    with _LOCK:
        _RUN["running"] = True
        _RUN["log"] = ""
        _RUN["results"] = []
    log_lines = []

    def emit(s):
        log_lines.append(s)
        with _LOCK:
            _RUN["log"] = "\n".join(log_lines)

    try:
        cmd = [sys.executable, "-u", "-X", "utf8", str(SCENE_BG_GEN),
               "--out", str(SCENE_BG_DIR), "--scene", scene]
        if wide:
            cmd.append("--wide")
        emit("[生成背景] " + " ".join(cmd))
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", bufsize=1)
        for line in p.stdout:
            emit(line.rstrip())
        p.wait()
        if p.returncode != 0:
            emit("[生成背景失敗] 請稍後重試")
        else:
            emit("[生成背景完成] ✓ 已在「場景」下拉選單出現")
    finally:
        with _LOCK:
            _RUN["running"] = False


def run_adhoc(fields):
    """即興型產片：呼叫 engine/core/adhoc.py，沿用 _RUN 日誌輪詢。"""
    with _LOCK:
        _RUN["running"] = True
        _RUN["log"] = ""
        _RUN["results"] = []
    log_lines = []

    def emit(s):
        log_lines.append(s)
        with _LOCK:
            _RUN["log"] = "\n".join(log_lines)

    try:
        cmd = [sys.executable, "-X", "utf8", str(ADHOC),
               "--pack", fields.get("pack") or "personal_greeting",
               "--occasion", fields.get("occasion", ""),
               "--to", fields.get("to", ""),
               "--relation", fields.get("relation", ""),
               "--wish", fields.get("wish", ""),
               "--lines", str(fields.get("lines") or 8)]
        if fields.get("style"):
            cmd += ["--style", fields["style"]]
        cmd += ["--render"]
        emit(f"[adhoc] {fields.get('occasion','')} → {fields.get('to','')}（{fields.get('pack','')}）")
        emit("  " + " ".join(cmd))
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.stdout:
            emit(p.stdout.rstrip())
        if p.returncode != 0 and p.stderr:
            emit("[stderr] " + p.stderr.rstrip()[-1500:])
        emit("[完成]" if p.returncode == 0 else "[失敗]")
        _RUN["results"].append({"ok": p.returncode == 0})
    finally:
        with _LOCK:
            _RUN["running"] = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _serve_file(self, fpath):
        try:
            rp = Path(fpath).resolve()
            rp.relative_to(FILMS.resolve())
        except Exception:
            self._send(403, b"forbidden", "text/plain")
            return
        if not rp.is_file():
            self._send(404, b"not found", "text/plain")
            return
        ctype = {".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg",
                 ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
                 ".srt": "text/plain; charset=utf-8", ".wav": "audio/wav",
                 ".mp3": "audio/mpeg", ".json": "application/json"}.get(
                     rp.suffix.lower(), "application/octet-stream")
        size = rp.stat().st_size
        start, end, code = 0, size - 1, 200
        rng = self.headers.get("Range") or ""
        if rng.startswith("bytes="):
            s = rng[6:].split("-")
            try:
                if s and s[0]:
                    start = int(s[0])
                if len(s) > 1 and s[1]:
                    end = int(s[1])
            except Exception:
                start, end = 0, size - 1
            end = min(end, size - 1)
            if start >= size or start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            code = 206
        length = end - start + 1
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(rp, "rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                buf = f.read(min(65536, left))
                if not buf:
                    break
                self.wfile.write(buf)
                left -= len(buf)

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/index.html"):
            html = LOCAL.read_bytes() if LOCAL.exists() else b"window.html missing"
            self._send(200, html, "text/html; charset=utf-8")
        elif p == "/api/queue":
            self._json(load_queue())
        elif p == "/api/reviews":
            self._json({"items": scan_reviews()})
        elif p == "/api/settings":
            self._json({"settings": load_settings(), "bgm_files": bgm_files(),
                        "char_dirs": ["characters", "characters_ai"],
                        "bgm_moods": ["warm", "calm", "playful", "upbeat"]})
        elif p == "/api/runstatus":
            with _LOCK:
                self._json(dict(_RUN))
        elif p == "/api/meta":
            self._json(meta())
        elif p == "/api/packs":
            self._json({"packs": packs_list()})
        elif p == "/api/outputs":
            self._json({"items": scan_outputs()})
        elif p == "/api/backgrounds":
            self._json(background_list())
        elif p == "/api/scenes":
            self._json({"items": scan_scenes()})
        elif p == "/api/scene_types":
            self._json({"items": [{"key": k, "name": SCENE_NAME.get(k, k), "pose": SCENE_POSE.get(k, "sit")}
                                  for k in SCENE_POSE]})
        elif p == "/api/char_modes":
            self._json({"items": CHAR_MODES})
        elif p == "/api/char_recipes":
            self._json({"items": CHAR_RECIPES})
        elif p == "/api/char_parts":
            self._json({"catalog": getattr(_char_parts_mod, "PART_CATALOG", {}),
                        "default": getattr(_char_parts_mod, "DEFAULT_SPEC", {})})
        elif p == "/api/custom_parts":
            self._json({"parts": _char_parts_mod.list_custom_parts("heads")})
        elif p == "/api/motion":
            self._json({"poses": MOTION_POSES, "kinds": MOTION_KINDS,
                        "facing": MOTION_FACING, "params": MOTION_PARAMS,
                        "config": motion_config(),
                        "recipes": CHAR_RECIPES, "scenes": scan_scenes()})
        elif p == "/api/scene_pos":
            self._json({"pos": (_read_json(SCENE_POS_JSON, None) if SCENE_POS_JSON.exists() else None)})
        elif p == "/api/scene_preview":
            qs = parse_qs(urlparse(self.path).query)
            def g(k, d=""):
                v = qs.get(k, [d])
                return v[0]
            data = {"bg": g("bg"),
                    "le": {"x": g("lx", "150"), "y": g("ly", "470"), "pose": g("lp", "sit")},
                    "ren": {"x": g("rx", "435"), "y": g("ry", "750"), "pose": g("rp", "stand")},
                    "wave": g("wave", "0") == "1", "seat": g("seat", "1") == "1",
                    "char_mode": g("cm", "mode_2"),
                    "le_recipe": g("lr", "le"), "ren_recipe": g("rr", "ren"),
                    "r": g("r", "55")}
            img, _anchors, err = render_scene_preview(data)
            if err:
                self._json({"ok": False, "error": err})
            else:
                self._send(200, img, "image/png")
        elif p == "/file":
            qs = parse_qs(urlparse(self.path).query)
            self._serve_file((qs.get("path") or [""])[0])
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            data = {}
        if p == "/api/queue":
            data["updated"] = time.strftime("%Y-%m-%d")
            _write_json(QUEUE_JSON, data)
            QUEUE_MD.write_text(queue_to_md(data), encoding="utf-8")
            self._json({"ok": True})
        elif p == "/api/review":
            rev = _read_json(REVIEW_JSON, {})
            rev[data.get("key", "")] = {"decision": data.get("decision", ""),
                                        "at": time.strftime("%Y-%m-%d %H:%M")}
            _write_json(REVIEW_JSON, rev)
            self._json({"ok": True})
        elif p == "/api/run":
            ids = data.get("ids", [])
            if _RUN["running"]:
                self._json({"ok": False, "reason": "running"})
                return
            threading.Thread(target=run_jobs,
                             args=(ids, data.get("script_map"),
                                   data.get("scene"), bool(data.get("scene_mode")),
                                   data.get("char_mode")),
                             daemon=True).start()
            self._json({"ok": True, "started": ids})
        elif p == "/api/script":
            if _RUN["running"]:
                self._json({"ok": False, "reason": "running"})
                return
            ids = data.get("ids") or None
            threading.Thread(target=run_scripts,
                             kwargs={"ids": ids, "starred": bool(data.get("starred")),
                                     "style": data.get("style") or None},
                             daemon=True).start()
            self._json({"ok": True})
        elif p == "/api/script_style":
            if _RUN["running"]:
                self._json({"ok": False, "reason": "running"})
                return
            tid = (data.get("id") or "").strip()
            style = (data.get("style") or "").strip()
            if not tid or style not in ("narr", "comic"):
                self._json({"ok": False, "error": "參數錯誤"})
                return
            threading.Thread(target=run_scripts,
                             kwargs={"ids": [tid], "style": style, "keep_script": True},
                             daemon=True).start()
            self._json({"ok": True})
        elif p == "/api/adhoc":
            if _RUN["running"]:
                self._json({"ok": False, "reason": "running"})
                return
            threading.Thread(target=run_adhoc, args=(data,), daemon=True).start()
            self._json({"ok": True})
        elif p == "/api/settings":
            s = load_settings()
            s.update({k: data[k] for k in DEFAULT_SETTINGS if k in data})
            _write_json(SETTINGS_JSON, s)
            self._json({"ok": True, "settings": s})
        elif p == "/api/open":
            try:
                rp = Path(data.get("path", "")).resolve()
                rp.relative_to(FILMS.resolve())
                os.startfile(str(rp))          # noqa: windows only
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "error": str(e)})
        elif p == "/api/pillar":
            q = load_queue()
            name = (data.get("name") or "").strip()
            if not name:
                self._json({"ok": False, "error": "請填分類名稱"})
                return
            nums = []
            for pl in q["pillars"]:
                d = "".join(c for c in str(pl.get("id", "")) if c.isdigit())
                if d:
                    nums.append(int(d))
            nid = "p%d" % ((max(nums) + 1) if nums else 1)
            q["pillars"].append({"id": nid, "name": name,
                                 "funnel": (data.get("funnel") or "").strip(),
                                 "goal": (data.get("goal") or "").strip()})
            q["updated"] = time.strftime("%Y-%m-%d")
            _write_json(QUEUE_JSON, q)
            QUEUE_MD.write_text(queue_to_md(q), encoding="utf-8")
            self._json({"ok": True, "id": nid, "name": name, "pillars": q["pillars"]})
        elif p == "/api/bgm":
            qs = parse_qs(urlparse(self.path).query)
            fname = (qs.get("name") or ["upload.wav"])[0]
            ext = Path(fname).suffix.lower()
            if ext not in (".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"):
                self._json({"ok": False, "error": "不支援的格式（wav / mp3 / m4a）"})
                return
            dest = BGM_DIR / ("bgm_%s%s" % (_safe_stem(Path(fname).stem), ext))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            self._json({"ok": True, "file": dest.name, "bgm_files": bgm_files()})
        elif p == "/api/backgrounds":
            qs = parse_qs(urlparse(self.path).query)
            if "delete" in qs:
                fname = Path((qs.get("delete") or [""])[0]).name
                target = PHOTO_BG_DIR / fname
                if target.exists() and target.is_file():
                    target.unlink()
                self._json({"ok": True, "backgrounds": background_list()})
                return
            fname = (qs.get("name") or ["bg.jpg"])[0]
            ext = Path(fname).suffix.lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                self._json({"ok": False, "error": "只支援 jpg / png / webp"})
                return
            dest = PHOTO_BG_DIR / ("%s%s" % (_safe_stem(Path(fname).stem), ext))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            self._json({"ok": True, "file": dest.name, "backgrounds": background_list()})
        elif p == "/api/scene_gen":
            scene = (data.get("scene") or "").strip()
            if scene not in SCENE_POSE:
                self._json({"ok": False, "error": "未知場景"})
                return
            if _RUN["running"]:
                self._json({"ok": False, "reason": "running"})
                return
            wide = bool(data.get("wide"))
            threading.Thread(target=run_scene_gen, args=(scene, wide), daemon=True).start()
            self._json({"ok": True})
        elif p == "/api/scene_pos":
            if data.get("clear"):
                if SCENE_POS_JSON.exists():
                    SCENE_POS_JSON.unlink()
                self._json({"ok": True})
            else:
                _write_json(SCENE_POS_JSON, {"le": data.get("le") or {}, "ren": data.get("ren") or {},
                                             "seat": bool(data.get("seat", True)),
                                             "wave": bool(data.get("wave", False)),
                                             "le_recipe": data.get("le_recipe") or "le",
                                             "ren_recipe": data.get("ren_recipe") or "ren",
                                             "le_pose": data.get("le_pose") or {},
                                             "ren_pose": data.get("ren_pose") or {}})
                self._json({"ok": True})
        elif p == "/api/custom_recipe":
            spec = data.get("spec") or {}
            key = _safe_stem(data.get("name") or "custom") or "custom"
            recipe = _char_parts_mod.build_recipe(spec)
            _char_parts_mod.register_recipe(key, recipe)
            self._json({"ok": True, "key": key, "recipes": _char_parts_mod.list_recipes()})
        elif p == "/api/render_char_head":
            import io
            recipe = _char_parts_mod.build_recipe(data.get("spec") or {})
            img = _char_parts_mod.render_head_image(recipe)
            buf = io.BytesIO()
            img.save(buf, "PNG")
            self._send(200, buf.getvalue(), "image/png")
        elif p == "/api/render_char_body":
            import io, base64
            recipe = _char_parts_mod.build_recipe(data.get("spec") or {})
            img = _char_parts_mod.render_character_image(recipe, r=70)
            (W, H), anchors = _char_parts_mod.character_geometry(recipe, r=70)
            buf = io.BytesIO()
            img.save(buf, "PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            self._json({"image": b64, "anchors": anchors, "size": [W, H]})
        elif p == "/api/part_preview":
            import io, base64
            recipe = _char_parts_mod.build_recipe(data.get("spec") or {})
            img, meta = _char_parts_mod.head_preview_meta(recipe, r=70)
            buf = io.BytesIO()
            img.save(buf, "PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            self._json({"image": b64, "meta": meta, "size": list(img.size)})
        elif p == "/api/custom_part":
            kind = data.get("kind") or "heads"
            name = data.get("name") or ""
            preset = data.get("preset") or {}
            ok = _char_parts_mod.save_custom_part(kind, name, preset)
            self._json({"ok": ok, "parts": _char_parts_mod.list_custom_parts(kind)})
        elif p == "/api/motion":
            cfg = data.get("config") or data
            _write_json(MOTION_JSON, cfg)
            self._json({"ok": True})
        elif p == "/api/motion_preview":
            import base64
            cfg = data.get("config") or data or {}
            try:
                t = float(data.get("t", 0.0))
            except Exception:
                t = 0.0
            png, meta, err = motion_frame(cfg, t)
            if err:
                self._json({"ok": False, "error": err})
            else:
                self._json({"ok": True, "image": base64.b64encode(png).decode("ascii"),
                            "x": meta["x"], "y": meta["y"], "mode": meta["mode"], "dir": meta["dir"]})
        elif p == "/api/motion_render":
            if _RUN["running"]:
                self._json({"ok": False, "reason": "running"})
                return
            threading.Thread(target=run_motion_render, args=(data,), daemon=True).start()
            self._json({"ok": True})
        elif p == "/api/scene_preview_full":
            import io, base64
            png, anchors, err = render_scene_preview(data)
            if err:
                self._json({"ok": False, "error": err})
            else:
                b64 = base64.b64encode(png).decode("ascii")
                self._json({"ok": True, "image": b64, "anchors": anchors})
        elif p == "/api/bgm_gen":
            mood = (data.get("mood") or "warm").lower()
            if mood not in ("warm", "calm", "playful", "upbeat"):
                mood = "warm"
            try:
                dur = int(data.get("duration") or 60)
            except Exception:
                dur = 60
            dur = max(20, min(dur, 180))
            name = _safe_stem(data.get("name") or mood)
            dest = BGM_DIR / ("bgm_%s.wav" % name)
            proc = subprocess.run([sys.executable, "-X", "utf8", str(MAKE_BGM),
                                   "--out", str(dest), "--duration", str(dur), "--mood", mood],
                                  capture_output=True, text=True, encoding="utf-8", errors="replace")
            if proc.returncode != 0 or not dest.exists():
                self._json({"ok": False, "error": ((proc.stderr or "").strip()[-300:]) or "生成失敗"})
                return
            self._json({"ok": True, "file": dest.name, "bgm_files": bgm_files()})
        else:
            self._send(404, b"not found", "text/plain")


def main():
    url = f"http://127.0.0.1:{PORT}/"
    print(f"押忍工作室內容窗口：{url}  (Ctrl+C 結束)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
