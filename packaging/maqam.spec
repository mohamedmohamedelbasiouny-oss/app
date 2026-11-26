# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — بيتشغل من جذر المشروع:  pyinstaller packaging/maqam.spec --noconfirm
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
PKG = ROOT / "packaging"

datas = []
for pkg in ("librosa", "demucs", "torchcrepe", "yt_dlp_ejs", "lazy_loader", "resampy"):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass
datas += [(str(PKG / "icon.ico"), "packaging"), (str(PKG / "icon.png"), "packaging")]
if (PKG / "models").exists():
    datas += [(str(PKG / "models"), "models")]

binaries = []
if (PKG / "bin").exists():
    for f in (PKG / "bin").iterdir():
        binaries.append((str(f), "bin"))

hiddenimports = []
for pkg in ("yt_dlp", "demucs", "torchcrepe", "julius", "openunmix", "einops", "mido",
            "sklearn.utils", "soxr", "maqam_app", "huggingface_hub", "safetensors"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass
hiddenimports += ["mido.backends.rtmidi", "scipy.special.cython_special"]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "jupyter", "notebook", "tensorboard",
              "torch.utils.tensorboard", "pytest", "PyQt5", "PyQt6", "tensorflow"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MaqamAnalyzer",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(PKG / "icon.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MaqamAnalyzer",
)
