"""engine.core.script - prompt assembly for the script engine.

Final prompt = base prompt + preset (tone) + structure options + extra (free text).

This module is additive: with no preset / structure / extra it returns an empty
string, so the caller's behavior is unchanged.
"""
from __future__ import annotations

try:
    from . import registry
except ImportError:  # run as a plain script / flat sys.path
    import registry  # type: ignore


def _index(items):
    return {i.get("key"): i for i in items or [] if i.get("key")}


def available_presets(pack_prompts=None):
    """Merged presets (engine defaults + pack overrides)."""
    merged = _index(registry.prompts().get("presets", []))
    if pack_prompts:
        merged.update(_index(pack_prompts.get("presets", [])))
    return list(merged.values())


def available_structures(pack_prompts=None):
    merged = _index(registry.prompts().get("structure_options", []))
    if pack_prompts:
        merged.update(_index(pack_prompts.get("structure_options", [])))
    return list(merged.values())


def compose(preset=None, structure=None, extra=None, pack_prompts=None):
    """Build the extra-instruction block to append to a base prompt.

    Returns "" when nothing to add (so callers stay backward compatible).
    """
    presets = _index(available_presets(pack_prompts))
    structs = _index(available_structures(pack_prompts))
    parts = []

    if preset and preset != "base":
        p = presets.get(preset)
        if p and p.get("text"):
            parts.append(f"【語氣風格】{p['text']}")
    for k in (structure or []):
        s = structs.get(k)
        if s and s.get("text"):
            parts.append(f"【必含要素】{s['text']}")
    if extra and str(extra).strip():
        parts.append(f"【額外要求】{str(extra).strip()}")

    if not parts:
        return ""
    body = "\n".join(f"- {x}" for x in parts)
    return "\n\n補充指示（務必遵守，與上述規則衝突時以本段為準）：\n" + body


def topic_overrides(topic):
    """Read preset/structure/extra from a topic dict (all optional)."""
    return {
        "preset": topic.get("preset"),
        "structure": topic.get("structure"),
        "extra": topic.get("extra"),
    }
