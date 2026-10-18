#!/usr/bin/env python3
"""make_bgm.py - 程序化生成極輕背景音樂（免版權）

不是要搶戲，是填掉空白、給情緒一點底色。用 numpy 合成，可選不同 mood。
mood: warm（溫暖沉穩）／calm（冷靜极簡）／playful（俏皮輕快）／upbeat（明快有勁）
用法：python make_bgm.py --out bgm.wav --duration 60 --mood playful
"""
import argparse
from pathlib import Path

import numpy as np

SR = 44100

_NOTES = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
          "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}


def note_freq(name: str) -> float:
    pitch = name[:-1]
    octave = int(name[-1])
    semis = _NOTES[pitch] + (octave - 4) * 12
    return 440.0 * (2 ** (semis / 12))


def _pad(freq, n):
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for mult, amp in ((1, 1.0), (2, 0.30), (3, 0.12), (4, 0.06)):
        sig += amp * np.sin(2 * np.pi * freq * mult * t)
    return sig


def _pluck(freq, n, decay=6.0):
    t = np.arange(n) / SR
    env = np.exp(-decay * t)
    sig = (np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(4 * np.pi * freq * t)
           + 0.15 * np.sin(6 * np.pi * freq * t))
    return sig * env


def _bass(freq, n):
    t = np.arange(n) / SR
    env = np.minimum(1.0, t * 30) * np.exp(-1.2 * t)
    return (np.sin(2 * np.pi * freq * t) + 0.2 * np.sin(4 * np.pi * freq * t)) * env * 0.8


def _kick(n):
    t = np.arange(n) / SR
    f = 120 * np.exp(-22 * t) + 45
    env = np.exp(-14 * t)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env


def _hat(n, rng):
    t = np.arange(n) / SR
    env = np.exp(-45 * t)
    return rng.uniform(-1, 1, n) * env * 0.25


def _snare(n, rng):
    t = np.arange(n) / SR
    env = np.exp(-24 * t)
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-30 * t)
    return (rng.uniform(-1, 1, n) * 0.6 + tone) * env


MOODS = {
    "warm":    dict(bpm=72,  prog=[["C4", "E4", "G4", "B4"], ["A3", "C4", "E4", "G4"],
                                   ["F3", "A3", "C4", "E4"], ["G3", "B3", "D4", "G4"]],
                    pad=1.0, arp=0.0, bass=0.0, drums=0.0),
    "calm":    dict(bpm=64,  prog=[["D3", "F3", "A3", "C4"], ["G3", "B3", "D4", "F4"],
                                   ["C4", "E4", "G4", "B4"], ["A3", "C4", "E4", "G4"]],
                    pad=1.0, arp=0.15, bass=0.0, drums=0.0),
    "playful": dict(bpm=104, prog=[["C4", "E4", "G4"], ["A3", "C4", "E4"], ["F3", "A3", "C4"],
                                   ["G3", "B3", "D4"]],
                    pad=0.35, arp=0.65, bass=0.45, drums=0.35),
    "upbeat":  dict(bpm=120, prog=[["C4", "E4", "G4"], ["G3", "B3", "D4"], ["A3", "C4", "E4"],
                                   ["F3", "A3", "C4"]],
                    pad=0.30, arp=0.75, bass=0.55, drums=0.6),
}


def build(duration, mood="warm"):
    cfg = MOODS.get(mood, MOODS["warm"])
    chords = cfg["prog"]
    bpm = cfg["bpm"]
    beat = 60.0 / bpm
    bar = beat * 4
    n = int((duration + 2) * SR)
    rng = np.random.default_rng(7)

    pad = np.zeros(n)
    arp = np.zeros(n)
    bass = np.zeros(n)
    drums = np.zeros(n)

    nbars = int(np.ceil(duration / bar)) + 1
    for b in range(nbars):
        chord = chords[b % len(chords)]
        s0 = int(b * bar * SR)
        if s0 >= n:
            break

        # pad: sustained chord
        seg = np.zeros(int(bar * SR) + SR)
        for nm in chord:
            seg += _pad(note_freq(nm), len(seg))
        seg /= max(1, len(chord))
        a = int(0.9 * SR)
        env = np.ones_like(seg)
        env[:a] = np.linspace(0, 1, a)
        env[-a:] = np.linspace(1, 0, a)
        seg *= env
        e = min(s0 + len(seg), n)
        pad[s0:e] += seg[: e - s0]

        # arpeggio: 8th notes cycling chord tones up and down
        if cfg["arp"] > 0:
            seqhi = [note_freq(x) * 2 for x in chord]
            pattern = seqhi + seqhi[::-1]
            for k in range(8):
                t0 = s0 + int(k * beat / 2 * SR)
                if t0 >= n:
                    break
                ln = min(int(beat * 0.55 * SR), n - t0)
                arp[t0:t0 + ln] += _pluck(pattern[k % len(pattern)], ln) * cfg["arp"]

        # bass: root on beats 1 and 3
        if cfg["bass"] > 0:
            root = note_freq(chord[0]) / 2
            for k, off in enumerate((0, 2)):
                t0 = s0 + int(off * beat * SR)
                if t0 >= n:
                    continue
                ln = min(int(beat * 1.6 * SR), n - t0)
                bass[t0:t0 + ln] += _bass(root, ln) * cfg["bass"]

        # drums
        if cfg["drums"] > 0:
            for k in range(4):
                t0 = s0 + int(k * beat * SR)
                if t0 >= n:
                    continue
                ln = min(int(beat * 0.5 * SR), n - t0)
                if k in (0, 2):
                    drums[t0:t0 + ln] += _kick(ln) * cfg["drums"]
                if k in (1, 3):
                    drums[t0:t0 + ln] += _snare(ln, rng) * cfg["drums"] * 0.7
                # hats on offbeats
                ho = s0 + int((k + 0.5) * beat * SR)
                if ho < n:
                    lh = min(int(beat * 0.2 * SR), n - ho)
                    drums[ho:ho + lh] += _hat(lh, rng) * cfg["drums"]

    mix = pad * cfg["pad"] + arp + bass + drums
    k = 64
    mix = np.convolve(mix, np.ones(k) / k, mode="same")
    mix /= max(1e-6, np.abs(mix).max())
    mix *= 0.45
    return mix[: int(duration * SR)]


def main():
    ap = argparse.ArgumentParser(description="程序化背景音樂生成")
    ap.add_argument("--out", required=True)
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--mood", default="warm", choices=list(MOODS))
    args = ap.parse_args()

    import wave
    sig = build(args.duration, args.mood)
    pcm = (sig * 32767).astype(np.int16)
    with wave.open(str(Path(args.out)), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"bgm -> {args.out} ({args.duration:.0f}s, mood={args.mood})")


if __name__ == "__main__":
    main()
