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
REVIEW_JSON = LEZHI / "review.json"
SETTINGS_JSON = LEZHI / "settings.json"
MAKE_DIALOG = LEZHI / "tools" / "make_dialog.py"
MAKE_COMIC = LEZHI / "tools" / "make_comic.py"   # 對話劇正式版型（2026-10-18 定案）
ADHOC = ENGINE / "core" / "adhoc.py"            # 即興型產片（Pack 驅動）
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


def bgm_files():
    if not BGM_DIR.exists():
        return []
    return sorted(p.name for p in BGM_DIR.glob("*.wav"))


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


def run_scripts(ids=None, starred=False, style=None):
    """Run the script engine to produce scripts for given ids / starred topics."""
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
        cmd = [sys.executable, "-X", "utf8", str(SCRIPT_ENGINE)]
        if ids:
            cmd += ["--topics", *ids]
        elif starred:
            cmd += ["--starred"]
        if style:
            cmd += ["--style", style]
        emit("[產腳本] " + " ".join(cmd))
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.stdout:
            emit(p.stdout.rstrip())
        if p.returncode != 0 and p.stderr:
            emit("[stderr] " + p.stderr.rstrip()[-1500:])
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


def run_jobs(ids, script_map=None):
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
            try:
                fmt = json.loads(sp.read_text(encoding="utf-8")).get("format", "narr")
            except Exception:
                pass
            outdir = OUTPUT / Path(script).stem
            if fmt == "dialog":
                cmd = [sys.executable, "-X", "utf8", str(MAKE_COMIC),
                       "--script", str(sp), "--out", str(outdir)]
            else:
                cmd = [sys.executable, "-X", "utf8", str(MAKE_SHORT),
                       "--script", str(sp), "--out", str(outdir)]
            cmd += _bgm_args(settings)
            emit(f"[執行/{'漫畫對話劇' if fmt == 'dialog' else '旁白'}] {t['title']}")
            emit("  " + " ".join(cmd))
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if p.stdout:
                emit(p.stdout.rstrip())
            if p.returncode != 0 and p.stderr:
                emit("[stderr] " + p.stderr.rstrip()[-1500:])
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
                        "char_dirs": ["characters", "characters_ai"]})
        elif p == "/api/runstatus":
            with _LOCK:
                self._json(dict(_RUN))
        elif p == "/api/meta":
            self._json(meta())
        elif p == "/api/packs":
            self._json({"packs": packs_list()})
        elif p == "/api/outputs":
            self._json({"items": scan_outputs()})
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
                             args=(ids, data.get("script_map")),
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
