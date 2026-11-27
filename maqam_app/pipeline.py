"""ربط كل مراحل التحليل ببعض."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import paths
from .audio_io import ANALYSIS_SR, SEPARATION_SR, file_hash, load_audio, make_playback_wav
from .maqam_detect import MaqamResult, detect
from .organ import OrganSettings, organ_settings
from .pitch import PitchTrack, track
from .rhythm import RhythmResult, analyze as analyze_rhythm
from .separation import Stems, save_stems, separate
from .transcribe import NoteEvent, transcribe
from .tuning import TuningInfo, corrected_cents, robust_tuning

ProgressCB = Callable[[float, str], None]


@dataclass
class Settings:
    use_demucs: bool = True
    pitch_engine: str = "auto"          # auto / crepe / pyin
    melody_source: str = "auto"         # auto / vocals / instruments / mix


@dataclass
class AnalysisResult:
    source: Path
    title: str
    duration: float
    playback: dict[str, Path]           # mix / vocals / instruments / drums → WAV
    separation_method: str
    melody_source: str
    pitch: PitchTrack
    cents: np.ndarray                   # بعد تصحيح الضبط
    tuning: TuningInfo
    notes: list[NoteEvent]
    maqam: MaqamResult
    rhythm: RhythmResult
    organ: OrganSettings
    section_organ: list[OrganSettings]
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    source_url: str | None = None
    score: object | None = None          # النوتة الموسيقية (وضع التمرين)


class Cancelled(Exception):
    pass


def _stage(progress: ProgressCB | None, lo: float, hi: float, cancel=None) -> ProgressCB:
    def cb(frac: float, msg: str):
        if cancel is not None and cancel():
            raise Cancelled()
        if progress:
            progress(lo + (hi - lo) * max(0.0, min(1.0, frac)), msg)
    return cb


def _load_cached_stems(key: str) -> Stems | None:
    import soundfile as sf

    d = paths.cache_dir() / f"stems_{key}"
    files = {n: d / f"{n}.wav" for n in ("vocals", "instruments", "drums")}
    meta = d / "method.txt"
    if not all(f.exists() for f in files.values()) or not meta.exists():
        return None
    arrs = {}
    sr = SEPARATION_SR
    for n, f in files.items():
        data, sr = sf.read(str(f), dtype="float32", always_2d=True)
        arrs[n] = data.T
    st = Stems(sr=sr, method=meta.read_text().strip(), **arrs)
    st.files = files
    return st


def analyze_file(path: str | Path, settings: Settings | None = None,
                 progress: ProgressCB | None = None, title: str | None = None,
                 cancel: Callable[[], bool] | None = None,
                 source_url: str | None = None) -> AnalysisResult:
    settings = settings or Settings()
    path = Path(path)
    warnings: list[str] = []
    timings: dict[str, float] = {}
    t0 = time.time()

    p = _stage(progress, 0.0, 0.05, cancel)
    p(0.0, "قراءة ملف الأغنية…")
    audio = load_audio(path, sr=SEPARATION_SR, channels=2)
    play_mix = make_playback_wav(path)
    duration = audio.duration
    timings["load"] = time.time() - t0

    # --- فصل الصوت
    t1 = time.time()
    key = file_hash(path) + ("_d" if settings.use_demucs else "_h")
    stems = _load_cached_stems(key)
    if stems is None or (settings.use_demucs and stems.method != "demucs"):
        stems, warn = separate(audio, settings.use_demucs, _stage(progress, 0.05, 0.5, cancel))
        if warn:
            warnings.append(warn)
        out_dir = paths.cache_dir() / f"stems_{key}"
        save_stems(stems, out_dir)
        (out_dir / "method.txt").write_text(stems.method)
    else:
        _stage(progress, 0.05, 0.5, cancel)(1.0, "فصل الصوت محفوظ من قبل")
    timings["separation"] = time.time() - t1

    # --- مصدر اللحن
    import librosa

    def to_analysis(x):
        mono = x.mean(axis=0) if x.ndim == 2 else x
        return librosa.resample(mono, orig_sr=stems.sr, target_sr=ANALYSIS_SR)

    src_name = settings.melody_source
    if src_name == "mix":
        melody_y = librosa.resample(audio.mono(), orig_sr=audio.sr, target_sr=ANALYSIS_SR)
    elif src_name == "instruments":
        melody_y = to_analysis(stems.instruments)
    elif stems.method != "demucs":
        # الفصل الاحتياطي بيبوّظ صوت المطرب شوية — الجزء اللحني كله أدق للتتبع
        melody_y = to_analysis(stems.vocals + stems.instruments)
        src_name = "harmonic"
    else:
        melody_y = to_analysis(stems.vocals)
        src_name = "vocals"

    t2 = time.time()
    pt = track(melody_y, ANALYSIS_SR, settings.pitch_engine, _stage(progress, 0.5, 0.82, cancel))
    voiced_frac = float(np.mean(pt.voiced)) if len(pt.f0) else 0.0
    if settings.melody_source == "auto" and voiced_frac < 0.12:
        warnings.append("الأغنية تقريبًا من غير غُنا — حللت لحن الآلات بدل صوت المطرب.")
        melody_y = to_analysis(stems.instruments)
        src_name = "instruments"
        pt = track(melody_y, ANALYSIS_SR, settings.pitch_engine,
                   _stage(progress, 0.6, 0.82, cancel))
    timings["pitch"] = time.time() - t2

    # --- الضبط + النوتات + المقامات
    p = _stage(progress, 0.82, 0.9, cancel)
    p(0.0, "اكتشاف ضبط التسجيل (لا = 440؟)…")
    mix_a = librosa.resample(audio.mono(), orig_sr=audio.sr, target_sr=ANALYSIS_SR)
    tuning = robust_tuning(pt, [(melody_y, ANALYSIS_SR), (mix_a, ANALYSIS_SR)])
    cents = corrected_cents(pt, tuning)
    p(0.3, "كتابة النوتات…")
    notes = transcribe(pt.times, cents, pt.confidence)
    p(0.6, "تحديد القرار والمقامات والتحويلات…")
    mres = detect(pt.times, cents, pt.confidence, notes, duration)

    # --- الإيقاع
    p = _stage(progress, 0.9, 0.99, cancel)
    p(0.0, "تحليل الإيقاع…")
    t3 = time.time()
    drums = to_analysis(stems.drums)
    rhythm = analyze_rhythm(drums, ANALYSIS_SR, y_full=mix_a)
    if not rhythm.percussion_found:
        warnings.append("مافيش إيقاع واضح في الأغنية — نتيجة الإيقاع تقريبية.")
    timings["rhythm"] = time.time() - t3

    organ = organ_settings(mres.global_best, tuning, rhythm)
    section_organ = [organ_settings(s.candidate, tuning, rhythm) for s in mres.sections]

    playback = {"mix": play_mix}
    playback.update(stems.files)
    res = AnalysisResult(
        source=path, title=title or path.stem, duration=duration, playback=playback,
        separation_method=stems.method, melody_source=src_name, pitch=pt, cents=cents,
        tuning=tuning, notes=notes, maqam=mres, rhythm=rhythm, organ=organ,
        section_organ=section_organ, warnings=warnings, timings=timings,
        source_url=source_url)

    # --- وضع التمرين: النوتة الموسيقية + البيانو اللي بيعزف اللحن
    _stage(progress, 0.99, 1.0, cancel)(0.0, "كتابة النوتة الموسيقية وصوت البيانو…")
    try:
        from .melody_synth import write_practice_stems
        from .score import build_score

        res.score = build_score(res)
        out_dir = paths.cache_dir() / f"practice_{key}_{len(res.notes)}"
        res.playback.update(write_practice_stems(res.score, res, out_dir))
    except Exception as e:  # وضع التمرين مش لازم يوقّف التحليل كله
        warnings.append(f"مقدرتش أعمل النوتة الموسيقية: {e}")
    timings["total"] = time.time() - t0
    if progress:
        progress(1.0, "خلص التحليل")
    return res


def analyze_url(url: str, settings: Settings | None = None,
                progress: ProgressCB | None = None,
                cancel: Callable[[], bool] | None = None) -> AnalysisResult:
    from .youtube import download_audio

    path, title = download_audio(url, _stage(progress, 0.0, 0.1, cancel))
    inner = _stage(progress, 0.1, 1.0, cancel)
    return analyze_file(path, settings, inner, title=title, cancel=cancel, source_url=url)
