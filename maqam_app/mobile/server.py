"""وضع الموبايل: سيرفر صغير جوه البرنامج بيفتح صفحة ويب على الآيفون (Safari).

الموبايل والكمبيوتر لازم يكونوا على نفس الواي فاي (أو على Tailscale من برة البيت).
كل الطلبات محمية بكود سري (token) موجود في الـ QR — اللي مش معاه الكود مش هيقدر يدخل.
التحليل نفسه بيحصل على الكمبيوتر، والموبايل بيعرض النتيجة ويشغّل الصوت.
"""
from __future__ import annotations

import json
import mimetypes
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from .. import APP_NAME, __version__, paths

STATIC = Path(__file__).resolve().parent / "static"
DEFAULT_PORT = 8765
MAX_UPLOAD = 1024 * 1024 * 1024  # 1 جيجا


def _token_file() -> Path:
    return paths.user_data_dir() / "mobile_token.txt"


def load_token() -> str:
    """الكود السري ثابت بين مرات التشغيل عشان اختصار الشاشة الرئيسية يفضل شغال."""
    f = _token_file()
    try:
        t = f.read_text(encoding="utf-8").strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{8,64}", t):
            return t
    except Exception:
        pass
    t = secrets.token_urlsafe(9)
    try:
        f.write_text(t, encoding="utf-8")
    except Exception:
        pass
    return t


def reset_token() -> str:
    try:
        _token_file().unlink()
    except Exception:
        pass
    return load_token()


def local_ips() -> list[str]:
    """عناوين الكمبيوتر على الشبكة (واي فاي / كابل / Tailscale)."""
    ips: list[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))   # مش بيبعت حاجة فعلاً
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    ips = [ip for ip in ips if not ip.startswith("127.") and not ip.startswith("169.254.")]

    def rank(ip):
        if ip.startswith("192.168.") or ip.startswith("10."):
            return 0
        if ip.startswith("172."):
            return 1
        if ip.startswith("100."):    # Tailscale
            return 2
        return 3
    return sorted(ips, key=rank) or ["127.0.0.1"]


def _creation_flags() -> int:
    return 0x08000000 if sys.platform == "win32" else 0


class MobileServer:
    def __init__(self, settings_provider: Callable[[], object] | None = None,
                 on_result: Callable[[object], None] | None = None,
                 is_busy_external: Callable[[], bool] | None = None,
                 gui_call: Callable[[Callable], object] | None = None):
        self.settings_provider = settings_provider
        self.on_result = on_result
        self.is_busy_external = is_busy_external or (lambda: False)
        self.gui_call = gui_call or (lambda fn: fn())
        self.token = load_token()
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.port = 0
        self.lock = threading.RLock()
        self.result = None
        self.result_json: bytes | None = None
        self.version = 0
        self.job = {"state": "idle", "progress": 0.0, "message": "", "error": "",
                    "title": ""}
        self._cancel = False
        self._job_thread: threading.Thread | None = None

    # ------------------------------------------------------------ تشغيل / إيقاف
    @property
    def running(self) -> bool:
        return self.httpd is not None

    def start(self, port: int = DEFAULT_PORT, host: str = "0.0.0.0") -> int:
        if self.httpd:
            return self.port
        last_err = None
        for p in [port] + list(range(port + 1, port + 15)):
            try:
                httpd = ThreadingHTTPServer((host, p), _make_handler(self))
                httpd.daemon_threads = True
                self.httpd = httpd
                self.port = httpd.server_address[1]
                break
            except OSError as e:
                last_err = e
        if not self.httpd:
            raise RuntimeError(f"مش قادر أفتح بورت للموبايل: {last_err}")
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="mobile-server",
                                       daemon=True)
        self.thread.start()
        return self.port

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        self.httpd = None
        self.thread = None

    def urls(self) -> list[str]:
        return [f"http://{ip}:{self.port}/?t={self.token}" for ip in local_ips()]

    def new_token(self):
        self.token = reset_token()

    # ------------------------------------------------------------ النتيجة الحالية
    def set_result(self, res):
        """بتتنادى من البرنامج على الكمبيوتر كمان — فالموبايل بيشوف آخر تحليل في الحالتين."""
        from .serialize import result_to_json

        data = json.dumps(result_to_json(res), ensure_ascii=False).encode("utf-8")
        with self.lock:
            self.result = res
            self.result_json = data
            self.version += 1
        threading.Thread(target=self._prepare_audio, args=(res, "mix"), daemon=True).start()

    def state(self) -> dict:
        with self.lock:
            return {
                "app": APP_NAME, "app_version": __version__,
                "job": dict(self.job), "version": self.version,
                "has_result": self.result is not None,
                "title": self.result.title if self.result is not None else "",
                "busy_external": bool(self.is_busy_external()),
            }

    # ------------------------------------------------------------ التحليل من الموبايل
    def start_job(self, source: str, is_url: bool, title: str = "") -> tuple[bool, str]:
        with self.lock:
            if self.job["state"] == "running":
                return False, "فيه تحليل شغال دلوقتي من الموبايل — استنى لما يخلص."
            if self.is_busy_external():
                return False, "الكمبيوتر بيحلل أغنية تانية دلوقتي — استنى لما يخلص."
            self._cancel = False
            self.job = {"state": "running", "progress": 0.0, "message": "بدء التحليل…",
                        "error": "", "title": title}
        self._job_thread = threading.Thread(target=self._run_job, args=(source, is_url),
                                            daemon=True)
        self._job_thread.start()
        return True, ""

    def cancel_job(self):
        self._cancel = True

    def _run_job(self, source: str, is_url: bool):
        from ..pipeline import Cancelled, Settings, analyze_file, analyze_url

        def progress(f, msg):
            with self.lock:
                self.job["progress"] = float(f)
                self.job["message"] = str(msg)

        settings = self.settings_provider() if self.settings_provider else Settings()
        try:
            if is_url:
                res = analyze_url(source, settings, progress, cancel=lambda: self._cancel)
            else:
                res = analyze_file(source, settings, progress, cancel=lambda: self._cancel)
            self.set_result(res)
            with self.lock:
                self.job.update(state="done", progress=1.0, message="خلص التحليل",
                                title=res.title)
            if self.on_result:
                try:
                    self.on_result(res)
                except Exception:
                    pass
        except Cancelled:
            with self.lock:
                self.job.update(state="idle", message="اتلغى", progress=0.0)
        except Exception as e:
            try:
                with open(paths.user_data_dir() / "errors.log", "a", encoding="utf-8") as f:
                    f.write("[mobile] " + traceback.format_exc() + "\n" + "-" * 60 + "\n")
            except Exception:
                pass
            with self.lock:
                self.job.update(state="error", error=str(e).split("\n\n")[0])

    # ------------------------------------------------------------ الصوت (AAC للآيفون)
    _audio_lock = threading.Lock()

    def _prepare_audio(self, res, stem: str) -> Path | None:
        """Safari على الآيفون بيشغّل WAV، بس AAC أصغر بكتير على الواي فاي."""
        src = res.playback.get(stem)
        if not src or not Path(src).exists():
            return None
        out = paths.cache_dir() / f"m_{Path(src).parent.name}_{Path(src).stem}.m4a"
        with self._audio_lock:   # عشان طلبين في نفس الوقت ما يحوّلوش نفس الملف
            if out.exists() and out.stat().st_size > 1000 and \
                    out.stat().st_mtime >= Path(src).stat().st_mtime:
                return out
            ff = paths.ffmpeg_exe()
            if not ff:
                return Path(src)
            tmp = out.with_name(out.stem + f".{threading.get_ident()}.tmp.m4a")
            r = subprocess.run([ff, "-y", "-nostdin", "-loglevel", "error", "-i", str(src),
                                "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                                str(tmp)], capture_output=True, creationflags=_creation_flags())
            if r.returncode != 0 or not tmp.exists():
                tmp.unlink(missing_ok=True)
                return Path(src)
            tmp.replace(out)
            return out

    def audio_file(self, stem: str) -> Path | None:
        with self.lock:
            res = self.result
        if res is None:
            return None
        return self._prepare_audio(res, stem)


# ====================================================================== HTTP

def _make_handler(srv: MobileServer):
    class Handler(BaseHTTPRequestHandler):
        server_version = "MaqamAnalyzer"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # من غير كتابة على الكونسول
            pass

        # -------------------------------------------------- أدوات
        def _query(self):
            return urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)

        def _path(self):
            return urllib.parse.urlsplit(self.path).path

        def _authorized(self) -> bool:
            tok = (self._query().get("t") or [""])[0] or self.headers.get("X-Token", "")
            if not tok:
                m = re.search(r"(?:^|;\s*)mt=([^;]+)", self.headers.get("Cookie", ""))
                tok = m.group(1) if m else ""
            return bool(tok) and secrets.compare_digest(tok, srv.token)

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _forbidden(self):
            body = ("<html dir='rtl'><body style='background:#161618;color:#eee;font-family:"
                    "-apple-system,sans-serif;padding:40px;text-align:center'>"
                    "<h2>محتاج الكود السري</h2><p>افتح الصفحة من الـ QR اللي في البرنامج على "
                    "الكمبيوتر (زرار الموبايل).</p></body></html>").encode("utf-8")
            self._send(403, body, "text/html; charset=utf-8")

        def _read_body(self, limit: int) -> bytes:
            n = int(self.headers.get("Content-Length") or 0)
            if n > limit:
                raise ValueError("الملف كبير أوي")
            return self.rfile.read(n) if n else b""

        def _send_file(self, path: Path, ctype: str | None = None, download: str | None = None):
            size = path.stat().st_size
            ctype = ctype or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            start, end = 0, size - 1
            rng = self.headers.get("Range")
            code = 200
            if rng:
                m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
                if m:
                    if m.group(1):
                        start = int(m.group(1))
                        if m.group(2):
                            end = min(int(m.group(2)), size - 1)
                    elif m.group(2):  # آخر N بايت
                        start = max(0, size - int(m.group(2)))
                    if start > end or start >= size:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    code = 206
            length = end - start + 1
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-cache")
            if code == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            if download:
                q = urllib.parse.quote(download)
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{q}")
            self.end_headers()
            if self.command == "HEAD":
                return
            with open(path, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(256 * 1024, left))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    left -= len(chunk)

        # -------------------------------------------------- GET
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            try:
                self._route_get()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                try:
                    with open(paths.user_data_dir() / "errors.log", "a", encoding="utf-8") as f:
                        f.write(f"[mobile GET {self.path.split('?')[0]}] " + traceback.format_exc()
                                + "\n" + "-" * 60 + "\n")
                except Exception:
                    pass
                try:
                    self._json({"error": str(e)}, 500)
                except Exception:
                    pass

        def _route_get(self):
            p = self._path()
            if p in ("/", "/index.html"):
                if not self._authorized():
                    return self._forbidden()
                html = (STATIC / "index.html").read_bytes()
                return self._send(200, html, "text/html; charset=utf-8", {
                    "Set-Cookie": f"mt={srv.token}; Max-Age=31536000; Path=/; SameSite=Lax"})
            if p == "/manifest.webmanifest":
                man = {
                    "name": APP_NAME, "short_name": "المقامات", "dir": "rtl", "lang": "ar",
                    "start_url": f"/?t={srv.token}", "display": "standalone",
                    "background_color": "#161618", "theme_color": "#161618",
                    "icons": [{"src": "/icon.png", "sizes": "512x512", "type": "image/png"}],
                }
                return self._send(200, json.dumps(man, ensure_ascii=False).encode("utf-8"),
                                  "application/manifest+json")
            if p in ("/icon.png", "/apple-touch-icon.png"):
                ic = paths.resource_dir() / "packaging" / "icon.png"
                if ic.exists():
                    return self._send_file(ic, "image/png")
                return self._send(404, b"", "text/plain")
            if not self._authorized():
                return self._json({"error": "unauthorized"}, 403)
            if p == "/api/state":
                return self._json(srv.state())
            if p == "/api/result":
                with srv.lock:
                    data = srv.result_json
                if data is None:
                    return self._json({"error": "no result"}, 404)
                return self._send(200, data, "application/json; charset=utf-8")
            m = re.fullmatch(r"/api/score/(\d+)\.svg", p)
            if m:
                with srv.lock:
                    sc = getattr(srv.result, "score", None) if srv.result is not None else None
                k = int(m.group(1))
                if sc is None or not (0 <= k < len(sc.svg_pages)):
                    return self._json({"error": "no score"}, 404)
                return self._send(200, sc.svg_pages[k].encode("utf-8"), "image/svg+xml")
            m = re.fullmatch(r"/api/audio/(mix|vocals|instruments|drums|piano|piano_band)\.m4a", p)
            if m:
                f = srv.audio_file(m.group(1))
                if not f:
                    return self._json({"error": "no audio"}, 404)
                ctype = "audio/mp4" if f.suffix == ".m4a" else "audio/wav"
                return self._send_file(f, ctype)
            if p == "/api/export/melody.mid":
                return self._export_midi()
            if p == "/api/export/report.pdf":
                return self._export_pdf()
            return self._json({"error": "not found"}, 404)

        def _safe_title(self) -> str:
            with srv.lock:
                t = srv.result.title if srv.result is not None else "song"
            return "".join(ch for ch in t if ch not in '\\/:*?"<>|').strip() or "song"

        def _export_midi(self):
            from ..midi_export import export_midi

            with srv.lock:
                res = srv.result
            if res is None:
                return self._json({"error": "no result"}, 404)
            bend = (self._query().get("bend") or ["1"])[0] != "0"
            out = paths.cache_dir() / f"mobile_{int(time.time() * 1000)}.mid"
            export_midi(res.notes, out, bpm=res.rhythm.bpm, use_pitch_bend=bend, title=res.title)
            self._send_file(out, "audio/midi", download=f"{self._safe_title()}.mid")

        def _export_pdf(self):
            from ..report import export_pdf

            with srv.lock:
                res = srv.result
            if res is None:
                return self._json({"error": "no result"}, 404)
            out = paths.cache_dir() / "mobile_report.pdf"
            srv.gui_call(lambda: export_pdf(res, out))   # الرسم لازم يحصل في thread الواجهة
            self._send_file(out, "application/pdf")

        # -------------------------------------------------- POST
        def do_POST(self):
            try:
                if not self._authorized():
                    return self._json({"error": "unauthorized"}, 403)
                p = self._path()
                if p == "/api/analyze/url":
                    body = json.loads(self._read_body(64 * 1024) or b"{}")
                    from ..youtube import is_url, normalize_url

                    url = normalize_url(str(body.get("url", "")))
                    if not is_url(url):
                        return self._json({"ok": False, "error": "اللينك مش صحيح"}, 400)
                    ok, err = srv.start_job(url, True, "تحميل من اللينك…")
                    return self._json({"ok": ok, "error": err}, 200 if ok else 409)
                if p == "/api/analyze/upload":
                    name = urllib.parse.unquote(self.headers.get("X-Filename", "song"))
                    name = Path(name).name or "song"
                    name = re.sub(r'[\\/:*?"<>|]', "_", name)[-120:]
                    if srv.job["state"] == "running" or srv.is_busy_external():
                        return self._json({"ok": False, "error": "فيه تحليل شغال دلوقتي"}, 409)
                    n = int(self.headers.get("Content-Length") or 0)
                    if n <= 0 or n > MAX_UPLOAD:
                        return self._json({"ok": False, "error": "حجم الملف مش مقبول"}, 413)
                    up = paths.user_data_dir() / "uploads" / str(int(time.time() * 1000))
                    up.mkdir(parents=True, exist_ok=True)
                    dest = up / name   # الاسم الأصلي = عنوان الأغنية
                    left = n
                    with open(dest, "wb") as f:
                        while left > 0:
                            chunk = self.rfile.read(min(1024 * 1024, left))
                            if not chunk:
                                break
                            f.write(chunk)
                            left -= len(chunk)
                    if left > 0:
                        dest.unlink(missing_ok=True)
                        return self._json({"ok": False, "error": "الرفع اتقطع"}, 400)
                    ok, err = srv.start_job(str(dest), False, Path(name).stem)
                    return self._json({"ok": ok, "error": err}, 200 if ok else 409)
                if p == "/api/cancel":
                    self._read_body(1024)
                    srv.cancel_job()
                    return self._json({"ok": True})
                return self._json({"error": "not found"}, 404)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                try:
                    self._json({"ok": False, "error": str(e)}, 500)
                except Exception:
                    pass

    return Handler
