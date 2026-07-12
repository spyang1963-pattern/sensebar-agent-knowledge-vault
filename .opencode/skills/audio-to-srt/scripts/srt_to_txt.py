#!/usr/bin/env python3
"""把清字後的 SRT 轉成可閱讀的純文字檔。"""
import argparse
import re
import sys
from pathlib import Path

STRONG_PUNCT = set("。！？!?…")


def parse_srt(path: Path):
    content = path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\r?\n\r?\n", content.strip())
    texts = []
    for b in blocks:
        lines = b.strip().splitlines()
        if len(lines) < 3:
            continue
        text = " ".join(l.strip() for l in lines[2:] if l.strip())
        if text:
            texts.append(text)
    return texts


def join_to_paragraphs(segments) -> str:
    out = []
    buf = ""
    for seg in segments:
        if buf and buf[-1].isascii() and seg[:1].isascii():
            buf += " " + seg
        else:
            buf += seg
        if buf and buf[-1] in STRONG_PUNCT:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return "\n\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    segs = parse_srt(args.src)
    text = join_to_paragraphs(segs)
    args.out.write_text(text + "\n", encoding="utf-8")
    n_chars = sum(1 for c in text if not c.isspace())
    n_paras = text.count("\n\n") + 1
    print(f"[OK] 輸出 {args.out}")
    print(f"     {n_paras} 段落，{n_chars} 字")
    return 0


if __name__ == "__main__":
    sys.exit(main())
