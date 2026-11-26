"""اختبار متكامل: أغنية تجريبية (بياتي + مقسوم، متسجلة على لا=446) من أول الملف لحد PDF و MIDI."""
import subprocess

import mido
import numpy as np
import pytest
import soundfile as sf

from maqam_app import paths
from maqam_app.maqam_db import MAQAM_BY_KEY
from maqam_app.organ import scale_tuning
from maqam_app.maqam_detect import MaqamCandidate
from maqam_app.pipeline import Settings, analyze_file
from maqam_app.youtube import is_url, is_youtube, normalize_url
from synth import SR, maqam_melody, percussion


@pytest.fixture(scope="module")
def song(tmp_path_factory):
    d = tmp_path_factory.mktemp("song")
    mel = maqam_melody(MAQAM_BY_KEY["bayati"].scale, 4, n_phrases=9, ref_hz=446.0)
    y = mel + percussion("maqsum", 100, len(mel) / SR)[: len(mel)]
    wav = d / "bayati.wav"
    sf.write(wav, y, SR)
    mp3 = d / "bayati.mp3"
    ff = paths.ffmpeg_exe()
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(wav), str(mp3)], check=True)
    return mp3


@pytest.fixture(scope="module")
def result(song):
    return analyze_file(song, Settings(use_demucs=False, pitch_engine="crepe-tiny"))


def test_pipeline_maqam(result):
    b = result.maqam.global_best
    assert b.maqam.key == "bayati"
    assert b.tonic == 4
    assert "دوكاه" in b.tonic_text


def test_pipeline_tuning(result):
    assert abs(result.tuning.offset_cents - 1200 * np.log2(446 / 440)) < 8
    assert abs(result.organ.master_tune_hz - 446) < 2.5


def test_pipeline_rhythm(result):
    assert result.rhythm.iqa.key == "maqsum"
    assert abs(result.rhythm.bpm - 100) < 4


def test_pipeline_organ(result):
    # بياتي على ري: مي نص بيمول → مي -50، وسي بيمول يفضل عادي.
    # (مفتاح سي بيتظبط -50 كمان عشان الأوج اللي ساعات بيظهر في البياتي)
    assert result.organ.offsets[4] == -50
    assert result.organ.offsets[10] == 0
    assert set(o for o in result.organ.offsets if o) == {-50}


def test_pipeline_notes(result):
    assert len(result.notes) > 40
    clear = [n for n in result.notes if n.clear]
    assert len(clear) / len(result.notes) > 0.8
    allowed = {4, 7, 10, 14, 18, 20, 0}
    assert all(n.pc24 in allowed for n in clear)


def test_midi_export(result, tmp_path):
    from maqam_app.midi_export import export_midi
    p = export_midi(result.notes, tmp_path / "m.mid", bpm=result.rhythm.bpm)
    mid = mido.MidiFile(p)
    ons = [m for m in mid.tracks[0] if m.type == "note_on"]
    bends = [m for m in mid.tracks[0] if m.type == "pitchwheel" and m.pitch != 0]
    assert len(ons) == len(result.notes)
    assert bends and all(abs(b.pitch + 2048) < 5 for b in bends)   # -50 cent بالظبط


def test_pdf_report(result, tmp_path):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from maqam_app.report import export_pdf
    p = export_pdf(result, tmp_path / "r.pdf")
    data = p.read_bytes()
    assert data.startswith(b"%PDF") and len(data) > 20_000


def test_scale_tuning_rules():
    rast = MaqamCandidate(MAQAM_BY_KEY["rast"], 0, 0, 0)
    off, _ = scale_tuning(rast)
    assert off[4] == -50 and off[11] == -50 and off[10] == 0   # مي -50، سي -50، سي بيمول عادي
    saba = MaqamCandidate(MAQAM_BY_KEY["saba"], 4, 0, 0)
    off, _ = scale_tuning(saba)
    assert off[4] == -50 and sum(1 for o in off if o) == 1
    sikah = MaqamCandidate(MAQAM_BY_KEY["sikah"], 7, 0, 0)
    off, _ = scale_tuning(sikah)
    assert off[4] == -50 and off[11] == -50


def test_url_helpers():
    assert is_url("https://www.youtube.com/watch?v=abc")
    assert is_youtube("https://youtu.be/abc")
    assert is_youtube("https://music.youtube.com/watch?v=x")
    assert normalize_url("youtu.be/abc") == "https://youtu.be/abc"
    assert not is_url("hello")
