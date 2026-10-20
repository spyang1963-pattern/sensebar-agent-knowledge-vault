#!/usr/bin/env python3
"""colab/worker.py - P5-5 Colab Batch Asset Factory worker

Runs in Google Colab. Reads tasks from working/_colab_tasks/*.json (or tasks/*.json)
and produces outputs to outputs/<task_id>/, zips as <task_id>.zip.

This is a minimal scaffold designed for easy extension by adding new task_type handlers.
"""
import json
import os
import sys
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


def handle_image_gen(task):
    task_id = task['id']
    params = task.get('params') or {}
    count = int(params.get('count') or 1)
    w = int(params.get('w') or 1080)
    h = int(params.get('h') or 1920)
    prompt = params.get('prompt') or 'interior design'

    outdir = OUT_ROOT / task_id
    outdir.mkdir(parents=True, exist_ok=True)

    log(f"[image_gen] {task_id}: {count}x ({w}x{h}) {prompt[:40]}...")
    # STUB: In Colab you can plug in free APIs/models here.
    # For now just write a README as placeholder to validate pipeline.
    (outdir / 'README.txt').write_text(
        f"task_id: {task_id}\ntype: image_gen\nprompt: {prompt}\ncount: {count}\nw: {w}\nh: {h}\ncreated: {datetime.utcnow().isoformat()}Z\n",
        encoding='utf-8'
    )
    log(f"[image_gen] wrote placeholder to {outdir}")
    return outdir


def handle_video_broll_fetch(task):
    task_id = task['id']
    params = task.get('params') or {}
    query = params.get('query') or 'interior design'
    orientation = params.get('orientation') or 'portrait'

    outdir = OUT_ROOT / task_id
    outdir.mkdir(parents=True, exist_ok=True)

    log(f"[video_broll_fetch] {task_id}: query='{query}' orient={orientation}")
    (outdir / 'README.txt').write_text(
        f"task_id: {task_id}\ntype: video_broll_fetch\nquery: {query}\norientation: {orientation}\ncreated: {datetime.utcnow().isoformat()}Z\n",
        encoding='utf-8'
    )
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
