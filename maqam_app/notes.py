"""تسمية النوتات بدقة الربع تون (24 درجة في الأوكتاف).

كل نوتة بتتسمى بثلاث طرق:
- سولفيج عربي: دو، ري، مي ... مع بيمول / دييز / نص بيمول / نص دييز
- الحرف الغربي: C D E ... مع ♭ ♯ و ½♭ (نص بيمول) و ½♯ (نص دييز)
- الاسم العربي التقليدي: راست، دوكاه، سيكاه ...

المرجع: لا4 (A4) = 440 هرتز، ودو4 (C4) = راست.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

A4_HZ = 440.0
QT_PER_OCTAVE = 24          # عدد الدرجات (ربع تون) في الأوكتاف
CENTS_PER_QT = 50.0

# (حرف غربي، سولفيج عربي، نوع العلامة) لكل درجة من الـ 24 بداية من دو
# accidental: "" طبيعي، "b" بيمول، "#" دييز، "hb" نص بيمول، "h#" نص دييز
_PITCH_CLASSES = [
    ("C", "دو", ""),
    ("C", "دو", "h#"),
    ("C", "دو", "#"),
    ("D", "ري", "hb"),
    ("D", "ري", ""),
    ("D", "ري", "h#"),
    ("E", "مي", "b"),
    ("E", "مي", "hb"),
    ("E", "مي", ""),
    ("E", "مي", "h#"),
    ("F", "فا", ""),
    ("F", "فا", "h#"),
    ("F", "فا", "#"),
    ("G", "صول", "hb"),
    ("G", "صول", ""),
    ("G", "صول", "h#"),
    ("A", "لا", "b"),
    ("A", "لا", "hb"),
    ("A", "لا", ""),
    ("A", "لا", "h#"),
    ("B", "سي", "b"),
    ("B", "سي", "hb"),
    ("B", "سي", ""),
    ("B", "سي", "h#"),
]

_ACC_WESTERN = {"": "", "b": "♭", "#": "♯", "hb": "½♭", "h#": "½♯"}
_ACC_ASCII = {"": "", "b": "b", "#": "#", "hb": "-", "h#": "+"}
_ACC_ARABIC = {"": "", "b": " بيمول", "#": " دييز", "hb": " نص بيمول", "h#": " نص دييز"}

# الأسماء العربية التقليدية — الأوكتاف الأساسي من راست (C4) لتيك ماهور
_ARABIC_OCT4 = [
    "راست", "نيم زيركلاه", "زيركلاه", "تيك زيركلاه", "دوكاه", "نيم كرد",
    "كرد", "سيكاه", "بوسليك", "تيك بوسليك", "جهاركاه", "نيم حجاز",
    "حجاز", "تيك حجاز", "نوا", "نيم حصار", "حصار", "تيك حصار",
    "حسيني", "نيم عجم", "عجم", "أوج", "ماهور", "تيك ماهور",
]
# أسماء خاصة في أوكتاف الجواب (C5 ...)
_ARABIC_OCT5 = {
    0: "كردان", 1: "نيم شهناز", 2: "شهناز", 3: "تيك شهناز", 4: "محير",
    5: "نيم سنبلة", 6: "سنبلة", 7: "بزرك", 8: "جواب بوسليك", 10: "ماهوران",
    14: "رمل توتي",
}
# أسماء خاصة في أوكتاف القرار (من يكاه G3 لتيك كوشت)
_ARABIC_OCT3 = {
    14: "يكاه", 15: "قرار نيم حصار", 16: "قرار حصار", 17: "قرار تيك حصار",
    18: "عشيران", 19: "قرار نيم عجم", 20: "قرار عجم", 21: "عراق",
    22: "كوشت", 23: "تيك كوشت",
}


LRM = "\u200e"


def signed(v: float, unit: str = "") -> str:
    """رقم بإشارة يظهر صح جوه نص عربي (من غير ما الإشارة تتنقل لآخر الرقم)."""
    txt = f"{v:+.0f}" if isinstance(v, float) else f"{v:+d}"
    return f"{LRM}{txt}{unit}{LRM}"


def hz_to_cents(hz, ref_hz: float = A4_HZ):
    """تحويل التردد لـ cents نسبة لـ A4 (A4 = 0)."""
    hz = np.asarray(hz, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 1200.0 * np.log2(hz / ref_hz)


def cents_to_hz(cents, ref_hz: float = A4_HZ):
    return ref_hz * 2.0 ** (np.asarray(cents, dtype=float) / 1200.0)


def cents_to_qt_index(cents: float) -> int:
    """رقم الدرجة (ربع تون) المطلق — 0 = دو4 (C4)."""
    # A4 = 0 cents، و C4 أوطى منها بـ 900 cent
    return int(round((cents + 900.0) / CENTS_PER_QT))


def qt_index_to_cents(idx: int) -> float:
    return idx * CENTS_PER_QT - 900.0


def is_quarter_tone(pc24: int) -> bool:
    return _PITCH_CLASSES[pc24 % 24][2] in ("hb", "h#")


@dataclass(frozen=True)
class NoteName:
    index: int              # رقم الدرجة المطلق (0 = C4)
    pc24: int               # الدرجة داخل الأوكتاف 0..23
    octave: int             # رقم الأوكتاف العلمي (C4 = 4)
    western: str            # مثال: E½♭4
    western_ascii: str      # مثال: E-4  (للملفات اللي مش بتدعم الرموز)
    solfege: str            # مثال: مي نص بيمول
    arabic: str             # مثال: سيكاه
    quarter_tone: bool

    @property
    def letter(self) -> str:
        return _PITCH_CLASSES[self.pc24][0]

    @property
    def accidental(self) -> str:
        return _PITCH_CLASSES[self.pc24][2]

    def full(self) -> str:
        return f"{self.solfege} ({self.western}) — {self.arabic}"


def arabic_name(pc24: int, octave: int) -> str:
    pc24 %= 24
    if octave == 4:
        return _ARABIC_OCT4[pc24]
    if octave == 5 and pc24 in _ARABIC_OCT5:
        return _ARABIC_OCT5[pc24]
    if octave == 3 and pc24 in _ARABIC_OCT3:
        return _ARABIC_OCT3[pc24]
    if octave > 4:
        base = _ARABIC_OCT4[pc24]
        return ("جواب " * (octave - 4)) + base
    base = _ARABIC_OCT4[pc24]
    return ("قرار " * (4 - octave)) + base


def name_from_index(idx: int) -> NoteName:
    pc24 = idx % 24
    octave = 4 + idx // 24
    letter, solf, acc = _PITCH_CLASSES[pc24]
    return NoteName(
        index=idx,
        pc24=pc24,
        octave=octave,
        western=f"{letter}{_ACC_WESTERN[acc]}{octave}",
        western_ascii=f"{letter}{_ACC_ASCII[acc]}{octave}",
        solfege=f"{solf}{_ACC_ARABIC[acc]}",
        arabic=arabic_name(pc24, octave),
        quarter_tone=acc in ("hb", "h#"),
    )


def name_from_cents(cents: float) -> tuple[NoteName, float]:
    """يرجع اسم النوتة وانحرافها بالـ cents عن أقرب درجة ربع تون."""
    idx = cents_to_qt_index(cents)
    dev = cents - qt_index_to_cents(idx)
    return name_from_index(idx), float(dev)


def name_from_hz(hz: float, ref_hz: float = A4_HZ) -> tuple[NoteName, float]:
    return name_from_cents(float(hz_to_cents(hz, ref_hz)))


def pc_name(pc24: int, octave: int = 4) -> NoteName:
    """اسم درجة (بدون أهمية للأوكتاف) — مفيد للقرار والمقامات."""
    return name_from_index((octave - 4) * 24 + (pc24 % 24))


def pc_label(pc24: int) -> str:
    """تسمية مختصرة لدرجة: سولفيج + حرف غربي (بدون رقم أوكتاف)."""
    letter, solf, acc = _PITCH_CLASSES[pc24 % 24]
    return f"{solf}{_ACC_ARABIC[acc]} ({letter}{_ACC_WESTERN[acc]})"


def tonic_label(pc24: int) -> str:
    """القرار بالاسم العربي التقليدي + السولفيج + الغربي، مثال: دوكاه = ري (D)."""
    nn = pc_name(pc24, 4)
    # نختار الاسم العربي في المنطقة اللي عادة بيكون فيها القرار (يكاه → تيك ماهور)
    if pc24 >= 14:
        ar = arabic_name(pc24, 3) if pc24 in _ARABIC_OCT3 else nn.arabic
    else:
        ar = nn.arabic
    letter, solf, acc = _PITCH_CLASSES[pc24 % 24]
    return f"{ar} = {solf}{_ACC_ARABIC[acc]} ({letter}{_ACC_WESTERN[acc]})"


def midi_from_cents(cents: float) -> tuple[int, float]:
    """رقم MIDI الأقرب (نص تون) + الفرق بالـ cents (للـ Pitch Bend)."""
    midi_float = 69.0 + cents / 100.0
    # نختار النوتة الطبيعية اللي تحت لو النوتة نص بيمول (عشان السيكا = مي - 50)
    m = int(math.floor(midi_float + 0.5 + 1e-9))
    return m, (midi_float - m) * 100.0
