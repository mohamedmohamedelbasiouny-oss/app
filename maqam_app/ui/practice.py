"""وضع التمرين: نوتة موسيقية بتمشي مع الأغنية + بيانو بينوّر النوتة اللي بتتعزف دلوقتي."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ..notes import midi_from_cents, qt_index_to_cents
from ..score import flatten_svg
from . import theme

PAPER = QColor("#FBF7EE")
GREEN = QColor("#3DBE5B")


def note_key(index: int) -> tuple[int, int]:
    """(رقم المفتاح MIDI، الانحراف بالسنت) — الربع تون بيروح للمفتاح اللي بيتظبط على الأورج."""
    midi, bend = midi_from_cents(qt_index_to_cents(index))
    return midi, int(round(bend))


# ------------------------------------------------------------------ النوتة

class ScoreCanvas(QWidget):
    noteClicked = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LeftToRight)
        self.renderers: list[QSvgRenderer] = []
        self.images: list[QImage] = []
        self.page_offsets: list[float] = []
        self.scale = 1.0
        self.score = None
        self.current = None
        self.bounds: dict[str, tuple[int, QRectF]] = {}
        self._render_w = 0

    def set_score(self, score):
        self.score = score
        self.renderers = [QSvgRenderer(QByteArray(flatten_svg(s).encode("utf-8")))
                          for s in (score.svg_pages if score else [])]
        self.bounds = {}
        for pi, r in enumerate(self.renderers):
            for n in score.notes:
                for xid in n.ids:
                    if xid not in self.bounds and r.elementExists(xid):
                        b = r.transformForElement(xid).mapRect(r.boundsOnElement(xid))
                        self.bounds[xid] = (pi, b)
        self._render_w = 0
        self.current = None
        self._rerender()

    def _rerender(self):
        w = max(400, self.width())
        if w == self._render_w or not self.renderers:
            return
        self._render_w = w
        self.images, self.page_offsets = [], []
        y = 0.0
        for r in self.renderers:
            vb = r.viewBoxF()
            self.scale = w / vb.width()
            h = int(vb.height() * self.scale)
            img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
            img.fill(PAPER)
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing)
            r.render(p, QRectF(0, 0, w, h))
            p.end()
            self.images.append(img)
            self.page_offsets.append(y)
            y += h
        self.setMinimumHeight(int(y))
        self.update()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        QTimer.singleShot(60, self._rerender)

    def note_rect(self, xid: str) -> QRectF | None:
        if xid not in self.bounds or not self.page_offsets:
            return None
        pi, b = self.bounds[xid]
        s = self.scale
        return QRectF(b.x() * s, b.y() * s + self.page_offsets[pi], b.width() * s, b.height() * s)

    def set_current(self, note):
        if note is not self.current:
            self.current = note
            self.update()

    def paintEvent(self, ev):
        if self.renderers and abs(self.width() - self._render_w) > 8:
            QTimer.singleShot(0, self._rerender)
        p = QPainter(self)
        p.fillRect(self.rect(), PAPER)
        for img, y in zip(self.images, self.page_offsets):
            p.drawImage(QPointF(0, y), img)
        if self.current is not None and self.current.ids:
            p.setRenderHint(QPainter.Antialiasing)
            for xid in self.current.ids:
                r = self.note_rect(xid)
                if r is None:
                    continue
                hl = QColor(GREEN)
                hl.setAlpha(70)
                p.setPen(Qt.NoPen)
                p.setBrush(hl)
                p.drawRoundedRect(r.adjusted(-4, -4, 4, 4), 5, 5)
            r = self.note_rect(self.current.ids[0])
            if r is not None:
                # المؤشر الأخضر زي الفيديو: خط طولي على المدرج كله
                cx = r.center().x()
                staff_h = 62
                p.setPen(QPen(GREEN, 2.4))
                p.drawLine(QPointF(cx, r.center().y() - staff_h), QPointF(cx, r.center().y() + staff_h))
        if not self.images:
            p.setPen(QColor("#888"))
            p.drawText(self.rect(), Qt.AlignCenter, "النوتة الموسيقية هتظهر هنا بعد التحليل")
        p.end()

    def mousePressEvent(self, ev):
        if not self.score:
            return
        pos = ev.position()
        best, dist = None, 1e9
        for n in self.score.notes:
            for xid in n.ids:
                r = self.note_rect(xid)
                if r is None:
                    continue
                d = abs(r.center().x() - pos.x()) + abs(r.center().y() - pos.y()) * 0.5
                if d < dist:
                    best, dist = n, d
        if best is not None and dist < 80:
            self.noteClicked.emit(best.start)


# ------------------------------------------------------------------ البيانو

_WHITE = {0: ("Do", "دو"), 2: ("Re", "ري"), 4: ("Mi", "مي"), 5: ("Fa", "فا"), 7: ("Sol", "صول"),
          9: ("La", "لا"), 11: ("Si", "سي")}
_BLACK = {1: "Di", 3: "Ri", 6: "Fi", 8: "Si", 10: "Li"}


class PianoView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LeftToRight)
        self.setMinimumHeight(150)
        self.lo, self.hi = 60, 84          # C4 .. C6
        self.active: tuple[int, int] | None = None
        self.tuned: dict[int, int] = {}    # pitch class (0..11) → cents (Scale Tune)

    def set_range(self, midis: list[int]):
        if midis:
            lo = (min(midis) // 12) * 12
            hi = ((max(midis) // 12) + 1) * 12
            if hi - lo < 24:
                hi = lo + 24
            self.lo, self.hi = lo, min(hi, lo + 48)
        self.update()

    def set_tuning(self, offsets: list[int]):
        self.tuned = {i: c for i, c in enumerate(offsets) if c}
        self.update()

    def set_active(self, key: tuple[int, int] | None):
        if key != self.active:
            self.active = key
            self.update()

    def _whites(self):
        return [m for m in range(self.lo, self.hi + 1) if m % 12 in _WHITE]

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        whites = self._whites()
        if not whites:
            return
        w, h = self.width(), self.height()
        ww = w / len(whites)
        bh = h * 0.6
        pos = {m: i for i, m in enumerate(whites)}
        act = self.active[0] if self.active else None
        f_big = QFont(self.font())
        f_big.setPointSizeF(max(7.0, min(11.0, ww / 4.2)))
        f_small = QFont(self.font())
        f_small.setPointSizeF(max(6.0, min(8.5, ww / 5.5)))
        for m in whites:
            x = pos[m] * ww
            rect = QRectF(x + 1, 0, ww - 2, h - 2)
            on = m == act
            p.setPen(QPen(QColor("#9a9a9a"), 1))
            p.setBrush(GREEN if on else QColor("#FFFFFF"))
            path = QPainterPath()
            path.addRoundedRect(rect, 4, 4)
            p.drawPath(path)
            lat, ar = _WHITE[m % 12]
            p.setPen(QColor("#111"))
            p.setFont(f_big)
            p.drawText(QRectF(x, h - 40, ww, 20), Qt.AlignCenter, lat)
            p.setFont(f_small)
            p.setPen(QColor("#444"))
            p.drawText(QRectF(x, h - 22, ww, 18), Qt.AlignCenter, ar)
            self._tuned_badge(p, m, QRectF(x, h * 0.62, ww, 18), dark=False)
        for m in range(self.lo, self.hi + 1):
            if m % 12 in _WHITE:
                continue
            left = pos.get(m - 1)
            if left is None:
                continue
            x = (left + 1) * ww - ww * 0.3
            rect = QRectF(x, 0, ww * 0.6, bh)
            on = m == act
            p.setPen(Qt.NoPen)
            p.setBrush(GREEN if on else QColor("#232327"))
            p.drawRoundedRect(rect, 3, 3)
            p.setPen(QColor("#fff"))
            p.setFont(f_small)
            p.drawText(QRectF(x, bh - 22, ww * 0.6, 18), Qt.AlignCenter, _BLACK[m % 12])
            self._tuned_badge(p, m, QRectF(x - 6, 4, ww * 0.6 + 12, 16), dark=True)
        # الربع تون اللي بيتعزف دلوقتي
        if self.active and self.active[1]:
            m, bend = self.active
            if m % 12 in _WHITE and m in pos:
                cx = pos[m] * ww + ww / 2
                y = h * 0.45
            else:
                left = pos.get(m - 1, 0)
                cx = (left + 1) * ww
                y = bh * 0.45
            txt = "\u200e½♭\u200e" if bend < 0 else "\u200e½♯\u200e"
            p.setBrush(QColor(theme.ACCENT))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(cx - 17, y - 11, 34, 22), 8, 8)
            p.setPen(QColor("#0B1726"))
            p.setFont(f_big)
            p.drawText(QRectF(cx - 17, y - 11, 34, 22), Qt.AlignCenter, txt)
        p.end()

    def _tuned_badge(self, p: QPainter, m: int, rect: QRectF, dark: bool):
        c = self.tuned.get(m % 12)
        if not c:
            return
        f = QFont(self.font())
        f.setPointSizeF(7.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.ACCENT) if dark else QColor("#1d5fae"))
        p.drawText(rect, Qt.AlignCenter, "\u200e" + f"{c:+d}".replace("-", "−") + "\u200e")


# ------------------------------------------------------------------ الشاشة كلها

class PracticeView(QWidget):
    seekRequested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.header = QLabel("")
        self.header.setTextFormat(Qt.RichText)
        self.header.setWordWrap(True)
        self.header.setStyleSheet(
            f"background:{PAPER.name()};color:#1b2a4a;border-radius:12px;padding:6px 14px;")
        lay.addWidget(self.header)
        self.canvas = ScoreCanvas()
        self.canvas.noteClicked.connect(self.seekRequested)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.canvas)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"QScrollArea{{background:{PAPER.name()};border-radius:12px;}}")
        lay.addWidget(self.scroll, 1)
        self.piano = PianoView()
        lay.addWidget(self.piano)
        self.hint = QLabel("دوس على أي نوتة في المدرج يشتغل من عندها • النوتة اللي بتتعزف بتنوّر "
                           "أخضر على المدرج وعلى البيانو • الأرقام الزرقا على المفاتيح = Scale Tune")
        self.hint.setObjectName("dim")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self.score = None

    def set_result(self, res):
        self.score = res.score
        b = res.maqam.global_best
        r = res.rhythm
        bpm = int(round(self.score.bpm)) if self.score else int(round(r.bpm))
        self.header.setText(
            f"<span style='font-size:15pt;font-weight:700;color:#1b2a4a'>{res.title}</span>&nbsp;&nbsp;"
            f"<span style='font-size:10.5pt;color:#2d5a2d'>المقام: <b>{b.display_name}</b> "
            f"({b.tonic_text}) &nbsp;•&nbsp; إيقاع: <b>{r.iqa.name_ar}</b> {r.meter}"
            f" &nbsp;•&nbsp; <span dir='ltr'>♩ = {bpm}</span></span>")
        self.canvas.set_score(self.score)
        if self.score and self.score.notes:
            self.piano.set_range([note_key(n.index)[0] for n in self.score.notes])
        self.piano.set_tuning(res.organ.offsets)
        self.piano.set_active(None)
        self.scroll.verticalScrollBar().setValue(0)

    def set_position(self, t: float):
        if not self.score:
            return
        n = self.score.note_at(t)
        self.canvas.set_current(n)
        self.piano.set_active(note_key(n.index) if n is not None else None)
        target = n or self.score.last_note_before(t)
        if target is not None and target.ids:
            r = self.canvas.note_rect(target.ids[0])
            if r is not None:
                sb = self.scroll.verticalScrollBar()
                view_h = self.scroll.viewport().height()
                top = sb.value()
                if r.top() < top + 30 or r.bottom() > top + view_h - 40:
                    sb.setValue(int(max(0, r.top() - view_h * 0.25)))
