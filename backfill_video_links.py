#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backfill_video_links.py — notebook 端：把收割條目的影片行補成「可點播」。

背景（2026-11-10 使用者定案）
----
- 影片永遠留在**產出機**的 D:\\YouTube_Videos（不複製到 notebook／NAS，省硬碟）。
- notebook 的條目要能**從存放位置直接點播**：條目內給 file:// 連結（點了用預設
  播放器開）＋可複製的 UNC 路徑。
- 但歷史條目有三種壞法：
  1. 11-09 的「打包剝除影片行」實驗 → 這批條目**沒有**影片行（例：PC2 11-09 的 20VTA）。
  2. 11-06~11-08 收割的條目帶的是**產出機的本機路徑**（D:\\YouTube_Videos\\...），
     notebook 上指不到（檔在 PC1／PC2）。
  3. notebook 自己的舊影片檔已被刪 → 無法救（列入待辦，不動那幾行）。

做法
----
1. 掃 knowledge-base 全部 .md 條目：
   - 有「本機影片／燒字幕影片」行：
     * 檔在 notebook 本機 → 改成 `- <label>：[▶ 點播](file:///D:/...)｜原路徑`
     * 檔不在本機 → 依序探測各產出機的 YouTube_Videos 唯讀分享（config.TAILSCALE_IPS），
       找到 → 改成 `- <label>（在 PCX）：[▶ 點播](file:////ip/YouTube_Videos/...)｜\\\\ip\\...`
       （格式與 publish_outbox.rewrite_producer_paths 完全一致）
     * 都找不到 → **保留原行**並列入待辦（該機可能還沒開分享，開了再重跑本工具）
   - **沒有**影片行、且該條目是從 PC 收割來的（working\\harvest_ledger.json）：
     到來源機的 YouTube_Videos 分享找 {stem}_字幕.mp4／{stem}.mp4，
     找到 → 在「影片資訊」區補上對應行（找不到 → 列待辦）
2. `--dry-run` 只印不寫。
冪等：已含 `[▶ 點播]` 或 `（在 PCX）` 的行不會再動；重跑只會補「上次找不到」的。

用法
----
    python -X utf8 backfill_video_links.py --dry-run    # 預覽
    python -X utf8 backfill_video_links.py              # 正式
    python -X utf8 fix_video_links.py                   # 接著跑：新行的 URI 點不開，要換成 .lnk 捷徑
    python -X utf8 backfill_video_links.py --report working\\my_report.txt

前提：產出機要先開 YouTube_Videos 唯讀分享（workspace-bundle\\infra\\setup\\setup_video_share.ps1），
notebook 要先存該機的 cmdkey（store_video_share_cmdkey.py）。沒開也照跑——只是那幾條
會進「找不到」清單，等開了再重跑一次即可。
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from publish_outbox import file_uri_for  # noqa: E402  與打包改寫同一份格式

KB_ROOT = ROOT / "knowledge-base"
LEDGER = ROOT / "working" / "harvest_ledger.json"
REPORT = ROOT / "working" / "backfill_video_links_report.txt"

VIDEO_LINE = re.compile(r"^([ \t]*-[ \t]*)(本機影片|燒字幕影片)：([^\r\n]*?)(\r?\n|$)", re.M)
YOUTUBE_LINE = re.compile(r"^(- YouTube 連結：[^\r\n]*)(\r?\n|$)", re.M)
DATE_LINE = re.compile(r"^(- 日期：[^\r\n]*)(\r?\n|$)", re.M)

EXCLUDE_DIRS = {"_harvest_conflicts", "_harvest_overwritten", "_archive_no_transcript"}


def log(msg=""):
    print(msg, flush=True)


def machine_shares():
    """要探測的產出機 → UNC 根（tailnet IP + YouTube_Videos 分享名）。"""
    out = []
    for name, ip in (config.TAILSCALE_IPS or {}).items():
        if not ip or name == config.MACHINE:
            continue
        out.append((name.upper(), "\\\\{ip}\\YouTube_Videos".format(ip=ip)))
    return out


def probe_unc(unc_path):
    try:
        return os.path.exists(unc_path)
    except OSError:
        return False


def find_video(base_name, shares):
    """回 (機器代號, UNC) 或 (None, None)；shares=[(LABEL, UNC_ROOT), ...]"""
    for label, root in shares:
        unc = root + "\\" + base_name
        if probe_unc(unc):
            return label, unc
    return None, None


def detect_newline(text):
    return "\r\n" if "\r\n" in text[:2000] else "\n"


def rewrite_line(prefix, label, raw_path, shares):
    """一行三種結果：('local'|'net'|'keep', 新行內容, 機器註記)"""
    raw = raw_path.strip()
    if "[▶ 點播]" in raw or "（在 " in raw:
        return "done", None, ""
    if os.path.exists(raw):
        uri = Path(raw).as_uri()          # file:///D:/YouTube_Videos/...
        return "local", f"{prefix}{label}：[▶ 點播]({uri})｜{raw}", ""
    base = os.path.basename(raw.rstrip("\\/"))
    if base:
        label_m, unc = find_video(base, shares)
        if label_m:
            return "net", f"{prefix}{label}（在 {label_m}）：[▶ 點播]({file_uri_for(unc)})｜{unc}", label_m
    return "keep", None, ""


def main():
    ap = argparse.ArgumentParser(description="回補收割條目的可點播影片行（notebook 端）")
    ap.add_argument("--dry-run", action="store_true", help="只印會做什麼，不寫任何檔")
    ap.add_argument("--report", default=str(REPORT), help="報告輸出檔（預設 working\\backfill_video_links_report.txt）")
    args = ap.parse_args()

    shares = machine_shares()
    log("== backfill_video_links ==")
    log(f"產出機分享探測清單：{[f'{l}:{u}' for l, u in shares] or '（無）'}")

    # 帳本：<machine>:<tid> → 這台收過哪些 stem（用來補「被剝除影片行」的條目）
    ledger_stems = {}   # stem -> machine（大寫）
    try:
        led = json.loads(LEDGER.read_text(encoding="utf-8-sig"))
        for tid, info in led.items():
            mach = str(tid).split(":")[0].upper()
            for fname in (info.get("sha256") or {}):
                if fname.endswith(".md") and not any(
                        k in fname for k in ("課程筆記", "摘要", "直播報告")):
                    ledger_stems[fname[:-3]] = mach
                    break
    except OSError:
        log(f"⚠️ 讀不到帳本 {LEDGER}（沒有 PC 收割紀錄可補行）")

    stats = {"done": 0, "local": 0, "net": 0, "keep": 0, "inserted": 0, "no_line": 0}
    fixed_files, pending = [], []

    for dp, dns, fns in os.walk(KB_ROOT):
        if any(part in EXCLUDE_DIRS for part in Path(dp).parts):
            continue
        for fn in fns:
            if not fn.endswith(".md"):
                continue
            p = Path(dp) / fn
            try:
                raw = p.read_bytes().decode("utf-8", "replace")
            except OSError:
                continue
            orig = raw

            # 1) 既有影片行 → 改寫
            def _rw(m):
                prefix, label, path, nl = m.group(1), m.group(2), m.group(3), m.group(4)
                kind, newline, mach = rewrite_line(prefix, label, path, shares)
                stats[kind if kind in stats else "keep"] += 1
                if kind in ("local", "net"):
                    fixed_files.append((str(p), kind, mach))
                elif kind == "keep":
                    pending.append((str(p), label, os.path.basename(path.strip())))
                if newline is None:
                    return m.group(0)
                return newline + nl

            raw = VIDEO_LINE.sub(_rw, raw)

            # 2) 沒有任何影片行 + 帳本說是 PC 收的 → 到來源機補行
            if not VIDEO_LINE.search(raw) and "YouTube 連結" in raw:
                stats["no_line"] += 1
                mach = ledger_stems.get(p.stem)
                if mach and shares:
                    src = next(((l, r) for l, r in shares if l == mach), None)
                    if src:
                        _, root = src
                        nl = detect_newline(raw)
                        add = ""
                        for label, suffix in (("本機影片", ".mp4"), ("燒字幕影片", "_字幕.mp4")):
                            base = p.stem + suffix
                            unc = root + "\\" + base
                            if probe_unc(unc):
                                add += (f"- {label}（在 {mach}）：[▶ 點播]({file_uri_for(unc)})｜{unc}{nl}")
                        if add:
                            anchor = DATE_LINE.search(raw) or YOUTUBE_LINE.search(raw)
                            if anchor:
                                raw = raw[:anchor.end()] + add + raw[anchor.end():]
                                stats["inserted"] += 1
                                fixed_files.append((str(p), "insert", mach))
                            else:
                                pending.append((str(p), "無影片資訊區可插入", mach))

            if raw != orig:
                rel = str(p.relative_to(KB_ROOT))
                if args.dry_run:
                    log(f"  [DRY] 會改寫 {rel}")
                else:
                    p.write_bytes(raw.encode("utf-8"))
                    log(f"  ✏️ {rel}")

    # 摘要
    log("")
    log("== 統計 ==")
    log(f"已可點播（不需改）      ：{stats['done']}")
    log(f"改成 notebook 本機點播   ：{stats['local']}")
    log(f"改成產出機 UNC 點播     ：{stats['net']}")
    log(f"補回被剝除的影片行      ：{stats['inserted']}")
    log(f"找不到影片（保留原行）  ：{stats['keep']}")
    log(f"無影片行條目（檢查過）  ：{stats['no_line']}")
    if pending:
        log("")
        log("== 找不到影片的清單（該機沒開分享？或影片已刪） ==")
        seen = set()
        for path, label, info in pending:
            if path in seen:
                continue
            seen.add(path)
            log(f"  - {Path(path).relative_to(KB_ROOT)}｜{label}｜{info}")

    lines = [
        f"# backfill_video_links 報告（{'dry-run' if args.dry_run else '正式'}）",
        f"機器：{config.MACHINE}｜探測：{[l for l, _ in shares]}",
        json.dumps(stats, ensure_ascii=False),
        "",
        "## 待辦（找不到影片）",
    ] + [f"- {p}｜{l}｜{i}" for p, l, i in pending]
    try:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text("\n".join(lines), encoding="utf-8")
        log(f"\n報告 → {args.report}")
    except OSError as e:
        log(f"⚠️ 報告寫入失敗：{e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
