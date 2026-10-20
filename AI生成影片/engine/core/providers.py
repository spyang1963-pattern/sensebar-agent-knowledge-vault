"""P5-2 provider registry: per-slot provider chain, cooldown state, content-hash cache.

Registry is the single source of truth (`engine/providers/registry.json`).
Adding/changing a source = edit JSON only; this module reads it.

- chain(slot)      ordered providers with runtime status annotated
- usable(slot)     chain filtered by: status==implemented, key present, cooldown expired
- cache_path(...)  content-hash cache path (auto-create parent)
- fetch(...)       try chain in order: cache hit -> cooldown skip -> producer callback
- mark_ok/mark_fail cooldown bookkeeping written to `provider_state.json`
- CLI `--status`   ASCII table of every slot/chain (safe for GBK console)

Encoding note: CLI output is ASCII-only; file I/O uses explicit encodings.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
PROJECT = ENGINE.parent
REGISTRY = ENGINE / "providers" / "registry.json"

_REG = None
_STATE = None


def load(refresh=False):
    """Load registry JSON; resolve state/cache paths relative to registry file."""
    global _REG
    if _REG is None or refresh:
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        base = REGISTRY.parent
        reg["_state_file"] = (base / reg.get("state", "../working/_provider_state.json")).resolve()
        reg["_cache_dir"] = (base / reg.get("cache", "../working/_provider_cache")).resolve()
        _REG = reg
    return _REG


def _now():
    return time.time()


def _load_state():
    global _STATE
    if _STATE is None:
        f = load()["_state_file"]
        try:
            _STATE = json.loads(Path(f).read_text(encoding="utf-8"))
        except FileNotFoundError:
            _STATE = {}
        except Exception:
            _STATE = {}
    return _STATE


def _save_state():
    f = load()["_state_file"]
    Path(f).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(f) + ".tmp")
    tmp.write_text(json.dumps(_STATE, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, f)


def cooldown_left(pid):
    """Seconds until provider `pid` leaves cooldown (0 = not cooling down)."""
    st = _load_state().get(pid) or {}
    until = st.get("cooldown_until") or 0
    return max(0, int(until - _now()))


def mark_ok(pid):
    """Provider answered: clear cooldown/failure counter."""
    st = _load_state().setdefault(pid, {})
    st.pop("cooldown_until", None)
    st["fail_count"] = 0
    st["last_ok"] = _now()
    _save_state()


def mark_fail(pid, error, cooldown_sec=600):
    """Provider failed (429/throttle/timeout): cool down for cooldown_sec."""
    st = _load_state().setdefault(pid, {})
    st["fail_count"] = int(st.get("fail_count") or 0) + 1
    st["cooldown_until"] = _now() + max(1, int(cooldown_sec))
    st["last_error"] = str(error)[:300]
    st["last_fail"] = _now()
    _save_state()


def key_ok(requires):
    """Resolve `requires` = {"env": NAME} and/or {"file": PATH}. Returns (ok, reason)."""
    if not requires:
        return True, ""
    env = requires.get("env")
    if env and os.environ.get(env):
        return True, ""
    fp = requires.get("file")
    if fp:
        p = Path(os.path.expandvars(fp)).expanduser()
        if p.exists() and p.read_text(encoding="utf-8", errors="replace").strip():
            return True, ""
    return False, "missing key (%s)" % (env or fp or "?")


def chain(slot, check_key=True):
    """Full chain for `slot`, each entry annotated with runtime `state`."""
    reg = load()
    out = []
    for e in reg["slots"].get(slot, {}).get("chain", []):
        e = dict(e)
        st = e.get("status", "planned")
        if st != "implemented":
            e["state"] = st
        elif check_key:
            ok, why = key_ok(e.get("requires"))
            if not ok:
                e["state"] = "no_key"
            elif cooldown_left(e["id"]):
                e["state"] = "cooldown:%ds" % cooldown_left(e["id"])
            else:
                e["state"] = "ready"
        else:
            e["state"] = "ready"
        out.append(e)
    return out


def usable(slot):
    """Chain entries the caller may actually try right now (state == ready)."""
    return [e for e in chain(slot) if e.get("state") == "ready"]


def cache_path(slot, pid, key, ext=".bin"):
    """Content-hash cache target. Returns Path; caller writes bytes there on success."""
    h = hashlib.sha1(("%s|%s|%s" % (slot, pid, key)).encode("utf-8")).hexdigest()[:20]
    d = load()["_cache_dir"] / slot / pid
    d.mkdir(parents=True, exist_ok=True)
    return d / (h + ext)


def _read_key_file(name):
    # try env first, then common files
    env = os.environ.get(name.upper())
    if env and env.strip():
        return env.strip()
    for cand in [os.path.expanduser(f"~/.{name.lower()}_api_key"), os.path.expanduser(f"~/.{name.lower()}")]:
        try:
            p = Path(cand)
            if p.exists():
                s = p.read_text(encoding="utf-8", errors="replace").strip()
                if s:
                    return s
        except Exception:
            pass
    return None


def _download(url, target):
    req = urllib.request.Request(url, headers={"User-Agent": "lezhi-providers/1.0"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = resp.read()
    if len(data) < 1000:
        raise RuntimeError("too small")
    Path(target).write_bytes(data)
    return target


def pixabay_video_producer(target, query="interior design", orientation="portrait"):
    key = _read_key_file("pixabay_api_key")
    if not key:
        raise RuntimeError("no key")
    q = urllib.parse.quote(query)
    url = f"https://pixabay.com/api/videos/?key={key}&q={q}&video_type=film&per_page=5&orientation={orientation}&safesearch=true"
    req = urllib.request.Request(url, headers={"User-Agent": "lezhi-providers/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    hits = data.get("hits") or []
    if not hits:
        raise RuntimeError("no results")
    v = hits[0]
    vids = v.get("videos") or {}
    # prefer medium/large/small
    pick = None
    for k in ("large", "medium", "small", "tiny"):
        if vids.get(k):
            pick = vids[k]
            break
    if not pick:
        raise RuntimeError("no video url")
    vurl = pick.get("url")
    if not vurl:
        raise RuntimeError("no video url")
    return _download(vurl, target)


def pexels_video_producer(target, query="interior design", orientation="portrait"):
    key = _read_key_file("pexels_api_key")
    if not key:
        raise RuntimeError("no key")
    q = urllib.parse.quote(query)
    url = f"https://api.pexels.com/videos/search?query={q}&per_page=5&orientation={orientation}&size=medium"
    req = urllib.request.Request(url, headers={"User-Agent": "lezhi-providers/1.0", "Authorization": key})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    vids = data.get("videos") or []
    if not vids:
        raise RuntimeError("no results")
    files = vids[0].get("video_files") or []
    pick = None
    for f in files:
        if f.get("quality") in ("hd", "sd"):
            pick = f
            break
    if not pick and files:
        pick = files[0]
    if not pick:
        raise RuntimeError("no video file")
    vurl = pick.get("link")
    if not vurl:
        raise RuntimeError("no video link")
    return _download(vurl, target)


def cached(slot, pid, key):
    """Return existing cached Path or None."""
    p = cache_path(slot, pid, key)
    return p if p.exists() else None


def fetch(slot, key, ext, producers, prefer_cached=True):
    """Run provider chain for `slot`.

    producers: {provider_id: callable(target_path) -> path|None}  (raise = failure)
    Returns (path|None, provider_label). label includes "(cache)" on hit.
    """
    tried = []
    for e in chain(slot):
        pid = e["id"]
        if e.get("state") != "ready" or pid not in producers:
            continue
        target = cache_path(slot, pid, key, ext)
        if prefer_cached and target.exists() and target.stat().st_size > 0:
            return target, pid + "(cache)"
        cd = cooldown_left(pid)
        if cd:
            tried.append("%s(cooldown %ds)" % (pid, cd))
            continue
        try:
            r = producers[pid](target)
            if r is None:
                mark_fail(pid, "returned None", e.get("cooldown_sec", 600))
                tried.append(pid + "(none)")
                continue
            r = Path(r)
            if not r.exists() or r.stat().st_size == 0:
                mark_fail(pid, "empty output", e.get("cooldown_sec", 600))
                tried.append(pid + "(empty)")
                continue
            mark_ok(pid)
            if r != target:
                try:
                    target.write_bytes(r.read_bytes())
                except Exception:
                    pass
            return r, pid
        except Exception as ex:
            mark_fail(pid, ex, e.get("cooldown_sec", 600))
            tried.append("%s(%s)" % (pid, type(ex).__name__))
    return None, ",".join(tried) or "no-provider"


def reset_state():
    global _STATE
    _STATE = {}
    _save_state()


def status_lines():
    """ASCII status report (console-safe)."""
    reg = load()
    lines = ["provider registry: %s" % REGISTRY, "slots: %d" % len(reg["slots"]), ""]
    for slot in reg["slots"]:
        lines.append("[%s]" % slot)
        for e in chain(slot):
            cd = cooldown_left(e["id"])
            mark = {"ready": "+", "no_key": "k", "disabled": "x", "planned": "."}
            tag = e.get("state", "?")
            flag = mark.get(tag, "~" if tag.startswith("cooldown") else "?")
            note = str(e.get("note", ""))[:46]
            lines.append("  %s %-16s %-14s %s" % (flag, e["id"], e.get("status", "?"), note))
            if cd:
                lines.append("      cooldown: %ds left" % cd)
        lines.append("")
    lines.append("(+ ready  k missing-key  x disabled  . planned  ~ cooling-down)")
    return lines


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--clear-state":
        reset_state()
        print("state cleared")
    elif args and args[0] == "--json":
        print(json.dumps({s: chain(s) for s in load()["slots"]}, ensure_ascii=False, indent=2))
    else:
        print("\n".join(status_lines()))
