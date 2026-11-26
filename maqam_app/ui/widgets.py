"""عناصر الواجهة المرسومة: رسم اللحن، شريط المقاطع، الدم والتك، توزيع النوتات."""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath,
                           QPen)
from PySide6.QtWidgets import QFrame, QToolTip, QVBoxLayout, QWidget

from ..notes import name_from_cents, qt_index_to_cents, pc_label
from . import theme


def fmt_time(t: float) -> str:
    t = max(0.0, float(t))
    m = int(t // 60)
    s = t - m * 60
    return f"{m}:{s:04.1f}" if m < 60 else f"{m // 60}:{m % 60:02d}:{int(s):02d}"


def fmt_clock(t: float) -> str:
    t = max(0, int(t))
    return f"{t // 60}:{t % 60:02d}"


class Panel(QFrame):
    """لوحة عائمة بحواف مدورة."""

    def __init__(self, parent=None, margins=14):
        super().__init__(parent)
        self.setObjectName("panel")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(margins, margins, margins, margins)
        self.lay.setSpacing(10)


class Card(QFrame):
    def __init__(self, parent=None, margins=12):
        super().__init__(parent)
        self.setObjectName("card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(margins, margins, margins, margins)
        self.lay.setSpacing(6)


# ------------------------------------------------------------------ رسم اللحن

class MelodyView(QWidget):
    """رسم خط اللحن على الزمن — كل مقام بلون، والضغط على أي مكان يشغّل من عنده."""

    seekRequested = Signal(float)

    TOP_BAND = 30       # شريط المقاطع فوق
    LEFT = 118          # مساحة أسماء النوتات
    BOTTOM = 26         # محور الزمن

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LeftToRight)   # الزمن دايمًا من الشمال لليمين
        self.setMouseTracking(True)
        self.setMinimumHeight(260)
        self.print_mode = False
        self.clear()

    # -- البيانات
    def clear(self):
        self.times = np.zeros(0)
        self.cents = np.zeros(0)
        self.notes = []
        self.sections = []
        self.duration = 0.0
        self.position = 0.0
        self.view_t0 = 0.0
        self.view_t1 = 1.0
        self.c_min, self.c_max = -900.0, 300.0
        self.tonic_pc = None
        self.scale_pcs = set()
        self.show_notes = True
        self._drag = None
        self.update()

    def set_result(self, res):
        self.times = res.pitch.times
        self.cents = res.cents
        self.notes = res.notes
        self.sections = res.maqam.sections
        self.duration = max(res.duration, 1e-3)
        self.tonic_pc = res.maqam.global_best.tonic
        self.scale_pcs = set()
        for s in res.maqam.sections:
            self.scale_pcs |= set(s.candidate.scale_pcs())
        v = self.cents[np.isfinite(self.cents)]
        if v.size:
            lo, hi = np.percentile(v, 1), np.percentile(v, 99.5)
        else:
            lo, hi = -900, 300
        self.c_min = math.floor((lo - 120) / 100) * 100
        self.c_max = math.ceil((hi + 120) / 100) * 100
        self.view_t0, self.view_t1 = 0.0, self.duration
        self.update()

    def set_position(self, t: float):
        self.position = t
        # متابعة المؤشر لما نكون عاملين زوم
        span = self.view_t1 - self.view_t0
        if span < self.duration - 1e-6 and not (self.view_t0 <= t <= self.view_t1 - span * 0.1):
            self.view_t0 = max(0.0, min(t - span * 0.1, self.duration - span))
            self.view_t1 = self.view_t0 + span
        self.update()

    # -- التحويلات
    def plot_rect(self) -> QRectF:
        return QRectF(self.LEFT, self.TOP_BAND + 6, max(10, self.width() - self.LEFT - 12),
                      max(10, self.height() - self.TOP_BAND - 6 - self.BOTTOM))

    def t2x(self, t, r=None):
        r = r or self.plot_rect()
        return r.left() + (t - self.view_t0) / max(self.view_t1 - self.view_t0, 1e-9) * r.width()

    def x2t(self, x, r=None):
        r = r or self.plot_rect()
        return self.view_t0 + (x - r.left()) / max(r.width(), 1) * (self.view_t1 - self.view_t0)

    def c2y(self, c, r=None):
        r = r or self.plot_rect()
        return r.bottom() - (c - self.c_min) / max(self.c_max - self.c_min, 1) * r.height()

    def y2c(self, y, r=None):
        r = r or self.plot_rect()
        return self.c_min + (r.bottom() - y) / max(r.height(), 1) * (self.c_max - self.c_min)

    def _section_color(self, t):
        for s in self.sections:
            if s.start <= t < s.end:
                return QColor(s.candidate.color)
        return QColor(theme.ACCENT)

    # -- الرسم
    def paintEvent(self, ev):
        p = QPainter(self)
        self.render_to(p, self.width(), self.height())
        p.end()

    def render_to(self, p: QPainter, w: int, h: int):
        p.setRenderHint(QPainter.Antialiasing)
        bg = QColor("#FFFFFF") if self.print_mode else QColor(theme.SURFACE)
        fg = QColor("#222222") if self.print_mode else QColor(theme.TEXT)
        dim = QColor("#777777") if self.print_mode else QColor(theme.TEXT_DIM)
        grid = QColor("#DDDDDD") if self.print_mode else QColor("#2C2C31")
        grid_q = QColor("#EEEEEE") if self.print_mode else QColor("#25252A")
        p.fillRect(0, 0, w, h, bg)
        r = self.plot_rect()
        small = QFont(self.font())
        small.setPointSizeF(8.2)
        p.setFont(small)

        if self.duration <= 0 or self.times.size == 0:
            p.setPen(dim)
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                       "خط اللحن هيظهر هنا بعد التحليل")
            return

        # خطوط الدرجات: نص تون واضح، ربع تون باهت، القرار مميز
        start_idx = int(math.floor((self.c_min + 900) / 50))
        end_idx = int(math.ceil((self.c_max + 900) / 50))
        px_per_qt = r.height() / max((self.c_max - self.c_min) / 50.0, 1)
        label_every = 1 if px_per_qt >= 13 else (2 if px_per_qt >= 7 else 4)
        for idx in range(start_idx, end_idx + 1):
            c = qt_index_to_cents(idx)
            y = self.c2y(c, r)
            if y < r.top() - 1 or y > r.bottom() + 1:
                continue
            is_tonic = self.tonic_pc is not None and idx % 24 == self.tonic_pc
            if idx % 2:
                p.setPen(QPen(grid_q, 1, Qt.DotLine))
            else:
                p.setPen(QPen(grid, 1))
            if is_tonic:
                p.setPen(QPen(QColor(theme.ACCENT), 1.2, Qt.DashLine))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            in_scale = (idx % 24) in self.scale_pcs
            if (idx % label_every == 0 and (in_scale or not self.scale_pcs or label_every == 1)) \
                    or is_tonic or (in_scale and px_per_qt >= 5):
                nn, _ = name_from_cents(c)
                txt = f"{nn.solfege}  {nn.western}"
                p.setPen(QColor(theme.ACCENT) if is_tonic else (fg if not nn.quarter_tone else dim))
                p.drawText(QRectF(4, y - 8, self.LEFT - 10, 16), Qt.AlignRight | Qt.AlignVCenter, txt)

        # شريط المقاطع (المقامات) فوق
        band = QRectF(r.left(), 4, r.width(), self.TOP_BAND - 4)
        for s in self.sections:
            x0, x1 = self.t2x(s.start, r), self.t2x(s.end, r)
            if x1 < r.left() or x0 > r.right():
                continue
            x0, x1 = max(x0, r.left()), min(x1, r.right())
            col = QColor(s.candidate.color)
            fill = QColor(col)
            fill.setAlpha(70 if not self.print_mode else 90)
            path = QPainterPath()
            path.addRoundedRect(QRectF(x0 + 1, band.top(), max(2, x1 - x0 - 2), band.height()), 8, 8)
            p.fillPath(path, fill)
            # ظل خفيف للمقطع على مساحة الرسم
            shade = QColor(col)
            shade.setAlpha(14 if not self.print_mode else 18)
            p.fillRect(QRectF(x0, r.top(), x1 - x0, r.height()), shade)
            p.setPen(fg)
            f2 = QFont(small)
            f2.setBold(True)
            p.setFont(f2)
            p.drawText(QRectF(x0 + 6, band.top(), max(0, x1 - x0 - 12), band.height()),
                       Qt.AlignCenter | Qt.TextSingleLine,
                       p.fontMetrics().elidedText(s.candidate.display_name, Qt.ElideRight,
                                                  int(max(0, x1 - x0 - 12))))
            p.setFont(small)

        p.save()
        p.setClipRect(r)
        # النوتات (مستطيلات مدورة) — الواضحة مليانة، وغير الواضحة متقطعة
        if self.show_notes:
            hq = max(4.0, px_per_qt * 0.8)
            for n in self.notes:
                if n.end < self.view_t0 or n.start > self.view_t1:
                    continue
                x0, x1 = self.t2x(n.start, r), self.t2x(n.end, r)
                y = self.c2y(qt_index_to_cents(n.index), r)
                col = self._section_color(n.start)
                rect = QRectF(x0, y - hq / 2, max(2.0, x1 - x0), hq)
                if n.clear:
                    c2 = QColor(col)
                    c2.setAlpha(60)
                    p.setPen(Qt.NoPen)
                    p.setBrush(c2)
                else:
                    p.setBrush(Qt.NoBrush)
                    c2 = QColor(dim)
                    p.setPen(QPen(c2, 1, Qt.DashLine))
                p.drawRoundedRect(rect, 3, 3)

        # خط اللحن نفسه
        t = self.times
        c = self.cents
        i0 = max(0, int(np.searchsorted(t, self.view_t0)) - 1)
        i1 = min(len(t), int(np.searchsorted(t, self.view_t1)) + 1)
        step = max(1, (i1 - i0) // int(max(r.width() * 2, 1)))
        path = None
        cur_col = None
        pen_w = 2.0
        for i in range(i0, i1, step):
            ci = c[i]
            if not np.isfinite(ci):
                if path is not None:
                    p.strokePath(path, QPen(cur_col, pen_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                    path = None
                continue
            pt = QPointF(self.t2x(t[i], r), self.c2y(ci, r))
            col = self._section_color(t[i])
            if path is None or col != cur_col:
                if path is not None:
                    path.lineTo(pt)
                    p.strokePath(path, QPen(cur_col, pen_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                path = QPainterPath(pt)
                cur_col = col
            else:
                path.lineTo(pt)
        if path is not None:
            p.strokePath(path, QPen(cur_col, pen_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.restore()

        # محور الزمن
        p.setPen(dim)
        span = self.view_t1 - self.view_t0
        nice = [1, 2, 5, 10, 15, 30, 60, 120, 300]
        stepT = next((s for s in nice if span / s <= max(4, r.width() / 90)), 600)
        tt = math.ceil(self.view_t0 / stepT) * stepT
        while tt <= self.view_t1:
            x = self.t2x(tt, r)
            p.setPen(QPen(grid, 1))
            p.drawLine(QPointF(x, r.bottom()), QPointF(x, r.bottom() + 4))
            p.setPen(dim)
            p.drawText(QRectF(x - 30, r.bottom() + 4, 60, 18), Qt.AlignCenter, fmt_clock(tt))
            tt += stepT

        # مؤشر التشغيل
        if not self.print_mode and self.view_t0 <= self.position <= self.view_t1:
            x = self.t2x(self.position, r)
            p.setPen(QPen(QColor(theme.TEXT), 1.4))
            p.drawLine(QPointF(x, band.top()), QPointF(x, r.bottom()))
            p.setBrush(QColor(theme.TEXT))
            p.drawEllipse(QPointF(x, r.bottom()), 3.5, 3.5)

    # -- التفاعل
    def wheelEvent(self, ev):
        if self.duration <= 0:
            return
        r = self.plot_rect()
        x = ev.position().x()
        anchor = self.x2t(x, r)
        factor = 0.8 if ev.angleDelta().y() > 0 else 1.25
        span = min(self.duration, max(2.0, (self.view_t1 - self.view_t0) * factor))
        frac = (x - r.left()) / max(r.width(), 1)
        t0 = anchor - frac * span
        t0 = max(0.0, min(t0, self.duration - span))
        self.view_t0, self.view_t1 = t0, t0 + span
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag = (ev.position().x(), self.view_t0, False)

    def mouseMoveEvent(self, ev):
        r = self.plot_rect()
        if self._drag is not None and ev.buttons() & Qt.LeftButton:
            x0, t0, _moved = self._drag
            dx = ev.position().x() - x0
            if abs(dx) > 4:
                span = self.view_t1 - self.view_t0
                nt = t0 - dx / max(r.width(), 1) * span
                nt = max(0.0, min(nt, self.duration - span))
                self.view_t0, self.view_t1 = nt, nt + span
                self._drag = (x0, t0, True)
                self.update()
            return
        if self.duration > 0 and r.contains(ev.position()):
            t = self.x2t(ev.position().x(), r)
            c = self.y2c(ev.position().y(), r)
            nn, _ = name_from_cents(c)
            note = next((n for n in self.notes if n.start <= t <= n.end), None)
            txt = f"{fmt_time(t)}\n{nn.solfege} ({nn.western}) — {nn.arabic}"
            if note is not None:
                conf = f"{note.confidence * 100:.0f}%" if note.clear else "غير واضحة"
                txt += (f"\nالنوتة: {note.name.solfege} ({note.name.western}) "
                        f"{note.deviation:+.0f}¢ — ثقة {conf}")
            QToolTip.showText(ev.globalPosition().toPoint(), txt, self)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._drag is not None:
            moved = self._drag[2]
            self._drag = None
            if not moved and self.duration > 0:
                r = self.plot_rect()
                if ev.position().y() < r.top():
                    # الضغط على شريط المقاطع = تشغيل من أول المقطع
                    t = self.x2t(ev.position().x(), r)
                    for s in self.sections:
                        if s.start <= t < s.end:
                            self.seekRequested.emit(s.start)
                            return
                self.seekRequested.emit(max(0.0, min(self.x2t(ev.position().x(), r),
                                                     self.duration)))

    def mouseDoubleClickEvent(self, ev):
        self.view_t0, self.view_t1 = 0.0, self.duration
        self.update()


# ------------------------------------------------------------------ الدم والتك

class DumTakView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LeftToRight)
        self.cells: list[str] = []
        self.dum: list[float] = []
        self.tak: list[float] = []
        self.print_mode = False
        self.setMinimumHeight(150)

    def set_data(self, cells, dum, tak):
        self.cells, self.dum, self.tak = list(cells), list(dum), list(tak)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        self.render_to(p, self.width(), self.height())
        p.end()

    def render_to(self, p: QPainter, w: int, h: int):
        p.setRenderHint(QPainter.Antialiasing)
        fg = QColor("#222") if self.print_mode else QColor(theme.TEXT)
        dim = QColor("#888") if self.print_mode else QColor(theme.TEXT_DIM)
        acc = QColor(theme.ACCENT)
        if not self.cells:
            p.setPen(dim)
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "—")
            return
        n = len(self.cells)
        cw = (w - 20) / n
        cy = 40
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        p.setFont(f)
        for i, c in enumerate(self.cells):
            cx = 10 + cw * (i + 0.5)
            p.setPen(dim)
            p.drawText(QRectF(cx - cw / 2, 0, cw, 14), Qt.AlignCenter, str(i + 1))
            if c == "D":
                p.setPen(Qt.NoPen)
                p.setBrush(acc)
                rad = min(16, cw * 0.38)
                p.drawEllipse(QPointF(cx, cy), rad, rad)
                p.setPen(QColor("#0B1726"))
                p.drawText(QRectF(cx - rad, cy - rad, 2 * rad, 2 * rad), Qt.AlignCenter, "دم")
            elif c == "T":
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(fg, 1.6))
                rad = min(11, cw * 0.28)
                p.drawEllipse(QPointF(cx, cy), rad, rad)
                p.setPen(fg)
                p.drawText(QRectF(cx - 20, cy + rad + 2, 40, 14), Qt.AlignCenter, "تك")
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(dim)
                p.drawEllipse(QPointF(cx, cy), 2, 2)
        # الطاقة المكتشفة فعلاً من الأغنية
        base = h - 10
        bar_h = h - cy - 50
        p.setPen(dim)
        p.drawText(QRectF(0, cy + 30, w, 14), Qt.AlignCenter, "اللي اتسمع فعلاً في الأغنية:")
        for i in range(n):
            cx = 10 + cw * (i + 0.5)
            d = self.dum[i] if i < len(self.dum) else 0
            t = self.tak[i] if i < len(self.tak) else 0
            bw = max(3, cw * 0.18)
            p.setPen(Qt.NoPen)
            p.setBrush(acc)
            p.drawRoundedRect(QRectF(cx - bw - 1, base - d * bar_h, bw, d * bar_h), 2, 2)
            p.setBrush(fg if not self.print_mode else QColor("#555"))
            p.drawRoundedRect(QRectF(cx + 1, base - t * bar_h, bw, t * bar_h), 2, 2)


# ------------------------------------------------------------------ توزيع النوتات

class HistogramView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LeftToRight)
        self.h = np.zeros(24)
        self.scale: set[int] = set()
        self.tonic = None
        self.setMinimumHeight(120)

    def set_data(self, h, scale_pcs, tonic):
        self.h = np.asarray(h)
        self.scale = set(scale_pcs)
        self.tonic = tonic
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, hgt = self.width(), self.height()
        mx = float(self.h.max()) if self.h.size and self.h.max() > 0 else 1.0
        bw = (w - 8) / 24
        f = QFont(self.font())
        f.setPointSizeF(7)
        p.setFont(f)
        for i in range(24):
            x = 4 + i * bw
            v = self.h[i] / mx if self.h.size else 0
            col = QColor(theme.ACCENT) if i in self.scale else QColor("#4A4A52")
            if i == self.tonic:
                col = QColor(theme.OK)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            bh = v * (hgt - 30)
            p.drawRoundedRect(QRectF(x + 1, hgt - 18 - bh, bw - 2, bh), 2, 2)
            if i % 2 == 0:
                p.setPen(QColor(theme.TEXT_DIM))
                lab = pc_label(i).split("(")[-1].rstrip(")")
                p.drawText(QRectF(x - 4, hgt - 16, bw + 8, 14), Qt.AlignCenter, lab)
        p.end()
