#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backfill_products.py — 批量回補「知識產品」（摘要報告 L3 / 詳細筆記 L2）
=====================================================================
掃描知識庫中「已收成逐字稿、但缺產品」的條目，逐一產出摘要報告與/或詳細筆記。

- 摘要與筆記可複選（無旗標＝兩者皆補；經 --summary/--note 單選）
- 與 channel_watcher 共用 `.note_quota.json` 每日產製配額（預設 20），逐筆扣除；
  達今日配額即停止並列出待補數量（隔日重跑續補）
- skip-if-exists：已有同名產品就略過（idempotent，批次可重跑）
- 輸出同目錄：`{stem} 摘要.md`（＋.docx）、`{stem} 課程筆記.md`（＋.docx）

用法:
  python -X utf8 backfill_products.py                 # 摘要+筆記都補
  python -X utf8 backfill_products.py --summary       # 只補摘要
  python -X utf8 backfill_products.py --note          # 只補詳細筆記
  python -X utf8 backfill_products.py --subtree "20VTA 頻道\直播"   # 限某子目錄
  python -X utf8 backfill_products.py --dry-run       # 只列出待補，不產生
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent
KB = ROOT / "knowledge-base"
KB_EXCLUDE = ("金融交易",)   # 老師全集語料，不回補（與 harvest_report 一致）
QUOTA_FILE = KB / ".note_quota.json"
QUOTA_LOG_FILE = KB / ".note_quota_log.tsv"
MAX_PRODUCTS_PER_DAY = 20    # 與 channel_watcher MAX_NOTES_PER_DAY 一致

PRODUCTS = {
    "summary": ("摘要.md", "generate_summary"),
    "note": ("課程筆記.md", "generate_note"),
}


def is_transcript_md(p: Path) -> bool:
    """判定是否為「逐字稿 md」（排除已產出的產品檔與預覽檔）"""
    if p.stem.endswith("課程筆記") or p.stem.endswith("摘要"):
        return False
    if p.name.startswith("_preview_") or "_preview_" in p.name:
        return False
    try:
        head = p.read_text(encoding="utf-8", errors="replace")[:400]
    except Exception:
        return False
    return ("## 逐字稿" in head) or ("# YouTube Metadata" in head) or ("## 影片資訊" in head)


def _read_quota() -> dict:
    """讀配額檔（容忍 BOM；PowerShell 的 UTF8 會寫入 BOM）"""
    if not QUOTA_FILE.exists():
        return {}
    try:
        return json.loads(QUOTA_FILE.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def today_quota_used() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    data = _read_quota()
    if data.get("date") == today:
        return int(data.get("count", 0))
    return 0


def quota_take(tag: str = "") -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    data = _read_quota()
    if data.get("date") != today:
        data = {"date": today, "count": 0}
    if data.get("count", 0) >= MAX_PRODUCTS_PER_DAY:
        return False
    data["count"] = int(data.get("count", 0)) + 1
    try:
        QUOTA_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        _quota_log(tag)
        return True
    except Exception:
        return True    # 配額檔寫失敗不擋（保守放行，避免整批停產）


def _quota_log(tag: str) -> None:
    """記錄每次配額消耗（時間、當時累計、來源），供日後查核「配額何時、被誰用掉」"""
    try:
        line = f"{datetime.now().isoformat(timespec='seconds')}\t{today_quota_used()}\t{tag}\n"
        with open(QUOTA_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def collect_pending(subtree=None, kinds=("summary", "note")):
    """回傳 [(transcript_path, kind)] 依 KB 路徑排序的待補清單"""
    base = (KB / subtree) if subtree else KB
    if not base.exists():
        print(f"[ERR] 子目錄不存在：{base}")
        sys.exit(1)
    rows = []
    for p in sorted(base.rglob("*.md")):
        rel = p.relative_to(KB)
        if rel.parts and rel.parts[0] in KB_EXCLUDE:
            continue
        if not is_transcript_md(p):
            continue
        safe = re.sub(r'[\\/:*?"<>|]', "_", p.stem)
        for kind in kinds:
            suffix = PRODUCTS[kind][0]
            if not (p.parent / f"{safe} {suffix}").exists():
                rows.append((p, kind))
    return rows


def produce(p, kind, dry_run) -> str:
    safe = re.sub(r'[\\/:*?"<>|]', "_", p.stem)
    product = p.parent / f"{safe} {PRODUCTS[kind][0]}"
    if product.exists():
        return "skip-exists"
    if dry_run:
        return "todo"          # dry-run 不扣配額、不產出
    if not quota_take(f"backfill {kind}:{p.name}"):
        return "no-quota"
    from make_course_note import generate_note, generate_summary
    fn = generate_summary if kind == "summary" else generate_note
    fn(p.stem, [str(p)], p.parent, progress=lambda m: print(f"    {m}"))
    return "ok"


def main():
    ap = argparse.ArgumentParser(description="批量回補知識產品（摘要/詳細筆記）")
    ap.add_argument("--summary", action="store_true", help="只補摘要報告")
    ap.add_argument("--note", action="store_true", help="只補詳細筆記")
    ap.add_argument("--subtree", default=None, help="只處理 KB 下某子目錄（相對 knowledge-base/）")
    ap.add_argument("--file", default=None, help="只處理相對路徑含此字串的逐字稿（單檔回補）")
    ap.add_argument("--dry-run", action="store_true", help="只列出待補，不實際產出")
    args = ap.parse_args()

    if args.summary and args.note:
        kinds = ("summary", "note")
    elif args.summary:
        kinds = ("summary",)
    elif args.note:
        kinds = ("note",)
    else:
        kinds = ("summary", "note")   # 複選預設：兩者皆補

    rows = collect_pending(args.subtree, kinds)
    if args.file:
        rows = [(p, k) for (p, k) in rows if args.file in str(p.relative_to(KB))]
    print(f"待補清單：{len(rows)} 筆（種類：{'>'.join(kinds)}）"
          + (f"，子目錄：{args.subtree}" if args.subtree else "")
          + (f"，檔名字串：{args.file}" if args.file else "")
          + f"，今日已用配額 {today_quota_used()}/{MAX_PRODUCTS_PER_DAY}")

    stats = {"ok": 0, "todo": 0, "no-quota": 0, "skip": 0, "error": 0}
    remaining = 0
    for p, kind in rows:
        label = f"[{kind}] {p.relative_to(KB)}"
        try:
            r = produce(p, kind, args.dry_run)
        except Exception as e:
            r = "error"
            print(f"  ✗ {label} 失敗：{e}")
        stats[r] = stats.get(r, 0) + 1
        if r == "ok":
            print(f"  ✓ {label}")
        elif r == "todo":
            print(f"  ⬜（待辦）{label}")
        elif r == "skip":
            print(f"  ∘（已存在）{label}")
        elif r == "no-quota":
            remaining += 1
        stats["remaining"] = remaining
    if stats.get("no-quota"):
        stats["remaining"] = stats["no-quota"]
    print(f"\n結果：成功 {stats.get('ok', 0)}，已存在跳過 {stats.get('skip', 0)}，"
          f"達今日配額未補 {stats.get('remaining', 0)}（隔日重跑續補）"
          + (f"，失敗 {stats.get('error', 0)}" if stats.get("error") else ""))
    if stats["ok"] == 0:
        print("（本次無新增；若為 dry-run，上列為預排待補清單）")


if __name__ == "__main__":
    main()