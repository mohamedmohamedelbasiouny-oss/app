"""المرحلة 1: تحميل الصوت — أي صيغة صوت (وحتى ملفات الفيديو).

بنستخدم soundfile للصيغ اللي بيدعمها مباشرة (WAV, FLAC, OGG, AIFF ...)،
ولأي صيغة تانية (MP3, M4A, AAC, OPUS, WMA, AMR, APE, AC3, MP4, MKV, WEBM ...)
بنفك التشفير بـ ffmpeg المرفق مع البرنامج.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import paths

# امتدادات الصوت والفيديو المقبولة في نافذة الفتح وفي السحب والإفلات
AUDIO_EXTENSIONS = [
    "mp3", "wav", "wave", "m4a", "flac", "aac", "ogg", "oga", "opus", "wma",
    "aif", "aiff", "aifc", "amr", "ape", "wv", "ac3", "eac3", "dts", "mka",
    "alac", "caf", "au", "snd", "mp2", "mpa", "m4b", "m4r", "3gp", "3ga",
    "webm", "weba", "spx", "tta", "ra", "rm", "voc", "w64", "rf64", "mid_",
    # فيديو — بناخد منه الصوت
    "mp4", "mkv", "mov", "avi", "wmv", "flv", "m4v", "ts", "mts", "mpg", "mpeg",
]
AUDIO_EXTENSIONS = [e for e in AUDIO_EXTENSIONS if not e.endswith("_")]

_SOUNDFILE_EXT = {"wav", "wave", "flac", "ogg", "oga", "aif", "aiff", "aifc",
                  "au", "snd", "w64", "rf64", "caf", "voc"}

ANALYSIS_SR = 22050     # معدل العينات للتحليل
SEPARATION_SR = 44100   # Demucs شغال على 44.1 كيلو


@dataclass
class AudioData:
    y: np.ndarray        # (channels, samples) float32
    sr: int
    path: Path

    @property
    def duration(self) -> float:
        return self.y.shape[-1] / float(self.sr)

    def mono(self) -> np.ndarray:
        return self.y.mean(axis=0) if self.y.ndim == 2 else self.y


def file_filter() -> str:
    pats = " ".join(f"*.{e}" for e in AUDIO_EXTENSIONS)
    return f"ملفات الصوت ({pats});;كل الملفات (*.*)"


def is_supported(path: str | Path) -> bool:
    return Path(path).suffix.lower().lstrip(".") in AUDIO_EXTENSIONS


def _creation_flags() -> int:
    # عشان ما يظهرش شباك كونسول أسود على ويندوز
    return 0x08000000 if sys.platform == "win32" else 0


def _decode_ffmpeg(path: Path, sr: int, channels: int) -> np.ndarray:
    ffmpeg = paths.ffmpeg_exe()
    if not ffmpeg:
        raise RuntimeError("ffmpeg غير موجود — مش قادر أفتح الصيغة دي.")
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(path),
           "-vn", "-f", "f32le", "-acodec", "pcm_f32le", "-ac", str(channels),
           "-ar", str(sr), "pipe:1"]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          creationflags=_creation_flags())
    if proc.returncode != 0 or not proc.stdout:
        err = proc.stderr.decode("utf-8", "ignore").strip()
        raise RuntimeError(f"فشل فك ملف الصوت: {err or 'ملف غير صالح'}")
    data = np.frombuffer(proc.stdout, dtype=np.float32)
    return data.reshape(-1, channels).T.copy()


def _decode_soundfile(path: Path, sr: int, channels: int) -> np.ndarray:
    import soundfile as sf

    data, file_sr = sf.read(str(path), dtype="float32", always_2d=True)
    y = data.T  # (ch, n)
    if channels == 1:
        y = y.mean(axis=0, keepdims=True)
    elif y.shape[0] == 1:
        y = np.repeat(y, channels, axis=0)
    elif y.shape[0] > channels:
        y = y[:channels]
    if file_sr != sr:
        import librosa

        y = librosa.resample(y, orig_sr=file_sr, target_sr=sr, res_type="soxr_hq")
    return np.ascontiguousarray(y, dtype=np.float32)


def load_audio(path: str | Path, sr: int = ANALYSIS_SR, channels: int = 1) -> AudioData:
    """تحميل أي ملف صوت/فيديو كمصفوفة float32."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"الملف مش موجود: {path}")
    ext = path.suffix.lower().lstrip(".")
    y = None
    if ext in _SOUNDFILE_EXT:
        try:
            y = _decode_soundfile(path, sr, channels)
        except Exception:
            y = None
    if y is None:
        y = _decode_ffmpeg(path, sr, channels)
    if y.size == 0:
        raise RuntimeError("الملف مافيهوش صوت.")
    return AudioData(y=y, sr=sr, path=path)


def file_hash(path: str | Path) -> str:
    h = hashlib.sha1()
    p = Path(path)
    st = p.stat()
    h.update(str(p.resolve()).encode())
    h.update(str(st.st_size).encode())
    h.update(str(int(st.st_mtime)).encode())
    return h.hexdigest()[:16]


def write_wav(path: str | Path, y: np.ndarray, sr: int) -> Path:
    import soundfile as sf

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = y.T if y.ndim == 2 else y
    peak = float(np.max(np.abs(arr))) if arr.size else 0.0
    if peak > 1.0:
        arr = arr / peak
    sf.write(str(path), arr, sr, subtype="PCM_16")
    return path


def make_playback_wav(audio_path: str | Path) -> Path:
    """نسخة WAV للتشغيل داخل البرنامج (عشان أي صيغة تشتغل في المشغل)."""
    audio_path = Path(audio_path)
    out = paths.cache_dir() / f"play_{file_hash(audio_path)}.wav"
    if out.exists() and out.stat().st_size > 1000:
        return out
    data = load_audio(audio_path, sr=44100, channels=2)
    return write_wav(out, data.y, data.sr)
