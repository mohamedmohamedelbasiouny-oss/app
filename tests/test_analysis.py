"""اختبارات المراحل: الأصوات المولّدة لازم تتسمى صح، والضبط والمقام والإيقاع يتعرفوا."""
import subprocess

import numpy as np
import pytest
import soundfile as sf

from maqam_app.audio_io import load_audio, AUDIO_EXTENSIONS
from maqam_app.maqam_db import MAQAMAT
from maqam_app.maqam_detect import detect
from maqam_app.notes import qt_index_to_cents
from maqam_app.pitch import crepe_available, track_crepe, track_pyin
from maqam_app.rhythm import IQAAT, analyze as analyze_rhythm
from maqam_app.transcribe import transcribe
from maqam_app.tuning import corrected_cents, estimate_tuning
from synth import SR, maqam_melody, note_sequence, percussion
from maqam_app import paths

# دو ري مي فا صول لا سي + سيكا + أوج (سي نص بيمول) + عراق
KNOWN = [0, 4, 8, 10, 14, 18, 22, 7, 21, -3]
KNOWN_SOLFEGE = ["دو", "ري", "مي", "فا", "صول", "لا", "سي", "مي نص بيمول", "سي نص بيمول",
                 "سي نص بيمول"]

ENGINES = ["pyin"] + (["crepe-tiny", "crepe-full"] if crepe_available() else [])


def _track(engine, y):
    if engine == "pyin":
        return track_pyin(y, SR)
    return track_crepe(y, SR, model="tiny" if engine == "crepe-tiny" else "full",
                       hop_s=0.01 if engine == "crepe-tiny" else 0.02)


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("ref_hz", [440.0, 446.0, 434.0])
def test_known_tones_named_100_percent(engine, ref_hz):
    y = note_sequence(KNOWN, dur=0.6, ref_hz=ref_hz)
    pt = _track(engine, y)
    tu = estimate_tuning(pt)
    expected_offset = 1200 * np.log2(ref_hz / 440.0)
    assert abs(tu.offset_cents - expected_offset) < 8, tu
    notes = transcribe(pt.times, corrected_cents(pt, tu), pt.confidence)
    assert [n.index for n in notes] == KNOWN
    assert [n.name.solfege for n in notes] == KNOWN_SOLFEGE
    assert all(n.clear for n in notes)


def test_unclear_note_is_marked():
    # نوتة بفيبراتو عنيف جدًا لازم تتعلّم "غير واضحة" بدل التخمين
    from synth import tone
    y = np.concatenate([tone(293.66, 0.6), np.zeros(2000, np.float32),
                        tone(330.0, 0.6, vibrato=0.06)])
    pt = track_pyin(y, SR)
    notes = transcribe(pt.times, corrected_cents(pt, estimate_tuning(pt)), pt.confidence)
    assert notes[0].clear
    assert any(not n.clear for n in notes[1:])


@pytest.mark.parametrize("maqam", MAQAMAT, ids=lambda m: m.key)
def test_maqam_detection_from_melody(maqam):
    rng = np.random.default_rng(abs(hash(maqam.key)) % 1000)
    # منحنى cents مباشر (من غير tracker) عشان نختبر منطق المقامات نفسه
    hop = 0.01
    degs = list(maqam.scale) + [s + 24 for s in maqam.scale]
    c, pos = [], 0
    for i in range(110):
        if i % 8 == 7:
            pos = 0 if pos < 5 else 7
        else:
            step = rng.choice([-1, 1, 1, 2, -2]) if pos < 7 else -rng.integers(1, 3)
            pos = int(np.clip(pos + step, 0, 9))
        q = maqam.default_tonic + degs[pos]
        k = int((0.8 if i % 8 == 7 else rng.uniform(0.15, 0.5)) / hop)
        c += list(qt_index_to_cents(q) + rng.normal(0, 6, k))
        if i % 8 == 7:
            c += [np.nan] * 30
    c = np.array(c)
    t = np.arange(len(c)) * hop
    conf = np.where(np.isfinite(c), 0.9, 0.0)
    notes = transcribe(t, c, conf)
    r = detect(t, c, conf, notes, float(t[-1]))
    assert r.global_best.maqam.key == maqam.key
    assert r.global_best.tonic == maqam.default_tonic


def test_modulation_detected():
    from maqam_app.maqam_db import MAQAM_BY_KEY
    a = maqam_melody(MAQAM_BY_KEY["rast"].scale, 0, n_phrases=7, seed=1)
    b = maqam_melody(MAQAM_BY_KEY["hijaz"].scale, 4, n_phrases=7, seed=2)
    y = np.concatenate([a, b])
    pt = track_pyin(y, SR)
    cc = corrected_cents(pt, estimate_tuning(pt))
    notes = transcribe(pt.times, cc, pt.confidence)
    r = detect(pt.times, cc, pt.confidence, notes, len(y) / SR)
    keys = [s.candidate.maqam.key for s in r.sections]
    assert keys[0] == "rast" and keys[-1] == "hijaz", keys
    boundary = r.sections[-1].start
    assert abs(boundary - len(a) / SR) < 8


@pytest.mark.parametrize("iqa", IQAAT, ids=lambda i: i.key)
@pytest.mark.parametrize("bpm", [85, 120])
def test_rhythm_detection(iqa, bpm):
    y = percussion(iqa.key, bpm, 40)
    r = analyze_rhythm(y, SR)
    assert r.iqa.key == iqa.key
    assert abs(r.bpm - bpm) / bpm < 0.04


@pytest.mark.parametrize("ext", ["mp3", "wav", "flac", "ogg", "m4a", "opus", "aiff", "wma",
                                 "aac", "mp4", "webm"])
def test_load_many_formats(tmp_path, ext):
    ffmpeg = paths.ffmpeg_exe()
    if not ffmpeg:
        pytest.skip("ffmpeg غير متاح")
    assert ext in AUDIO_EXTENSIONS
    y = note_sequence([0, 4, 8], dur=0.5)
    wav = tmp_path / "src.wav"
    sf.write(wav, y, SR)
    out = tmp_path / f"song.{ext}"
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(wav)]
    if ext in ("mp4", "webm"):
        cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
               "color=c=black:s=64x64:d=1.7", "-i", str(wav), "-shortest"]
    p = subprocess.run(cmd + [str(out)], capture_output=True)
    if p.returncode != 0:
        pytest.skip(f"ffmpeg هنا مش بيعرف يكتب {ext}")
    a = load_audio(out)
    assert a.sr == 22050
    assert 1.3 < a.duration < 2.2
    assert np.max(np.abs(a.y)) > 0.05
