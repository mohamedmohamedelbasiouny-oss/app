"""وضع التمرين: النوتة الموسيقية + صوت البيانو."""
import numpy as np
import pytest

from maqam_app.notes import name_from_index
from maqam_app.score import _key_signature, build_mei, flatten_svg, quantize, render_svg
from maqam_app.transcribe import NoteEvent


def _ev(start, end, idx, conf=0.9):
    return NoteEvent(start=start, end=end, cents=0.0, index=idx, deviation=0.0,
                     confidence=conf, name=name_from_index(idx))


def test_quantize_grid_and_unclear_dropped():
    bpm = 120          # 1/16 = 0.125 ث
    notes = [_ev(0.0, 0.5, 4), _ev(0.51, 0.74, 7), _ev(0.76, 1.0, 10, conf=0.2), _ev(1.0, 1.24, 14)]
    ev, unit = quantize(notes, bpm)
    assert unit == pytest.approx(0.125)
    assert ev == [(0, 4, 4), (4, 2, 7), (8, 2, 14)]   # النوتة غير الواضحة اتشالت


def test_key_signatures():
    assert _key_signature([4, 6, 12, 14, 18, 20, 0])[0] == "2f"     # حجاز على ري: سي ومي بيمول
    assert _key_signature([0, 4, 7, 10, 14, 18, 21])[0] == "0"      # راست: ربع تون بس
    assert _key_signature([4, 7, 10, 14, 18, 20, 0])[0] == "1f"     # بياتي: سي بيمول


def test_mei_quarter_tones_ties_and_render():
    # سيكا (مي نص بيمول) + نوتة طويلة بتعدي خط المازورة
    events = [(0, 4, 7), (4, 4, 4), (12, 8, 21)]
    mei, ids = build_mei(events, "4/4", "0", {}, 90, "تجربة")
    assert 'accid="1qf"' in mei
    assert 'tie="i"' in mei and 'tie="t"' in mei
    assert len(ids[2]) == 2                    # النوتة المربوطة = عنصرين
    pages = render_svg(mei)
    assert pages and all(f'id="{i}"' in "".join(pages) for v in ids.values() for i in v)
    flat = flatten_svg(pages[0])
    assert flat.count("<svg") == 1


def test_pipeline_builds_score_and_piano(tmp_path):
    import soundfile as sf
    from maqam_app.maqam_db import MAQAM_BY_KEY
    from maqam_app.pipeline import Settings, analyze_file
    from synth import SR, maqam_melody, percussion

    mel = maqam_melody(MAQAM_BY_KEY["rast"].scale, 0, n_phrases=5)
    y = mel + percussion("maqsum", 100, len(mel) / SR)[: len(mel)]
    f = tmp_path / "rast.wav"
    sf.write(f, y, SR)
    res = analyze_file(f, Settings(use_demucs=False, pitch_engine="crepe-tiny"))
    sc = res.score
    assert sc is not None and sc.svg_pages and len(sc.notes) > 20
    assert all(n.ids for n in sc.notes)
    assert all(sc.notes[i].end <= sc.notes[i + 1].start + 1e-6 for i in range(len(sc.notes) - 1))
    # الراست فيه سيكا → لازم يظهر نص بيمول في النوتة
    assert 'accid="1qf"' in sc.mei
    for key in ("piano", "piano_band"):
        assert key in res.playback
        data, sr = sf.read(str(res.playback[key]))
        assert abs(len(data) / sr - res.duration) < 1.0 and np.max(np.abs(data)) > 0.05
    # note_at بيرجع النوتة الصح
    n = sc.notes[5]
    assert sc.note_at((n.start + n.end) / 2) is n
