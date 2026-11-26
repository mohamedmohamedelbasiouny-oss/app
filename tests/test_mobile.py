"""اختبار وضع الموبايل: رفع أغنية من "الآيفون" → تحليل → نتيجة → صوت بـ Range → تصدير."""
import json
import subprocess
import time
import urllib.error
import urllib.request

import numpy as np
import pytest
import soundfile as sf

from maqam_app import paths
from maqam_app.maqam_db import MAQAM_BY_KEY
from maqam_app.mobile.server import MobileServer
from maqam_app.pipeline import Settings
from synth import SR, maqam_melody, percussion


@pytest.fixture(scope="module")
def server():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841 (للـ PDF)
    srv = MobileServer(settings_provider=lambda: Settings(use_demucs=False,
                                                          pitch_engine="crepe-tiny"))
    srv.start(port=18765, host="127.0.0.1")
    yield srv
    srv.stop()


def _req(srv, path, data=None, headers=None, token=True, method=None):
    h = dict(headers or {})
    if token:
        h["X-Token"] = srv.token
    r = urllib.request.Request(f"http://127.0.0.1:{srv.port}{path}", data=data, headers=h,
                               method=method)
    return urllib.request.urlopen(r, timeout=120)


def test_requires_token(server):
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(server, "/api/state", token=False)
    assert e.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(server, "/", token=False)
    assert e.value.code == 403
    page = _req(server, f"/?t={server.token}", token=False)
    assert b"<html" in page.read() and "mt=" in page.headers.get("Set-Cookie", "")


def test_upload_analyze_and_result(server, tmp_path):
    mel = maqam_melody(MAQAM_BY_KEY["hijaz"].scale, 4, n_phrases=7)
    y = mel + percussion("malfuf", 110, len(mel) / SR)[: len(mel)]
    wav = tmp_path / "song.wav"
    sf.write(wav, y, SR)
    m4a = tmp_path / "أغنية تجربة.m4a"      # اسم عربي زي ما بيحصل من الآيفون
    subprocess.run([paths.ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(wav), str(m4a)],
                   check=True)
    body = m4a.read_bytes()
    r = _req(server, "/api/analyze/upload", data=body, method="POST",
             headers={"X-Filename": urllib.request.quote(m4a.name),
                      "Content-Type": "application/octet-stream"})
    assert json.loads(r.read())["ok"]

    for _ in range(240):
        st = json.loads(_req(server, "/api/state").read())
        if st["job"]["state"] in ("done", "error"):
            break
        time.sleep(0.5)
    assert st["job"]["state"] == "done", st
    assert st["has_result"] and st["title"] == "أغنية تجربة"

    res = json.loads(_req(server, "/api/result").read())
    assert res["maqam"]["name"] == "حجاز"
    assert "دوكاه" in res["maqam"]["tonic"]
    assert res["rhythm"]["name"] == "ملفوف"
    assert res["organ"]["offsets"][4] == 0          # الحجاز على ري مافيهوش سيكا
    assert len(res["notes"]) > 30 and len(res["melody"]["t"]) > 100
    assert {s["key"] for s in res["stems"]} >= {"mix", "vocals", "drums"}


def test_audio_range_for_safari(server):
    full = _req(server, "/api/audio/mix.m4a")
    assert full.status == 200 and full.headers["Accept-Ranges"] == "bytes"
    data = full.read()
    assert full.headers["Content-Type"] == "audio/mp4" and len(data) > 10_000
    part = _req(server, "/api/audio/mix.m4a", headers={"Range": "bytes=0-1"})
    assert part.status == 206 and part.read() == data[:2]
    assert part.headers["Content-Range"] == f"bytes 0-1/{len(data)}"
    tail = _req(server, "/api/audio/mix.m4a", headers={"Range": "bytes=100-"})
    assert tail.read() == data[100:]


def test_exports(server):
    mid = _req(server, "/api/export/melody.mid?bend=1").read()
    assert mid[:4] == b"MThd"
    pdf = _req(server, "/api/export/report.pdf").read()
    assert pdf[:4] == b"%PDF"
    man = json.loads(_req(server, "/manifest.webmanifest", token=False).read())
    assert server.token in man["start_url"]


def test_bad_url_rejected(server):
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(server, "/api/analyze/url", data=json.dumps({"url": "مش لينك"}).encode(),
             method="POST", headers={"Content-Type": "application/json"})
    assert e.value.code == 400
