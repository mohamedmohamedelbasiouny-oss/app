"""تحويل نتيجة التحليل لـ JSON للصفحة بتاعة الموبايل."""
from __future__ import annotations

import math

import numpy as np

from ..notes import name_from_index, qt_index_to_cents, signed
from ..organ import KEYS_12, KEYS_12_AR, ORGAN_MODEL
from ..pipeline import AnalysisResult
from ..separation import STEM_LABELS


def _f(x, nd=3):
    x = float(x)
    return None if not math.isfinite(x) else round(x, nd)


def _organ(o):
    return {
        "title": o.maqam_title,
        "offsets": list(o.offsets),
        "keys": KEYS_12,
        "keys_ar": KEYS_12_AR,
        "summary": o.short(),
        "master_tune": o.master_tune_hz,
        "style": o.style,
        "tempo": o.tempo,
        "notes": o.notes,
    }


def _melody(res: AnalysisResult, max_points: int = 2500):
    t = res.pitch.times
    c = res.cents
    if len(t) == 0:
        return {"t": [], "c": []}
    step = max(1, int(math.ceil(len(t) / max_points)))
    tt, cc = [], []
    for i in range(0, len(t), step):
        seg = c[i:i + step]
        fin = seg[np.isfinite(seg)]
        tt.append(round(float(t[i]), 3))
        cc.append(round(float(np.median(fin)), 1) if fin.size >= max(1, step // 2) else None)
    return {"t": tt, "c": cc}


def result_to_json(res: AnalysisResult) -> dict:
    b = res.maqam.global_best
    v = res.cents[np.isfinite(res.cents)]
    lo = float(np.percentile(v, 1)) if v.size else -900.0
    hi = float(np.percentile(v, 99.5)) if v.size else 300.0
    c_min = math.floor((lo - 120) / 100) * 100
    c_max = math.ceil((hi + 120) / 100) * 100
    scale_pcs = set()
    for s in res.maqam.sections:
        scale_pcs |= set(s.candidate.scale_pcs())
    grid = []
    for idx in range(int(math.floor((c_min + 900) / 50)), int(math.ceil((c_max + 900) / 50)) + 1):
        nn = name_from_index(idx)
        grid.append({"c": qt_index_to_cents(idx), "label": f"{nn.solfege} {nn.western}",
                     "scale": (idx % 24) in scale_pcs, "tonic": idx % 24 == b.tonic,
                     "qt": nn.quarter_tone})
    r = res.rhythm
    return {
        "title": res.title,
        "source_url": res.source_url,
        "duration": round(res.duration, 3),
        "warnings": res.warnings,
        "tuning": res.tuning.describe(),
        "tuning_cents": round(res.tuning.offset_cents, 1),
        "separation": res.separation_method,
        "engine": res.pitch.engine,
        "organ_model": ORGAN_MODEL,
        "maqam": {
            "name": b.display_name,
            "tonic": b.tonic_text,
            "probability": round(b.probability, 3),
            "fit": round(b.fit, 3),
            "ajnas": b.ajnas_desc(),
            "description": b.maqam.description,
            "color": b.color,
            "alternatives": [c.title() for c in res.maqam.ranking[1:5]
                             if not (c.maqam.key == b.maqam.key and c.tonic == b.tonic)][:3],
            "histogram": [round(float(x), 4) for x in res.maqam.histogram],
            "scale_pcs": b.scale_pcs(),
            "tonic_pc": b.tonic,
        },
        "sections": [{
            "start": round(s.start, 2), "end": round(s.end, 2),
            "name": s.candidate.display_name, "tonic": s.candidate.tonic_text,
            "color": s.candidate.color, "probability": round(s.candidate.probability, 3),
            "alternatives": [a.display_name for a in s.alternatives[:2]],
            "organ": _organ(o),
        } for s, o in zip(res.maqam.sections, res.section_organ)],
        "notes": [{
            "start": round(n.start, 3), "end": round(n.end, 3),
            "solfege": n.name.solfege, "western": n.name.western, "arabic": n.name.arabic,
            "dev": signed(float(n.deviation)), "conf": round(n.confidence, 2),
            "clear": n.clear, "qt": n.name.quarter_tone, "c": qt_index_to_cents(n.index),
        } for n in res.notes],
        "rhythm": {
            "name": r.iqa.name_ar, "name_en": r.iqa.name_en, "meter": r.meter,
            "bpm": round(r.bpm, 1), "confidence": round(r.confidence, 2),
            "cells": r.iqa.cells, "dum": [round(x, 3) for x in r.dum_profile],
            "tak": [round(x, 3) for x in r.tak_profile], "style": r.iqa.organ_style,
            "tempo": r.organ_tempo(), "alternatives": [a[0] for a in r.alternatives],
            "found": r.percussion_found,
        },
        "organ": _organ(res.organ),
        "melody": _melody(res),
        "grid": grid,
        "c_min": c_min, "c_max": c_max,
        "stems": [{"key": k, "label": STEM_LABELS[k]}
                  for k in ("mix", "piano_song", "piano_band", "piano", "vocals",
                            "instruments", "drums")
                  if k in res.playback],
        "score": _score(res),
    }


def _score(res):
    sc = getattr(res, "score", None)
    if sc is None:
        return None
    from ..notes import midi_from_cents

    notes = []
    for n in sc.notes:
        midi, bend = midi_from_cents(qt_index_to_cents(n.index))
        nn = n.name
        notes.append({"s": round(n.start, 3), "e": round(n.end, 3), "ids": n.ids,
                      "key": midi, "bend": int(round(bend)), "solfege": nn.solfege,
                      "western": nn.western})
    return {"pages": len(sc.svg_pages), "bpm": round(sc.bpm), "meter": sc.meter,
            "notes": notes}
