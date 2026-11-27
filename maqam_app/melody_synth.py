"""صوت بيانو بيعزف نوتات اللحن (نفس النوتة المكتوبة) — عشان تسمعها وتعزف معاها.

بيانو بسيط بالـ additive synthesis (هارمونيكس بتخفت مع الوقت + ضربة خفيفة في الأول)،
والربع تون بيتعزف بالظبط (مش أقرب مفتاح).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .notes import cents_to_hz, qt_index_to_cents

SR = 44100


def _piano_note(hz: float, dur: float, vel: float = 0.8) -> np.ndarray:
    tail = 0.35
    n = int((dur + tail) * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    B = 0.0004   # inharmonicity خفيفة زي البيانو
    for k in range(1, 9):
        f = hz * k * np.sqrt(1 + B * k * k)
        if f > SR / 2 - 500:
            break
        decay = 1.6 + 0.9 * k
        y += (0.55 ** (k - 1)) * np.sin(2 * np.pi * f * t) * np.exp(-t * decay)
    attack = np.minimum(1.0, t / 0.004)
    release = np.where(t > dur, np.exp(-(t - dur) / 0.08), 1.0)
    hammer = np.exp(-t * 60) * 0.15 * np.sin(2 * np.pi * hz * 7.1 * t)
    return (vel * (y + hammer) * attack * release).astype(np.float32)


def render_melody(score_notes, duration: float, ref_hz: float = 440.0) -> np.ndarray:
    """mono float32 بطول الأغنية — الضبط على نفس ضبط التسجيل عشان يركب على الأغنية."""
    out = np.zeros(int((duration + 1.0) * SR), np.float32)
    for n in score_notes:
        if n.index is None:
            continue
        hz = float(cents_to_hz(qt_index_to_cents(n.index), ref_hz))
        seg = _piano_note(hz, max(0.08, n.end - n.start))
        s = int(max(0.0, n.start) * SR)
        e = min(len(out), s + len(seg))
        if e > s:
            out[s:e] += seg[: e - s]
    peak = float(np.max(np.abs(out))) or 1.0
    return (out / peak * 0.6)[: int(duration * SR)]


def write_practice_stems(score, res, out_dir: Path) -> dict[str, Path]:
    """بيانو لوحده + بيانو مع الموسيقى من غير المطرب."""
    import librosa
    import soundfile as sf

    out_dir.mkdir(parents=True, exist_ok=True)
    piano = render_melody(score.notes, res.duration, res.tuning.reference_hz)
    files = {}
    p1 = out_dir / "piano.wav"
    sf.write(str(p1), np.stack([piano, piano], 1), SR, subtype="PCM_16")
    files["piano"] = p1
    band = None
    for key in ("instruments", "drums"):
        f = res.playback.get(key)
        if f and Path(f).exists():
            y, sr = sf.read(str(f), dtype="float32", always_2d=True)
            y = y.mean(axis=1)
            if sr != SR:
                y = librosa.resample(y, orig_sr=sr, target_sr=SR)
            band = y if band is None else band[: len(y)] + y[: len(band)]
    if band is not None:
        L = min(len(band), len(piano))
        b = band[:L]
        b = b / (np.max(np.abs(b)) or 1.0) * 0.45
        mix = b + piano[:L] * 1.1
        mix = mix / max(1.0, float(np.max(np.abs(mix))))
        p2 = out_dir / "piano_band.wav"
        sf.write(str(p2), np.stack([mix, mix], 1), SR, subtype="PCM_16")
        files["piano_band"] = p2
    # البيانو فوق الأغنية كاملة (بالمطرب والموسيقى والإيقاع)
    f = res.playback.get("mix")
    if f and Path(f).exists():
        y, sr = sf.read(str(f), dtype="float32", always_2d=True)
        y = y.mean(axis=1)
        if sr != SR:
            y = librosa.resample(y, orig_sr=sr, target_sr=SR)
        L = min(len(y), len(piano))
        song = y[:L] / (np.max(np.abs(y[:L])) or 1.0) * 0.55
        mix = song + piano[:L] * 0.9
        mix = mix / max(1.0, float(np.max(np.abs(mix))))
        p3 = out_dir / "piano_song.wav"
        sf.write(str(p3), np.stack([mix, mix], 1), SR, subtype="PCM_16")
        files["piano_song"] = p3
    return files
