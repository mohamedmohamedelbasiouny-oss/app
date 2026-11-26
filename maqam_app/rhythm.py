"""المرحلة 9: الإيقاع — السرعة (BPM)، الميزان، واسم الإيقاع الشرقي + الدم والتك.

من مسار الإيقاع (الطبلة والرق) بنطلع غلافين للضربات:
- دم (Dum): طاقة الترددات الواطية (أقل من 250 هرتز)
- تك (Tak): طاقة الترددات العالية (أعلى من 1.5 كيلو)
بعدين بنقسم الزمن لشبكة (حسب البيت المكتشف) ونطوي الشبكة على طول دورة كل
إيقاع، ونقارن شكل الدم والتك بقوالب الإيقاعات الشرقية.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Iqa:
    key: str
    name_ar: str
    name_en: str
    meter: str
    pattern: str            # D = دم، T = تك، - = سكتة
    units_per_beat: int     # 2 = كل خانة ثُمن، 4 = كل خانة 1/16
    organ_style: str        # اقتراح Style على الأورج
    bpm_range: tuple[int, int] = (55, 190)   # السرعات المعتادة للإيقاع ده

    @property
    def cells(self) -> list[str]:
        return self.pattern.split()

    @property
    def length(self) -> int:
        return len(self.cells)


IQAAT: list[Iqa] = [
    Iqa("maqsum", "مقسوم", "Maqsum", "4/4", "D T - T D - T -", 2,
        "Style شرقي (Maqsum) لو عندك Style Pack شرقي، أو أقرب مدمج: 8Beat / Pop 4/4", bpm_range=(60, 160)),
    Iqa("baladi", "بلدي", "Baladi", "4/4", "D D - T D - T -", 2,
        "Style بلدي/شعبي شرقي، أو 8Beat Pop مع تقليل الـ Variation", bpm_range=(60, 150)),
    Iqa("saidi", "صعيدي", "Saidi", "4/4", "D T - D D - T -", 2,
        "Style صعيدي من Style Pack شرقي، أو 8Beat مع Fill كتير", bpm_range=(70, 170)),
    Iqa("wahda", "وحدة", "Wahda", "4/4", "D - - - T - - -", 2,
        "Style Ballad / Slow 4/4 (هادي)", bpm_range=(45, 125)),
    Iqa("malfuf", "ملفوف", "Malfuf", "2/4", "D - - T - - T -", 4,
        "Style 2/4 سريع (Polka / Dance 2/4) أو ملفوف من Style Pack شرقي", bpm_range=(80, 210)),
    Iqa("ayyub", "أيوب", "Ayyub", "2/4", "D - T D T - - -", 4,
        "Style أيوب/زار من Style Pack شرقي، أو 2/4 Dance", bpm_range=(70, 210)),
    Iqa("fallahi", "فلاحي", "Fallahi", "2/4", "D - T T D - T -", 4,
        "Style فلاحي/شعبي سريع، أو 2/4 Polka", bpm_range=(85, 210)),
    Iqa("samai_thaqil", "سماعي ثقيل", "Samai Thaqil", "10/8", "D - - - T - D D T -", 2,
        "مافيش Style مدمج 10/8 — استخدم Style Pack شرقي أو اعزف من غير Style", bpm_range=(40, 140)),
    Iqa("dawr_hindi", "دور هندي", "Dawr Hindi", "7/8", "D - T D - T -", 2,
        "مافيش Style مدمج 7/8 — استخدم Style Pack شرقي أو Drum بس", bpm_range=(55, 190)),
    Iqa("aqsaq", "أقساق", "Aqsaq", "9/8", "D - T - D - T - T", 2,
        "Style 9/8 تركي/شرقي من Style Pack", bpm_range=(55, 190)),
    Iqa("jurjina", "جورجينا", "Jurjina", "10/16", "D - - T - D - T - -", 4,
        "Style 10/16 من Style Pack شرقي", bpm_range=(60, 210)),
]
IQA_BY_KEY = {i.key: i for i in IQAAT}


@dataclass
class RhythmResult:
    bpm: float
    iqa: Iqa
    confidence: float
    meter: str
    beat_times: np.ndarray
    dum_profile: list[float]        # شدة الدم المكتشفة في كل خانة من الدورة
    tak_profile: list[float]
    cycle_start: float              # بداية أول دورة (ثواني)
    alternatives: list[tuple[str, float]] = field(default_factory=list)
    percussion_found: bool = True

    def organ_tempo(self) -> int:
        return int(round(self.bpm))


def _band_envelope(y, sr, hop, fmin, fmax):
    import librosa

    S = librosa.feature.melspectrogram(y=y, sr=sr, hop_length=hop, n_fft=2048, n_mels=64,
                                       fmin=20, fmax=min(sr / 2, 11000))
    freqs = librosa.mel_frequencies(n_mels=64, fmin=20, fmax=min(sr / 2, 11000))
    band = (freqs >= fmin) & (freqs <= fmax)
    S_db = librosa.power_to_db(S[band], ref=np.max)
    env = librosa.onset.onset_strength(S=S_db, sr=sr, hop_length=hop)
    return env


def _norm_env(env):
    from scipy.ndimage import maximum_filter1d

    env = np.maximum(env, 0)
    ref = np.percentile(env, 98) if env.size else 1.0
    env = np.clip(env / (ref + 1e-9), 0, 1.5)
    return maximum_filter1d(env, size=3)


SUBDIV = 2  # بنفحص كمان نص كل خانة عشان الضربات اللي بين الخانات تتحسب غلط


def _template_cells(iqa: Iqa):
    L = iqa.length * SUBDIV
    dum = np.zeros(L)
    tak = np.zeros(L)
    for i, c in enumerate(iqa.cells):
        if c == "D":
            dum[i * SUBDIV] = 1.0
            tak[i * SUBDIV] = 0.3
        elif c == "T":
            tak[i * SUBDIV] = 1.0
    return dum, tak


def _corr(a, b):
    a = a - a.mean()
    b = b - b.mean()
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return float(a @ b / (na * nb))


def _corr_rows(A, b):
    """ارتباط كل صف في A مع المتجه b."""
    A = A - A.mean(axis=1, keepdims=True)
    b = b - b.mean()
    na = np.linalg.norm(A, axis=1)
    nb = np.linalg.norm(b)
    return (A @ b) / (na * nb + 1e-9)


def _periodicity_candidates(env, fps, n_peaks=6):
    """أقوى الدورات الزمنية في الغلاف (autocorrelation)."""
    import librosa

    x = env - env.mean()
    ac = librosa.autocorrelate(x, max_size=int(2.5 * fps))
    ac[: int(0.08 * fps)] = 0
    peaks = []
    for i in range(1, len(ac) - 1):
        if ac[i] > ac[i - 1] and ac[i] >= ac[i + 1] and ac[i] > 0:
            peaks.append((ac[i], i / fps))
    peaks.sort(reverse=True)
    return [p for _, p in peaks[:n_peaks]]


def _fold_scores(low, high, fps, cell_s, iqa, t0_frames, n_frames):
    """أحسن مطابقة (على كل الأطوار) لإيقاع معين بطول خانة معين داخل نافذة."""
    L = iqa.length
    cycle = cell_s * L * fps
    # لازم 4 دورات على الأقل، وإلا الطيّ بيطابق أي حاجة بالصدفة
    n_frames = max(n_frames, int(cycle * 5) + 2)
    n_frames = min(n_frames, len(low) - t0_frames)
    n_cyc = int((n_frames - cycle) // cycle)
    if n_cyc < 4:
        return -1.0, 0, None, None
    from scipy.ndimage import maximum_filter1d

    # كل نقطة عينة بتغطي المسافة لحد اللي بعدها — كده أي ضربة في الدورة لازم تتحسب
    width = max(1, int(round(cell_s * fps / SUBDIV)))
    low = maximum_filter1d(low, width)
    high = maximum_filter1d(high, width)
    phases = np.arange(0, int(cycle), 2)
    cells = np.arange(L * SUBDIV) * cell_s * fps / SUBDIV
    cyc = np.arange(n_cyc) * cycle
    idx = (t0_frames + phases[:, None, None] + cyc[None, :, None] + cells[None, None, :])
    idx = np.clip(np.round(idx).astype(int), 0, len(low) - 1)
    Lp = low[idx].mean(axis=1)      # (phases, L)
    Hp = high[idx].mean(axis=1)
    dum_t, tak_t = _template_cells(iqa)
    sc = 0.6 * _corr_rows(Lp, dum_t) + 0.4 * _corr_rows(Hp, tak_t)
    k = int(np.argmax(sc))
    return float(sc[k]), int(phases[k]) + t0_frames, Lp[k], Hp[k]


def analyze(y: np.ndarray, sr: int, y_full: np.ndarray | None = None) -> RhythmResult:
    import librosa

    hop = 256
    fps = sr / hop
    if y.ndim == 2:
        y = y.mean(axis=0)
    energy = float(np.sqrt(np.mean(y ** 2))) if y.size else 0.0
    perc_found = energy > 1e-3
    src = y
    if not perc_found and y_full is not None:
        src = y_full.mean(axis=0) if y_full.ndim == 2 else y_full

    low = _band_envelope(src, sr, hop, 20, 250)
    high = _band_envelope(src, sr, hop, 1500, 11000)
    n = min(len(low), len(high))
    low, high = _norm_env(low[:n]), _norm_env(high[:n])
    comb = low + high

    tempo = float(np.atleast_1d(librosa.feature.tempo(onset_envelope=comb, sr=sr,
                                                       hop_length=hop))[0])
    beat_times = librosa.frames_to_time(
        librosa.beat.beat_track(onset_envelope=comb, sr=sr, hop_length=hop, units="frames")[1],
        sr=sr, hop_length=hop)

    # الفترات المرشحة لطول "الخانة" (ثُمن أو 1/16)
    periods = _periodicity_candidates(comb, fps)
    if tempo > 0:
        periods.append(60.0 / tempo)
    cell_cands = set()
    for p in periods:
        for k in (1, 2, 3, 4, 6, 8):
            c = p / k
            if 0.06 <= c <= 0.75:
                cell_cands.add(round(c, 4))
    if not cell_cands or n < fps * 6:
        iqa = IQA_BY_KEY["maqsum"]
        return RhythmResult(bpm=tempo, iqa=iqa, confidence=0.0, meter=iqa.meter,
                            beat_times=beat_times, dum_profile=[0.0] * iqa.length,
                            tak_profile=[0.0] * iqa.length, cycle_start=0.0,
                            percussion_found=False)

    # نوافذ 16 ثانية من جسم الأغنية (عشان التمبو الحي اللي بيتغير شوية)
    win = int(16 * fps)
    start = int(min(n * 0.1, max(0, n - win)))
    stop = min(n, start + int(120 * fps))
    windows = list(range(start, max(start + 1, stop - win + 1), int(8 * fps)))[:10]
    win_len = min(win, n - start)

    def evaluate(iqa, cell_s):
        tot, best = 0.0, None
        for w0 in windows:
            sc, ph, Lp, Hp = _fold_scores(low, high, fps, cell_s, iqa, w0, min(win_len, n - w0))
            tot += sc
            if best is None or sc > best[0]:
                best = (sc, ph, Lp, Hp)
        return tot / len(windows), best

    results = []
    for iqa in IQAAT:
        for c in sorted(cell_cands):
            bpm = 60.0 / (c * iqa.units_per_beat)
            if not (40 <= bpm <= 240):
                continue
            coarse, _ = evaluate(iqa, c)
            results.append([coarse, iqa, c])
    results.sort(key=lambda r: r[0], reverse=True)

    # تحسين دقيق حوالين أحسن المرشحين (±3%)
    refined = []
    for coarse, iqa, c in results[:12]:
        best = None
        for f in np.linspace(0.97, 1.03, 13):
            sc, b = evaluate(iqa, c * f)
            if best is None or sc > best[0]:
                best = (sc, c * f, b)
        sc, cell, b = best
        bpm = 60.0 / (cell * iqa.units_per_beat)
        lo, hi = iqa.bpm_range
        plaus = 0.0 if lo <= bpm <= hi else -0.08
        common = {"maqsum": 0.03, "baladi": 0.02, "malfuf": 0.02, "saidi": 0.01,
                  "wahda": -0.03}.get(iqa.key, -0.01)
        refined.append((sc + plaus + common, iqa, bpm, b))
    refined.sort(key=lambda r: r[0], reverse=True)

    score, iqa, bpm, (sc, phase, Lp, Hp) = refined[0]
    alts, seen = [], {iqa.key}
    for r in refined[1:]:
        if r[1].key not in seen:
            seen.add(r[1].key)
            alts.append((r[1].name_ar, float(r[0])))
        if len(alts) >= 3:
            break
    second = next((r[0] for r in refined[1:] if r[1].key != iqa.key), 0.0)
    conf = float(np.clip(0.6 * max(score, 0) + 3.0 * (score - second), 0, 1))
    if not perc_found:
        conf *= 0.5
    Lp, Hp = Lp[::SUBDIV], Hp[::SUBDIV]
    mx = max(float(np.max(Lp)), float(np.max(Hp)), 1e-9)
    return RhythmResult(bpm=float(bpm), iqa=iqa, confidence=conf, meter=iqa.meter,
                        beat_times=beat_times,
                        dum_profile=[float(v) / mx for v in Lp],
                        tak_profile=[float(v) / mx for v in Hp],
                        cycle_start=float(phase / fps), alternatives=alts,
                        percussion_found=perc_found)
