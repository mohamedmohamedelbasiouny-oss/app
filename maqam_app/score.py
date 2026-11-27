"""وضع التمرين: تحويل اللحن لنوتة موسيقية (مدرج) زي فيديوهات التعليم.

1. تكميم (quantize) النوتات على شبكة الإيقاع (1/16) حسب الـ BPM.
2. تقسيمها لمازورات حسب الميزان، مع ربط (tie) النوتات اللي بتعدي خط المازورة.
3. كتابتها بصيغة MEI (فيها علامات الربع تون: نص بيمول ونص دييز).
4. رسمها بـ Verovio كـ SVG — كل نوتة ليها id عشان نلوّنها وقت التشغيل.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from xml.sax.saxutils import escape

import numpy as np

from .notes import name_from_index, qt_index_to_cents

# طول المازورة بوحدات 1/16 لكل ميزان
METER_UNITS = {"4/4": 16, "2/4": 8, "3/4": 12, "10/8": 20, "7/8": 14, "9/8": 18,
               "10/16": 10, "6/8": 12}
# الأطوال اللي ينفع تتكتب في نوتة واحدة (بالـ 1/16) → (dur, dots)
_DURS = {16: ("1", 0), 12: ("2", 1), 8: ("2", 0), 6: ("4", 1), 4: ("4", 0),
         3: ("8", 1), 2: ("8", 0), 1: ("16", 0)}
_ACC_MEI = {"": "n", "b": "f", "#": "s", "hb": "1qf", "h#": "1qs"}
_FLAT_ORDER = ["b", "e", "a", "d", "g", "c", "f"]
_SHARP_ORDER = ["f", "c", "g", "d", "a", "e", "b"]


@dataclass
class ScoreNote:
    start: float            # ثواني (بعد التكميم)
    end: float
    index: int | None       # درجة الربع تون (None = سكتة)
    ids: list[str] = field(default_factory=list)   # عناصر SVG (أكتر من واحد لو فيه ربط)

    @property
    def name(self):
        return name_from_index(self.index) if self.index is not None else None


@dataclass
class Score:
    notes: list[ScoreNote]          # النوتات بس (من غير السكتات)
    svg_pages: list[str]
    bpm: float
    meter: str
    unit_s: float                   # طول الـ 1/16 بالثواني
    offset_s: float                 # بداية الشبكة
    key_sig: str
    mei: str = ""

    def note_at(self, t: float) -> ScoreNote | None:
        lo, hi = 0, len(self.notes) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            n = self.notes[mid]
            if t < n.start:
                hi = mid - 1
            elif t >= n.end:
                lo = mid + 1
            else:
                return n
        return None

    def last_note_before(self, t: float) -> ScoreNote | None:
        best = None
        for n in self.notes:
            if n.start <= t:
                best = n
            else:
                break
        return best


# ---------------------------------------------------------------- التكميم

def quantize(notes, bpm: float, offset_s: float = 0.0, min_conf: float = 0.45,
             grid_per_beat: int = 4) -> tuple[list[tuple[int, int, int]], float]:
    """يرجع [(بداية بالوحدات، الطول بالوحدات، الدرجة)] و طول الوحدة بالثواني."""
    bpm = bpm if bpm and 30 < bpm < 260 else 90.0
    unit = 60.0 / bpm / grid_per_beat
    out: list[list[int]] = []
    for n in notes:
        if n.confidence < min_conf:
            continue
        s = int(round((n.start - offset_s) / unit))
        e = int(round((n.end - offset_s) / unit))
        if s < 0:
            continue
        if e <= s:
            if n.end - n.start < unit * 0.45:
                continue      # زخرفة قصيرة جدًا
            e = s + 1
        if out and s < out[-1][0] + out[-1][1]:
            prev = out[-1]
            if prev[2] == n.index:          # نفس النوتة → نكمّلها
                prev[1] = max(prev[1], e - prev[0])
                continue
            if s <= prev[0]:                 # النوتة الجديدة بتبدأ في نفس الخانة
                if (e - s) > prev[1]:
                    out[-1] = [s, e - s, n.index]
                continue
            prev[1] = s - prev[0]
        out.append([s, e - s, n.index])
    # دمج نوتات متتالية بنفس الدرجة بينهم فراغ خانة واحدة أو أقل (نَفَس/فيبراتو)
    merged: list[list[int]] = []
    for ev in out:
        if merged and merged[-1][2] == ev[2] and ev[0] - (merged[-1][0] + merged[-1][1]) <= 0:
            merged[-1][1] = ev[0] + ev[1] - merged[-1][0]
        else:
            merged.append(ev)
    return [tuple(x) for x in merged], unit


def _split_len(n: int) -> list[int]:
    """تقسيم طول لأطوال ينفع تتكتب (مع ربط)."""
    parts = []
    for d in (16, 12, 8, 6, 4, 3, 2, 1):
        while n >= d:
            parts.append(d)
            n -= d
    return parts


def _key_signature(scale_pcs: list[int]) -> tuple[str, dict[str, str]]:
    """دليل المقام (الـ key signature) من البيمولات/الدييزات العادية في السلم."""
    flats, sharps = set(), set()
    for pc in scale_pcs:
        nn = name_from_index(pc)
        if nn.accidental == "b":
            flats.add(nn.letter.lower())
        elif nn.accidental == "#":
            sharps.add(nn.letter.lower())
    for order, got, sym in ((_FLAT_ORDER, flats, "f"), (_SHARP_ORDER, sharps, "s")):
        if not got:
            continue
        k = 0
        while k < len(order) and order[k] in got:
            k += 1
        if k == len(got):
            return f"{k}{sym}", {order[i]: sym for i in range(k)}
    return "0", {}


# ---------------------------------------------------------------- MEI

def build_mei(events, meter: str, key_sig: str, key_map: dict[str, str], bpm: float,
              title: str = "", clef_down: bool = False) -> tuple[str, dict[int, list[str]]]:
    m_len = METER_UNITS.get(meter, 16)
    count, unit = (meter.split("/") + ["4"])[:2]
    ids: dict[int, list[str]] = {}
    total = (events[-1][0] + events[-1][1]) if events else m_len
    n_meas = max(1, int(np.ceil(total / m_len)))

    # تحويل الأحداث لمحتوى كل مازورة: (طول، درجة أو None، رقم الحدث، مربوط بالجاية؟)
    measures: list[list[tuple]] = [[] for _ in range(n_meas)]
    pos = 0
    timeline = []
    for k, (s, d, idx) in enumerate(events):
        if s > pos:
            timeline.append((pos, s - pos, None, -1))
        timeline.append((s, d, idx, k))
        pos = s + d
    if pos < n_meas * m_len:
        timeline.append((pos, n_meas * m_len - pos, None, -1))
    for s, d, idx, k in timeline:
        while d > 0:
            mi = s // m_len
            room = (mi + 1) * m_len - s
            take = min(d, room)
            parts = _split_len(take)
            for j, p in enumerate(parts):
                last_piece = (j == len(parts) - 1) and take == d
                measures[mi].append((p, idx, k, idx is not None and not last_piece))
            s += take
            d -= take

    uid = 0
    body = []
    tie_open = False                      # الربط بيكمّل عبر خط المازورة
    for mi, items in enumerate(measures):
        acc_state = dict(key_map)        # الحالة جوه المازورة
        entries = []                      # (xml, طول، نوتة؟، رقم الضربة)
        mpos = 0
        for p, idx, k, tie_next in items:
            dur, dots = _DURS[p]
            dots_attr = f' dots="{dots}"' if dots else ""
            beat = mpos // 4
            same_beat = (mpos + p - 1) // 4 == beat
            if idx is None:
                entries.append((f'<rest dur="{dur}"{dots_attr}/>', p, False, beat, same_beat))
                mpos += p
                continue
            uid += 1
            xid = f"sn{uid}"
            ids.setdefault(k, []).append(xid)
            nn = name_from_index(idx)
            letter = nn.letter.lower()
            want = _ACC_MEI[nn.accidental]
            current = acc_state.get(letter, "n")
            octv = nn.octave + (1 if clef_down else 0)
            if want != current:
                acc_attr = f' accid="{want}"'
                acc_state[letter] = want
            else:
                acc_attr = f' accid.ges="{want}"' if want != "n" else ""
            tie = ""
            if tie_next and tie_open:
                tie = ' tie="m"'
            elif tie_next:
                tie = ' tie="i"'
            elif tie_open:
                tie = ' tie="t"'
            tie_open = tie_next
            entries.append((f'<note xml:id="{xid}" pname="{letter}" oct="{octv}" '
                            f'dur="{dur}"{dots_attr}{acc_attr}{tie}/>', p, True, beat, same_beat))
            mpos += p
        # تجميع الـ beams: نوتات قصيرة (ثُمن أو أقل) في نفس الضربة
        layer = []
        group: list[str] = []
        gbeat = None

        def flush():
            if len(group) >= 2:
                layer.append("<beam>" + "".join(group) + "</beam>")
            else:
                layer.extend(group)
            group.clear()

        for xml, p, is_note, beat, same_beat in entries:
            beamable = is_note and p < 4 and same_beat
            if beamable and (gbeat is None or beat == gbeat):
                group.append(xml)
                gbeat = beat
                continue
            flush()
            gbeat = None
            if beamable:
                group.append(xml)
                gbeat = beat
            else:
                layer.append(xml)
        flush()
        body.append(f'<measure n="{mi + 1}"><staff n="1"><layer n="1">{"".join(layer)}'
                    f'</layer></staff></measure>')

    clef = 'clef.shape="G" clef.line="2"' + (' clef.dis="8" clef.dis.place="below"' if clef_down else "")
    mei = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<mei xmlns="http://www.music-encoding.org/ns/mei" meiversion="5.0">'
        f'<meiHead><fileDesc><titleStmt><title>{escape(title)}</title></titleStmt>'
        '<pubStmt/></fileDesc></meiHead>'
        '<music><body><mdiv><score>'
        f'<scoreDef meter.count="{count}" meter.unit="{unit}" keysig="{key_sig}" '
        f'midi.bpm="{int(round(bpm))}">'
        f'<staffGrp><staffDef n="1" lines="5" {clef}/></staffGrp></scoreDef>'
        f'<section>{"".join(body)}</section></score></mdiv></body></music></mei>')
    return mei, ids


def render_svg(mei: str, page_width: int = 1500, scale: int = 40) -> list[str]:
    import verovio

    tk = verovio.toolkit()
    try:
        tk.setResourcePath(verovio.__path__[0] + "/data")
    except Exception:
        pass
    tk.setOptions({
        "pageWidth": page_width, "pageHeight": 60000, "adjustPageHeight": True,
        "scale": scale, "breaks": "auto", "header": "none", "footer": "none",
        "svgViewBox": True, "spacingSystem": 4, "pageMarginTop": 30,
        "pageMarginBottom": 40, "pageMarginLeft": 40, "pageMarginRight": 40,
    })
    if not tk.loadData(mei):
        raise RuntimeError("Verovio مقدرش يقرا النوتة")
    return [tk.renderToSVG(i) for i in range(1, tk.getPageCount() + 1)]


def build_score(res, page_width: int = 1500, render: bool = True) -> Score:
    bpm = float(res.rhythm.bpm or 90.0)
    meter = res.rhythm.meter if res.rhythm.meter in METER_UNITS else "4/4"
    unit_s = 60.0 / bpm / 4
    # بنبدأ الشبكة من بداية دورة الإيقاع عشان المازورات تطلع مظبوطة
    offset = float(res.rhythm.cycle_start or 0.0)
    cycle_s = METER_UNITS.get(meter, 16) * unit_s
    if cycle_s > 0:
        first = min((n.start for n in res.notes), default=0.0)
        while offset > first:
            offset -= cycle_s
        offset = max(offset, -cycle_s)
    events, unit_s = quantize(res.notes, bpm, offset)
    best = res.maqam.global_best
    key_sig, key_map = _key_signature(best.scale_pcs())
    idxs = [e[2] for e in events]
    clef_down = bool(idxs) and float(np.median(idxs)) < -10   # صوت رجالي واطي
    mei, idmap = build_mei(events, meter, key_sig, key_map, bpm, res.title, clef_down)
    svgs = render_svg(mei, page_width) if render else []
    notes = []
    for k, (s, d, idx) in enumerate(events):
        start = offset + s * unit_s
        notes.append(ScoreNote(start=start, end=start + d * unit_s, index=idx,
                               ids=idmap.get(k, [])))
    return Score(notes=notes, svg_pages=svgs, bpm=bpm, meter=meter, unit_s=unit_s,
                 offset_s=offset, key_sig=key_sig, mei=mei)


def flatten_svg(svg: str) -> str:
    """QtSvg (SVG Tiny) مش بيدعم <svg> جوه <svg> — بنحوّل الداخلي لـ <g transform>."""
    import re

    outer = re.search(r'<svg[^>]*viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    inner = re.search(r'<svg class="definition-scale"([^>]*)viewBox="0 0 ([\d.]+) ([\d.]+)"[^>]*>', svg)
    if not outer or not inner:
        return svg
    ow, oh = float(outer.group(1)), float(outer.group(2))
    iw, ih = float(inner.group(2)), float(inner.group(3))
    g = f'<g class="definition-scale" transform="scale({ow / iw:.8f},{oh / ih:.8f})">'
    svg = svg[:inner.start()] + g + svg[inner.end():]
    last = svg.rfind("</svg>")
    prev = svg.rfind("</svg>", 0, last)
    if prev != -1:
        svg = svg[:prev] + "</g>" + svg[prev + len("</svg>"):]
    return svg
