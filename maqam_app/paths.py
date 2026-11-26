"""مسارات البرنامج — بتشتغل سواء من الكود أو من ملف exe (PyInstaller)."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def resource_dir() -> Path:
    """مجلد الملفات المرفقة مع البرنامج (موديلات، أيقونات)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
    """مجلد قابل للكتابة لبيانات المستخدم والكاش."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / "MaqamAnalyzer"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    d = user_data_dir() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def models_dir() -> Path:
    """مجلد موديلات Demucs. الأول بندور على الموديلات المرفقة، وبعدين مجلد المستخدم."""
    bundled = resource_dir() / "models"
    if (bundled / "hf").exists() or (bundled / "hub" / "checkpoints").exists():
        return bundled
    d = user_data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ffmpeg_exe() -> str | None:
    """مسار ffmpeg: المرفق مع البرنامج، أو imageio-ffmpeg، أو اللي على الجهاز."""
    exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    bundled = resource_dir() / "bin" / exe_name
    if bundled.exists():
        return str(bundled)
    try:
        import imageio_ffmpeg

        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and Path(p).exists():
            return p
    except Exception:
        pass
    return shutil.which("ffmpeg")


def setup_runtime_env() -> None:
    """متغيرات بيئة لازمة قبل استيراد librosa/numba/torch."""
    os.environ.setdefault("NUMBA_CACHE_DIR", str(cache_dir() / "numba"))
    md = models_dir()
    os.environ.setdefault("TORCH_HOME", str(md))
    # demucs 4.1 بيحمّل موديلاته من HuggingFace — لو الموديل مرفق نشتغل offline على طول
    os.environ.setdefault("HF_HOME", str(md / "hf"))
    if (md / "hf" / "hub").exists() and any((md / "hf" / "hub").glob("models--*")):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
