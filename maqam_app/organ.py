"""مخرجات خاصة بالأورج — Yamaha PSR-2000.

الـ PSR-2000 بيسمح بضبط كل نوتة من الـ 12 (دو → سي) بالـ cents من -64 لـ +63
(Scale Tune)، وبيسمح بضبط Master Tune بالهرتز (من 414.8 لـ 466.8 هرتز تقريبًا).
الضبط بيأثر على النوتة في كل الأوكتافات.

القاعدة المستخدمة (زي ما العازفين بيعملوا):
- نص بيمول ← نوطّي المفتاح الطبيعي 50 cent (سيكا = مي -50)
- نص دييز  ← نعلّي المفتاح الطبيعي 50 cent، أو نوطّي المفتاح الأعلى لو
  المفتاح الطبيعي مستخدم في نفس المقام.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .maqam_detect import MaqamCandidate
from .notes import pc_label, signed
from .rhythm import RhythmResult
from .tuning import TuningInfo

ORGAN_MODEL = "Yamaha PSR-2000"
KEYS_12 = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
KEYS_12_AR = ["دو", "دو دييز", "ري", "مي بيمول", "مي", "فا", "فا دييز", "صول",
              "لا بيمول", "لا", "سي بيمول", "سي"]
SCALE_TUNE_MIN, SCALE_TUNE_MAX = -64, 63
MASTER_TUNE_MIN, MASTER_TUNE_MAX = 414.8, 466.8


@dataclass
class OrganSettings:
    maqam_title: str
    offsets: list[int]                          # 12 قيمة بالـ cents (دو → سي)
    changes: list[tuple[str, str, int, str]]    # (المفتاح، عربي، cents، النوتة المقصودة)
    master_tune_hz: float
    transpose: int = 0
    style: str = ""
    tempo: int = 0
    notes: list[str] = field(default_factory=list)

    def table_rows(self):
        return [(KEYS_12[i], KEYS_12_AR[i], self.offsets[i]) for i in range(12)]

    def short(self) -> str:
        if not self.changes:
            return "مافيش ربع تون — سيب الـ Scale Tune على 0 (Equal)"
        return "، ".join(f"{ar} ({k}) = {signed(c)} سنت" for k, ar, c, _ in self.changes)


def scale_tuning(cand: MaqamCandidate, extra_pcs: list[int] | None = None) -> tuple[list[int], list]:
    """إعدادات Scale Tune لمقام (12 قيمة بالـ cents)."""
    pcs = set(cand.scale_pcs())
    pcs |= {(cand.tonic + a) % 24 for a in cand.maqam.alternates}
    if extra_pcs:
        pcs |= set(extra_pcs)
    offsets = [0] * 12
    used_keys = {pc // 2 for pc in pcs if pc % 2 == 0}
    changes = []
    for pc in sorted(pcs):
        if pc % 2 == 0:
            continue
        lower_key = (pc - 1) // 2 % 12      # المفتاح اللي تحت النوتة
        upper_key = (pc + 1) // 2 % 12      # المفتاح اللي فوقها
        label = pc_label(pc)
        is_half_flat = "نص بيمول" in label
        if is_half_flat:
            prefer = [(upper_key, -50), (lower_key, +50)]
        else:
            prefer = [(lower_key, +50), (upper_key, -50)]
        for key, cents in prefer:
            if key not in used_keys and offsets[key] == 0:
                offsets[key] = cents
                used_keys.add(key)
                changes.append((KEYS_12[key], KEYS_12_AR[key], cents, label))
                break
    return offsets, changes


def organ_settings(cand: MaqamCandidate, tuning: TuningInfo,
                   rhythm: RhythmResult | None) -> OrganSettings:
    offsets, changes = scale_tuning(cand)
    master = min(max(tuning.reference_hz, MASTER_TUNE_MIN), MASTER_TUNE_MAX)
    notes = [
        f"على {ORGAN_MODEL}: اضغط FUNCTION ← MASTER TUNE/SCALE TUNE ← تاب SCALE TUNE، "
        "واختار كل نوتة واضبطها بالـ cents (Data Dial أو أزرار 1-8).",
        "الضبط بيطبق على النوتة في كل الأوكتافات. احفظ الإعداد في Registration Memory "
        "لو حبيت ترجعله بسرعة (اتأكد إن Scale Tune متعلّم في Freeze/Memory حسب الموديل).",
    ]
    if abs(tuning.offset_cents) >= 3:
        notes.append(
            f"التسجيل مش على 440: اضبط MASTER TUNE على {master:.1f} هرتز عشان تعزف "
            "مع الأغنية الأصلية من غير نشاز.")
    style, tempo = "", 0
    if rhythm is not None:
        style = rhythm.iqa.organ_style
        tempo = rhythm.organ_tempo()
    return OrganSettings(maqam_title=cand.title(), offsets=offsets, changes=changes,
                         master_tune_hz=round(master, 1), style=style, tempo=tempo, notes=notes)


def settings_for_all_maqamat(tonic_override: int | None = None) -> list[tuple[str, str]]:
    """جدول مرجعي: كل مقام على قراره التقليدي وإعداداته."""
    from .maqam_db import MAQAMAT

    rows = []
    for m in MAQAMAT:
        t = m.default_tonic if tonic_override is None else tonic_override
        cand = MaqamCandidate(m, t, 0.0, 0.0)
        _, changes = scale_tuning(cand)
        txt = "، ".join(f"{k} {signed(c)}" for k, _, c, _ in changes) or "بدون ربع تون"
        rows.append((cand.title(), txt))
    return rows
