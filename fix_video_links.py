#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_video_links.py — notebook 端：把條目裡「點不開」的 file:// 影片連結換成 .lnk 捷徑連結。

根因（2026-11-10 實測，三種開法全試過，勿再走回頭路）
----
- Markdown 連結目的地不能含空白 → 影片檔名（中文＋空格）只能 percent-encode（%E3%80%90…）；
- 但 Windows 開檔（ShellExecute／Obsidian 點 file:// 連結）**不會解碼 %XX** →
  percent-encoded 中文路徑一律 WinError 2「系統找不到指定的檔案」；
- 純路徑（\\ip\\YouTube_Videos\\中文 檔名.mp4）os.startfile 可以開，但檔名含空白 →
  放進 Markdown 連結會在第一個空白處被切斷。
解法：為每支影片建一個**全 ASCII 檔名**的 Windows 捷徑（.lnk）指向原路徑
（notebook 本機 D:\\ 或產出機 UNC \\\\ip\\…），條目連結改指捷徑——
檔名無中文無空白，Markdown 與系統開啟兩層都通（2026-11-10 實測點開會播）。

- .lnk 放 <kb>\\_video_links\\（預設 knowledge-base\\_video_links\\，隨 nas_backup 備份；
  遺失或失效重跑本腳本即重建）。
- 條目行尾的「｜原路徑」保留 → 可複製貼到檔案總管當後備。
- **自動對時（每晚排程就會做）**：每行都登記目標到 _video_links\\_targets.json，
  目標變了（產出機換 tailnet IP 等）才重建該 .lnk——「（在 PCX）」對照 config.TAILSCALE_IPS
  現值，IP 漂移時行尾 UNC 也一起換新，不必手動 --force。
- 冪等：已指捷徑且目標沒變的行不動；`--force` 無條件重建所有 .lnk。
- 排程：`harvest_daily.bat` 收割後接著跑（同 fix_youtube_links.py 模式）。
- 處理兩種行：
  * PC 收割：`- 燒字幕影片（在 PC2）：[▶ 點播](file://<ip>/…)｜\\\\<ip>\\…`
    （publish_outbox.rewrite_producer_paths 寫的，URI 點不開）
  * notebook 本機：`- 本機影片：[▶ 點播](file:///D:/…)｜D:\\…`
    （backfill_video_links 寫的，URI 同樣點不開）

用法
----
    python -X utf8 fix_video_links.py --dry-run
    python -X utf8 fix_video_links.py
    python -X utf8 fix_video_links.py --force        # 無條件重建所有 .lnk（一般不必；換 IP 會自動對時）
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve()
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402  （與其他工具同款：本機身分判斷用）

KB_ROOT = ROOT / "knowledge-base"
REPORT = ROOT / "working" / "fix_video_links_report.txt"

EXCLUDE_DIRS = {"_harvest_conflicts", "_harvest_overwritten",
                "_archive_no_transcript", "_video_links"}

# 點播行：- 本機影片（在 PC2）：[▶ 點播](file://…)｜\\ip\…
LINE_RE = re.compile(
    r"^(?P<pre>[ \t]*-[ \t]*)"
    r"(?P<label>本機影片|燒字幕影片)"
    r"(?P<mach>（在 [^）]+）)?："
    r"\[▶ 點播\]\((?P<uri>file:[^)\s]+)\)"
    r"(?P<rest>[^\r\n]*)",
    re.M,
)
VID_RE = re.compile(r"watch\?v=([A-Za-z0-9_-]{5,})")


def log(msg=""):
    print(msg, flush=True)


def resolve_target(uri, rest):
    """行尾「｜原路徑」優先（raw 未編碼）；沒有才解 URI。回傳本機路徑或 UNC 字串。"""
    if rest.startswith("｜"):
        t = rest[1:].strip()
        if t:
            return t
    u = uri.split(":", 1)[1] if uri.startswith("file:") else uri
    if u.startswith("//"):                      # file:////ip/share/x、file://ip/share/x → UNC
        return "\\\\" + unquote(u.lstrip("/")).replace("/", "\\")
    return unquote(u.lstrip("/")).replace("/", "\\")   # file:///D:/x → D:\x


def lnk_name(label, target, vid):
    """全 ASCII 檔名（video_id 可用就用，不然用路徑雜湊）。"""
    suffix = "burned" if "燒字幕" in label else "video"
    base = vid or hashlib.sha1(target.encode("utf-8")).hexdigest()[:12]
    return f"{base}_{suffix}.lnk"


def sync_machine_ip(target, rest, mach):
    r"""產出機換 tailnet IP 後自動對時：「（在 PCX）」對照 config.TAILSCALE_IPS 現值。

    只動我們自己寫的 UNC（\\<ip>\YouTube_Videos\…）；host 已是「別台機器的現值 IP」
    （label 過時、影片真的在別台）時不猜、不動。回傳 (新target, 新rest)。
    """
    if not target.startswith("\\\\") or "\\YouTube_Videos\\" not in target:
        return target, rest
    mk = (mach or "").strip("（）").replace("在", "").strip().lower()
    ips = config.TAILSCALE_IPS or {}
    cur = ips.get(mk)
    if not cur:
        return target, rest
    host = target[2:].split("\\", 1)[0]
    if host == cur or host in {ip for k, ip in ips.items() if k != mk}:
        return target, rest
    new_target = "\\\\" + cur + target[2 + len(host):]
    new_rest = rest.replace("\\\\" + host + "\\", "\\\\" + cur + "\\", 1)
    return new_target, new_rest


def make_shortcuts(items, links_dir):
    """一次 PowerShell 批次建立 .lnk（WScript.Shell）。items=[(ASCII名, 目標路徑)]。

    暫存檔（_batch.json／_mk_lnk.ps1）寫在系統暫存目錄，不落在 KB 裡。
    回傳 (成功數, powershell rc)。.lnk 不驗證目標存在（遠端離線也能先建好，
    之後連得上就點得開），所以遠端機器當下離線不算失敗。
    逾時 120 秒＋重試一次（2026-11-10 實測過一次無輸出卡死，勿移除防護）。
    """
    import tempfile
    links_dir = Path(links_dir)
    links_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lnk_") as td:
        td = Path(td)
        mf = td / "batch.json"
        mf.write_text(json.dumps(dict(items), ensure_ascii=False), encoding="utf-8-sig")
        ps1 = td / "mk.ps1"
        ps1.write_text(
            f"$links = Get-Content -Raw -Encoding UTF8 '{mf}' | ConvertFrom-Json\n"
            f"$ws = New-Object -ComObject WScript.Shell\n"
            f"foreach ($p in $links.PSObject.Properties) {{\n"
            f"  $s = $ws.CreateShortcut((Join-Path '{links_dir}' $p.Name))\n"
            f"  $s.TargetPath = [string]$p.Value\n"
            f"  $s.Save()\n"
            f"}}\n"
            f"Write-Output DONE\n",
            encoding="utf-8-sig",
        )
        rc = -1
        for attempt in (1, 2):
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                     "Bypass", "-File", str(ps1)],
                    capture_output=True, timeout=120)
                rc = r.returncode
                if rc == 0:
                    break
                log(f"⚠ PowerShell rc={rc}：{(r.stderr or b'').decode('utf-8', 'replace')[:300]}")
            except subprocess.TimeoutExpired:
                log(f"⚠ PowerShell 逾時（第 {attempt} 次，120 秒無輸出）")
                rc = -2
            except Exception as e:
                log(f"⚠ PowerShell 執行失敗：{e}")
                rc = -1
                break
    ok = sum(1 for n, _ in items
             if (links_dir / n).exists() and (links_dir / n).stat().st_size > 0)
    return ok, rc


def run(kb_root=None, links_dir=None, dry_run=False, force=False, report=None):
    """核心：掃 KB → 收集改寫 → 建 .lnk → 寫回。回傳 0/1。"""
    kb_root = Path(kb_root).resolve() if kb_root else KB_ROOT
    links_dir = Path(links_dir).resolve() if links_dir else kb_root / "_video_links"

    stats = {"fixed": 0, "already": 0, "keep": 0, "resync": 0}
    short = {}                      # ASCII .lnk 名 → 目標路徑
    pending_writes = []             # (path, new_text)
    unreachable = []                # (rel, .lnk 名) 目標目前不存在

    for dp, dns, fns in os.walk(kb_root):
        dns[:] = [d for d in dns if d not in EXCLUDE_DIRS]
        for fn in fns:
            if not fn.lower().endswith(".md"):
                continue
            p = Path(dp) / fn
            try:
                orig = p.read_bytes().decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            m_vid = VID_RE.search(orig)
            vid = m_vid.group(1) if m_vid else ""
            state = {"changed": False}

            def _rw(m):
                uri = m.group("uri")
                already = "_video_links/" in uri or "_video_links\\" in uri
                rest = m.group("rest")
                target, rest2 = sync_machine_ip(
                    resolve_target(uri, rest), rest, m.group("mach") or "")
                if not target:
                    stats["keep"] += 1
                    return m.group(0)
                name = lnk_name(m.group("label"), target, vid)
                if name in short and short[name] != target:
                    # 同名不同目標（少見：同 video_id 兩個存放位置）→ 用路徑雜湊消歧（確定性）
                    name = name[:-4] + "_" + hashlib.sha1(
                        target.encode("utf-8")).hexdigest()[:6] + ".lnk"
                short[name] = target
                if not os.path.exists(target):
                    unreachable.append((str(p.relative_to(kb_root)), name))
                want_uri = (links_dir / name).as_uri()
                if already:
                    # 行已指捷徑：URI／行尾路徑有漂移（換 IP、搬 links_dir）才重寫行
                    stats["already"] += 1
                    if uri == want_uri and rest2 == rest:
                        return m.group(0)
                    stats["resync"] += 1
                    state["changed"] = True
                    return (m.group("pre") + m.group("label") + (m.group("mach") or "")
                            + "：[▶ 點播](" + want_uri + ")" + rest2)
                stats["fixed"] += 1
                state["changed"] = True
                return (m.group("pre") + m.group("label") + (m.group("mach") or "")
                        + "：[▶ 點播](" + want_uri + ")" + rest2)

            new = LINE_RE.sub(_rw, orig)
            if new != orig:
                pending_writes.append((p, new))

    log("")
    log("== fix_video_links ==")
    log(f"KB：{kb_root}")
    log(f"捷徑目錄：{links_dir}")
    log(f"影片行：改寫 {stats['fixed']}｜已指捷徑 {stats['already']}"
        f"｜對時重寫 {stats['resync']}｜無法解析 {stats['keep']}")
    log(f"登記 .lnk 目標：{len(short)}（_targets.json 對照，目標變了才重建）")

    if dry_run:
        for p, _ in pending_writes:
            log(f"  [DRY] 會改寫 {p.relative_to(kb_root)}")
        return 0

    # 1) 建 .lnk（全有成才寫 md：避免 md 指到不存在的捷徑）。
    #    _targets.json 記「上次各 .lnk 指去哪」→ 目標變了（換 tailnet IP）才重建。
    created = 0
    if short:
        map_file = links_dir / "_targets.json"
        try:
            known = json.loads(map_file.read_text(encoding="utf-8-sig"))
            if not isinstance(known, dict):
                known = {}
        except (OSError, ValueError):
            known = {}
        todo = [(n, t) for n, t in sorted(short.items())
                if force or known.get(n) != t or not (links_dir / n).exists()]
        if todo:
            ok, rc = make_shortcuts(todo, links_dir)
            created = ok
            log(f".lnk 建立／對時：{ok}/{len(todo)} 成功（powershell rc={rc}）")
            if ok < len(todo):
                log("⚠ 有捷徑沒建成功 → 不改寫任何條目（下次重跑再試）")
                return 1
        else:
            log(".lnk 目標全都最新（冪等）")
        try:
            map_file.write_text(json.dumps(short, ensure_ascii=False, indent=1),
                                encoding="utf-8")
        except OSError as e:
            log(f"⚠ _targets.json 寫入失敗（下次會多重建一次，無害）：{e}")
        for n in short:
            if "%" in (links_dir / n).as_uri():
                log(f"⚠ 捷徑路徑含非 ASCII（URI 會被編碼，可能點不開）：{n}")
    else:
        log("（沒有需要處理的影片行）")

    # 2) 寫回條目
    for p, new in pending_writes:
        try:
            p.write_bytes(new.encode("utf-8"))
            log(f"  ✏️ {p.relative_to(kb_root)}")
        except OSError as e:
            log(f"  ⚠ 寫入失敗 {p.name}：{e}")
    if not pending_writes:
        log("（沒有條目需要改寫）")

    if unreachable:
        log("")
        log("== 目標目前連不上（.lnk 已建，之後連得上就點得開）==")
        for rel, name in unreachable:
            log(f"  - {rel} → {name}")

    if report:
        try:
            Path(report).parent.mkdir(parents=True, exist_ok=True)
            Path(report).write_text(
                "fix_video_links 報告（"
                + ("dry-run" if dry_run else "正式") + "）\n"
                + f"機器：{config.MACHINE}｜KB：{kb_root}\n"
                + json.dumps(stats, ensure_ascii=False) + f"\n.lnk：{created} 建立\n\n"
                "## 目標目前連不上\n"
                + "".join(f"- {r} → {n}\n" for r, n in unreachable),
                encoding="utf-8")
        except OSError as e:
            log(f"⚠ 報告寫入失敗：{e}")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="把條目裡點不開的 file:// 影片連結換成 _video_links 的 .lnk 捷徑（notebook 端）")
    ap.add_argument("--dry-run", action="store_true", help="只印會做什麼，不寫任何檔")
    ap.add_argument("--force", action="store_true",
                    help="無條件重建所有 .lnk（一般不必：換 tailnet IP 每晚自動對時）")
    ap.add_argument("--kb", help="覆寫 KB 根（測試用）")
    ap.add_argument("--links-dir", help="覆寫 .lnk 目錄（測試用；預設 <kb>/_video_links）")
    ap.add_argument("--report", default=str(REPORT), help="報告輸出檔")
    args = ap.parse_args()
    return run(kb_root=args.kb, links_dir=args.links_dir,
               dry_run=args.dry_run, force=args.force, report=args.report)


if __name__ == "__main__":
    sys.exit(main())
