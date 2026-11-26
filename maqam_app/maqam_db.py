"""المرحلة 6: قاعدة بيانات المقامات وأجناسها.

كل المسافات بوحدة الربع تون (1 = 50 cent، 2 = نص تون، 4 = تون كامل).
كل مقام متعرّف بأجناسه (الجنس الأساسي على القرار + الجنس الفرعي على الغماز)
والسلم الكامل، ودرجات بديلة مسموحة (مثلاً سي بيمول في نزول الراست).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Jins:
    key: str
    name_ar: str
    name_en: str
    steps: tuple[int, ...]          # مواقع النوتات من أساس الجنس
    kind: str                       # ثلاثي / رباعي / خماسي


AJNAS: dict[str, Jins] = {j.key: j for j in [
    Jins("rast", "راست", "Rast", (0, 4, 7, 10, 14), "خماسي"),
    Jins("rast4", "راست", "Rast", (0, 4, 7, 10), "رباعي"),
    Jins("bayati", "بياتي", "Bayati", (0, 3, 6, 10), "رباعي"),
    Jins("sikah", "سيكاه", "Sikah", (0, 3, 7), "ثلاثي"),
    Jins("hijaz", "حجاز", "Hijaz", (0, 2, 8, 10), "رباعي"),
    Jins("saba", "صبا", "Saba", (0, 3, 6, 8), "رباعي"),
    Jins("saba_zamzam", "صبا زمزم", "Saba Zamzam", (0, 2, 6, 8), "رباعي"),
    Jins("kurd", "كرد", "Kurd", (0, 2, 6, 10), "رباعي"),
    Jins("nahawand", "نهاوند", "Nahawand", (0, 4, 6, 10, 14), "خماسي"),
    Jins("nahawand4", "نهاوند", "Nahawand", (0, 4, 6, 10), "رباعي"),
    Jins("ajam", "عجم", "Ajam", (0, 4, 8, 10, 14), "خماسي"),
    Jins("ajam4", "عجم", "Ajam", (0, 4, 8, 10), "رباعي"),
    Jins("ajam3", "عجم", "Ajam", (0, 4, 8), "ثلاثي"),
    Jins("nikriz", "نكريز", "Nikriz", (0, 4, 6, 12, 14), "خماسي"),
]}


@dataclass(frozen=True)
class Maqam:
    key: str
    name_ar: str
    name_en: str
    family: str                         # العائلة (للون)
    default_tonic: int                  # القرار التقليدي (درجة 0..23 من دو)
    scale: tuple[int, ...]              # السلم الصاعد من القرار
    ajnas: tuple[tuple[str, int], ...]  # (الجنس، موقعه من القرار)
    alternates: tuple[int, ...] = ()    # درجات بديلة مسموحة (في النزول مثلاً)
    prior: float = 0.0                  # شهرة المقام (لحسم التعادل)
    description: str = ""
    ghammaz: int = field(default=-1)

    @property
    def lower_jins(self) -> tuple[str, int]:
        return self.ajnas[0]

    @property
    def upper_jins(self) -> tuple[str, int] | None:
        return self.ajnas[1] if len(self.ajnas) > 1 else None

    def ghammaz_pos(self) -> int:
        if self.ghammaz >= 0:
            return self.ghammaz
        up = self.upper_jins
        return up[1] if up else 14

    def lower_notes(self) -> list[int]:
        j, off = self.lower_jins
        return [off + s for s in AJNAS[j].steps]

    def upper_notes(self) -> list[int]:
        if not self.upper_jins:
            return []
        j, off = self.upper_jins
        return [(off + s) for s in AJNAS[j].steps]

    def ajnas_text(self) -> str:
        from .notes import pc_label  # noqa
        parts = []
        for jk, off in self.ajnas:
            j = AJNAS[jk]
            parts.append(f"{j.name_ar} ({j.kind})")
        return " + ".join(parts)


# القرار: 0 = دو (راست)، 4 = ري (دوكاه)، 7 = مي نص بيمول (سيكاه)، 21 = سي نص بيمول (عراق)
MAQAMAT: list[Maqam] = [
    Maqam("rast", "راست", "Rast", "rast", 0, (0, 4, 7, 10, 14, 18, 21),
          (("rast", 0), ("rast4", 14)), alternates=(20,), prior=0.05,
          description="جنس راست على القرار وجنس راست على النوا؛ في النزول بيستخدم نهاوند على النوا."),
    Maqam("suznak", "سوزناك", "Suznak", "rast", 0, (0, 4, 7, 10, 14, 16, 22),
          (("rast", 0), ("hijaz", 14)), prior=0.01,
          description="راست على القرار وحجاز على النوا."),
    Maqam("nairuz", "نيرز", "Nairuz", "rast", 0, (0, 4, 7, 10, 14, 17, 20),
          (("rast", 0), ("bayati", 14)), prior=0.0,
          description="راست على القرار وبياتي على النوا."),
    Maqam("bayati", "بياتي", "Bayati", "bayati", 4, (0, 3, 6, 10, 14, 16, 20),
          (("bayati", 0), ("nahawand4", 10)), alternates=(17,), prior=0.05,
          description="جنس بياتي على الدوكاه وجنس نهاوند على النوا."),
    Maqam("husayni", "حسيني", "Husayni", "bayati", 4, (0, 3, 6, 10, 14, 17, 20),
          (("bayati", 0), ("bayati", 14)), alternates=(16,), prior=0.015,
          description="بياتي على الدوكاه وبياتي على الحسيني."),
    Maqam("shuri", "شوري (بياتي شوري)", "Bayati Shuri", "bayati", 4, (0, 3, 6, 10, 12, 18, 20),
          (("bayati", 0), ("hijaz", 10)), prior=0.015,
          description="بياتي على الدوكاه وحجاز على النوا."),
    Maqam("saba", "صبا", "Saba", "saba", 4, (0, 3, 6, 8, 14, 16, 20),
          (("saba", 0), ("hijaz", 6)), alternates=(12, 2), prior=0.04,
          description="جنس صبا على الدوكاه وجنس حجاز على الجهاركاه."),
    Maqam("saba_zamzam", "صبا زمزم", "Saba Zamzam", "saba", 4, (0, 2, 6, 8, 14, 16, 20),
          (("saba_zamzam", 0), ("hijaz", 6)), prior=0.0,
          description="صبا بالكرد بدل السيكاه."),
    Maqam("hijaz", "حجاز", "Hijaz", "hijaz", 4, (0, 2, 8, 10, 14, 16, 20),
          (("hijaz", 0), ("nahawand4", 10)), alternates=(17, 18), prior=0.05,
          description="جنس حجاز على الدوكاه وجنس نهاوند (أو راست) على النوا."),
    Maqam("hijazkar", "حجاز كار", "Hijaz Kar", "hijaz", 0, (0, 2, 8, 10, 14, 16, 22),
          (("hijaz", 0), ("hijaz", 14)), prior=0.03,
          description="حجاز على الراست وحجاز على النوا."),
    Maqam("zanjaran", "زنجران", "Zanjaran", "hijaz", 0, (0, 2, 8, 10, 14, 18, 20),
          (("hijaz", 0), ("ajam4", 10)), prior=0.0,
          description="حجاز على الراست وعجم على الجهاركاه."),
    Maqam("nahawand", "نهاوند", "Nahawand", "nahawand", 0, (0, 4, 6, 10, 14, 16, 22),
          (("nahawand", 0), ("hijaz", 14)), alternates=(20, 18), prior=0.05,
          description="جنس نهاوند على الراست وحجاز (أو كرد) على النوا."),
    Maqam("kurd", "كرد", "Kurd", "kurd", 4, (0, 2, 6, 10, 14, 16, 20),
          (("kurd", 0), ("nahawand4", 10)), prior=0.04,
          description="جنس كرد على الدوكاه ونهاوند على النوا."),
    Maqam("sikah", "سيكاه", "Sikah", "sikah", 7, (0, 3, 7, 11, 14, 17, 21),
          (("sikah", 0), ("rast4", 7)), alternates=(10, 13), prior=0.04,
          description="جنس سيكاه على السيكاه وراست على الجهاركاه."),
    Maqam("huzam", "هزام", "Huzam", "sikah", 7, (0, 3, 7, 9, 15, 17, 21),
          (("sikah", 0), ("hijaz", 7)), prior=0.035,
          description="سيكاه على السيكاه وحجاز على النوا."),
    Maqam("iraq", "عراق", "Iraq", "sikah", 21, (0, 3, 7, 10, 13, 17, 21),
          (("sikah", 0), ("bayati", 7)), prior=0.01,
          description="سيكاه على العراق وبياتي على الدوكاه."),
    Maqam("ajam", "عجم", "Ajam", "ajam", 20, (0, 4, 8, 10, 14, 18, 22),
          (("ajam", 0), ("ajam4", 14)), prior=0.04,
          description="جنس عجم على القرار وعجم على الغماز (زي الماجير)."),
    Maqam("nikriz", "نكريز", "Nikriz", "nahawand", 0, (0, 4, 6, 12, 14, 18, 20),
          (("nikriz", 0), ("nahawand4", 14)), prior=0.01,
          description="نكريز على الراست ونهاوند على النوا."),
    Maqam("nawa_athar", "نوا أثر", "Nawa Athar", "nahawand", 0, (0, 4, 6, 12, 14, 16, 22),
          (("nikriz", 0), ("hijaz", 14)), prior=0.005,
          description="نكريز على الراست وحجاز على النوا."),
    Maqam("athar_kurd", "أثر كرد", "Athar Kurd", "kurd", 0, (0, 2, 6, 12, 14, 16, 22),
          (("kurd", 0), ("hijaz", 14)), prior=0.0,
          description="كرد على الراست مع فا دييز، وحجاز على النوا."),
]

MAQAM_BY_KEY = {m.key: m for m in MAQAMAT}

# أسماء خاصة لما المقام يتصوّر على قرار تاني (نقل المقام)
TRANSPOSED_NAMES = {
    ("kurd", 0): "حجاز كار كرد (كرد على الراست)",
    ("hijazkar", 4): "شهناز (حجاز كار على الدوكاه)",
    ("nahawand", 14): "فرحفزا (نهاوند على النوا)",
    ("huzam", 21): "راحة الأرواح (هزام على العراق)",
    ("ajam", 0): "عجم على الراست (جهاركاه/ماجير)",
    ("ajam", 10): "جهاركاه (عجم على الجهاركاه)",
    ("bayati", 18): "بياتي على الحسيني",
    ("rast", 14): "سازكار/راست على النوا",
    ("saba", 18): "صبا على الحسيني",
    ("hijaz", 18): "حجاز على الحسيني",
}

# لون مميز لكل عائلة مقامات (هادي على الخلفية الغامقة)
FAMILY_COLORS = {
    "rast": "#6FB7FF",
    "bayati": "#7ED6A5",
    "saba": "#C59CFF",
    "hijaz": "#FF8A7A",
    "nahawand": "#FFC86B",
    "kurd": "#F28FC4",
    "sikah": "#5FD8D2",
    "ajam": "#E5E28A",
}


def maqam_color(key: str) -> str:
    m = MAQAM_BY_KEY.get(key)
    return FAMILY_COLORS.get(m.family, "#9AA0A6") if m else "#9AA0A6"
