"""char_modes - 2人角色構圖插件（可版本化：2人角色-1 / -2 / -3 ...）

每個模式模組都提供同一組介面（供 scene_dialog.py 呼叫）：
  draw_char(...)           主入口（依 pose 分派）
  draw_char_standing(...)  站姿
  draw_char_seated(...)    坐姿
  draw_seat(...)           椅凳（可選）

角色位置/姿勢/表情/對嘴全參數化，與背景無關；視線對齊（dir/tilt/shift/lean）
由 scene_dialog.py 的 look_at() 計算後傳入。
"""
from __future__ import annotations

import importlib

# key → (顯示名, 模組名)
MODES = {
    "mode_2": ("2人角色-2（怪奇盤腿側身）", "char_modes.mode_2"),
    "mode_1": ("2人角色-1（半身對坐）", "char_modes.mode_1"),
}
DEFAULT = "mode_2"


def list_modes():
    return [{"key": k, "name": v[0]} for k, v in MODES.items()]


def get(mode_key):
    """載入角色模式模組（找不到就回預設 mode_2）。"""
    name = MODES.get(mode_key, MODES[DEFAULT])[1]
    return importlib.import_module(name)
