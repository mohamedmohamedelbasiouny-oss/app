"""المرحلة 2: فصل الصوت — المطرب / الآلات / الإيقاع.

الأساس: Demucs (htdemucs) — بيطلع 4 مسارات: vocals, drums, bass, other.
  المطرب = vocals، الإيقاع (طبلة/رق) = drums، الآلات = bass + other.
احتياطي: لو Demucs مش متاح أو فشل، بنستخدم فصل HPSS + REPET-SIM من librosa
(أقل دقة بس شغال على أي جهاز).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import paths
from .audio_io import AudioData, write_wav

ProgressCB = Callable[[float, str], None]

STEM_LABELS = {
    "mix": "الأغنية الأصلية",
    "vocals": "صوت المطرب",
    "instruments": "الآلات",
    "drums": "الإيقاع (طبلة ورق)",
}


@dataclass
class Stems:
    sr: int
    vocals: np.ndarray          # (ch, n)
    instruments: np.ndarray
    drums: np.ndarray
    method: str                 # "demucs" أو "hpss"
    files: dict[str, Path] = field(default_factory=dict)

    def mono(self, name: str) -> np.ndarray:
        a = getattr(self, name)
        return a.mean(axis=0) if a.ndim == 2 else a


def demucs_available() -> bool:
    try:
        import torch  # noqa: F401
        import demucs.pretrained  # noqa: F401
        return True
    except Exception:
        return False


def _patch_demucs_progress(progress: ProgressCB | None):
    """Demucs بيستخدم tqdm للتقدم — بنحوّله لإشارة تقدم في الواجهة."""
    import demucs.apply as dapply

    class _TQ:
        @staticmethod
        def tqdm(iterable, **kw):
            items = list(iterable)
            n = max(len(items), 1)
            for i, it in enumerate(items):
                if progress:
                    progress(i / n, f"فصل الصوت بـ Demucs… {i * 100 // n}%")
                yield it

    original = dapply.tqdm
    dapply.tqdm = _TQ
    return lambda: setattr(dapply, "tqdm", original)


def separate_demucs(audio: AudioData, progress: ProgressCB | None = None,
                    model_name: str = "htdemucs", model=None) -> Stems:
    import torch
    from demucs.apply import apply_model

    os.environ["TORCH_HOME"] = str(paths.models_dir())
    torch.hub.set_dir(str(paths.models_dir() / "hub"))
    try:
        torch.set_num_threads(max(1, os.cpu_count() or 1))
    except Exception:
        pass

    if model is None:
        from demucs.pretrained import get_model

        if progress:
            progress(0.0, "تحميل موديل Demucs…")
        model = get_model(model_name)
    model.eval()

    y = audio.y
    if audio.sr != model.samplerate:
        import librosa

        y = librosa.resample(y, orig_sr=audio.sr, target_sr=model.samplerate)
    if y.shape[0] == 1:
        y = np.repeat(y, 2, axis=0)
    y = y[: model.audio_channels]

    wav = torch.from_numpy(np.ascontiguousarray(y, dtype=np.float32))
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    wav_n = (wav - mean) / std

    restore = _patch_demucs_progress(progress)
    try:
        with torch.no_grad():
            out = apply_model(model, wav_n[None], device="cpu", shifts=0, split=True,
                              overlap=0.25, progress=True, num_workers=0)[0]
    finally:
        restore()
    out = out * std + mean
    out = out.cpu().numpy()
    names = list(model.sources)
    get = lambda n: out[names.index(n)] if n in names else np.zeros_like(out[0])  # noqa: E731
    vocals = get("vocals")
    drums = get("drums")
    instruments = get("other") + get("bass")
    if "guitar" in names:
        instruments = instruments + get("guitar")
    if "piano" in names:
        instruments = instruments + get("piano")
    if progress:
        progress(1.0, "خلص فصل الصوت")
    return Stems(sr=int(model.samplerate), vocals=vocals, instruments=instruments,
                 drums=drums, method="demucs")


def separate_hpss(audio: AudioData, progress: ProgressCB | None = None) -> Stems:
    """فصل احتياطي بدون ذكاء اصطناعي: HPSS للإيقاع، و REPET-SIM لصوت المطرب."""
    import librosa

    n_fft, hop = 2048, 512
    y_mono = audio.mono()
    if progress:
        progress(0.05, "فصل الإيقاع عن اللحن (HPSS)…")
    S_m = librosa.stft(y_mono, n_fft=n_fft, hop_length=hop)
    H_m, P_m = librosa.decompose.hpss(S_m, margin=(1.0, 2.0))
    mag = np.abs(H_m)
    mask_p = np.abs(P_m) / (np.abs(P_m) + mag + 1e-9)

    # REPET-SIM على أجزاء 30 ثانية (أسرع بكتير من الأغنية كلها مرة واحدة)
    block = int(librosa.time_to_frames(30.0, sr=audio.sr, hop_length=hop))
    mask_v = np.zeros_like(mag)
    n = mag.shape[1]
    for i, a in enumerate(range(0, n, block)):
        if progress:
            progress(0.2 + 0.7 * a / max(n, 1), "عزل صوت المطرب (REPET-SIM)…")
        m = mag[:, a:a + block]
        width = max(3, min(int(librosa.time_to_frames(2.0, sr=audio.sr, hop_length=hop)),
                           m.shape[1] // 2 - 1))
        try:
            filt = librosa.decompose.nn_filter(m, aggregate=np.median, metric="cosine",
                                               width=width)
        except Exception:
            filt = m
        filt = np.minimum(m, filt)
        mask_v[:, a:a + block] = librosa.util.softmask(m - filt, 10 * filt, power=2)

    chans_v, chans_h, chans_p = [], [], []
    for ch in range(audio.y.shape[0]):
        y = audio.y[ch]
        S = librosa.stft(y, n_fft=n_fft, hop_length=hop)
        P = S * mask_p
        H = S - P
        V = H * mask_v
        chans_v.append(librosa.istft(V, hop_length=hop, length=len(y)))
        chans_h.append(librosa.istft(H - V, hop_length=hop, length=len(y)))
        chans_p.append(librosa.istft(P, hop_length=hop, length=len(y)))
    if progress:
        progress(1.0, "خلص الفصل")
    return Stems(sr=audio.sr, vocals=np.array(chans_v, dtype=np.float32),
                 instruments=np.array(chans_h, dtype=np.float32),
                 drums=np.array(chans_p, dtype=np.float32), method="hpss")


def separate(audio: AudioData, use_demucs: bool = True,
             progress: ProgressCB | None = None) -> tuple[Stems, str | None]:
    """يرجع (المسارات، رسالة تحذير لو رجعنا للطريقة الاحتياطية)."""
    warning = None
    if use_demucs and demucs_available():
        try:
            return separate_demucs(audio, progress), None
        except Exception as e:  # مثلاً الموديل مش موجود ومافيش إنترنت
            warning = f"Demucs فشل ({e}) — استخدمت الفصل الاحتياطي HPSS."
    elif use_demucs:
        warning = "Demucs مش متثبت — استخدمت الفصل الاحتياطي HPSS."
    return separate_hpss(audio, progress), warning


def save_stems(stems: Stems, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in ("vocals", "instruments", "drums"):
        files[name] = write_wav(out_dir / f"{name}.wav", getattr(stems, name), stems.sr)
    stems.files = files
    return files
