"""收割鏈「目錄與格式對齊」自我檢查（唯讀；只在 working\\_align_check\\ 內作業）

用途：確認這台機器產出的 KB 條目，打包（publish_outbox）後由 notebook 收割
（harvest_pc）時，會**落在與 notebook 知識庫完全相同的相對目錄**，而且
直播報告（`直播報告\\<stem>.docx`）不會被漏掉。

2026-11-09 起因：頻道掃描從 notebook 移到 PC2。PC2 的 knowledge-base 是從零開始
（`knowledge-base/*` 不進 git），所以「路徑與格式是否對齊」只能用模擬驗證，
不能等到真的有新片才發現。

它做的事（全程不碰真實 KB、不碰 outbox、不碰 NAS、不寫排程）：
  1. 用 channel_watcher.kb_subdir_of() 驗證相對／絕對路徑都算得出子目錄
  2. 在 working\\_align_check\\ 造一個「直播條目」（md/srt/link.txt/課程筆記 docx/直播報告 docx）
  3. 用真正的 publish_outbox.publish_one() 打包到暫存 outbox
  4. 用真正的 harvest_pc 收割到暫存 KB
  5. 比對落地路徑是否與 notebook 的知識庫結構一致，並確認第二次為 skipped_same
  6. 清掉 working\\_align_check\\

用法：
    python -X utf8 workspace-bundle\\infra\\setup\\check_harvest_align.py
    python -X utf8 workspace-bundle\\infra\\setup\\check_harvest_align.py --keep   # 保留暫存目錄
"""
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]  # setup -> infra -> workspace-bundle -> 專案根
sys.path.insert(0, str(ROOT))

SUB = "人工智慧/AI agent-三師爸/直播"          # 三師爸直播（與 config.yaml 一致）
STEM = "2026-11-09_對齊測試"
VID = "V56PcjmqbWg"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)))
    mark = "OK  " if ok else "FAIL"
    print(f"  [{mark}] {name}{('  → ' + detail) if detail else ''}")
    return ok


def main():
    keep = "--keep" in sys.argv
    tmp = ROOT / "working" / "_align_check"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    kb = tmp / "kb"
    out = tmp / "outbox"
    kbh = tmp / "kb_harvest"
    shared = tmp / "shared"
    (shared / "tasks").mkdir(parents=True)

    print("== 1. 條目路徑換算（kb_subdir_of）==")
    import channel_watcher as cw

    rel_probe = f"knowledge-base\\{SUB}\\{STEM}.md"
    check("相對路徑算得出 kb_subdir", cw.kb_subdir_of(rel_probe) == SUB, cw.kb_subdir_of(rel_probe))
    abs_probe = str((ROOT / rel_probe).resolve())
    check("絕對路徑算得出 kb_subdir", cw.kb_subdir_of(abs_probe) == SUB, cw.kb_subdir_of(abs_probe))
    check("KB 外的路徑回空字串（不會誤判）", cw.kb_subdir_of(r"C:\Temp\x.md") == "", "''")

    print("\n== 2. 造一個「直播條目」==")
    d = kb / SUB
    d.mkdir(parents=True)
    md = d / f"{STEM}.md"
    md.write_text(f"# {STEM}\n\n## 影片資訊\n- YouTube 連結：https://www.youtube.com/watch?v={VID}\n\n"
                  "---\n\n## 逐字稿\n\n（對齊測試用，非真實內容）\n", encoding="utf-8")
    (d / f"{STEM}.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n測試\n", encoding="utf-8")
    (d / f"{STEM}.link.txt").write_text(f"https://www.youtube.com/watch?v={VID}\n", encoding="utf-8")
    (d / f"{STEM} 課程筆記.md").write_text("# 課程筆記\n", encoding="utf-8")
    (d / f"{STEM} 課程筆記.docx").write_bytes(b"PK\x03\x04note")
    rep = d / "直播報告"
    rep.mkdir()
    (rep / f"{STEM}.docx").write_bytes(b"PK\x03\x04report")

    tid = "990001"
    info = {"type": "youtube", "status": "completed", "name": STEM, "title": STEM,
            "video_id": VID, "kb_subdir": SUB, "harvest_to_kb": True, "machine": "aligncheck"}
    (shared / "tasks" / f"task_{tid}.json").write_text(
        json.dumps({"task_id": tid, "task_info": info, "status": "completed"}, ensure_ascii=False),
        encoding="utf-8")

    print("\n== 3. publish（真的打包到暫存 outbox，不碰 NAS）==")
    os.environ["OC_PUBLISH_SETTLE"] = "0"
    import publish_outbox as po

    po.PROJECT_ROOT = tmp
    po.SHARED_ROOT = shared
    po.KB_ROOT = kb
    po.PROGRESS_DIR = tmp / "progress"
    ledger = tmp / "pub_ledger.json"
    argv, sys.argv = sys.argv, [str(HERE), "--kb", str(kb), "--outbox", str(out),
                                "--ledger", str(ledger), "--task", tid]
    try:
        rc = po.main()
    finally:
        sys.argv = argv
    pkg = out / tid
    manifest = {}
    mf_path = pkg / "manifest.json"
    if mf_path.exists():
        manifest = json.loads(mf_path.read_text(encoding="utf-8"))
    files = manifest.get("files") or []
    rels = sorted((f.get("rel") or f.get("name")) for f in files)
    check("打包成功（rc=0）", rc == 0, f"rc={rc}")
    check("manifest kb_subdir 正確", manifest.get("kb_subdir") == SUB, manifest.get("kb_subdir"))
    expect = {f"{STEM}.md", f"{STEM}.srt", f"{STEM}.link.txt",
              f"{STEM} 課程筆記.md", f"{STEM} 課程筆記.docx",
              f"直播報告/{STEM}.docx"}
    missing = expect - set(rels)
    check("六個檔案都進包（含 直播報告 子目錄）", not missing,
          "缺 " + ", ".join(sorted(missing)) if missing else f"{len(rels)} 檔")

    print("\n== 4. harvest（真的收割到暫存 KB）==")
    import harvest_pc as hp

    hled = tmp / "h_ledger.json"
    argv, sys.argv = sys.argv, [str(HERE), "--machine", "aligncheck", "--root", str(out),
                                "--kb", str(kbh), "--ledger", str(hled), "--no-dedupe"]
    try:
        rc1 = hp.main()
        rc2 = hp.main()
    finally:
        sys.argv = argv
    landed = sorted(str(p.relative_to(kbh)).replace("\\", "/")
                    for p in kbh.rglob("*") if p.is_file())
    expect_landed = {f"{SUB}/{r}" for r in expect}
    missing_l = expect_landed - set(landed)
    check("收割 rc=0（第一次）", rc1 == 0, f"rc={rc1}")
    check("落地路徑與 notebook 知識庫結構一致", not missing_l,
          "缺 " + ", ".join(sorted(missing_l)) if missing_l else f"{len(landed)} 檔")
    check("第二次 harvest 不重複（冪等）", rc2 == 0 and len(landed) == len(expect_landed),
          f"檔案數 {len(landed)}")

    print("\n== 5. 清理 ==")
    if keep:
        print(f"  （--keep）暫存目錄保留：{tmp}")
    else:
        shutil.rmtree(tmp, ignore_errors=True)
        check("暫存目錄已清除", not tmp.exists(), str(tmp))

    bad = [n for n, ok, _ in results if not ok]
    print("\n" + "=" * 56)
    if bad:
        print(f"結果：{len(bad)} 項未通過 → {', '.join(bad)}")
        return 1
    print(f"結果：全部通過（{len(results)} 項）— 這台產出可安全收割進 notebook 知識庫")
    return 0


if __name__ == "__main__":
    sys.exit(main())
