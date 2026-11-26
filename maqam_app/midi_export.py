"""تصدير اللحن كملف MIDI.

الربع تون في MIDI: بنكتب النوتة على أقرب مفتاح، وبنضيف Pitch Bend بقيمة الفرق
(مثلاً السيكا = مي مع Pitch Bend -50 cent). مدى الـ Pitch Bend مضبوط على ±2 تون.
فيه كمان اختيار "بدون Pitch Bend" عشان لو هتعزف على الأورج بعد ضبط Scale Tune.
"""
from __future__ import annotations

from pathlib import Path

import mido

from .notes import midi_from_cents
from .transcribe import NoteEvent

TICKS_PER_BEAT = 480
BEND_RANGE_SEMITONES = 2


def export_midi(notes: list[NoteEvent], path: str | Path, bpm: float = 120.0,
                use_pitch_bend: bool = True, only_clear: bool = False,
                program: int = 73, title: str = "Melody") -> Path:
    """program 73 = Flute (أقرب صوت للناي)."""
    path = Path(path)
    bpm = bpm if bpm and bpm > 20 else 120.0
    mid = mido.MidiFile(ticks_per_beat=TICKS_PER_BEAT)
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tempo = mido.bpm2tempo(bpm)
    # mido بيكتب الاسم latin-1؛ بنحط بايتات UTF-8 عشان الأسامي العربي تتحفظ من غير ما يقع
    safe_name = title[:60].encode("utf-8")[:120].decode("latin-1")
    tr.append(mido.MetaMessage("track_name", name=safe_name, time=0))
    tr.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    tr.append(mido.Message("program_change", program=program, channel=0, time=0))
    # ضبط مدى الـ Pitch Bend (RPN 0)
    for cc, val in ((101, 0), (100, 0), (6, BEND_RANGE_SEMITONES), (38, 0), (101, 127), (100, 127)):
        tr.append(mido.Message("control_change", control=cc, value=val, channel=0, time=0))

    def sec_to_ticks(s: float) -> int:
        return int(round(mido.second2tick(s, TICKS_PER_BEAT, tempo)))

    events = []
    for n in notes:
        if only_clear and not n.clear:
            continue
        midi, bend_c = midi_from_cents(n.cents - n.deviation)  # على الدرجة المضبوطة
        if not (0 <= midi <= 127):
            continue
        vel = int(50 + 60 * max(0.0, min(1.0, n.confidence)))
        bend = int(round(bend_c / (BEND_RANGE_SEMITONES * 100) * 8191)) if use_pitch_bend else 0
        events.append((sec_to_ticks(n.start), 0, bend, midi, vel))
        events.append((sec_to_ticks(max(n.end, n.start + 0.03)), 1, 0, midi, 0))
    events.sort(key=lambda e: (e[0], -e[1]))  # note_off قبل note_on في نفس اللحظة

    last = 0
    for tick, kind, bend, midi, vel in events:
        dt = max(0, tick - last)
        if kind == 0:
            if use_pitch_bend:
                tr.append(mido.Message("pitchwheel", pitch=max(-8192, min(8191, bend)),
                                       channel=0, time=dt))
                dt = 0
            tr.append(mido.Message("note_on", note=midi, velocity=vel, channel=0, time=dt))
        else:
            tr.append(mido.Message("note_off", note=midi, velocity=0, channel=0, time=dt))
        last = tick
    tr.append(mido.MetaMessage("end_of_track", time=0))
    path.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(path))
    return path
