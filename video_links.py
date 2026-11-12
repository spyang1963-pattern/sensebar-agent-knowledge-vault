#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""video_links.py — 知識庫「影片在哪一台、在哪個路徑」的單一權威。

為什麼要有這支（2026-11-12 使用者定案）
--------------------------------------
知識庫的影片行過去由 4 種工具各自產生，格式互不相容，補救腳本又只認得其中一種：

  1. channel_watcher：`- 本機影片：D:\\YouTube_Videos\\...`（沒有機器名、沒有可點連結）
  2. run_pipeline + scheduler：`## 影片` 下一行**裸路徑**（連欄位名都沒有）
  3. publish_outbox 打包：`- 燒字幕影片（在 PC2）：[▶ 點播](file://…)｜\\\\ip\\...`
  4. 舊工具／手動：以上混搭

結果：同一份知識庫，有的點得開、有的要猜影片在哪台、有的連欄位都沒有。
本工具是唯一出口（誕生、打包、收割、補救都呼叫它），一律輸出**帶機器名**的標準行：

  - 本機影片（在 notebook）：[▶ 點播](file:///…/_video_links/<id>_video.lnk)｜D:\\XQ直播_Videos\\…
  - 燒字幕影片（在 PC2）：[▶ 點播](file:///…/_video_links/<id>_burned.lnk)｜\\\\100.113.234.81\\YouTube_Videos\\…

規則
----
* 認得所有舊寫法，包含 `## 影片` 的裸路徑 → 改成標準行（GUI 已同步改用 first_video_path）。
* 機器判定順序：
    1. 絕對路徑且本機存在 → 本機（config.MACHINE）
    2. UNC → 用 config.TAILSCALE_IPS 反查機器
    3. 歷史條目 → working/harvest_ledger.json 的收割帳本回推來源機
    4. 都沒有才去探測各機分享（可用 --no-probe 關掉）
    5. 真的查不到 → 標 `（在 未確認）` 並列報告，**不猜**
* 遠端影片：`D:\\<root>\\...` 對應 `\\\\<該機 IP>\\<root>\\...`，該分享真的存在才用。
    分享沒開 → 保留機器名＋原路徑（誠實），並列進報告讓使用者一次補齊。
* 產品（` 摘要.md`／` 課程筆記.md`）：從同層逐字稿取影片位置，補 `> 影片位置：…`。
* **備份／內部目錄一律不處理**：_harvest_overwritten、_harvest_conflicts、
  _archive_no_transcript、_video_links，以及任何 backup_* 目錄。
* 冪等：已是標準行且 .lnk 目標沒變就不動；可重跑。

用法
----
    python -X utf8 video_links.py --dry-run     # 先看會改什麼（不寫檔、不建捷徑）
    python -X utf8 video_links.py --audit       # 只盤點（等於 dry-run + 不建捷徑）
    python -X utf8 video_links.py               # 正式套用（排程用這個）
    python -X utf8 video_links.py --no-probe    # 不做跨機分享探測（快，但可能標未確認）
    python -X utf8 video_links.py --force       # 無條件重建所有 .lnk
    python -X utf8 video_links.py --verify      # 回讀所有 .lnk，確認目標與 _targets.json 一致
"""
import argparse
import hashlib
import json
import ntpath
import os
import re
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

KB_ROOT = ROOT / "knowledge-base"
LEDGER = ROOT / "working" / "harvest_ledger.json"
REPORT = ROOT / "working" / "video_links_report.txt"

# 內部作業／備份目錄：永不處理（使用者 2026-11-12 明確要求「備份檔的知識庫不要再處理」）
EXCLUDE_DIRS = {
    "_harvest_overwritten", "_harvest_conflicts", "_archive_no_transcript",
    "_video_links", "_video_links_backup", ".git", ".obsidian",
}
EXCLUDE_PREFIX = ("backup_", "knowledge-base-backup")

MACHINE_LABEL = {"pc1": "PC1", "pc2": "PC2", "pc3": "PC3", "notebook": "notebook"}
VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".flv", ".m4v")
PRODUCT_SUFFIXES = (" 摘要.md", " 課程筆記.md", " 重點整理.md")
UNKNOWN = "未確認"

# 標準影片行（label 後面的機器註記可有可無，舊資料兩種都有）
LINE_RE = re.compile(
    r"^(?P<pre>[ \t]*-[ \t]*)"
    r"(?P<label>本機影片|燒字幕影片)"
    r"(?P<mach>（在 [^）]+）)?"
    r"：(?P<rest>[^\r\n]*)(?P<nl>\r?\n|$)",
    re.M,
)
HEADING_RE = re.compile(r"^##[ \t]*影片[ \t]*$")
ANY_HEADING_RE = re.compile(r"^##[ \t]")
LINK_RE = re.compile(r"\[▶ 點播\]\((?P<uri>file:[^)\s]+)\)(?P<tail>[^\r\n]*)")
VID_RE = re.compile(r"watch\?v=([A-Za-z0-9_-]{5,})")
ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")
PRODUCT_LOC_RE = re.compile(r"^>[ \t]*影片位置：[^\r\n]*(?:\r?\n|$)", re.M)
ORIGINAL_RE = re.compile(r"^>[ \t]*原始影片：[^\r\n]*(?:\r?\n|$)", re.M)
H1_RE = re.compile(r"^#[ \t]+[^\r\n]*(?:\r?\n|$)", re.M)


def log(msg=""):
    print(msg, flush=True)


# ---------------------------------------------------------------- 路徑／機器
def uri_to_path(uri):
    r"""file:// URI → Windows 路徑。

    `file:///D:/x`（三斜線）＝本機；`file:////host/share`（四斜線，path_to_uri 的寫法）
    或 `file://host/share` ＝ UNC。舊版把三斜線也當 UNC → 變成 `\\D:\x`（錯）。
    """
    u = unquote(uri[5:] if uri.startswith("file:") else uri)
    if u.startswith("////"):
        return "\\\\" + u.lstrip("/").replace("/", "\\")
    if u.startswith("///"):
        return u[3:].replace("/", "\\")
    if u.startswith("//"):
        return "\\\\" + u.lstrip("/").replace("/", "\\")
    return u.lstrip("/").replace("/", "\\")


def path_to_uri(path):
    r"""本機絕對路徑或 UNC → file:// URI（只給非 .lnk 的臨時顯示用）。"""
    if path.startswith("\\\\"):
        return "file:////" + quote(path.lstrip("\\").replace("\\", "/"), safe="/:")
    return Path(path).as_uri()


def split_rest(rest):
    """拆 `[▶ 點播](uri)｜path` 或純路徑 → (uri, path, tail)。"""
    rest = (rest or "").strip()
    m = LINK_RE.search(rest)
    if m:
        uri = m.group("uri")
        tail = m.group("tail") or ""
        if tail.startswith("｜"):
            path = tail[1:].strip()
        elif tail.strip():
            path = tail.strip()
        else:
            path = uri_to_path(uri)
        return uri, path, tail
    return "", rest, ""


def lnk_name(label, target, vid):
    """全 ASCII 捷徑名（與 fix_video_links 舊命名完全一致，既有 .lnk 直接沿用）。"""
    suffix = "burned" if "燒字幕" in label else "video"
    base = vid or hashlib.sha1(target.encode("utf-8")).hexdigest()[:12]
    return f"{base}_{suffix}.lnk"


def lnk_key(label, target, vid):
    return (label, target, vid or "")


def build_name_map(refs):
    """refs=[(label, target, vid)] → {key: 唯一 .lnk 名}。

    同一個 video_id 在不同目錄指向不同檔案時（罕見），名稱會撞在一起。
    撞名就補 `sha1(target)[:6]` 消歧，避免後建的捷徑默默蓋掉前一個目標。
    """
    seen = {}
    for label, target, vid in refs:
        seen.setdefault(lnk_name(label, target, vid), set()).add(target)
    out = {}
    for label, target, vid in refs:
        name = lnk_name(label, target, vid)
        if len(seen.get(name, ())) > 1:
            name = f"{name[:-4]}_{hashlib.sha1(target.encode('utf-8')).hexdigest()[:6]}.lnk"
        out[lnk_key(label, target, vid)] = name
    return out


def resolve_lnk_name(ctx, label, target, vid):
    """渲染時取 .lnk 名（有 name_map 就用消歧後的名字）。"""
    nm = ctx.get("name_map") or {}
    return nm.get(lnk_key(label, target, vid)) or lnk_name(label, target, vid)


def machine_display(machine):
    return MACHINE_LABEL.get((machine or "").lower(), machine or UNKNOWN)


def parse_mach_tag(tag):
    """`（在 PC1）` → `pc1`；`（在 notebook）` → `notebook`；未確認 → ``。"""
    s = (tag or "").strip("（）").replace("在", "").strip().lower()
    if not s or s in ("未確認", "unknown", "?"):
        return ""
    if s in MACHINE_LABEL:
        return s
    for key, label in MACHINE_LABEL.items():
        if s == label.lower():
            return key
    return s


class Resolver:
    """機器判定＋遠端分享探測（結果快取，避免重複等網路）。"""

    def __init__(self, hints=None, probe=True):
        self.hints = hints or {}
        self.probe = probe
        self._smb = {}
        self._share = {}

    def smb_open(self, ip):
        if ip in self._smb:
            return self._smb[ip]
        ok = False
        try:
            s = socket.create_connection((ip, 445), timeout=2.5)
            s.close()
            ok = True
        except OSError:
            ok = False
        self._smb[ip] = ok
        return ok

    def share_ok(self, ip, share):
        key = (ip, share)
        if key in self._share:
            return self._share[key]
        ok = bool(ip and share) and self.smb_open(ip) and os.path.isdir(f"\\\\{ip}\\{share}")
        self._share[key] = ok
        return ok

    def machine_of(self, path, hint=""):
        hint = "" if (hint or "").lower() in ("", "未確認", "unknown", "?") else hint
        if not path:
            return hint or ""
        if path.startswith("\\\\"):
            host = path[2:].split("\\", 1)[0]
            for m, ip in (config.TAILSCALE_IPS or {}).items():
                if ip and host.lower() == str(ip).lower():
                    return m
            return hint or ""      # 不認得的機器：標未確認，不亂取名
        if ABS_RE.match(path):
            if os.path.exists(path):
                return config.MACHINE
            if hint:
                return hint
            if self.probe:
                found = self._probe_machine(path)
                if found:
                    return found
            return ""
        return hint or ""

    def _probe_machine(self, local_path):
        m = re.match(r"^[A-Za-z]:\\(?P<root>[^\\]+)\\(?P<rest>.*)$", local_path)
        if not m:
            return ""
        root, rest = m.group("root"), m.group("rest")
        for mach, ip in (config.TAILSCALE_IPS or {}).items():
            if not ip or not self.share_ok(ip, root):
                continue
            cand = f"\\\\{ip}\\{root}\\{rest}"
            try:
                if os.path.exists(cand):
                    return mach
            except OSError:
                continue
        return ""

    def net_path_for(self, path, machine):
        r"""本機路徑 → 該機可讀的 UNC（分享存在且檔案看得到才回傳）。"""
        if not path:
            return ""
        if path.startswith("\\\\"):
            return path
        m = re.match(r"^[A-Za-z]:\\(?P<root>[^\\]+)\\(?P<rest>.*)$", path)
        if not m:
            return ""
        ip = (config.TAILSCALE_IPS or {}).get((machine or "").lower())
        root, rest = m.group("root"), m.group("rest")
        if not ip or not self.share_ok(ip, root):
            return ""
        cand = f"\\\\{ip}\\{root}\\{rest}"
        try:
            return cand if os.path.exists(cand) else ""
        except OSError:
            return ""


# ---------------------------------------------------------------- 帳本線索
_HINTS_CACHE = None


def load_ledger_hints():
    """歷史條目沒有機器名時，用收割帳本回推（dest 檔名 → 來源機）。

    結果快取（worker 一次跑很多篇時不必重讀帳本）；長駐程序若帳本有更新，
    重啟或跑一次 `video_links.py` 就會重讀。
    """
    global _HINTS_CACHE
    if _HINTS_CACHE is not None:
        return _HINTS_CACHE
    hints, exact = {}, {}
    try:
        data = json.loads(LEDGER.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        _HINTS_CACHE = hints
        return hints
    if not isinstance(data, dict):
        _HINTS_CACHE = hints
        return hints
    for key, rec in data.items():
        if not isinstance(rec, dict):
            continue
        mach = (rec.get("machine") or (key.split(":", 1)[0] if ":" in key else "")).lower()
        dest = rec.get("dest") or ""
        if not mach or not dest:
            continue
        stem = Path(dest).stem
        is_product = False
        for suf in (" 摘要", " 課程筆記", " 重點整理"):
            if stem.endswith(suf):
                stem = stem[: -len(suf)]
                is_product = True
                break
        if stem:
            if is_product:
                hints.setdefault(stem, mach)
            else:
                exact.setdefault(stem, mach)
    exact.update(hints)
    _HINTS_CACHE = exact
    return exact


# ---------------------------------------------------------------- 行改寫
def _looks_like_path(s):
    s = (s or "").strip()
    if not s:
        return False
    return bool(
        s.startswith("[▶ 點播](") or s.startswith("file:")
        or s.startswith("\\\\") or ABS_RE.match(s)
    )


def _render(pre, label, machine, target, display, ctx):
    tag = f"（在 {machine_display(machine)}）"
    if ctx.get("make_link") and target:
        name = resolve_lnk_name(ctx, label, target, ctx.get("vid"))
        uri = (ctx["links_dir"] / name).as_uri()
        return f"{pre}{label}{tag}：[▶ 點播]({uri})｜{display}"
    return f"{pre}{label}{tag}：{display}"


def _resolve_ref(label, path, hint, resolver):
    """→ (machine, target_for_lnk, display_path, linkable)。"""
    machine = resolver.machine_of(path, hint)
    if not machine:
        return "", "", path, False
    if machine == config.MACHINE and os.path.exists(path):
        return machine, path, path, True
    net = resolver.net_path_for(path, machine)
    if net:
        return machine, net, net, True
    # 遠端但目前連不上／沒分享：保留機器名＋原始路徑（誠實，不假裝可點）
    return machine, "", path, False


def normalize_text(text, ctx, hint=""):
    """把一段 md 內所有影片寫法改成標準行；回傳 (new_text, changed, stats, targets, issues)。

    hint：這篇條目在收割帳本裡的來源機（沒有機器註記的舊行才用得到）。
    """
    hint = (hint or "").lower()
    lines = text.splitlines(keepends=True)
    out, changed = [], False
    stats = {"lines": 0, "local": 0, "remote": 0, "unknown": 0}
    targets = {}        # lnk 名 → 目標
    issues = []         # (kind, label, machine, path)
    in_video = False

    def handle(pre, label, path, hint=""):
        nonlocal changed
        stats["lines"] += 1
        if not path:
            return None
        machine, target, display, linkable = _resolve_ref(label, path, hint, ctx["resolver"])
        if not machine:
            stats["unknown"] += 1
            issues.append(("unknown", label, "", path))
        elif machine == config.MACHINE:
            stats["local"] += 1
        else:
            stats["remote"] += 1
            if not linkable:
                issues.append(("no-share", label, machine, path))
        if target:
            targets[lnk_name(label, target, ctx["vid"])] = target
            ctx.setdefault("refs", []).append((label, target, ctx["vid"]))
        return _render(pre, label, machine, target, display, ctx)

    for line in lines:
        stripped = line.strip()
        if HEADING_RE.match(stripped):
            in_video = True
            out.append(line)
            continue
        if ANY_HEADING_RE.match(stripped):
            in_video = False
            out.append(line)
            continue

        m = LINE_RE.match(line)
        if m:
            _, path, _ = split_rest(m.group("rest"))
            line_hint = parse_mach_tag(m.group("mach")) or hint
            new = handle(m.group("pre"), m.group("label"), path, line_hint)
            if new is None:
                out.append(line)
                continue
            new += m.group("nl")
            if new != line:
                changed = True
            out.append(new)
            continue

        if in_video and _looks_like_path(stripped):
            indent = line[: len(line) - len(line.lstrip())]
            nl = line[len(line.rstrip("\r\n")):] or "\n"
            _, path, _ = split_rest(stripped)
            new = handle(indent + "- ", "本機影片", path, hint)
            if new is None:
                out.append(line)
                continue
            new += nl
            if new != line:
                changed = True
            out.append(new)
            in_video = False
            continue

        out.append(line)

    return "".join(out), changed, stats, targets, issues


def extract_first_ref(text, ctx, hint=""):
    """取條目內第一條影片行（供產品補 `> 影片位置：`、GUI 取路徑用）。"""
    lines = text.splitlines()
    in_video = False
    for line in lines:
        stripped = line.strip()
        if HEADING_RE.match(stripped):
            in_video = True
            continue
        if ANY_HEADING_RE.match(stripped):
            in_video = False
        m = LINE_RE.match(line)
        if m:
            _, path, _ = split_rest(m.group("rest"))
            if path:
                line_hint = parse_mach_tag(m.group("mach")) or hint
                machine, target, display, linkable = _resolve_ref(
                    m.group("label"), path, line_hint, ctx["resolver"])
                return m.group("label"), machine, target, display, linkable
        if in_video and _looks_like_path(stripped):
            _, path, _ = split_rest(stripped)
            if path:
                machine, target, display, linkable = _resolve_ref(
                    "本機影片", path, hint, ctx["resolver"])
                return "本機影片", machine, target, display, linkable
    return None


def normalize_product(text, ctx, transcript_text):
    """把 `> 影片位置：…` 插入／更新到產品 md（冪等）。回傳 (new_text, changed, targets)。"""
    ref = extract_first_ref(transcript_text, ctx)
    if not ref:
        return text, False, {}
    label, machine, target, display, linkable = ref
    vid_m = VID_RE.search(transcript_text)
    vid = vid_m.group(1) if vid_m else ""
    tag = f"（在 {machine_display(machine)}）"
    if target:
        name = resolve_lnk_name(ctx, label, target, vid)
        uri = (ctx["links_dir"] / name).as_uri()
        line = f"> 影片位置：{tag}[▶ 點播]({uri})｜{display}"
    else:
        line = f"> 影片位置：{tag}{display}"
    targets = {resolve_lnk_name(ctx, label, target, vid): target} if target else {}

    existing = PRODUCT_LOC_RE.search(text)
    if existing:
        if existing.group(0).strip() == line:
            return text, False, targets
        # 用函式當替換值：line 內含 Windows 路徑反斜線（\C、\Y…），
        # 直接當字串替換會被 re 當成跳脫序列 → re.error: bad escape（2026-11-12 實踩）
        return PRODUCT_LOC_RE.sub(lambda _m: line + "\n", text, count=1), True, targets

    m = ORIGINAL_RE.search(text)
    if m:
        pos = m.end()
        return text[:pos] + line + "\n" + text[pos:], True, targets
    m = H1_RE.search(text)
    if m:
        pos = m.end()
        sep = "" if text[pos:pos + 1] in ("\r", "\n") else "\n"
        return text[:pos] + sep + "\n" + line + "\n" + text[pos:], True, targets
    return text, False, targets


# ---------------------------------------------------------------- .lnk 建立
SHORTCUT_BATCH = 300      # 一次 PowerShell 建幾個 .lnk（1000+ 個會超過單次逾時）
LNK_MIN_SIZE = 200        # 小於這個大小＝空殼捷徑（80 bytes）＝沒寫進目標，要重建

# WScript.Shell 的 TargetPath 只吃「系統 ANSI 碼頁（本機 Big5/cp950）」組得出來的
# 字元：檔名含簡體專用字（恶、学、众…）會丟 E_INVALIDARG，而且 Save() 仍留下
# 80 bytes 的空殼 .lnk（不會報錯）。2026-11-12 實測確認。
# → 改用 IShellLinkW（UTF-16）直接寫，與檔案名稱用哪種中文無關。
LNK_CS = r"""
using System;
using System.Runtime.InteropServices;
using System.Text;

[ComImport, Guid("00021401-0000-0000-C000-000000000046")]
public class CShellLink { }

[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown),
 Guid("000214F9-0000-0000-C000-000000000046")]
public interface IShellLinkW {
    void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszFile,
                 int cch, IntPtr pfd, uint fFlags);
    void GetIDList(out IntPtr ppidl);
    void SetIDList(IntPtr pidl);
    void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszName, int cch);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string pszName);
    void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszDir, int cch);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string pszDir);
    void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszArgs, int cch);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string pszArgs);
    void GetHotkey(out short pwHotkey);
    void SetHotkey(short wHotkey);
    void GetShowCmd(out int piShowCmd);
    void SetShowCmd(int iShowCmd);
    void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszIconPath,
                         int cch, out int piIcon);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string pszIconPath, int iIcon);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string pszPathRel, uint dwReserved);
    void Resolve(IntPtr hwnd, uint fFlags);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string pszFile);
}

[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown),
 Guid("0000010b-0000-0000-C000-000000000046")]
public interface IPersistFile {
    void GetClassID(out Guid pClassID);
    [PreserveSig] int IsDirty();
    void Load([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, uint dwMode);
    void Save([MarshalAs(UnmanagedType.LPWStr)] string pszFileName,
              [MarshalAs(UnmanagedType.Bool)] bool fRemember);
    void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string pszFileName);
    void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string ppszFileName);
}

public static class LnkWriter {
    public static string Make(string listFile, string outDir) {
        var sl = (IShellLinkW)new CShellLink();
        var pf = (IPersistFile)sl;
        int ok = 0;
        var errs = new StringBuilder();
        // IPersistFile::Save 只吃「絕對路徑」：相對路徑一律回 E_INVALIDARG(0x80070057)。
        string dir = System.IO.Path.GetFullPath(outDir);
        foreach (var raw in System.IO.File.ReadAllLines(listFile, Encoding.UTF8)) {
            if (raw.Length == 0) continue;
            int t = raw.IndexOf('\t');
            if (t < 0) continue;
            string name = raw.Substring(0, t);
            string target = raw.Substring(t + 1);
            string step = "setpath";
            try {
                sl.SetPath(target);
                step = "save";
                pf.Save(System.IO.Path.Combine(dir, name), true);
                ok++;
            } catch (Exception e) {
                errs.AppendLine(name + "@" + step + ":" + e.GetType().Name + ":" + e.Message);
            }
        }
        return "OK\t" + ok + "\t" + errs.ToString().Replace("\n", " | ");
    }

    public static string Get(string lnkFile) {
        var sl = (IShellLinkW)new CShellLink();
        var pf = (IPersistFile)sl;
        pf.Load(System.IO.Path.GetFullPath(lnkFile), 0);
        var sb = new StringBuilder(2048);
        sl.GetPath(sb, sb.Capacity, IntPtr.Zero, 0);
        return sb.ToString();
    }
}
"""


def lnk_ok(path):
    """.lnk 是否真的寫進目標（80 bytes 空殼＝失敗）。"""
    try:
        return path.exists() and path.stat().st_size >= LNK_MIN_SIZE
    except OSError:
        return False


def _make_shortcut_batch(items, links_dir):
    """單批建立 .lnk；回傳 rc（0=成功）。暫存檔不落在 KB。"""
    with tempfile.TemporaryDirectory(prefix="vlnk_") as td:
        td = Path(td)
        mf = td / "batch.tsv"
        mf.write_text(
            "".join(f"{n}\t{t}\n" for n, t in items),
            encoding="utf-8",
        )
        cs = td / "lnk.cs"
        cs.write_text(LNK_CS, encoding="utf-8-sig")
        ps1 = td / "mk.ps1"
        ps1.write_text(
            f"$ErrorActionPreference = 'Stop'\n"
            f"Add-Type -TypeDefinition (Get-Content -Raw -Encoding UTF8 '{cs}')\n"
            f"[LnkWriter]::Make('{mf}', '{links_dir}')\n",
            encoding="utf-8-sig",
        )
        for attempt in (1, 2):
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                     "Bypass", "-File", str(ps1)],
                    capture_output=True, timeout=300)
                out = (r.stdout or b"").decode("utf-8", "replace").strip()
                if r.returncode == 0 and out.startswith("OK\t"):
                    parts = out.split("\t")
                    made = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else -1
                    if made == len(items):
                        return 0
                    detail = parts[2] if len(parts) > 2 else ""
                    log(f"⚠ 捷徑只寫成 {made}/{len(items)}：{detail[:400]}")
                else:
                    log(f"⚠ PowerShell rc={r.returncode}："
                        f"{(r.stderr or b'').decode('utf-8', 'replace')[:400]}")
            except subprocess.TimeoutExpired:
                log(f"⚠ PowerShell 逾時（第 {attempt} 次，300 秒無輸出）")
            except Exception as e:
                log(f"⚠ PowerShell 執行失敗：{e}")
                return -1
        return -2


def make_shortcuts(items, links_dir):
    """分批建立 .lnk；回傳 (成功數, rc)。"""
    links_dir = Path(links_dir).absolute()
    links_dir.mkdir(parents=True, exist_ok=True)
    items = list(items)
    rc = 0
    for i in range(0, len(items), SHORTCUT_BATCH):
        chunk = items[i:i + SHORTCUT_BATCH]
        r = _make_shortcut_batch(chunk, links_dir)
        if r != 0:
            rc = r
        if len(items) > SHORTCUT_BATCH:
            log(f"  … 捷徑進度 {min(i + SHORTCUT_BATCH, len(items))}/{len(items)}")
    ok = sum(1 for n, _ in items if lnk_ok(links_dir / n))
    return ok, rc


# ---------------------------------------------------------------- 回讀驗證
def read_shortcut_targets(names, links_dir):
    """用 IShellLinkW 讀回 .lnk 目標（分批）；回傳 {name: target}。"""
    links_dir = Path(links_dir).absolute()
    got = {}
    with tempfile.TemporaryDirectory(prefix="vlrb_") as td:
        td = Path(td)
        cs = td / "lnk.cs"
        cs.write_text(LNK_CS, encoding="utf-8-sig")
        ps1 = td / "rb.ps1"
        out = td / "rb.txt"
        for i in range(0, len(names), SHORTCUT_BATCH):
            chunk = names[i:i + SHORTCUT_BATCH]
            lst = td / "names.txt"
            lst.write_text("\n".join(chunk), encoding="utf-8")
            ps1.write_text(
                "$ErrorActionPreference='Stop'\n"
                f"Add-Type -TypeDefinition (Get-Content -Raw -Encoding UTF8 '{cs}')\n"
                f"$lines = Get-Content -LiteralPath '{lst}' -Encoding UTF8 | ForEach-Object {{\n"
                f"  $_ + \"`t\" + [LnkWriter]::Get((Join-Path '{links_dir}' $_))\n"
                f"}}\n"
                f"$lines | Set-Content -LiteralPath '{out}' -Encoding UTF8\n",
                encoding="utf-8-sig",
            )
            try:
                subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                                "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
                               capture_output=True, timeout=300)
            except subprocess.TimeoutExpired:
                log(f"⚠ 回讀逾時（{len(chunk)} 個 .lnk）")
                continue
            for line in out.read_text(encoding="utf-8-sig").splitlines():
                if "\t" in line:
                    n, t = line.split("\t", 1)
                    got[n.strip()] = t.strip()
            if len(names) > SHORTCUT_BATCH:
                log(f"  … 回讀進度 {min(i + SHORTCUT_BATCH, len(names))}/{len(names)}")
    return got


def verify_links(links_dir=None):
    """回讀所有 .lnk 與 _targets.json 比對。回傳 (ok, 問題清單)。

    `GetPath` 會把 `\\..\\` 正規化，所以比對用 ntpath.normpath；其他差異都算問題。
    """
    links_dir = Path(links_dir).absolute() if links_dir else KB_ROOT / "_video_links"
    map_file = links_dir / "_targets.json"
    try:
        targets = json.loads(map_file.read_text(encoding="utf-8-sig"))
        if not isinstance(targets, dict):
            raise ValueError
    except (OSError, ValueError):
        return False, [f"讀不到 {map_file}（先跑一次 video_links.py 建立）"]

    issues = []
    for n in targets:
        p = links_dir / n
        if not p.exists():
            issues.append(f"{n}：.lnk 不存在")
        elif not lnk_ok(p):
            issues.append(f"{n}：空殼捷徑（{p.stat().st_size} bytes）")

    got = read_shortcut_targets(sorted(targets), links_dir)

    def norm(s):
        return ntpath.normpath(s).rstrip("\\").lower()

    for n, t in sorted(targets.items()):
        g = got.get(n)
        if g is None:
            issues.append(f"{n}：回讀不到目標")
        elif norm(g) != norm(t):
            issues.append(f"{n}：目標不符\n  記的：{t}\n  實際：{g}")
    return not issues, issues


# ---------------------------------------------------------------- 掃 KB
def iter_md(kb_root):
    for dp, dns, fns in os.walk(kb_root):
        dns[:] = sorted(d for d in dns
                        if d not in EXCLUDE_DIRS
                        and not any(d.lower().startswith(p) for p in EXCLUDE_PREFIX))
        for fn in sorted(fns):
            if fn.lower().endswith(".md"):
                yield Path(dp) / fn


def _transcript_for(product_path):
    for suf in PRODUCT_SUFFIXES:
        if product_path.name.endswith(suf):
            cand = product_path.with_name(product_path.name[: -len(suf)] + ".md")
            return cand if cand.exists() else None
    return None


def run(kb_root=None, links_dir=None, dry_run=False, force=False,
        report=None, probe=True, quiet=False):
    kb_root = Path(kb_root).resolve() if kb_root else KB_ROOT
    links_dir = Path(links_dir).resolve() if links_dir else kb_root / "_video_links"
    hints = load_ledger_hints()
    resolver = Resolver(hints, probe=probe)

    scan = {"files": 0, "changed": 0, "products": 0, "skipped": 0}
    stats = {"lines": 0, "local": 0, "remote": 0, "unknown": 0}
    all_targets, issues = {}, []
    pending = []            # (path, new_text)

    # 先逐字稿、後產品（產品要讀已標準化的同層逐字稿）
    files = list(iter_md(kb_root))
    transcripts = [p for p in files if not p.name.endswith(PRODUCT_SUFFIXES)]
    products = [p for p in files if p.name.endswith(PRODUCT_SUFFIXES)]

    def ctx_for(path):
        try:
            raw = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        m = VID_RE.search(raw)
        return {"resolver": resolver, "links_dir": links_dir,
                "vid": m.group(1) if m else "", "make_link": not dry_run}

    # 1) 逐字稿：第一遍只收集 (label,target,vid) 建捷徑名稱表，第二遍才渲染
    parsed, refs = [], []
    for p in transcripts:
        scan["files"] += 1
        ctx = ctx_for(p)
        if ctx is None:
            scan["skipped"] += 1
            continue
        try:
            orig = p.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            scan["skipped"] += 1
            continue
        hint = hints.get(p.stem, "")
        probe_ctx = dict(ctx, make_link=False)
        normalize_text(orig, probe_ctx, hint)          # 只為收集 refs（不寫檔）
        refs.extend(probe_ctx.get("refs", []))
        parsed.append((p, orig, ctx, hint))

    name_map = build_name_map(refs)

    for p, orig, ctx, hint in parsed:
        ctx = dict(ctx, name_map=name_map, make_link=True)
        new, changed, st, tg, iss = normalize_text(orig, ctx, hint)
        for k in stats:
            stats[k] += st[k]
        all_targets.update(tg)
        issues.extend((str(p.relative_to(kb_root)),) + i for i in iss)
        if changed:
            scan["changed"] += 1
            pending.append((p, new))

    # 2) 產品（用「記憶體中已標準化」的逐字稿當來源）
    new_by_path = {p: t for p, t in pending}
    for p in products:
        scan["products"] += 1
        src = _transcript_for(p)
        if not src:
            continue
        src_text = new_by_path.get(src)
        if src_text is None:
            try:
                src_text = src.read_bytes().decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
        ctx = ctx_for(p)
        if ctx is None:
            continue
        ctx = dict(ctx, name_map=name_map, make_link=True)
        try:
            orig = p.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        new, changed, tg = normalize_product(orig, ctx, src_text)
        all_targets.update(tg)
        if changed:
            scan["changed"] += 1
            pending.append((p, new))

    if not quiet:
        log("")
        log("== video_links ==")
        log(f"KB：{kb_root}")
        log(f"捷徑目錄：{links_dir}")
        log(f"掃描 {scan['files']} 篇逐字稿＋{scan['products']} 篇產品"
            f"｜需改寫 {scan['changed']}｜跳過 {scan['skipped']}")
        log(f"影片行：本機 {stats['local']}｜遠端 {stats['remote']}"
            f"｜未確認 {stats['unknown']}（共 {stats['lines']} 行）")

    if dry_run:
        for p, _ in pending[:60]:
            log(f"  [DRY] 會改寫 {p.relative_to(kb_root)}")
        if len(pending) > 60:
            log(f"  [DRY] …另有 {len(pending) - 60} 篇")
        _write_report(report, kb_root, scan, stats, all_targets, issues, 0, 0, dry_run=True)
        return 0

    # 3) 建／對時 .lnk（全有成才寫 md，避免 md 指到不存在的捷徑）
    created = 0
    if all_targets:
        ok, total = _write_links(all_targets, links_dir, force=force)
        created = ok
        if not quiet:
            log(f".lnk 建立／對時：{ok}/{total}（共登記 {len(all_targets)}）")
        if ok < total:
            log("⚠ 有捷徑沒建成功 → 不改寫任何條目（下次重跑再試）")
            _write_report(report, kb_root, scan, stats, all_targets, issues, ok, total)
            return 1
        if not total and not quiet:
            log(".lnk 目標全都最新（冪等）")

    # 4) 寫回條目
    for p, new in pending:
        try:
            p.write_bytes(new.encode("utf-8"))
            if not quiet:
                log(f"  ✏️ {p.relative_to(kb_root)}")
        except OSError as e:
            log(f"  ⚠ 寫入失敗 {p.name}：{e}")

    if not quiet and not pending:
        log("（沒有條目需要改寫）")

    _write_report(report, kb_root, scan, stats, all_targets, issues, created, len(all_targets))
    if not quiet:
        _print_issues(issues)
    return 0


def _print_issues(issues):
    no_share = [i for i in issues if i[1] == "no-share"]
    unknown = [i for i in issues if i[1] == "unknown"]
    if no_share:
        log("")
        log("== 有機器名、但該機沒開影片分享（點不開，需在該機補分享）==")
        for rel, _, label, mach, path in no_share[:40]:
            log(f"  - {rel}｜{label}（在 {machine_display(mach)}）：{path}")
        if len(no_share) > 40:
            log(f"  …另有 {len(no_share) - 40} 筆，詳見 working\\video_links_report.txt")
    if unknown:
        log("")
        log("== 來源機未確認（保留原路徑，未亂猜）==")
        for rel, _, label, _, path in unknown[:40]:
            log(f"  - {rel}｜{label}：{path}")
        if len(unknown) > 40:
            log(f"  …另有 {len(unknown) - 40} 筆，詳見 working\\video_links_report.txt")


def _write_report(path, kb_root, scan, stats, targets, issues, created, total, dry_run=False):
    if not path:
        return
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "video_links 報告（" + ("dry-run" if dry_run else "正式") + "）",
            f"機器：{config.MACHINE}｜KB：{kb_root}",
            f"掃描：逐字稿 {scan['files']}／產品 {scan['products']}｜需改寫 {scan['changed']}",
            f"影片行：本機 {stats['local']}｜遠端 {stats['remote']}｜未確認 {stats['unknown']}",
            f".lnk：本次建立／對時 {created}（共登記 {total}）",
            "",
            "## 有機器名、但該機沒開影片分享（需在該機補分享後重跑）",
        ]
        for rel, _, label, mach, p in [i for i in issues if i[1] == "no-share"]:
            lines.append(f"- {rel}｜{label}（在 {machine_display(mach)}）：{p}")
        lines += ["", "## 來源機未確認（保留原路徑，未猜）"]
        for rel, _, label, _, p in [i for i in issues if i[1] == "unknown"]:
            lines.append(f"- {rel}｜{label}：{p}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as e:
        log(f"⚠ 報告寫入失敗：{e}")


# ---------------------------------------------------------------- 給其他工具用
def kb_root_of(md_path):
    """往上找 knowledge-base 層；找不到就用 md 的上一層。"""
    for parent in Path(md_path).parents:
        if parent.name == "knowledge-base":
            return parent
    return Path(md_path).parent


def _write_links(targets, links_dir, force=False):
    """建立 targets（名→目標）缺的 .lnk；回傳 (成功數, 總數)。"""
    links_dir = Path(links_dir)
    links_dir.mkdir(parents=True, exist_ok=True)
    map_file = links_dir / "_targets.json"
    try:
        known = json.loads(map_file.read_text(encoding="utf-8-sig"))
        if not isinstance(known, dict):
            known = {}
    except (OSError, ValueError):
        known = {}
    todo = [(n, t) for n, t in sorted(targets.items())
            if force or known.get(n) != t or not lnk_ok(links_dir / n)]
    if todo:
        ok, rc = make_shortcuts(todo, links_dir)
        if ok < len(todo):
            log(f"⚠ .lnk 只建成 {ok}/{len(todo)}（rc={rc}），條目暫不指向捷徑")
            return ok, len(todo)
    known.update(targets)
    try:
        map_file.write_text(json.dumps(known, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    except OSError as e:
        log(f"⚠ _targets.json 寫入失敗（無害，下次會重建）：{e}")
    return len(todo), len(todo)


def normalize_file(md_path, links_dir=None, dry_run=False, quiet=True):
    """誕生／收成時就地標準化「單一」md（給 channel_watcher、scheduler 呼叫）。

    只處理這一篇（不掃整庫），成本固定。回傳 1=有改寫、0=沒變。
    產品（` 摘要.md`／` 課程筆記.md`）改補 `> 影片位置：`。
    """
    md_path = Path(md_path)
    if not md_path.exists():
        return 0
    md_path = md_path.absolute()          # .as_uri() 需要絕對路徑（呼叫端可能傳相對路徑）
    kb_root = kb_root_of(md_path)
    links_dir = Path(links_dir).absolute() if links_dir else kb_root / "_video_links"
    try:
        orig = md_path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return 0

    hints = load_ledger_hints()
    resolver = Resolver(hints, probe=True)
    m = VID_RE.search(orig)
    ctx = {"resolver": resolver, "links_dir": links_dir,
           "vid": m.group(1) if m else "", "make_link": True}
    hint = hints.get(md_path.stem, "")

    if md_path.name.endswith(PRODUCT_SUFFIXES):
        src = _transcript_for(md_path)
        if not src:
            return 0
        try:
            src_text = src.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return 0
        probe = dict(ctx, make_link=False)
        ref = extract_first_ref(src_text, probe)
        name_map = {}
        if ref and ref[2]:
            name_map = build_name_map([(ref[0], ref[2], ctx["vid"])])
        ctx = dict(ctx, name_map=name_map)
        new, changed, targets = normalize_product(orig, ctx, src_text)
    else:
        probe = dict(ctx, make_link=False)
        normalize_text(orig, probe, hint)
        ctx = dict(ctx, name_map=build_name_map(probe.get("refs", [])))
        new, changed, _st, targets, _iss = normalize_text(orig, ctx, hint)

    if dry_run or not changed:
        return 0 if not changed else 1

    if targets:
        ok, total = _write_links(targets, links_dir)
        if ok < total:
            return 0                      # 捷徑沒建好就不寫（避免指向不存在）
    try:
        md_path.write_bytes(new.encode("utf-8"))
    except OSError as e:
        log(f"⚠ 寫入失敗 {md_path.name}：{e}")
        return 0
    if not quiet:
        log(f"  ✏️ {md_path.name}")
    return 1


def first_video_path(text):
    """從條目文字取第一個影片的實際路徑（GUI／工具用；支援新舊格式）。"""
    ctx = {"resolver": Resolver({}, probe=False), "links_dir": Path("."),
           "vid": "", "make_link": False}
    ref = extract_first_ref(text, ctx)
    return ref[3] if ref else ""


def render_pack_line(label, path, machine=None, net_path=""):
    r"""打包副本用：只標機器名＋可用的網路路徑，不帶產出機自己的 .lnk。"""
    machine = (machine or config.MACHINE).lower()
    display = net_path or path
    return f"- {label}（在 {machine_display(machine)}）：{display}"


def pack_text(text, machine=None):
    """publish_outbox 打包時呼叫：把產出機的影片行改成「（在 PCX）＋UNC／原路徑」。

    不建 .lnk（那是收割端的事），也不改產出機自己的 KB。
    """
    machine = (machine or config.MACHINE).lower()
    resolver = Resolver({}, probe=False)
    out, changed = [], False
    in_video = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if HEADING_RE.match(stripped):
            in_video = True
            out.append(line)
            continue
        if ANY_HEADING_RE.match(stripped):
            in_video = False
            out.append(line)
            continue
        m = LINE_RE.match(line)
        if m:
            _, path, _ = split_rest(m.group("rest"))
            net = resolver.net_path_for(path, machine)
            new = render_pack_line(m.group("label"), path, machine, net) + m.group("nl")
            changed |= new != line
            out.append(new)
            continue
        if in_video and _looks_like_path(stripped):
            indent = line[: len(line) - len(line.lstrip())]
            nl = line[len(line.rstrip("\r\n")):] or "\n"
            _, path, _ = split_rest(stripped)
            net = resolver.net_path_for(path, machine)
            new = indent + render_pack_line("本機影片", path, machine, net) + nl
            changed |= new != line
            out.append(new)
            in_video = False
            continue
        # 產品（摘要／課程筆記）的「> 影片位置：」也要改成產出機的機器名＋UNC
        if stripped.startswith("> 影片位置："):
            key = "影片位置："
            pos = line.index(key) + len(key)
            prefix = line[:pos]
            body = line[pos:].rstrip("\r\n")
            nl = line[len(line.rstrip("\r\n")):] or "\n"
            _, path, _ = split_rest(body)
            net = resolver.net_path_for(path, machine) if path else ""
            new = f"{prefix}（在 {machine_display(machine)}）：{net or path}{nl}"
            changed |= new != line
            out.append(new)
            continue
        out.append(line)
    return "".join(out)


def main():
    ap = argparse.ArgumentParser(
        description="知識庫影片行唯一權威：標機器名＋可點 .lnk（含產品影片位置）")
    ap.add_argument("--dry-run", action="store_true", help="只印會做什麼，不寫檔、不建捷徑")
    ap.add_argument("--audit", action="store_true", help="只盤點（同 dry-run，不建捷徑）")
    ap.add_argument("--force", action="store_true", help="無條件重建所有 .lnk")
    ap.add_argument("--no-probe", action="store_true", help="不做跨機分享探測（快）")
    ap.add_argument("--kb", help="覆寫 KB 根（測試用）")
    ap.add_argument("--links-dir", help="覆寫 .lnk 目錄（測試用；預設 <kb>/_video_links）")
    ap.add_argument("--report", default=str(REPORT), help="報告輸出檔")
    ap.add_argument("--verify", action="store_true",
                    help="回讀所有 .lnk，確認目標與 _targets.json 一致（不掃 KB）")
    args = ap.parse_args()
    if args.verify:
        links_dir = args.links_dir or (
            (Path(args.kb).resolve() / "_video_links") if args.kb else KB_ROOT / "_video_links")
        ok, issues = verify_links(links_dir)
        if ok:
            n = len(json.loads((Path(links_dir) / "_targets.json").read_text(
                encoding="utf-8-sig")))
            log(f"✓ 捷徑全部正常（{n} 個）")
            return 0
        log(f"✗ 捷徑有 {len(issues)} 個問題：")
        for i in issues[:40]:
            log(f"  - {i}")
        if len(issues) > 40:
            log(f"  … 其餘 {len(issues) - 40} 筆見報告")
        try:
            Path(args.report).parent.mkdir(parents=True, exist_ok=True)
            Path(args.report).write_text("\n".join(issues) + "\n", encoding="utf-8")
            log(f"報告：{args.report}")
        except OSError as e:
            log(f"⚠ 報告寫入失敗：{e}")
        return 1
    return run(kb_root=args.kb, links_dir=args.links_dir,
               dry_run=args.dry_run or args.audit, force=args.force,
               report=args.report, probe=not args.no_probe)


if __name__ == "__main__":
    sys.exit(main())
