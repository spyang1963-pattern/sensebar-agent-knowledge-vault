"""engine.core.pack - resolve a domain Pack's content root and paths.

A Pack is a folder under engine/../packs/<key>/ holding a pack.json plus
all domain content (brand, characters, topics, assets, output...). The
engine stays content-free; it only asks the Pack where things live.

Manifest-first: pack.json may point `root` at an existing content tree
(e.g. "lezhi"), so nothing has to be physically moved yet.
"""
from __future__ import annotations

import json
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]      # .../AI生成影片/engine
FILMS = ENGINE.parent                             # .../AI生成影片
PACKS = FILMS / "packs"

DEFAULT_PACK = "interior_lezhi"


def pack_path(key=DEFAULT_PACK):
    return PACKS / key / "pack.json"


def load(key=DEFAULT_PACK):
    """Load a Pack manifest. Falls back to a bare manifest when absent."""
    p = pack_path(key)
    if not p.exists():
        return {"key": key, "root": None, "__dir__": PACKS / key}
    data = json.loads(p.read_text(encoding="utf-8"))
    data.setdefault("key", key)
    data["__dir__"] = p.parent
    return data


def content_root(pack=DEFAULT_PACK):
    """Absolute path to the Pack's content root (brand/assets/topics live here)."""
    if isinstance(pack, str):
        pack = load(pack)
    root = pack.get("root")
    if root:
        rp = Path(root)
        return rp if rp.is_absolute() else (FILMS / rp)
    return pack["__dir__"]


def resolve(pack, rel):
    """Resolve a Pack-relative path to an absolute path."""
    p = Path(rel)
    return p if p.is_absolute() else (content_root(pack) / p)


def available():
    if not PACKS.exists():
        return []
    return sorted(p.parent.name for p in PACKS.glob("*/pack.json"))


if __name__ == "__main__":
    print("packs   =", available())
    print("root    =", content_root())
    print("scripts =", resolve(DEFAULT_PACK, "scripts"))
    print("output  =", resolve(DEFAULT_PACK, "output"))
