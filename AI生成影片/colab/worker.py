#!/usr/bin/env python3
"""colab/worker.py - P5-5 Colab Batch Asset Factory worker

Runs in Google Colab. Reads tasks from tasks/*.json
and produces outputs to outputs/<task_id>/, zips as <task_id>.zip.

Designed for easy extension: add new task_type + handler.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from datetime import datetime

ROOT = Path('.')
TASK_DIR = ROOT / 'tasks'
OUT_ROOT = ROOT / 'outputs'


def log(msg):
    print(f"[colab-worker] {msg}")


def ensure_dirs():
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)


def load_tasks():
    tasks = []
    for p in sorted(TASK_DIR.glob('*.json')):
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
            tasks.append(d)
        except Exception as e:
            log(f"skip {p.name}: {e}")
    tasks.sort(key=lambda x: (x.get('priority', 1), x.get('id', '')))
    return tasks


def _pollinations_img(prompt, w, h, out_path, seed=None):
    encoded = urllib.parse.quote(prompt)
    base = f"https://image.pollinations.ai/prompt/{encoded}?width={w}&height={h}&model=flux"
    if seed is not None:
        base += f"&seed={seed}"
    delays = [0, 5, 10, 15, 20]
    for attempt, wait in enumerate(delays):
        if wait:
            time.sleep(wait)
        try:
            req = urllib.request.Request(base, headers={"User-Agent": "colab-worker/1.0"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = resp.read()
            if len(data) < 5000:
                continue
            Path(out_path).write_bytes(data)
            return out_path
        except Exception as e:
            log(f"    pollinations try {attempt} err: {e}")
    raise RuntimeError("pollinations failed")


def handle_image_gen(task):
    task_id = task['id']
    params = task.get('params') or {}
    count = int(params.get('count') or 1)
    w = int(params.get('w') or 1080)
    h = int(params.get('h') or 1920)
    prompt = params.get('prompt') or 'interior design'
    style = params.get('style') or 'minimal modern interior, soft natural light, photorealistic'

    outdir = OUT_ROOT / task_id
    outdir.mkdir(parents=True, exist_ok=True)

    log(f"[image_gen] {task_id}: {count}x ({w}x{h}) {prompt[:40]}...")
    full = f"{prompt}, {style}"
    ok = 0
    for i in range(count):
        try:
            out = outdir / f"img_{i:03d}.png"
            _pollinations_img(full, w, h, out, seed=i)
            log(f"    saved {out.name} ({out.stat().st_size} bytes)")
            ok += 1
        except Exception as e:
            log(f"    failed {i}: {e}")
    meta = {
        "task_id": task_id,
        "type": "image_gen",
        "prompt": prompt,
        "style": style,
        "count": count,
        "w": w,
        "h": h,
        "ok": ok,
        "created": datetime.utcnow().isoformat() + "Z",
    }
    (outdir / "task_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[image_gen] done {ok}/{count}")
    return outdir


def _pixabay_video_download(target, query, orientation="portrait", key=None):
    try:
        from google.colab import userdata
        key = key or userdata.get('PIXABAY_API_KEY')
    except Exception:
        pass
    if not key:
        key = os.environ.get('PIXABAY_API_KEY')
    if not key:
        raise RuntimeError("no PIXABAY_API_KEY (set in Colab userdata or env)")
    q = urllib.parse.quote(query)
    url = f"https://pixabay.com/api/videos/?key={key}&q={q}&video_type=film&per_page=5&orientation={orientation}&safesearch=true"
    req = urllib.request.Request(url, headers={"User-Agent": "colab-worker/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    hits = data.get("hits") or []
    if not hits:
        raise RuntimeError("no results")
    v = hits[0]
    vids = v.get("videos") or {}
    for k in ("large", "medium", "small", "tiny"):
        if vids.get(k):
            vurl = vids[k].get("url")
            break
    else:
        raise RuntimeError("no video url")
    # download
    req2 = urllib.request.Request(vurl, headers={"User-Agent": "colab-worker/1.0"})
    with urllib.request.urlopen(req2, timeout=300) as resp:
        Path(target).write_bytes(resp.read())
    return target


def handle_video_broll_fetch(task):
    task_id = task['id']
    params = task.get('params') or {}
    query = params.get('query') or 'interior design'
    orientation = params.get('orientation') or 'portrait'
    count = int(params.get('count') or 1)

    outdir = OUT_ROOT / task_id
    outdir.mkdir(parents=True, exist_ok=True)

    log(f"[video_broll_fetch] {task_id}: {count}x query='{query}' orient={orientation}")
    ok = 0
    for i in range(count):
        try:
            out = outdir / f"broll_{i:03d}.mp4"
            _pixabay_video_download(out, query, orientation)
            log(f"    saved {out.name} ({out.stat().st_size} bytes)")
            ok += 1
        except Exception as e:
            log(f"    failed {i}: {e}")
    meta = {
        "task_id": task_id,
        "type": "video_broll_fetch",
        "query": query,
        "orientation": orientation,
        "count": count,
        "ok": ok,
        "created": datetime.utcnow().isoformat() + "Z",
    }
    (outdir / "task_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return outdir


def handle_batch_rebuild(task):
    task_id = task['id']
    outdir = OUT_ROOT / task_id
    outdir.mkdir(parents=True, exist_ok=True)
    log(f"[batch_rebuild] {task_id}")
    (outdir / 'README.txt').write_text(
        f"task_id: {task_id}\ntype: batch_rebuild\ncreated: {datetime.utcnow().isoformat()}Z\n",
        encoding='utf-8'
    )
    return outdir


HANDLERS = {
    'image_gen': handle_image_gen,
    'video_broll_fetch': handle_video_broll_fetch,
    'batch_rebuild': handle_batch_rebuild,
}


def zip_dir(src_dir, zip_path):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(src_dir):
            for fn in files:
                full = Path(root) / fn
                rel = full.relative_to(src_dir.parent)
                z.write(full, rel)
    return zip_path


def main():
    ensure_dirs()
    tasks = load_tasks()
    if not tasks:
        log("No tasks found in ./tasks (upload tasks.zip or put *.json there)")
        return
    log(f"Loaded {len(tasks)} task(s)")
    for t in tasks:
        tid = t.get('id') or f"task-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        t['id'] = tid
        typ = t.get('type') or 'unknown'
        log(f"==> {tid} [{typ}]")
        try:
            h = HANDLERS.get(typ)
            if not h:
                log(f"  unknown type, skip")
                continue
            outdir = h(t)
            zp = ROOT / f"{tid}.zip"
            zip_dir(outdir, zp)
            log(f"  zipped -> {zp}")
        except Exception as e:
            log(f"  ERROR: {e}")


if __name__ == '__main__':
    main()
