#!/usr/bin/env python3
"""對 SRT 做機械式詞彙替換（只動文字行，時間碼與段號原封不動）。"""
import argparse
import re
import sys
from pathlib import Path

REPLACEMENTS = [
    # GPT Codex
    ("GPT-ClaudeX", "GPT-Codex"),
    ("GPT ClaudeX", "GPT Codex"),
    ("GPT-CloudX", "GPT-Codex"),
    ("GPT CloudX", "GPT Codex"),
    ("GPT-Cloud X", "GPT-Codex"),
    ("GPT Cloud X", "GPT Codex"),
    ("ClaudeX", "Codex"),
    ("CloudX", "Codex"),
    ("Cloud X", "Codex"),
    ("Claude X", "Codex"),
    ("CodeX", "Codex"),
    ("Code X", "Codex"),
    ("DexDex", "Codex"),
    ("Dex Dex", "Codex"),
    ("dex dex", "Codex"),
    ("克勞德X", "Codex"),
    ("克勞X", "Codex"),
    # Claude 生態
    ("ClockCode", "Claude Code"),
    ("Clock Code", "Claude Code"),
    ("Cloud Code", "Claude Code"),
    ("cloud code", "Claude Code"),
    ("CloudCode", "Claude Code"),
    ("ClawCode", "Claude Code"),
    ("claw code", "Claude Code"),
    ("Claw code", "Claude Code"),
    ("克勞德", "Claude"),
    ("克勞", "Claude"),
    ("Cloud", "Claude"),
    ("cloud", "Claude"),
    # 其他 AI 工具
    ("Notebook AM", "NotebookLM"),
    ("notebook AM", "NotebookLM"),
    ("Notebook LM", "NotebookLM"),
    ("notebook LM", "NotebookLM"),
    ("NotebookAM", "NotebookLM"),
    ("notebookLM", "NotebookLM"),
    ("ImageR", "Image 2"),
    ("Image R", "Image 2"),
    ("GPT Image 2", "GPT-Image 2"),
    ("GPT-Image2", "GPT-Image 2"),
    # 錯字
    ("斷考", "段考"),
    ("翻例", "範例"),
    ("烤卷", "考卷"),
    ("小課", "小克"),
]


def _group(span):
    groups = []
    for o in span:
        if groups and groups[-1][0] == o:
            groups[-1][1] += 1
        else:
            groups.append([o, 1])
    return [(o, c) for o, c in groups]


def _distribute(new_text, groups):
    g = len(groups)
    n = len(new_text)
    if g == 1:
        return [(groups[0][0], new_text)]
    if n == 0:
        return [(o, "") for o, _ in groups]
    total = sum(c for _, c in groups)
    quotas = [n * c / total for _, c in groups]
    counts = [int(q) for q in quotas]
    remainder = n - sum(counts)
    order = sorted(range(g), key=lambda i: quotas[i] - counts[i], reverse=True)
    for k in range(remainder):
        counts[order[k]] += 1
    if n >= g:
        for i in range(g):
            if counts[i] == 0:
                j = max(range(g), key=lambda k: counts[k])
                counts[j] -= 1
                counts[i] += 1
    res = []
    p = 0
    for (o, _), c in zip(groups, counts):
        res.append((o, new_text[p:p + c]))
        p += c
    return res


def _apply_pairs(joined, owner, pairs):
    for old, new in pairs:
        if not old:
            continue
        out_chars = []
        out_owner = []
        pos = 0
        idx = joined.find(old, pos)
        while idx != -1:
            out_chars.append(joined[pos:idx])
            out_owner.extend(owner[pos:idx])
            span = owner[idx:idx + len(old)]
            for o, sub in _distribute(new, _group(span)):
                out_chars.append(sub)
                out_owner.extend([o] * len(sub))
            pos = idx + len(old)
            idx = joined.find(old, pos)
        out_chars.append(joined[pos:])
        out_owner.extend(owner[pos:])
        joined = "".join(out_chars)
        owner = out_owner
    return joined, owner


def apply_cross_segment(bodies, pairs):
    joined = "".join(bodies)
    owner = []
    for i, b in enumerate(bodies):
        owner.extend([i] * len(b))
    joined, owner = _apply_pairs(joined, owner, pairs)
    new_bodies = [[] for _ in bodies]
    for ch, o in zip(joined, owner):
        new_bodies[o].append(ch)
    result = ["".join(parts) for parts in new_bodies]
    for i, b in enumerate(bodies):
        if result[i] == "" and b != "":
            result[i] = b
    return result


def process_srt(src: Path, dst: Path) -> None:
    content = src.read_text(encoding="utf-8-sig")
    segs = re.split(r"(\r?\n\r?\n)", content)
    text_positions = []
    headers = []
    bodies = []
    for si, seg in enumerate(segs):
        if not seg.strip() or seg.isspace() or "-->" not in seg:
            continue
        lines = seg.splitlines(keepends=False)
        if len(lines) < 3:
            continue
        text_positions.append(si)
        headers.append("\n".join(lines[:2]))
        bodies.append("\n".join(lines[2:]))
    new_bodies = apply_cross_segment(bodies, REPLACEMENTS)
    n_replaced = sum(1 for a, b in zip(bodies, new_bodies) if a != b)
    out = list(segs)
    for k, si in enumerate(text_positions):
        out[si] = headers[k] + "\n" + new_bodies[k]
    dst.write_text("".join(out), encoding="utf-8")
    print(f"[OK] 輸出 {dst}")
    print(f"     {n_replaced} 段有替換")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    process_srt(args.src, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
