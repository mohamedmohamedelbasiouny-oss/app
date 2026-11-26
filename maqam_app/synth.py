"""مولّد أصوات تجريبية (للاختبارات والفحص الذاتي): نغمات، ألحان مقامات، وإيقاعات."""
from __future__ import annotations

import numpy as np

from .notes import cents_to_hz, qt_index_to_cents
from .rhythm import IQA_BY_KEY

SR = 22050


def tone(hz: float, dur: float, sr: int = SR, harmonics: int = 6, vibrato: float = 0.0,
         amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(dur * sr)) / sr
    f = hz * (1 + vibrato * np.sin(2 * np.pi * 5.5 * t))
    phase = 2 * np.pi * np.cumsum(f) / sr
    y = sum((0.6 ** k) * np.sin((k + 1) * phase) for k in range(harmonics))
    env = np.minimum(1, np.minimum(t / 0.02, (dur - t) / 0.03).clip(0, 1))
    return (amp * y * env).astype(np.float32)


def note_sequence(indices, dur=0.5, gap=0.05, sr=SR, ref_hz=440.0, vibrato=0.0) -> np.ndarray:
    """تسلسل نوتات (رقم درجة الربع تون المطلق، 0 = دو4)."""
    parts = []
    for idx in indices:
        if idx is None:
            parts.append(np.zeros(int(0.4 * sr), np.float32))
            continue
        hz = float(cents_to_hz(qt_index_to_cents(idx), ref_hz))
        parts.append(tone(hz, dur, sr, vibrato=vibrato))
        parts.append(np.zeros(int(gap * sr), np.float32))
    return np.concatenate(parts)


def maqam_melody(scale, tonic_idx, n_phrases=10, seed=0, sr=SR, ref_hz=440.0):
    """لحن عشوائي على سلم مقام — كل جملة بتقفل على القرار."""
    rng = np.random.default_rng(seed)
    degs = list(scale) + [s + 24 for s in scale]
    seq = []
    pos = 0
    for _ in range(n_phrases):
        for _k in range(7):
            pos = int(np.clip(pos + rng.choice([-1, 1, 1, 2, -2]), 0, 9))
            seq.append(tonic_idx + degs[pos])
        pos = 0 if pos < 5 else 7
        seq.append(tonic_idx + degs[pos])
        seq.append(tonic_idx + degs[pos])
        seq.append(None)
    durs = rng.uniform(0.22, 0.45, len(seq))
    parts = []
    for idx, d in zip(seq, durs):
        if idx is None:
            parts.append(np.zeros(int(0.35 * sr), np.float32))
            continue
        hz = float(cents_to_hz(qt_index_to_cents(idx), ref_hz))
        parts.append(tone(hz, float(d), sr, vibrato=0.002))
    return np.concatenate(parts)


def percussion(iqa_key: str, bpm: float, dur: float, sr: int = SR, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    iqa = IQA_BY_KEY[iqa_key]
    y = np.zeros(int(dur * sr) + sr, np.float32)
    unit = 60.0 / bpm / iqa.units_per_beat

    def dum():
        n = int(0.15 * sr)
        t = np.arange(n) / sr
        return 0.6 * np.sin(2 * np.pi * 70 * t) * np.exp(-t * 25)

    def tak():
        n = int(0.06 * sr)
        x = np.diff(rng.normal(0, 1, n), prepend=0)
        t = np.arange(n) / sr
        return 0.25 * x * np.exp(-t * 60)

    t = 0.2
    while t < dur:
        for i, c in enumerate(iqa.cells):
            s = int((t + i * unit) * sr)
            seg = dum() if c == "D" else tak() if c == "T" else None
            if seg is None or s >= len(y):
                continue
            seg = seg[: len(y) - s]
            y[s:s + len(seg)] += seg.astype(np.float32)
        t += unit * iqa.length
    return y[: int(dur * sr)]
