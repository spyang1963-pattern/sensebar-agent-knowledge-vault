#!/usr/bin/env python3
"""依 Groq JSON 重新切段，輸出 SRT。"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MAX_DUR = 3.0
MIN_DUR = 0.6
MAX_CHARS = 15
SOFT_CHARS = 10
STRONG_PUNCT = set("。！？!?…")
WEAK_PUNCT = set("，、；：,;:")
ALL_PUNCT = STRONG_PUNCT | WEAK_PUNCT


def ms_tc(s: float) -> str:
    ms = int(round(s * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    sec, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def char_w(text: str) -> float:
    return sum(0.5 if c.isascii() else 1.0 for c in text if not c.isspace())


def is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def last_char(buf) -> str:
    text = "".join(x["word"] for x in buf).strip()
    return text[-1] if text else ""


def char_count(buf) -> float:
    return char_w("".join(x["word"] for x in buf))


def duration(buf) -> float:
    if not buf:
        return 0.0
    return buf[-1]["end"] - buf[0]["start"]


def find_back_punct(buf, max_back: int = 4) -> int:
    start = max(0, len(buf) - max_back)
    for i in range(len(buf) - 1, start - 1, -1):
        word_text = buf[i]["word"].rstrip()
        if word_text and word_text[-1] in ALL_PUNCT:
            return i
    return -1


def near_seg_boundary(word_end: float, seg_ends: list, tol: float = 0.25) -> bool:
    return any(abs(word_end - se) <= tol for se in seg_ends)


INTERJECTIONS = {"好", "嗯", "欸", "誒", "對", "來", "喔", "哦", "OK", "Ok", "ok"}


def punct_ahead(words, i, look: int = 2, max_extra: float = 4.0) -> bool:
    extra = 0.0
    for k in range(1, look + 1):
        if i + k >= len(words):
            return False
        wt = words[i + k]["word"].rstrip()
        extra += char_w(wt)
        if extra > max_extra:
            return False
        if wt and wt[-1] in ALL_PUNCT:
            core = wt[:-1].strip()
            if core in INTERJECTIONS:
                return False
            return True
    return False


def rescue_orphan_tails(chunks):
    k = 1
    while k < len(chunks):
        cur = chunks[k]
        prev_last = last_char(chunks[k - 1])
        if prev_last and prev_last in ALL_PUNCT:
            k += 1
            continue
        take = 0
        lead_chars = 0.0
        lead_text = ""
        for j, w in enumerate(cur):
            wt = w["word"].rstrip()
            if not wt:
                continue
            if wt[-1] in ALL_PUNCT:
                take = j + 1
                lead_chars += char_w(wt[:-1])
                lead_text += wt[:-1].strip()
                break
            lead_chars += char_w(wt)
            lead_text += wt
            if lead_chars > 2:
                break
        if take and lead_chars <= 2 and lead_text not in INTERJECTIONS:
            if take < len(cur):
                chunks[k - 1].extend(cur[:take])
                chunks[k] = cur[take:]
            else:
                chunks[k - 1].extend(cur)
                del chunks[k]
                continue
        k += 1
    return chunks


def resegment(words, segments):
    seg_ends = [float(s["end"]) for s in segments]
    chunks = []
    buf = []

    i = 0
    while i < len(words):
        w = words[i]
        buf.append(w)
        chars = char_count(buf)
        dur = duration(buf)
        last = last_char(buf)
        at_seg_end = near_seg_boundary(w["end"], seg_ends)

        cut_here = False
        cut_back = -1

        if last in STRONG_PUNCT and dur >= MIN_DUR:
            cut_here = True
        elif at_seg_end and dur >= MIN_DUR and chars >= 4:
            if not punct_ahead(words, i):
                cut_here = True
        elif chars >= SOFT_CHARS and last in WEAK_PUNCT and dur >= MIN_DUR:
            cut_here = True
        elif (chars >= MAX_CHARS or dur >= MAX_DUR) and last in ALL_PUNCT:
            cut_here = True
        elif dur >= MAX_DUR + 0.8 or chars >= MAX_CHARS + 3:
            back = find_back_punct(buf)
            if back >= 0 and back < len(buf) - 1:
                cut_back = back
            elif (
                punct_ahead(words, i)
                and chars <= MAX_CHARS + 6
                and dur < MAX_DUR + 2.5
            ):
                pass
            else:
                nxt_raw = words[i + 1]["word"] if i + 1 < len(words) else ""
                nxt_first = nxt_raw.lstrip()[:1] if nxt_raw else ""
                last_cjk = is_cjk(last) if last else False
                nxt_cjk = is_cjk(nxt_first) if nxt_first else False
                safe = (
                    not last
                    or last in ALL_PUNCT
                    or nxt_raw.startswith(" ")
                    or (last_cjk != nxt_cjk and nxt_first)
                )
                if safe:
                    cut_here = True
                elif dur >= MAX_DUR + 2.5 or chars >= MAX_CHARS + 8:
                    cut_here = True

        if cut_back >= 0:
            chunks.append(buf[: cut_back + 1])
            buf = buf[cut_back + 1:]
        elif cut_here:
            chunks.append(buf)
            buf = []

        i += 1

    if buf:
        if chunks and char_count(buf) < 3:
            chunks[-1].extend(buf)
        else:
            chunks.append(buf)
    return rescue_orphan_tails(chunks)


def chunk_to_entry(buf):
    text = "".join(w["word"] for w in buf).strip()
    return buf[0]["start"], buf[-1]["end"], text


def detect_silence(audio_path: Path, noise_db: int = -35, min_dur: float = 0.25):
    cmd = [
        "ffmpeg", "-i", str(audio_path),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    output = result.stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", output)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", output)]
    pairs = list(zip(starts, ends))
    if len(starts) > len(ends):
        pairs.append((starts[-1], float("inf")))
    return pairs


def apply_silence_gaps(entries, silence_periods):
    if not silence_periods or not entries:
        return entries
    adj = list(entries)
    for i, (start, end, text) in enumerate(adj):
        next_start = adj[i + 1][0] if i + 1 < len(adj) else float("inf")
        for sil_s, sil_e in silence_periods:
            if start < sil_s <= next_start + 0.05:
                new_end = max(sil_s, start + 0.2)
                adj[i] = (start, new_end, text)
                if i + 1 < len(adj) and sil_e < float("inf"):
                    ns, ne, nt = adj[i + 1]
                    adj[i + 1] = (max(ns, sil_e), ne, nt)
                break
    return adj


def write_srt(entries, out: Path) -> None:
    lines = []
    prev_end = 0.0
    for i, (start, end, text) in enumerate(entries, start=1):
        if start < prev_end:
            start = prev_end
        if end <= start:
            end = start + 0.3
        if end - start < 0.3:
            end = start + 0.3
        lines.append(str(i))
        lines.append(f"{ms_tc(start)} --> {ms_tc(end)}")
        lines.append(text)
        lines.append("")
        prev_end = end
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("json_file", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--audio", type=Path, default=None)
    ap.add_argument("--silence-db", type=int, default=-35)
    ap.add_argument("--silence-dur", type=float, default=0.25)
    args = ap.parse_args()

    data = json.loads(args.json_file.read_text(encoding="utf-8"))
    words = data.get("words") or []
    segments = data.get("segments") or []

    if not words:
        if not segments:
            sys.exit("[ERR] JSON 無 words 也無 segments")
        entries = [
            (float(s["start"]), float(s["end"]), s["text"].strip()) for s in segments
        ]
    else:
        chunks = resegment(words, segments)
        entries = [chunk_to_entry(c) for c in chunks]

    all_text_in = "".join(w["word"] for w in words).replace(" ", "")
    all_text_out = "".join(e[2] for e in entries).replace(" ", "")
    if len(all_text_in) != len(all_text_out):
        print(f"[WARN] 字數不一致：輸入 {len(all_text_in)} vs 輸出 {len(all_text_out)}")

    if args.audio:
        if not args.audio.exists():
            print(f"[WARN] 找不到音訊檔 {args.audio}，跳過靜音修正")
        else:
            silences = detect_silence(args.audio, args.silence_db, args.silence_dur)
            print(f"[INFO] 偵測到 {len(silences)} 段靜音")
            entries = apply_silence_gaps(entries, silences)

    write_srt(entries, args.out)
    durs = [e - s for s, e, _ in entries]
    avg = sum(durs) / len(durs) if durs else 0
    max_d = max(durs) if durs else 0
    print(f"[OK] 輸出 {args.out}")
    print(f"     段數：{len(entries)}，平均 {avg:.2f}s/段，最長 {max_d:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
