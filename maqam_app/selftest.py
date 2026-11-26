"""فحص ذاتي للبرنامج بعد البناء: MaqamAnalyzer.exe --selftest [مسار_ملف_النتيجة.json]

بيولّد أغنية تجريبية (بياتي على الدوكاه + إيقاع مقسوم 100، متسجلة على لا=446)
وبيشغل التحليل كله (Demucs + CREPE) ويتأكد من النتايج، ويصدّر PDF و MIDI.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path


def run(out_path: str | None = None) -> int:
    report: dict = {"ok": False}
    try:
        import numpy as np
        import soundfile as sf

        from . import paths
        from .maqam_db import MAQAM_BY_KEY
        from .pipeline import Settings, analyze_file
        from .separation import demucs_available
        from .synth import SR, maqam_melody, percussion

        work = paths.cache_dir() / "selftest"
        work.mkdir(parents=True, exist_ok=True)
        mel = maqam_melody(MAQAM_BY_KEY["bayati"].scale, 4, n_phrases=8, ref_hz=446.0)
        y = mel + percussion("maqsum", 100, len(mel) / SR)[: len(mel)]
        wav = work / "selftest.wav"
        sf.write(wav, np.stack([y, y], axis=1), SR)
        report["demucs_available"] = demucs_available()
        report["ffmpeg"] = paths.ffmpeg_exe()

        # MP3 عشان نختبر فك الصيغ بـ ffmpeg كمان
        import subprocess
        mp3 = work / "selftest.mp3"
        subprocess.run([paths.ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(wav), str(mp3)],
                       check=True, creationflags=0x08000000 if sys.platform == "win32" else 0)

        t = time.time()
        res = analyze_file(mp3, Settings(use_demucs=True, pitch_engine="auto"))
        report["seconds"] = round(time.time() - t, 1)
        b = res.maqam.global_best
        report.update({
            "maqam": b.maqam.key, "tonic": b.tonic, "rhythm": res.rhythm.iqa.key,
            "bpm": round(res.rhythm.bpm, 1), "tuning_cents": round(res.tuning.offset_cents, 1),
            "separation": res.separation_method, "engine": res.pitch.engine,
            "notes": len(res.notes), "warnings": res.warnings,
        })
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication(sys.argv[:1])  # noqa: F841
        from .midi_export import export_midi
        from .report import export_pdf

        export_pdf(res, work / "selftest.pdf")
        export_midi(res.notes, work / "selftest.mid", bpm=res.rhythm.bpm)
        checks = {
            "maqam": b.maqam.key == "bayati" and b.tonic == 4,
            "rhythm": res.rhythm.iqa.key == "maqsum" and abs(res.rhythm.bpm - 100) < 5,
            "tuning": abs(res.tuning.offset_cents - 23.6) < 10,
            "demucs": res.separation_method == "demucs",
            "pdf": (work / "selftest.pdf").stat().st_size > 10000,
        }
        report["checks"] = checks
        report["ok"] = all(checks.values())
    except Exception:
        report["error"] = traceback.format_exc()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
    try:
        print(text)
    except Exception:
        pass
    return 0 if report.get("ok") else 1
