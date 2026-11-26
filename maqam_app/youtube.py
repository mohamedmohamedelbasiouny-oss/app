"""تحميل الصوت من لينك (يوتيوب أو أي موقع بيدعمه yt-dlp: ساوند كلاود، فيسبوك ...).

بننزل أحسن جودة صوت متاحة في مجلد الكاش، وبعدين بنفكها بـ ffmpeg زي أي ملف عادي.
لو اللينك اتحمّل قبل كده بنستخدم النسخة المحفوظة على طول.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Callable

from . import paths

ProgressCB = Callable[[float, str], None]

_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_YT_RE = re.compile(
    r"(youtube\.com/(watch\?|shorts/|live/|embed/)|youtu\.be/|music\.youtube\.com/)",
    re.IGNORECASE,
)


def is_url(text: str) -> bool:
    return bool(_URL_RE.match((text or "").strip()))


def is_youtube(text: str) -> bool:
    return bool(_YT_RE.search(text or ""))


def normalize_url(url: str) -> str:
    url = url.strip()
    if url.startswith("www.") or url.startswith("youtu"):
        url = "https://" + url
    return url


def _downloads_dir() -> Path:
    d = paths.user_data_dir() / "downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _url_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _deno_path() -> str | None:
    exe = "deno.exe" if sys.platform == "win32" else "deno"
    bundled = paths.resource_dir() / "bin" / exe
    if bundled.exists():
        return str(bundled)
    try:
        import deno  # type: ignore

        p = deno.find_deno_bin()
        if p and Path(p).exists():
            return str(p)
    except Exception:
        pass
    return shutil.which("deno")


class _QuietLogger:
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


def download_audio(url: str, progress: ProgressCB | None = None) -> tuple[Path, str]:
    """ينزّل الصوت من اللينك ويرجع (مسار الملف، عنوان الأغنية)."""
    url = normalize_url(url)
    if not is_url(url):
        raise ValueError("اللينك مش صحيح — لازم يبدأ بـ http أو https.")

    key = _url_key(url)
    meta_file = _downloads_dir() / f"{key}.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            p = Path(meta["path"])
            if p.exists() and p.stat().st_size > 0:
                if progress:
                    progress(1.0, "الأغنية متحمّلة قبل كده")
                return p, meta.get("title", p.stem)
        except Exception:
            pass

    import yt_dlp

    def hook(d):
        if not progress:
            return
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            frac = (done / total) if total else 0.0
            progress(min(frac, 0.99), f"تحميل من اللينك… {frac * 100:.0f}%")
        elif d.get("status") == "finished":
            progress(1.0, "خلص التحميل")

    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(_downloads_dir() / f"{key}.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _QuietLogger(),
        "progress_hooks": [hook],
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
        "overwrites": True,
    }
    ff = paths.ffmpeg_exe()
    if ff:
        opts["ffmpeg_location"] = ff
    deno = _deno_path()
    if deno:
        opts["js_runtimes"] = {"deno": {"path": deno}}

    if progress:
        progress(0.0, "جاري قراءة بيانات اللينك…")
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise RuntimeError("مافيش بيانات للينك ده.")
            if "entries" in info and info["entries"]:
                info = info["entries"][0]
            filename = Path(ydl.prepare_filename(info))
    except Exception as e:  # yt_dlp.utils.DownloadError وغيرها
        msg = str(e)
        msg = re.sub(r"\x1b\[[0-9;]*m", "", msg)
        raise RuntimeError(f"مش قادر أحمّل من اللينك:\n{msg}") from e

    if not filename.exists():
        # أحيانًا الامتداد بيتغير بعد التحميل
        cands = sorted(_downloads_dir().glob(f"{key}.*"))
        cands = [c for c in cands if c.suffix not in (".json", ".part", ".ytdl")]
        if not cands:
            raise RuntimeError("التحميل خلص بس الملف مش موجود.")
        filename = cands[0]

    title = info.get("title") or filename.stem
    meta_file.write_text(json.dumps({"path": str(filename), "title": title, "url": url},
                                    ensure_ascii=False), encoding="utf-8")
    return filename, title
