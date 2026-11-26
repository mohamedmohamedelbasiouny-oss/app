"""تصدير التقرير الكامل كـ PDF (بيدعم العربي من اليمين للشمال عن طريق Qt)."""
from __future__ import annotations

import datetime as _dt
import html
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QSizeF, Qt
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QTextDocument

from . import __version__
from .organ import ORGAN_MODEL, settings_for_all_maqamat
from .pipeline import AnalysisResult


def _img_tag(img: QImage, width_px: int) -> str:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    b64 = bytes(ba.toBase64()).decode("ascii")
    return f'<img src="data:image/png;base64,{b64}" width="{width_px}">'


class _Headless:
    """نسخة من رسّام الـ widget من غير QWidget — عشان التقرير يتعمل من أي thread
    (مثلاً لما الآيفون يطلب PDF من وضع الموبايل)."""

    def __init__(self, w: int, h: int):
        self._w, self._h = w, h

    def width(self):
        return self._w

    def height(self):
        return self._h

    def font(self):
        from PySide6.QtGui import QFont
        return QFont()

    def update(self):
        pass


def _headless(widget_cls, w: int, h: int):
    attrs = {k: v for k, v in widget_cls.__dict__.items()
             if not k.startswith("__") and not isinstance(v, type)}
    attrs = {k: v for k, v in attrs.items() if k not in ("seekRequested", "staticMetaObject")}
    cls = type(f"Headless{widget_cls.__name__}", (_Headless,), attrs)
    return cls(w, h)


def _render_widget(widget_cls, setup, w=1150, h=430) -> QImage:
    wid = _headless(widget_cls, w, h)
    if hasattr(wid, "clear"):
        wid.clear()
    else:
        wid.cells, wid.dum, wid.tak = [], [], []
    setup(wid)
    wid.print_mode = True
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(Qt.white)
    p = QPainter(img)
    wid.render_to(p, w, h)
    p.end()
    return img


def _fmt(t: float) -> str:
    m = int(t // 60)
    return f"{m}:{t - m * 60:04.1f}"


def build_html(res: AnalysisResult) -> str:
    from .ui.widgets import DumTakView, MelodyView

    e = html.escape
    best = res.maqam.global_best
    rh = res.rhythm
    org = res.organ

    melody_img = _render_widget(MelodyView, lambda w: w.set_result(res))
    dumtak_img = _render_widget(
        DumTakView, lambda w: w.set_data(rh.iqa.cells, rh.dum_profile, rh.tak_profile), 640, 190)

    css = """
    body { font-family: 'Segoe UI', Tahoma, 'DejaVu Sans'; font-size: 10pt; color: #222; }
    h1 { font-size: 20pt; color: #1d4f86; margin-bottom: 0; }
    h2 { font-size: 13pt; color: #1d4f86; border-bottom: 1px solid #ccc; margin-top: 16px; }
    table { border-collapse: collapse; width: 100%; }
    th { background: #e8eef6; padding: 4px; border: 1px solid #ccd; }
    td { padding: 3px 5px; border: 1px solid #dde; }
    .dim { color: #777; }
    .big { font-size: 15pt; font-weight: bold; }
    .unclear { color: #a33; }
    """
    out = [f'<html><head><style>{css}</style></head><body dir="rtl">']
    out.append(f"<h1>تقرير تحليل: {e(res.title)}</h1>")
    src = res.source_url or str(res.source)
    out.append(f'<p class="dim">المصدر: {e(src)}<br>التاريخ: '
               f'{_dt.datetime.now():%Y-%m-%d %H:%M} — محلل المقامات {__version__}</p>')

    out.append("<h2>الملخص</h2><table>")
    rows = [
        ("المقام الأساسي", f'<span class="big">{e(best.display_name)}</span>'),
        ("القرار (التونيك)", e(best.tonic_text)),
        ("الأجناس", "<br>".join(e(x) for x in best.ajnas_desc())),
        ("ضبط التسجيل", e(res.tuning.describe())),
        ("الإيقاع", f"{e(rh.iqa.name_ar)} ({e(rh.meter)}) — {rh.bpm:.0f} BPM — "
                    f"ثقة {rh.confidence * 100:.0f}%"),
        ("مدة الأغنية", _fmt(res.duration)),
        ("فصل الصوت", "Demucs" if res.separation_method == "demucs" else "HPSS (احتياطي)"),
        ("محرك اللحن", e(res.pitch.engine)),
    ]
    for k, v in rows:
        out.append(f"<tr><th width='22%'>{k}</th><td>{v}</td></tr>")
    out.append("</table>")
    if res.warnings:
        out.append("<p class='unclear'>" + "<br>".join(e(w) for w in res.warnings) + "</p>")

    out.append("<h2>خط اللحن والمقامات على الزمن</h2>")
    out.append(_img_tag(melody_img, 680))

    out.append("<h2>المقاطع والتحويلات</h2><table><tr><th>من</th><th>إلى</th><th>المقام</th>"
               "<th>القرار</th><th>الاحتمال</th><th>بدائل</th></tr>")
    for s in res.maqam.sections:
        c = s.candidate
        alts = "، ".join(a.display_name for a in s.alternatives[:2])
        out.append(f"<tr><td>{_fmt(s.start)}</td><td>{_fmt(s.end)}</td>"
                   f"<td><b style='color:{c.color}'>■</b> {e(c.display_name)}</td>"
                   f"<td>{e(c.tonic_text)}</td><td>{c.probability * 100:.0f}%</td>"
                   f"<td class='dim'>{e(alts)}</td></tr>")
    out.append("</table>")

    out.append(f"<h2>إعدادات الأورج — {ORGAN_MODEL}</h2>")
    out.append(f"<p><b>{e(org.maqam_title)}</b></p><table><tr>")
    for k, ar, c in org.table_rows():
        out.append(f"<th>{k}<br><span class='dim'>{ar}</span></th>")
    out.append("</tr><tr>")
    for k, ar, c in org.table_rows():
        style = " style='background:#fff3c4;font-weight:bold'" if c else ""
        out.append(f"<td align='center'{style}>{c:+d}</td>")
    out.append("</tr></table>")
    out.append(f"<p>Master Tune: <b>{org.master_tune_hz:.1f} Hz</b> — "
               f"Style مقترح: {e(org.style)} — Tempo: <b>{org.tempo}</b></p>")
    for n in org.notes:
        out.append(f"<p class='dim'>• {e(n)}</p>")
    if len(res.section_organ) > 1:
        out.append("<p><b>إعدادات كل مقطع:</b></p><table>")
        for s, so in zip(res.maqam.sections, res.section_organ):
            out.append(f"<tr><td>{_fmt(s.start)}–{_fmt(s.end)}</td><td>{e(so.maqam_title)}</td>"
                       f"<td>{e(so.short())}</td></tr>")
        out.append("</table>")

    out.append("<h2>الإيقاع</h2>")
    out.append(f"<p>{e(rh.iqa.name_ar)} — الميزان {e(rh.meter)} — {rh.bpm:.0f} BPM. "
               f"النمط: {e(rh.iqa.pattern.replace('D', 'دم').replace('T', 'تك'))}</p>")
    out.append(_img_tag(dumtak_img, 520))
    if rh.alternatives:
        out.append("<p class='dim'>احتمالات تانية: " +
                   "، ".join(e(a[0]) for a in rh.alternatives) + "</p>")

    out.append("<h2>نوتات اللحن الأساسي</h2>")
    out.append("<table><tr><th>#</th><th>الوقت</th><th>المدة</th><th>السولفيج</th>"
               "<th>الغربي</th><th>الاسم العربي</th><th>الانحراف</th><th>الثقة</th></tr>")
    for i, n in enumerate(res.notes, 1):
        conf = f"{n.confidence * 100:.0f}%" if n.clear else "<span class='unclear'>غير واضحة</span>"
        qt = " ◆" if n.name.quarter_tone else ""
        out.append(f"<tr><td>{i}</td><td>{_fmt(n.start)}</td><td>{n.duration:.2f}</td>"
                   f"<td>{e(n.name.solfege)}{qt}</td><td dir='ltr'>{e(n.name.western)}</td>"
                   f"<td>{e(n.name.arabic)}</td><td dir='ltr'>{n.deviation:+.0f}¢</td>"
                   f"<td>{conf}</td></tr>")
    out.append("</table><p class='dim'>◆ = ربع تون (نص بيمول أو نص دييز)</p>")

    out.append("<h2>جدول مرجعي: الربع تون لكل مقام على قراره التقليدي</h2><table>")
    for title, txt in settings_for_all_maqamat():
        out.append(f"<tr><td>{e(title)}</td><td dir='ltr'>{e(txt)}</td></tr>")
    out.append("</table></body></html>")
    return "".join(out)


def export_pdf(res: AnalysisResult, path: str | Path) -> Path:
    path = Path(path)
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait,
                                     QMarginsF(12, 12, 12, 12), QPageLayout.Millimeter))
    writer.setResolution(110)
    writer.setTitle(f"Maqam report - {res.title}")
    doc = QTextDocument()
    doc.setDocumentMargin(0)
    opt = doc.defaultTextOption()
    opt.setTextDirection(Qt.RightToLeft)
    doc.setDefaultTextOption(opt)
    doc.setHtml(build_html(res))
    layout = writer.pageLayout()
    rect = layout.paintRectPixels(writer.resolution())
    doc.setPageSize(QSizeF(rect.width(), rect.height()))
    doc.print_(writer)
    return path
