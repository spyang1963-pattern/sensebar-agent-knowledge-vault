"""engine.core.registry - load and validate engine registries.

Registries are plain JSON files. This module is the single place that knows
where they live and how to resolve paths, so renderers and the UI never
hardcode paths. Adding a style / background / motion / voice / caption /
prompt preset == drop a JSON entry here (no code change).
"""
from __future__ import annotations

import json
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]   # .../AI生成影片/engine
PROJECT = ENGINE.parent                        # .../AI生成影片
WORKSPACE = PROJECT.parent                     # D:\\AI-Agent-Workspace

SLOTS_DIR = ENGINE / "slots"
STYLES_JSON = ENGINE / "styles" / "registry.json"
PROMPTS_JSON = ENGINE / "prompts" / "presets.json"

SLOT_FILES = {
    "layout": SLOTS_DIR / "layout.json",
    "bg": SLOTS_DIR / "bg.json",
    "motion": SLOTS_DIR / "motion.json",
    "look": SLOTS_DIR / "look.json",
    "voice": SLOTS_DIR / "voice.json",
    "caption": SLOTS_DIR / "caption.json",
}


def _read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def resolve(p):
    """Resolve a registry path. Absolute wins; else try WORKSPACE/PROJECT/ENGINE."""
    p = Path(p)
    if p.is_absolute():
        return p
    for base in (WORKSPACE, PROJECT, ENGINE):
        cand = base / p
        if cand.exists():
            return cand
    return WORKSPACE / p


def _entries(data):
    """First list value in a registry dict (its entries)."""
    for v in data.values():
        if isinstance(v, list):
            return v
    return []


def styles():
    return _read(STYLES_JSON, {"styles": []}).get("styles", [])


def style(key):
    return next((s for s in styles() if s.get("key") == key), None)


def slot(name):
    return _read(SLOT_FILES[name], {})


def slots():
    return {name: slot(name) for name in SLOT_FILES}


def slot_keys(name, status="implemented"):
    """Keys of one slot registry, optionally filtered by status.

    status=None returns every key. Prompt builders and renderers should
    read this instead of hardcoding value lists.
    """
    return [e.get("key") for e in slot_entries(name, status)]


def slot_entries(name, status="implemented"):
    entries = _entries(slot(name))
    if status is None:
        return entries
    return [e for e in entries if e.get("status") == status]


def slot_entry(name, key):
    return next((e for e in _entries(slot(name)) if e.get("key") == key), None)


def prompts():
    return _read(PROMPTS_JSON, {"presets": [], "structure_options": []})


def renderer_path(style_key):
    s = style(style_key)
    return resolve(s["script"]) if s and s.get("script") else None


def validate():
    """Return a list of problems (empty list == OK)."""
    problems = []
    seen = set()
    for s in styles():
        k = s.get("key")
        if not k:
            problems.append("style 缺少 key")
            continue
        if k in seen:
            problems.append(f"style key 重複：{k}")
        seen.add(k)
        for req in ("name", "format"):
            if not s.get(req):
                problems.append(f"style {k} 缺少 {req}")
        if s.get("script") and not renderer_path(k).exists():
            problems.append(f"style {k} 的 renderer 不存在：{s['script']}")
    for name in SLOT_FILES:
        data = slot(name)
        if not data:
            problems.append(f"slot 檔不存在或為空：{name}.json")
            continue
        keys = [e.get("key") for e in _entries(data)]
        for key in keys:
            if not key:
                problems.append(f"{name}.json 有條目缺 key")
        dups = sorted({x for x in keys if x and keys.count(x) > 1})
        if dups:
            problems.append(f"{name}.json key 重複：{dups}")
    return problems


if __name__ == "__main__":
    print(f"engine   = {ENGINE}")
    print(f"styles   = {[s.get('key') for s in styles()]}")
    for name in SLOT_FILES:
        print(f"{name:8s} = {len(_entries(slot(name)))} 條")
    print(f"prompts  = {[p.get('key') for p in prompts().get('presets', [])]}")
    ps = validate()
    print("OK" if not ps else "問題：\n  - " + "\n  - ".join(ps))
