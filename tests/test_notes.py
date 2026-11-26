"""اختبارات تسمية النوتات — لازم تبقى صح 100%."""
import numpy as np
import pytest

from maqam_app.notes import (cents_to_hz, hz_to_cents, midi_from_cents, name_from_hz,
                             name_from_index, qt_index_to_cents, tonic_label)


@pytest.mark.parametrize("hz,solfege,western,arabic", [
    (261.63, "دو", "C4", "راست"),
    (293.66, "ري", "D4", "دوكاه"),
    (329.63, "مي", "E4", "بوسليك"),
    (349.23, "فا", "F4", "جهاركاه"),
    (392.00, "صول", "G4", "نوا"),
    (440.00, "لا", "A4", "حسيني"),
    (493.88, "سي", "B4", "ماهور"),
    (196.00, "صول", "G3", "يكاه"),
    (220.00, "لا", "A3", "عشيران"),
    (523.25, "دو", "C5", "كردان"),
    (587.33, "ري", "D5", "محير"),
])
def test_natural_notes(hz, solfege, western, arabic):
    nn, dev = name_from_hz(hz)
    assert nn.solfege == solfege
    assert nn.western == western
    assert nn.arabic == arabic
    assert abs(dev) < 2
    assert not nn.quarter_tone


def test_sikah_quarter_tone():
    # السيكا = مي نص بيمول = E4 - 50 cent
    hz = 329.63 * 2 ** (-50 / 1200)
    nn, dev = name_from_hz(hz)
    assert nn.solfege == "مي نص بيمول"
    assert nn.western == "E½♭4"
    assert nn.arabic == "سيكاه"
    assert nn.quarter_tone
    assert abs(dev) < 2


@pytest.mark.parametrize("idx,solfege,arabic", [
    (21, "سي نص بيمول", "أوج"),
    (-3, "سي نص بيمول", "عراق"),
    (11, "فا نص دييز", "نيم حجاز"),
    (17, "لا نص بيمول", "تيك حصار"),
    (6, "مي بيمول", "كرد"),
    (12, "فا دييز", "حجاز"),
    (20, "سي بيمول", "عجم"),
    (31, "مي نص بيمول", "بزرك"),
])
def test_named_degrees(idx, solfege, arabic):
    nn = name_from_index(idx)
    assert nn.solfege == solfege
    assert nn.arabic == arabic


def test_roundtrip_all_quarter_tones():
    for idx in range(-48, 49):
        c = qt_index_to_cents(idx)
        nn, dev = name_from_hz(float(cents_to_hz(c)))
        assert nn.index == idx
        assert abs(dev) < 1e-6


def test_tonic_label():
    assert tonic_label(4) == "دوكاه = ري (D)"
    assert tonic_label(0) == "راست = دو (C)"
    assert tonic_label(7).startswith("سيكاه = مي نص بيمول")
    assert tonic_label(21).startswith("عراق")


def test_midi_quarter_tone_bend():
    m, bend = midi_from_cents(float(hz_to_cents(329.63 * 2 ** (-50 / 1200))))
    assert m == 64 and abs(bend + 50) < 1   # مي مع -50
    m, bend = midi_from_cents(0.0)
    assert m == 69 and abs(bend) < 1e-9
