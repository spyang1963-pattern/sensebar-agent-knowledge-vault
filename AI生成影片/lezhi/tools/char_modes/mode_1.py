"""char_modes/mode_1.py - 2人角色-1（半身對坐，原始版重寫）

構圖模式：半身（頭＋肩胸，底端裁在畫面下緣）。角色長相由 char_parts 的
配方（阿忍/小樂）決定，與 mode_2 同一組角色；差別只在「構圖」＝半身對坐。

模式介面同 mode_2。
"""
from __future__ import annotations

import char_parts as cp


def draw_seat(d, sx, sy, r):
    """半身模式不需椅凳（背景自行提供座位）。"""
    return


def draw_char(d, who, sx, sy, r, dir, t, pose, brow, eye, mouth, wave=False, seat=False, gaze=0, tilt=0, shift=(0, 0), lean=0, facing=None, pose_override=None):
    dy = -int(r * 0.4) if pose == "stand" else 0
    _draw_half(d, who, sx, sy + dy, r, dir, brow, eye, mouth, gaze, tilt, shift, facing)


def draw_char_standing(d, who, sx, sy, r, dir, t, wave, brow="flat", eye="normal", mouth="closed", gaze=0, tilt=0, shift=(0, 0), lean=0, facing=None, pose_override=None):
    _draw_half(d, who, sx, sy - int(r * 0.4), r, dir, brow, eye, mouth, gaze, tilt, shift, facing)


def draw_char_seated(d, who, sx, sy, r, dir, brow, eye, mouth, gaze=0, tilt=0, shift=(0, 0), lean=0, facing=None, pose_override=None):
    _draw_half(d, who, sx, sy, r, dir, brow, eye, mouth, gaze, tilt, shift, facing)


def _draw_half(d, who, sx, sy, r, dir, brow, eye, mouth, gaze, tilt, shift, facing=None):
    """半身：肩胸（底端超出畫面下緣）＋頭。"""
    recipe = cp.get_recipe(who)
    nx = sx
    ny = sy + int(r * 0.9)
    px = sx
    py = sy + int(r * 4.5)
    cp.render_torso(d, recipe, nx, ny, px, py, r, int(r * 1.35), int(r * 1.35))
    cp.render_head(d, recipe, sx, sy, r, dir, brow, eye, mouth, gaze, tilt, shift, facing)
