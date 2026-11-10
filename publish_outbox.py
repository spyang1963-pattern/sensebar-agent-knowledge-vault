#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""publish_outbox.py — 產出機（PC1/PC2/PC3）把完成的 KB 產出打包到 outbox。

用途
----
三機不互相同步 `knowledge-base/`（只有 notebook 是正本）。產出機把「文字產出」
複製到 `shared\\<machine>\\outbox\\<task_id>\\`，最後寫 `manifest.json`；
notebook 端再用 `harvest_pc.py` 主動 pull 回去。

設計依據：`workspace-bundle/STEP7-HARVEST-DESIGN.md`
- **複製不搬**：本機 KB 條目照舊留著（產出機自己也要能查）
- **manifest.json 最後寫**：先寫 `.tmp` 再 os.replace，收割器看到 manifest 就代表整包完整
- **重跑同一 task 先清空該目錄**，避免新舊檔混在一起
- **冪等**：帳本 `working/_outbox_published.json` 記下檔案大小＋mtime，沒變就跳過

用法
----
    python -X utf8 publish_outbox.py                 # 所有已完成任務（沒變的會跳過）
    python -X utf8 publish_outbox.py --task 1951     # 只處理一筆
    python -X utf8 publish_outbox.py --dry-run       # 只印會做什麼，不寫任何檔
    python -X utf8 publish_outbox.py --force         # 忽略帳本，全部重打包
    python -X utf8 publish_outbox.py --outbox D:\\tmp\\outbox   # 測試用
    set OC_OUTBOX_ROOT=\\\\NAS\\exchange\\pc1\\outbox          # NAS 上線後（或直接寫在 config）

結束碼 = 失敗的任務數（沿用 smoke_test.py 慣例）。
"""
import argparse
import datetime as dt
import glob
import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import quote

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config

PROJECT_ROOT = Path(config.PROJECT_ROOT)
KB_ROOT = PROJECT_ROOT / "knowledge-base"
SHARED_ROOT = Path(config.SHARED_ROOT)
LEDGER = PROJECT_ROOT / "working" / "_outbox_published.json"
PROGRESS_DIR = PROJECT_ROOT / "working" / "_task_progress"

# 哪些副檔名算「文字產出」
EXTS = {".md", ".srt", ".txt", ".docx"}
# 條目附屬檔案可能放在條目同層的子目錄（例：20VTA／三師爸直播的「直播報告\<stem>.docx」）。
# 收割端會照 manifest 的 rel 還原路徑，所以這裡要收得到，否則報告永遠留在產出機。
SUBEXTS = ("直播報告",)


# 任務型別 → 是否有 KB 產出可收割
HARVESTABLE = {"youtube", "note", "summary", "video", "subtitle", "audio", "document", "web"}

# 檔案「靜止」幾秒才允許打包（避免把正在寫入的檔案做成半成品送進 outbox）
SETTLE_SECONDS = int(os.environ.get("OC_PUBLISH_SETTLE", "120"))


def _pid_alive(pid):
    """Windows：PID 還活著嗎（不開新 console、不依賴 psutil）。"""
    try:
        import ctypes
        from ctypes import wintypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        h = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return False
        code = wintypes.DWORD()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == STILL_ACTIVE
    except Exception:
        return False


_WORKER_ACTIVE = None


def worker_active():
    """本機此刻有沒有 worker 在跑（`working\\_worker_<machine>.lock` 的 PID 還活著）。

    2026-11-09：靜止保護原本一律 120 秒，結果「掃描跑完立刻打包」時，
    剛寫好的那一支一定被跳過 → 當晚最新影片要等到**隔天**才進 notebook。
    掃描與打包是同一條鏈（掃完才打包），掃描結束後已無寫入者；
    真正會同時寫 KB 的是 worker，所以只有「worker 在跑」時才需要等。
    """
    global _WORKER_ACTIVE
    if _WORKER_ACTIVE is not None:
        return _WORKER_ACTIVE
    lock = PROJECT_ROOT / "working" / f"_worker_{config.MACHINE}.lock"
    active = False
    if lock.exists():
        try:
            info = json.loads(lock.read_text(encoding="utf-8"))
            pid = info.get("pid")
            active = bool(pid) and int(pid) != os.getpid() and _pid_alive(pid)
        except Exception:
            active = True  # 讀不到就當作有（保守）
    _WORKER_ACTIVE = active
    return active


# 同一支影片的 youtube / note / summary 任務會指向同一個 stem，只打包一次
SEEN_STEMS = set()


def log(msg):
    print(msg, flush=True)


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def load_json(path, default=None):
    try:
        with io.open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ------------------------------------------------------------------ 任務來源
def iter_tasks():
    """讀 shared/tasks（唯一來源）；shared 不存在才退回 task_status.json。"""
    tasks_dir = SHARED_ROOT / "tasks"
    files = sorted(tasks_dir.glob("task_*.json")) if tasks_dir.is_dir() else []
    if files:
        for p in files:
            t = load_json(p)
            if not isinstance(t, dict):
                continue
            info = t.get("task_info") or {}
            status = t.get("status") or info.get("status")
            tid = str(info.get("task_id") or p.stem.split("_", 1)[1])
            yield tid, info, status
        return

    st = load_json(PROJECT_ROOT / "task_status.json", {}) or {}
    items = st.get("tasks") or {}
    if isinstance(items, list):
        items = {str(x.get("task_id")): x for x in items}
    for tid, info in items.items():
        yield str(tid), (info or {}), (info or {}).get("status")


# ------------------------------------------------------------------ 找 stem
def stem_from_progress(tid):
    """worker 完成時會寫 `KB: <md 路徑>`，最可靠。"""
    d = load_json(PROGRESS_DIR / f"{tid}.json")
    msg = (d or {}).get("message") or ""
    if msg.startswith("KB:"):
        p = msg[3:].strip()
        if p.lower().endswith(".md"):
            return Path(p)
    return None


VID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")


def derive_video_id(md_path):
    """note / summary 任務常常沒有 video_id 欄位（獨立派生），從 KB 條目回填。

    順序：`<stem>.link.txt`（channel_watcher 產生，內容就是 URL）→ 逐字稿前 40 行。
    都找不到回空字串（收割器會退回「同名比對」，比較容易誤判衝突）。
    """
    link = md_path.with_name(md_path.stem + ".link.txt")
    try:
        if link.exists():
            m = VID_RE.search(link.read_text(encoding="utf-8", errors="replace"))
            if m:
                return m.group(1)
    except OSError:
        pass
    try:
        with io.open(md_path, encoding="utf-8", errors="replace") as f:
            head = "".join(f.readlines()[:40])
    except OSError:
        head = ""
    m = VID_RE.search(head)
    return m.group(1) if m else ""


def stem_from_link(kb_dir, video_id):
    if not video_id or not kb_dir.is_dir():
        return None
    for f in kb_dir.glob("*.link.txt"):
        try:
            txt = io.open(f, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if video_id in txt:
            return f.with_name(f.name[: -len(".link.txt")] + ".md")
    return None


def resolve_stem(tid, info):
    """回傳 KB 條目 .md 的路徑（不存在回 None）。"""
    ttype = (info.get("type") or "").lower()

    # note / summary：從 source_md 推
    src = info.get("source_md")
    if src:
        p = Path(src)
        if p.suffix.lower() == ".md":
            return p

    # youtube：優先用 worker 的進度訊息，其次用 video_id 比對 .link.txt
    p = stem_from_progress(tid)
    if p and p.exists():
        return p

    vid = (info.get("video_id") or "").strip()
    subdir = (info.get("kb_subdir") or "youtube-clips").strip("/\\")
    kb_dir = KB_ROOT / subdir
    p = stem_from_link(kb_dir, vid)
    if p and p.exists():
        return p

    # 最後：document/web → title 命名的 .md
    title = (info.get("title") or info.get("name") or "").strip()
    if title:
        safe = "".join("_" if c in '\\/:*?"<>|' else c for c in title)
        for cand in (kb_dir / f"{safe}.md", KB_ROOT / f"{safe}.md"):
            if cand.exists():
                return cand
    return None


def collect_files(md_path):
    """同一 stem 的所有產出（逐字稿、srt、link、筆記、摘要…）。

    除了條目同層，也收 `SUBEXTS` 指名的子目錄（直播報告），
    否則搬去產出機的掃描產出會少掉 .docx 報告。
    """
    stem = md_path.with_suffix("")
    out = []
    for f in sorted(stem.parent.glob(md_path.stem + "*")):
        if not f.is_file():
            continue
        if f.suffix.lower() not in EXTS:
            continue
        rest = f.name[len(md_path.stem):]
        # `<stem>.md` 或 `<stem> 課程筆記.md`；排除只是前綴相同的其他條目
        if rest and not rest.startswith((".", " ")):
            continue
        out.append(f)
    for sub in SUBEXTS:
        d = stem.parent / sub
        if not d.is_dir():
            continue
        for f in sorted(d.glob(md_path.stem + "*")):
            if f.is_file() and f.suffix.lower() in EXTS:
                rest = f.name[len(md_path.stem):]
                if rest and not rest.startswith((".", " ")):
                    continue
                out.append(f)
    return out


def rel_in_pack(md_path, f):
    """檔案在 KB 條目目錄內的相對路徑（一律用 /）；同層檔就是檔名。"""
    try:
        return str(f.relative_to(md_path.parent)).replace("\\", "/")
    except ValueError:
        return f.name


def local_video_for(md_path):
    """產出機上的影片檔（燒字幕版優先）。"""
    vids = Path(config.get_machine_paths().get("videos") or PROJECT_ROOT / "videos")
    for c in (Path(r"D:\YouTube_Videos") / (md_path.stem + "_字幕.mp4"),
              Path(r"D:\YouTube_Videos") / (md_path.stem + ".mp4"),
              vids / (md_path.stem + ".mp4")):
        if c.exists():
            return str(c)
    return ""


def to_net_path(local_path):
    r"""產出機的本機影片路徑 → 收割端可點播的 UNC（\\<tailnet-ip>\YouTube_Videos\...）。
    影片統一放 D:\YouTube_Videos；其他位置／本機沒有 tailnet IP → 回 ""（沒有可用網路路徑）。"""
    ip = (config.TAILSCALE_IPS or {}).get(config.MACHINE)
    s = str(local_path or "")
    if ip and s.startswith(r"D:\YouTube_Videos"):
        rest = s[len(r"D:\YouTube_Videos"):].lstrip("\\/")
        return f"\\\\{ip}\\YouTube_Videos\\{rest}"
    return ""


def net_video_for(md_path):
    r"""notebook 點的網路影片路徑（\\<ip>\YouTube_Videos\...）。"""
    return to_net_path(local_video_for(md_path))


def file_uri_for(net_path):
    """UNC 路徑 → file:// URI（Obsidian 筆記裡可點擊，點了用預設播放器直接播放）。"""
    rest = str(net_path).lstrip("\\").replace("\\", "/")
    return "file:////" + quote(rest, safe="/:")


# 條目裡的影片路徑行：影片檔留在產出機（D:\YouTube_Videos），打包時改寫成
# 「機器註記＋UNC 點播路徑」，notebook 從影片存放位置直接播放（不複製檔案、不浪費硬碟）。
PRODUCER_PATH_LINE = re.compile(r"^([ \t]*-[ \t]*)(本機影片|燒字幕影片)：([^\r\n]*?)(\r?\n|$)", re.M)


def rewrite_producer_paths(text):
    """把打包副本裡的「本機影片／燒字幕影片」行改寫成「（在 PCX）＋ UNC 點播路徑」。

    2026-11-10 使用者定案（取代 11-09 的「直接剝除」）：
    - 影片永遠留在產出機的 D:\\YouTube_Videos，**不複製到 notebook／NAS**（省硬碟）。
    - notebook 端從網路路徑直接點播：條目內提供可點的 file:// 連結＋可複製的 UNC 路徑。
    - 算不出 UNC（影片不在 YouTube_Videos 或這台沒 tailnet IP）→ 仍標機器名＋原路徑。
    產出機自己的 KB 不動（它的本機路徑本來就是對的）。
    """
    machine = (config.MACHINE or "?").upper()

    def _rw(m):
        prefix, label, raw, nl = m.group(1), m.group(2), m.group(3).strip(), m.group(4)
        net = to_net_path(raw)
        if net:
            return f"{prefix}{label}（在 {machine}）：[▶ 點播]({file_uri_for(net)})｜{net}{nl}"
        return f"{prefix}{label}（在 {machine}）：{raw}{nl}"

    return PRODUCER_PATH_LINE.sub(_rw, text)


def publish_one(tid, info, out_root, kb_root, ledger, dry_run=False, force=False,
                keep_paths=False):
    ttype = (info.get("type") or "").lower()
    if ttype not in HARVESTABLE:
        return "ignore"  # 不是要收割的型別，安靜跳過

    md_path = resolve_stem(tid, info)
    if not md_path or not Path(md_path).exists():
        return "skip" if ttype in ("video", "subtitle", "audio") else f"#{tid} 找不到 KB 條目（{ttype}）"

    md_path = Path(md_path)
    try:
        md_path = kb_root / md_path.resolve().relative_to(kb_root.resolve()) \
            if str(md_path).lower().startswith(str(kb_root.resolve()).lower()) else md_path
    except Exception:
        pass

    files = collect_files(md_path)
    if not files:
        return f"#{tid} 條目存在但沒有可收割的檔案"

    # 2026-11-06：worker 正在跑長批次（44 支影片）時，22:50 的排程可能剛好撞上「檔案寫到一半」。
    # 半成品一旦進 outbox，收割後本機會保留那份內容（同家族不覆蓋），錯的會留下來。
    # 因此「最近 SETTLE_SECONDS 內還有變動」的條目先跳過，下一輪再打包（成本幾乎為零）。
    newest = max(f.stat().st_mtime for f in files)
    settle = SETTLE_SECONDS if worker_active() else 0
    if not force and settle and (time.time() - newest) < settle:
        return f"#{tid} 剛寫入（{int(time.time() - newest)} 秒前），本輪先不打包"

    if md_path.stem in SEEN_STEMS:
        return "skip"  # 同支影片的另一筆任務已打包
    SEEN_STEMS.add(md_path.stem)

    fingerprint = {f.name: [f.stat().st_size, int(f.stat().st_mtime)] for f in files}
    key = f"{config.MACHINE}:{md_path.stem}"
    if not force and ledger.get(key, {}).get("fingerprint") == fingerprint:
        return "skip"  # 沒變，跳過

    dest = out_root / str(tid)
    rel = None
    try:
        rel = str(md_path.resolve().parent.relative_to(kb_root.resolve())).replace("\\", "/")
    except Exception:
        rel = (info.get("kb_subdir") or "").strip("/\\") or "."

    if dry_run:
        log(f"  [DRY] #{tid} {ttype} → {dest}  ({len(files)} 檔, kb_subdir={rel})")
        for f in files:
            log(f"        + {f.name}")
        return "ok"

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    manifest_files = []
    for f in files:
        rel_f = rel_in_pack(md_path, f)
        target = dest / rel_f
        target.parent.mkdir(parents=True, exist_ok=True)
        if f.suffix.lower() == ".md" and not keep_paths:
            # 只改「打包副本」：把產出機的本機影片路徑改寫成「機器註記＋UNC 點播路徑」
            # （收割端沒有那些檔案，但可以從網路路徑直接點播，不必複製檔案）。
            # 走 bytes 以求原樣保留換行（KB 是 CRLF）與 BOM 有無；產出機自己的 KB 不動。
            text = f.read_bytes().decode("utf-8", "replace")
            target.write_bytes(rewrite_producer_paths(text).encode("utf-8"))
        else:
            shutil.copy2(f, target)
        manifest_files.append({"name": f.name, "rel": rel_f, "bytes": target.stat().st_size,
                               "sha256": sha256(target)})

    # note / summary 任務多半沒有 video_id，從 KB 條目回填（收割器靠它精確去重）
    vid = (info.get("video_id") or "").strip() or derive_video_id(md_path)

    manifest = {
        "schema": 1,
        "task_id": str(tid),
        "machine": config.MACHINE,
        "video_id": vid,
        "title": (info.get("title") or info.get("name") or md_path.stem),
        "kb_subdir": rel,
        "stem": md_path.stem,
        "local_video": local_video_for(md_path),
        "net_video": net_video_for(md_path),
        "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "files": manifest_files,
    }
    tmp = dest / "manifest.json.tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    os.replace(tmp, dest / "manifest.json")  # 最後才出現 → 代表整包完整

    ledger[key] = {"published_at": manifest["created_at"], "task_id": str(tid),
                   "dest": str(dest), "fingerprint": fingerprint}
    log(f"  [OK] #{tid} {ttype} → {dest}（{len(files)} 檔）")
    return "ok"


def main():
    ap = argparse.ArgumentParser(description="把完成的 KB 產出打包到 outbox")
    ap.add_argument("--task", help="只處理指定 task id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="忽略帳本，全部重打包")
    ap.add_argument("--outbox", help="覆寫 outbox 根（預設 shared/<machine>/outbox）")
    ap.add_argument("--kb", help="覆寫 knowledge-base 根（測試用）")
    ap.add_argument("--ledger", help="覆寫帳本路徑（測試用）")
    ap.add_argument("--keep-local-paths", action="store_true",
                    help="打包時保留原始「本機影片／燒字幕影片」行不改寫"
                         "（預設改寫成「（在 PCX）＋UNC 點播路徑」；收割端從網路路徑直接播放）")
    args = ap.parse_args()

    if args.outbox:
        out_root = Path(args.outbox)
    elif getattr(config, "OUTBOX_ROOT", ""):
        # NAS 上線後：OC_OUTBOX_ROOT=\\NAS\exchange\<machine>\outbox
        out_root = Path(config.OUTBOX_ROOT)
    else:
        out_root = SHARED_ROOT / config.MACHINE / "outbox"
    kb_root = Path(args.kb) if args.kb else KB_ROOT
    ledger = {} if args.dry_run else (load_json(args.ledger or LEDGER, {}) or {})
    SEEN_STEMS.clear()
    global _WORKER_ACTIVE
    _WORKER_ACTIVE = None  # 每輪重判斷（同一個 process 可能被呼叫多次）

    log(f"機器 {config.MACHINE}｜KB {kb_root}")
    log(f"outbox {out_root}{'（dry-run）' if args.dry_run else ''}")
    if worker_active():
        log(f"⚠️ 偵測到 worker 在跑 → 套用 {SETTLE_SECONDS} 秒靜止保護（避免打包半成品）")
    else:
        log("無 worker 在跑 → 掃描完成的檔案直接打包（不等靜止時間）")

    errors, n_ok, n_skip = [], 0, 0
    for tid, info, status in iter_tasks():
        if args.task and str(tid) != str(args.task):
            continue
        if status != "completed":
            continue
        r = publish_one(tid, info, out_root, kb_root, ledger,
                        dry_run=args.dry_run, force=args.force,
                        keep_paths=args.keep_local_paths)
        if r == "ok":
            n_ok += 1
        elif r in (None, "skip", "ignore"):
            n_skip += 1
        else:
            errors.append(r)

    if not args.dry_run:
        save_json(args.ledger or LEDGER, ledger)

    log(f"\n完成：打包 {n_ok}｜未變/跳過 {n_skip}｜失敗 {len(errors)}")
    for e in errors[:20]:
        log(f"  ⚠ {e}")
    if len(errors) > 20:
        log(f"  …另有 {len(errors) - 20} 筆")
    return len(errors)


if __name__ == "__main__":
    sys.exit(main())
