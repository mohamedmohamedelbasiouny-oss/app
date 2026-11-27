"""المرحلة 8: كتابة نوتات اللحن الأساسي بالترتيب مع التوقيت ودرجة الثقة."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import median_filter

from .notes import NoteName, name_from_index, qt_index_to_cents, cents_to_qt_index

UNCLEAR_THRESHOLD = 0.5


@dataclass
class NoteEvent:
    start: float
    end: float
    cents: float            # متوسط الـ cents (بعد التصحيح)
    index: int              # درجة الربع تون المطلقة
    deviation: float        # الانحراف عن الدرجة بالـ cents
    confidence: float       # 0..1
    name: NoteName

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def clear(self) -> bool:
        return self.confidence >= UNCLEAR_THRESHOLD

    @property
    def pc24(self) -> int:
        return self.index % 24


def _runs(mask: np.ndarray):
    """(بداية، نهاية) لكل مجموعة True متتالية."""
    if mask.size == 0:
        return []
    d = np.diff(np.concatenate([[0], mask.astype(int), [0]]))
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0]
    return list(zip(starts, ends))


def transcribe(times: np.ndarray, cents: np.ndarray, conf: np.ndarray,
               min_dur: float = 0.07, merge_gap: float = 0.05) -> list[NoteEvent]:
    if len(times) < 3:
        return []
    hop = float(times[1] - times[0])
    voiced = np.isfinite(cents)
    c = np.where(voiced, cents, 0.0)
    c_s = median_filter(c, size=5, mode="nearest")
    c_s = np.where(voiced, c_s, np.nan)

    q = np.full(len(c_s), -10_000, dtype=int)
    q[voiced] = np.round((c_s[voiced] + 900.0) / 50.0).astype(int)

    # تقسيم لأجزاء بنفس الدرجة، مع "هسترة" عشان الفيبراتو ما يقطعش النوتة
    segments = []  # (start_idx, end_idx, q)
    i = 0
    n = len(q)
    while i < n:
        if not voiced[i]:
            i += 1
            continue
        cur = q[i]
        center = qt_index_to_cents(cur)
        j = i + 1
        while j < n and voiced[j] and abs(c_s[j] - center) <= 40.0:
            j += 1
        segments.append([i, j, cur])
        i = j

    # دمج الأجزاء القصيرة جدًا (زخارف) مع اللي جنبها
    min_frames = max(1, int(round(min_dur / hop)))
    merged = []
    for seg in segments:
        if merged:
            prev = merged[-1]
            gap = seg[0] - prev[1]
            if seg[2] == prev[2] and gap * hop <= merge_gap:
                prev[1] = seg[1]
                continue
        merged.append(seg)
    segments = [s for s in merged if (s[1] - s[0]) >= min_frames]

    events: list[NoteEvent] = []
    for s, e, _ in segments:
        seg_c = cents[s:e]
        seg_c = seg_c[np.isfinite(seg_c)]
        if seg_c.size == 0:
            continue
        med = float(np.median(seg_c))
        idx = cents_to_qt_index(med)
        dev = med - qt_index_to_cents(idx)
        std = float(np.std(seg_c))
        # درجة الثقة — متظبطة على الغُنا العربي الحقيقي (اتجربت على أغنية حقيقية):
        # الفيبراتو الطبيعي (لحد ~15 سنت) والتلوين الشرقي للدرجات مش أخطاء.
        dur = (e - s) * hop
        per = float(np.mean(conf[s:e]))
        c_conf = float(np.clip((per - 0.35) / 0.35, 0, 1))
        c_stab = float(np.clip(1.0 - max(0.0, std - 15.0) / 50.0, 0.3, 1))
        c_grid = 1.0 - min(abs(dev), 25.0) / 25.0 * 0.35
        c_dur = float(np.clip(dur / 0.12, 0.45, 1.0))
        confidence = float(np.clip(c_conf * c_stab * c_grid * c_dur, 0, 1))
        events.append(NoteEvent(start=float(times[s]), end=float(times[s] + (e - s) * hop),
                                cents=med, index=idx, deviation=dev,
                                confidence=confidence, name=name_from_index(idx)))
    # تذبذب سريع بين درجتين (فيبراتو عنيف جدًا أو تريل): أ-ب-أ بنوتات قصيرة لازقة في بعض
    # → النغمة نفسها مش واضحة، فبنقلل الثقة بدل ما نكتب درجات مش حقيقية
    for i in range(1, len(events) - 1):
        a, b, c = events[i - 1], events[i], events[i + 1]
        if (a.index == c.index != b.index and b.duration < 0.12
                and b.start - a.end < 0.04 and c.start - b.end < 0.04):
            for ev in (a, b, c):
                if ev.duration < 0.15:
                    ev.confidence *= 0.6
    # دمج نوتات متتالية بنفس الاسم بينها فاصل صغير جدًا
    out: list[NoteEvent] = []
    for ev in events:
        if out and out[-1].index == ev.index and ev.start - out[-1].end <= merge_gap:
            p = out[-1]
            tot = p.duration + ev.duration
            p.cents = (p.cents * p.duration + ev.cents * ev.duration) / tot
            p.confidence = (p.confidence * p.duration + ev.confidence * ev.duration) / tot
            p.end = ev.end
            p.deviation = p.cents - qt_index_to_cents(p.index)
            continue
        out.append(ev)
    return out


def pitch_class_histogram(cents: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    """توزيع النوتات على 24 درجة (ربع تون) — مع توزيع ناعم بين الدرجتين الأقرب."""
    finite = np.isfinite(cents)
    c = cents[finite]
    w = np.ones_like(c) if weights is None else np.asarray(weights)[finite]
    h = np.zeros(24)
    if c.size == 0:
        return h
    pos = np.mod((c + 900.0) / 50.0, 24.0)
    lo = np.floor(pos).astype(int) % 24
    frac = pos - np.floor(pos)
    # وزن مثلثي: لو قريب من درجة ياخد معظم الوزن
    wl = np.clip(1.0 - frac, 0, 1) ** 2
    wh = np.clip(frac, 0, 1) ** 2
    norm = wl + wh
    np.add.at(h, lo, w * wl / norm)
    np.add.at(h, (lo + 1) % 24, w * wh / norm)
    s = h.sum()
    return h / s if s > 0 else h
