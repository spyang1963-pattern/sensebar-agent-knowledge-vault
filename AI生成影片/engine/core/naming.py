"""engine.core.naming - versioned names for scripts and films.

Convention:  {id}__{style}.json   (v1)
             {id}__{style}v2.json (v2)
             {id}__{style}v3.json ...

Layout stays compatible with legacy single-slot names ({id}.json): callers
fall back to the legacy file when no versioned file exists.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

_SPLIT = re.compile(r"^(?P<id>.+?)__(?P<style>[A-Za-z0-9_]+?)(?:v(?P<v>\d+))?$")

_BAD = '<>:"/\\|?*'


def sanitize(name):
    """Make a string safe for a Windows filename."""
    s = "".join("_" if (c in _BAD or ord(c) < 32) else c for c in str(name))
    return s.strip().rstrip(".") or "untitled"


def film_filename(style=None, topic_id=None, title="", date=None):
    """Indexable film name: {date}__{style}__{topic_id}__{title}.mp4

    date  -> production day (YYYY-MM-DD); style -> render style key
    (comic/narr); topic_id -> queue topic id; title -> human title.
    Missing parts are simply skipped.
    """
    date = date or time.strftime("%Y-%m-%d")
    parts = [date]
    if style:
        parts.append(sanitize(style))
    if topic_id:
        parts.append(sanitize(topic_id))
    if title:
        parts.append(sanitize(title))
    return "__".join(parts) + ".mp4"


def script_filename(topic_id, style, version=1):
    suffix = "" if (version or 1) <= 1 else f"v{version}"
    return f"{topic_id}__{style}{suffix}.json"


def film_dirname(topic_id, style, version=1):
    suffix = "" if (version or 1) <= 1 else f"v{version}"
    return f"{topic_id}__{style}{suffix}"


def film_fields(style=None, topic_id=None, title="", version=1, date=None, pack=None):
    """Parts + stem of an indexable film name (the metadata spine)."""
    date = date or time.strftime("%Y-%m-%d")
    stem = Path(film_filename(style, topic_id, title, date)).stem
    return {"pack": pack, "topic_id": topic_id, "style": style,
            "version": version, "date": date, "title": title, "stem": stem}


def next_version(existing, topic_id, style):
    """Given existing script filenames, return the next version number."""
    v = 0
    for n in existing:
        m = _SPLIT.match(Path(n).stem)
        if m and m.group("id") == topic_id and m.group("style") == style:
            v = max(v, int(m.group("v") or 1))
    return v + 1


def parse(name):
    m = _SPLIT.match(Path(name).stem)
    if not m:
        return None
    return {"id": m.group("id"), "style": m.group("style"),
            "version": int(m.group("v") or 1)}


if __name__ == "__main__":
    names = ["q__comic.json", "q__comicv2.json", "q__narr.json", "legacy.json"]
    print(script_filename("q", "comic", 1), script_filename("q", "comic", 3))
    print("next comic =", next_version(names, "q", "comic"))
    print("next narr  =", next_version(names, "q", "narr"))
    print("parse      =", parse("q__comicv2.json"), parse("legacy.json"))
    print("film       =", film_filename("comic", "quote_checklist", "裝潢報價單，這 5 項沒問清楚一定後悔", "2026-10-18"))
    print("film(legacy)=", film_filename(None, "quote_checklist", "未命名", "2026-10-18"))
    print("fields     =", film_fields("comic", "small_house_mistakes", "小宅 3 錯", 2, pack="interior_lezhi"))
