"""char_modes/mode_2.py - 2人角色-2（怪奇盤腿側身，全身）

構圖模式：全身（盤腿坐／站）。角色長相（頭/髮/帽/眼鏡/身/腿/手）由
char_parts 的「配方」決定，此檔只負責「構圖組合」（坐姿盤腿 vs 站姿）。

模式介面（供 scene_dialog.py 呼叫）：
  draw_char(...) / draw_char_standing(...) / draw_char_seated(...) / draw_seat(...)
"""
from __future__ import annotations

from PIL import Image, ImageDraw

import char_parts as cp


def draw_seat(d, sx, sy, r):
    """簡單椅凳（座位在角色臀部高度，給 AI 背景沒椅子的場景用）。"""
    ink = (21, 26, 27)
    top = sy + int(r * 3.3)
    d.rounded_rectangle([sx - int(r * 1.5), top, sx + int(r * 1.5), top + int(r * 0.35)],
                        radius=int(r * 0.2), fill=(176, 138, 104), outline=ink, width=4)
    for lx in (sx - int(r * 1.1), sx + int(r * 1.1)):
        d.line([(lx, top + int(r * 0.35)), (lx, top + int(r * 1.2))], fill=(120, 96, 70), width=int(r * 0.32))


def draw_char(d, who, sx, sy, r, dir, t, pose, brow, eye, mouth, wave=False, seat=False, gaze=0, tilt=0, shift=(0, 0), lean=0, facing=None):
    """依姿勢畫角色（坐/站）。seat=True 時坐姿先畫椅子。facing=正視/後視（預設側視）。"""
    if pose == "stand":
        draw_char_standing(d, who, sx, sy, r, dir, t, wave, brow, eye, mouth, gaze, tilt, shift, lean, facing)
    else:
        if seat:
            draw_seat(d, sx, sy, r)
        draw_char_seated(d, who, sx, sy, r, dir, brow, eye, mouth, gaze, tilt, shift, lean, facing)


def _anchors(recipe, sx, sy, r):
    """依配方算出十一錨點：頭/頸/髖/雙肘/雙手/雙膝/雙腳。"""
    nx = sx + int(recipe.get("neck_dx", 0.0) * r)
    ny = sy + int(recipe.get("neck_dy", 0.7) * r)
    px = nx + int(recipe.get("hip_dx", 0.0) * r)
    py = ny + int(recipe.get("hip_dy", 2.0) * r)
    el = (nx + int(recipe.get("elbow_lx", -0.4) * r), ny + int(recipe.get("elbow_ly", 0.15) * r))
    er = (nx + int(recipe.get("elbow_rx", 0.4) * r), ny + int(recipe.get("elbow_ry", 0.15) * r))
    hl = (el[0] + int(recipe.get("hand_lx", -0.2) * r), el[1] + int(recipe.get("hand_ly", 0.15) * r))
    hr = (er[0] + int(recipe.get("hand_rx", 0.2) * r), er[1] + int(recipe.get("hand_ry", 0.15) * r))
    kl = (px + int(recipe.get("knee_lx", -0.3) * r), py + int(recipe.get("knee_ly", 0.95) * r))
    kr = (px + int(recipe.get("knee_rx", 0.3) * r), py + int(recipe.get("knee_ry", 0.95) * r))
    fl = (kl[0] + int(recipe.get("foot_lx", -0.08) * r), kl[1] + int(recipe.get("foot_ly", 0.95) * r))
    fr = (kr[0] + int(recipe.get("foot_rx", 0.08) * r), kr[1] + int(recipe.get("foot_ry", 0.95) * r))
    return (sx, sy), (nx, ny), (px, py), el, er, hl, hr, kl, kr, fl, fr


def draw_char_seated(d, who, sx, sy, r, dir, brow, eye, mouth, gaze=0, tilt=0, shift=(0, 0), lean=0, facing=None):
    """盤腿坐。側視＝盤腿側身；正視/後視＝對稱。"""
    recipe = cp.get_recipe(who)
    fac = cp.resolve_facing(recipe, dir, facing)
    side = fac in ("left", "right")
    (hx, hy), (nx, ny), (px, py), _el, _er, _hl, _hr, _kl, _kr, _fl, _fr = _anchors(recipe, sx, sy, r)
    cp.render_hip_seated(d, recipe, px, py, r, dir, symmetric=not side)
    cp.render_torso(d, recipe, nx, ny, px, py, r, int(r * 0.75), lean=lean if side else 0)
    if side:
        d.line([(nx, ny + int(r * 0.4)), (nx + dir * int(r * 0.6), py)], fill=recipe["top"], width=int(r * 0.4))
    cp.render_head(d, recipe, hx, hy, r, dir, brow, eye, mouth, gaze, tilt, shift, facing)


def draw_char_standing(d, who, sx, sy, r, dir, t, wave, brow="flat", eye="normal", mouth="closed", gaze=0, tilt=0, shift=(0, 0), lean=0, facing=None):
    """站姿。側視＝近側單手；正視/後視＝雙手。十一錨點骨架。"""
    recipe = cp.get_recipe(who)
    fac = cp.resolve_facing(recipe, dir, facing)
    side = fac in ("left", "right")
    (hx, hy), (nx, ny), (px, py), el, er, hl, hr, kl, kr, fl, fr = _anchors(recipe, sx, sy, r)
    cp.render_legs_stand(d, recipe, px, py, kl[0], kl[1], kr[0], kr[1], fl[0], fl[1], fr[0], fr[1], r)
    if side:
        # 側視：遠手（背側）畫在身體後方，近手（面側）畫在身體前方
        if dir < 0:
            near_el, near_hl, far_el, far_hl = el, hl, er, hr
        else:
            near_el, near_hl, far_el, far_hl = er, hr, el, hl
        cp.render_arm(d, recipe, nx, ny, far_el[0], far_el[1], far_hl[0], far_hl[1], r, t, False)
        cp.render_torso(d, recipe, nx, ny, px, py, r, int(r * 0.7), lean=lean if side else 0)
        cp.render_arm(d, recipe, nx, ny, near_el[0], near_el[1], near_hl[0], near_hl[1], r, t, wave)
    else:
        cp.render_torso(d, recipe, nx, ny, px, py, r, int(r * 0.7), lean=lean if side else 0)
        cp.render_arms(d, recipe, nx, ny, el[0], el[1], er[0], er[1], hl[0], hl[1], hr[0], hr[1], r)
    cp.render_head(d, recipe, hx, hy, r, dir, brow, eye, mouth, gaze, tilt, shift, facing)
