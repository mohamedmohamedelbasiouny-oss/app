"""المرحلة 4: دقة الربع تون + اكتشاف ضبط التسجيل.

الأغنية ممكن تكون متسجلة أعلى أو أوطى شوية من لا = 440 هرتز.
بنحسب الانحراف الغالب لكل النوتات الثابتة عن شبكة النص تون (الأغلبية الساحقة
من نوتات أي مقام بتقع على النص تون)، وبنصحح كل الترددات قبل التسمية.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter1d

from .notes import A4_HZ, hz_to_cents
from .pitch import PitchTrack


@dataclass
class TuningInfo:
    offset_cents: float     # كم cent الأغنية أعلى (+) أو أوطى (-) من 440
    reference_hz: float     # تردد لا المرجعي الفعلي للتسجيل
    reliability: float      # 0..1

    def describe(self) -> str:
        if abs(self.offset_cents) < 3:
            return f"التسجيل مضبوط على لا = 440 هرتز تقريبًا ({self.reference_hz:.1f} هرتز)"
        direction = "أعلى" if self.offset_cents > 0 else "أوطى"
        return (f"التسجيل {direction} من 440 بـ {abs(self.offset_cents):.0f} سنت "
                f"(لا = {self.reference_hz:.1f} هرتز) — اتصحح قبل تسمية النوتات")


def stable_mask(cents: np.ndarray, max_slope: float = 6.0) -> np.ndarray:
    """الفريمات اللي النغمة فيها ثابتة (مش انزلاق أو فيبراتو قوي)."""
    finite = np.isfinite(cents)
    d = np.abs(np.gradient(np.where(finite, cents, 0.0)))
    return finite & (d < max_slope)


def estimate_tuning(track: PitchTrack, conf_thr: float = 0.5) -> TuningInfo:
    cents = hz_to_cents(track.f0)
    mask = stable_mask(cents) & (track.confidence >= conf_thr)
    vals = cents[mask]
    if vals.size < 50:
        return TuningInfo(0.0, A4_HZ, 0.0)
    # هيستوجرام دائري للانحراف عن النص تون بدقة 1 cent
    dev = np.mod(vals + 50.0, 100.0)          # 0..100 حيث 50 = على الشبكة بالظبط
    hist, _ = np.histogram(dev, bins=100, range=(0, 100))
    hist = gaussian_filter1d(hist.astype(float), sigma=6, mode="wrap")
    peak = int(np.argmax(hist))
    # تحسين القمة بمتوسط دائري حواليها
    window = np.arange(peak - 15, peak + 16)
    w = hist[np.mod(window, 100)]
    ang = (window / 100.0) * 2 * np.pi
    mean_ang = np.arctan2((w * np.sin(ang)).sum(), (w * np.cos(ang)).sum())
    peak_pos = (mean_ang / (2 * np.pi) * 100.0) % 100.0
    offset = float(peak_pos - 50.0)
    reliability = float(np.clip((hist.max() - np.median(hist)) / (hist.max() + 1e-9), 0, 1))
    return TuningInfo(offset_cents=offset, reference_hz=float(A4_HZ * 2 ** (offset / 1200)),
                      reliability=reliability)


def spectral_offset(y: np.ndarray, sr: int) -> float | None:
    """تقدير الضبط من الطيف مباشرة (librosa) — مستقل عن متتبع اللحن."""
    try:
        import librosa

        if y.size < sr:
            return None
        return float(100.0 * librosa.estimate_tuning(y=y, sr=sr, resolution=0.01))
    except Exception:
        return None


def robust_tuning(track: PitchTrack, extra_signals: list[tuple[np.ndarray, int]]) -> TuningInfo:
    """وسيط (median) لأكتر من تقدير: من اللحن نفسه + من طيف صوت المطرب + من طيف الأغنية كلها.
    كده لو تقدير واحد اتلخبط (مثلاً بسبب فصل الصوت) التاني بيصححه."""
    base = estimate_tuning(track)
    ests = [base.offset_cents] if base.reliability > 0 else []
    for y, sr in extra_signals:
        o = spectral_offset(y, sr)
        if o is not None and np.isfinite(o):
            ests.append(o)
    if not ests:
        return base
    # الاختلافات حوالين ±50 دائرية — بنقرّبهم لنفس الفرع قبل الوسيط
    ref = ests[0]
    adj = [((e - ref + 50) % 100) - 50 + ref for e in ests]
    off = float(np.median(adj))
    off = ((off + 50) % 100) - 50
    return TuningInfo(offset_cents=off, reference_hz=float(A4_HZ * 2 ** (off / 1200)),
                      reliability=base.reliability)


def corrected_cents(track: PitchTrack, tuning: TuningInfo) -> np.ndarray:
    """الـ cents بعد التصحيح (نسبة لـ A4 = 440 مثالي)."""
    return hz_to_cents(track.f0) - tuning.offset_cents
