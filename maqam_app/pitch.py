"""المرحلة 3: استخراج خط اللحن (pitch) بدقة عالية.

المحركات:
- CREPE (torchcrepe, موديل full) — الأدق، شغال بـ PyTorch.
- pYIN (librosa) — احتياطي من غير شبكات عصبية.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.ndimage import median_filter

ProgressCB = Callable[[float, str], None]

FMIN = 65.0     # تقريبًا C2
FMAX = 1400.0   # تقريبًا F6


@dataclass
class PitchTrack:
    times: np.ndarray       # ثواني
    f0: np.ndarray          # هرتز (nan لو مافيش صوت)
    confidence: np.ndarray  # 0..1
    engine: str

    @property
    def voiced(self) -> np.ndarray:
        return np.isfinite(self.f0)

    @property
    def hop_s(self) -> float:
        return float(self.times[1] - self.times[0]) if len(self.times) > 1 else 0.01


def crepe_available() -> bool:
    try:
        import torch  # noqa: F401
        import torchcrepe  # noqa: F401
        return True
    except Exception:
        return False


def _rms_gate(y: np.ndarray, sr: int, hop: int, n_frames: int) -> np.ndarray:
    import librosa

    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop, center=True)[0]
    rms = np.pad(rms, (0, max(0, n_frames - len(rms))))[:n_frames]
    ref = np.percentile(rms[rms > 0], 95) if np.any(rms > 0) else 1.0
    db = 20 * np.log10(np.maximum(rms, 1e-9) / max(ref, 1e-9))
    return db > -40.0


def _clean(f0: np.ndarray, conf: np.ndarray, thr: float) -> np.ndarray:
    f0 = f0.astype(float).copy()
    f0[(conf < thr) | ~np.isfinite(f0) | (f0 <= 0)] = np.nan
    # إزالة قفزات الأوكتاف المنفردة (frame أو اتنين)
    c = 1200 * np.log2(np.where(np.isfinite(f0), f0, 1.0) / 440.0)
    med = median_filter(c, size=5, mode="nearest")
    jump = np.abs(c - med) > 600
    f0[jump & np.isfinite(f0)] = np.nan
    return f0


def _active_regions(y: np.ndarray, sr: int, hop: int, min_gap_s: float = 0.4,
                   pad_s: float = 0.1) -> list[tuple[int, int]]:
    """الأجزاء اللي فيها صوت فعلاً (بالعينات) — عشان ما نضيعش وقت على السكوت."""
    import librosa

    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop, center=True)[0]
    if not np.any(rms > 0):
        return []
    ref = np.percentile(rms[rms > 0], 95)
    act = 20 * np.log10(np.maximum(rms, 1e-9) / max(ref, 1e-9)) > -40.0
    regions = []
    gap = int(min_gap_s * sr / hop)
    pad = int(pad_s * sr / hop)
    i, n = 0, len(act)
    while i < n:
        if not act[i]:
            i += 1
            continue
        j = i
        while j < n:
            if act[j]:
                j += 1
                continue
            k = j
            while k < n and not act[k] and k - j < gap:
                k += 1
            if k < n and act[k] and k - j < gap:
                j = k
                continue
            break
        regions.append((max(0, (i - pad) * hop), min(len(y), (j + pad) * hop)))
        i = j + 1
    return regions


def _viterbi_refined(logits):
    """Viterbi (لحن ناعم من غير قفزات) + متوسط موزون حوالين النتيجة عشان دقة أقل من 20 cent.

    الـ Viterbi العادي في torchcrepe بيرجع مركز الخانة بس (كل خانة 20 cent)، وده مش
    كفاية لاكتشاف الضبط والربع تون، فبنحسب المتوسط الموزون حوالين الخانة المختارة.
    """
    import torch
    import torchcrepe

    bins, _ = torchcrepe.decode.viterbi(logits)
    with torch.no_grad():
        # تفعيل CREPE على شكل جرس (Gaussian) حوالين النغمة، فبنفيت قطع مكافئ على
        # log الاحتمال في 3 خانات حوالين الـ Viterbi — ده بيشيل انحياز شبكة الـ 20 cent.
        logp = torch.nn.functional.logsigmoid(logits)            # (B, 360, T)
        n = logits.size(1)
        b0 = bins.clamp(1, n - 2)
        lm = torch.gather(logp, 1, (b0 - 1)[:, None, :])[:, 0]
        l0 = torch.gather(logp, 1, b0[:, None, :])[:, 0]
        lp = torch.gather(logp, 1, (b0 + 1)[:, None, :])[:, 0]
        den = lm - 2 * l0 + lp
        delta = torch.where(den < -1e-6, 0.5 * (lm - lp) / den, torch.zeros_like(den))
        delta = delta.clamp(-0.5, 0.5)
        c = torchcrepe.convert.bins_to_cents(b0) + delta * torchcrepe.CENTS_PER_BIN
    return bins, torchcrepe.convert.cents_to_frequency(c)


def track_crepe(y: np.ndarray, sr: int, progress: ProgressCB | None = None,
                model: str = "full", hop_s: float = 0.02) -> PitchTrack:
    import librosa
    import torch
    import torchcrepe

    target_sr = 16000
    if sr != target_sr:
        y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
    y = np.ascontiguousarray(y, dtype=np.float32)
    hop = int(target_sr * hop_s)
    n_frames = int(np.ceil(len(y) / hop))
    f0 = np.full(n_frames, np.nan)
    per = np.zeros(n_frames)

    # بنحلل الأجزاء اللي فيها صوت بس، وكل جزء طويل بنقسمه 30 ثانية
    regions = _active_regions(y, target_sr, hop)
    chunks = []
    max_len = target_sr * 30
    for a, b in regions:
        a = (a // hop) * hop
        while a < b:
            chunks.append((a, min(b, a + max_len)))
            a += max_len
    total = sum(b - a for a, b in chunks) or 1
    done = 0
    try:
        torch.set_num_threads(max(1, __import__("os").cpu_count() or 1))
    except Exception:
        pass
    with torch.no_grad():
        for a, b in chunks:
            if b - a < 1024:
                continue
            if progress:
                progress(done / total, f"استخراج اللحن (CREPE {model})… {done * 100 // total}%")
            seg = torch.from_numpy(y[a:b])[None]
            pf, pp = torchcrepe.predict(
                seg, target_sr, hop, FMIN, FMAX, model=model, batch_size=512,
                device="cpu", return_periodicity=True, decoder=_viterbi_refined,
                pad=True)
            pp = torchcrepe.filter.median(pp, 3)
            k0 = a // hop
            m = min(pf.shape[-1], n_frames - k0)
            f0[k0:k0 + m] = pf[0, :m].numpy()
            per[k0:k0 + m] = pp[0, :m].numpy()
            done += b - a
    gate = _rms_gate(y, target_sr, hop, n_frames)
    per = np.where(gate, per, 0.0)
    times = np.arange(n_frames) * hop / target_sr
    if progress:
        progress(1.0, "خلص استخراج اللحن")
    name = "CREPE" if model == "full" else f"CREPE-{model}"
    return PitchTrack(times=times, f0=_clean(f0, per, 0.45), confidence=per, engine=name)


def track_pyin(y: np.ndarray, sr: int, progress: ProgressCB | None = None) -> PitchTrack:
    import librosa

    hop = 256 if sr <= 22050 else 512
    if progress:
        progress(0.05, "استخراج اللحن (pYIN)…")
    # بنقسم الأغنية أجزاء عشان نقدر نعرض التقدم
    seg_len = sr * 30
    n = int(np.ceil(len(y) / seg_len)) or 1
    f0s, probs = [], []
    for i in range(n):
        seg = y[i * seg_len:(i + 1) * seg_len]
        if len(seg) < 2048:
            pad = np.zeros(2048 - len(seg), dtype=seg.dtype)
            seg = np.concatenate([seg, pad])
        f0, vflag, vprob = librosa.pyin(seg, fmin=FMIN, fmax=FMAX, sr=sr, frame_length=2048,
                                        hop_length=hop, resolution=0.1, center=True)
        expected = int(np.ceil(min(seg_len, len(y) - i * seg_len) / hop))
        f0s.append(f0[:max(expected, 1)])
        probs.append(np.where(vflag, vprob, 0.0)[:max(expected, 1)])
        if progress:
            progress((i + 1) / n, f"استخراج اللحن (pYIN)… {(i + 1) * 100 // n}%")
    f0 = np.concatenate(f0s)
    conf = np.concatenate(probs)
    times = np.arange(len(f0)) * hop / sr
    return PitchTrack(times=times, f0=_clean(f0, conf, 0.3), confidence=conf, engine="pYIN")


def track(y: np.ndarray, sr: int, engine: str = "auto",
          progress: ProgressCB | None = None) -> PitchTrack:
    if engine in ("auto", "crepe", "crepe-tiny") and crepe_available():
        try:
            # "auto" = السريع (tiny) — أسرع بحوالي 10 مرات؛ "crepe" = الدقيق (full)
            model = "full" if engine == "crepe" else "tiny"
            return track_crepe(y, sr, progress, model=model,
                               hop_s=0.01 if model == "tiny" else 0.02)
        except Exception:
            if engine.startswith("crepe"):
                raise
    return track_pyin(y, sr, progress)
