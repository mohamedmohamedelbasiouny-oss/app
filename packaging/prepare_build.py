"""تجهيز الملفات اللي بتتحط جوه البرنامج قبل PyInstaller:
- موديل Demucs (htdemucs) في packaging/models/hub/checkpoints
- ffmpeg و deno في packaging/bin
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    models = HERE / "models"
    models.mkdir(exist_ok=True)
    os.environ["TORCH_HOME"] = str(models)
    import torch

    torch.hub.set_dir(str(models / "hub"))
    from demucs.pretrained import get_model

    m = get_model("htdemucs")
    print("Demucs:", type(m).__name__, "sources:", getattr(m, "sources", None))
    ckpts = list((models / "hub" / "checkpoints").glob("*.th"))
    assert ckpts, "مفيش موديل Demucs اتحمّل"
    print("checkpoints:", [c.name for c in ckpts])

    bindir = HERE / "bin"
    bindir.mkdir(exist_ok=True)
    import imageio_ffmpeg

    ff = Path(imageio_ffmpeg.get_ffmpeg_exe())
    shutil.copy2(ff, bindir / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"))
    print("ffmpeg:", ff)

    import deno

    dn = Path(deno.find_deno_bin())
    shutil.copy2(dn, bindir / ("deno.exe" if sys.platform == "win32" else "deno"))
    print("deno:", dn)


if __name__ == "__main__":
    main()
