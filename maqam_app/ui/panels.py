"""اللوحات الجانبية: المقامات، النوتات، الإيقاع، وإعدادات الأورج."""
from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QTableView, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ..notes import signed
from ..organ import KEYS_12, KEYS_12_AR, ORGAN_MODEL, settings_for_all_maqamat
from . import theme
from .widgets import Card, DumTakView, HistogramView, fmt_clock, fmt_time


def _label(text="", obj=None, wrap=True) -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    lb.setWordWrap(wrap)
    lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lb


def _scroll(widget: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setWidget(widget)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    return sa


# ------------------------------------------------------------------ المقامات

class MaqamPanel(QWidget):
    seekRequested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(10)

        self.main_card = Card()
        self.lbl_sec = _label("المقام الأساسي", "section")
        self.lbl_name = _label("—", "big")
        self.lbl_tonic = _label("")
        self.lbl_conf = _label("", "dim")
        self.lbl_ajnas = _label("", "dim", wrap=False)
        self.lbl_desc = _label("", "dim")
        for w in (self.lbl_sec, self.lbl_name, self.lbl_tonic, self.lbl_conf, self.lbl_ajnas,
                  self.lbl_desc):
            self.main_card.lay.addWidget(w)
        lay.addWidget(self.main_card)

        hist_card = Card()
        hist_card.lay.addWidget(_label("توزيع النوتات (Pitch Histogram)", "section"))
        self.hist = HistogramView()
        hist_card.lay.addWidget(self.hist)
        hist_card.lay.addWidget(_label("الأزرق = نوتات المقام، الأخضر = القرار", "dim"))
        lay.addWidget(hist_card)

        sec_card = Card()
        sec_card.lay.addWidget(_label("المقاطع والتحويلات — اضغط على أي مقطع يشتغل من عنده",
                                      "section"))
        self.sections = QListWidget()
        self.sections.setMinimumHeight(180)
        self.sections.itemClicked.connect(self._on_section)
        sec_card.lay.addWidget(self.sections)
        lay.addWidget(sec_card)

        alt_card = Card()
        alt_card.lay.addWidget(_label("احتمالات تانية", "section"))
        self.lbl_alts = _label("", "dim")
        alt_card.lay.addWidget(self.lbl_alts)
        lay.addWidget(alt_card)
        lay.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(inner))

    def _on_section(self, item: QListWidgetItem):
        t = item.data(Qt.UserRole)
        if t is not None:
            self.seekRequested.emit(float(t))

    def set_result(self, res):
        b = res.maqam.global_best
        self.lbl_name.setText(b.display_name)
        self.lbl_name.setStyleSheet(f"color: {b.color};")
        self.lbl_tonic.setText(f"القرار: {b.tonic_text}")
        self.lbl_conf.setText(f"درجة الثقة: {b.probability * 100:.0f}% — "
                              f"{b.fit * 100:.0f}% من النوتات جوه السلم")
        self.lbl_ajnas.setText("\n".join(b.ajnas_desc()))
        self.lbl_desc.setText(b.maqam.description)
        self.hist.set_data(res.maqam.histogram, b.scale_pcs(), b.tonic)

        self.sections.clear()
        for i, s in enumerate(res.maqam.sections, 1):
            c = s.candidate
            txt = (f"{fmt_clock(s.start)} ← {fmt_clock(s.end)}    {c.display_name}\n"
                   f"القرار: {c.tonic_text}   •   {c.probability * 100:.0f}%")
            it = QListWidgetItem(txt)
            it.setData(Qt.UserRole, s.start)
            it.setForeground(QBrush(QColor(theme.TEXT)))
            it.setBackground(QBrush(QColor(c.color).darker(380)))
            it.setToolTip("بدائل: " + "، ".join(a.display_name for a in s.alternatives[:3]))
            self.sections.addItem(it)
        alts = [c for c in res.maqam.ranking[1:] if c.maqam.key != b.maqam.key or c.tonic != b.tonic]
        self.lbl_alts.setText("\n".join(f"• {c.title()}  ({c.probability * 100:.0f}%)"
                                        for c in alts[:4]))


# ------------------------------------------------------------------ النوتات

class NotesModel(QAbstractTableModel):
    HEAD = ["الوقت", "السولفيج", "الغربي", "العربي", "انحراف", "الثقة"]

    def __init__(self):
        super().__init__()
        self.notes = []

    def set_notes(self, notes):
        self.beginResetModel()
        self.notes = list(notes)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.notes)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEAD)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEAD[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        n = self.notes[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            if col == 0:
                return fmt_time(n.start)
            if col == 1:
                return n.name.solfege + (" ◆" if n.name.quarter_tone else "")
            if col == 2:
                return n.name.western
            if col == 3:
                return n.name.arabic
            if col == 4:
                return signed(float(n.deviation))
            if col == 5:
                return f"{n.confidence * 100:.0f}%" if n.clear else "غير واضحة"
        if role == Qt.ToolTipRole:
            return (f"#{index.row() + 1} — {n.name.full()}\nالمدة: {n.duration:.2f} ث"
                    f"\nالانحراف: {signed(float(n.deviation))} سنت")
        if role == Qt.ForegroundRole:
            if not n.clear:
                return QBrush(QColor(theme.TEXT_DIM))
            if col == 1 and n.name.quarter_tone:
                return QBrush(QColor(theme.ACCENT))
        if role == Qt.TextAlignmentRole and col in (0, 2, 4, 5):
            return Qt.AlignCenter
        if role == Qt.UserRole:
            return n
        return None


class NotesFilter(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.hide_unclear = False

    def filterAcceptsRow(self, row, parent):
        if not self.hide_unclear:
            return True
        n = self.sourceModel().notes[row]
        return n.clear


class NotesPanel(QWidget):
    seekRequested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.lbl_count = _label("", "dim", wrap=False)
        self.chk = QCheckBox("إخفاء غير الواضحة")
        self.chk.toggled.connect(self._toggle)
        self.btn_csv = QPushButton("تصدير CSV")
        self.btn_csv.clicked.connect(self._export_csv)
        top.addWidget(self.lbl_count, 1)
        top.addWidget(self.chk)
        top.addWidget(self.btn_csv)
        lay.addLayout(top)
        self.model = NotesModel()
        self.proxy = NotesFilter()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        f = QFont(self.table.font())
        f.setPointSizeF(9.2)
        self.table.setFont(f)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.verticalHeader().setDefaultSectionSize(28)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        self.table.doubleClicked.connect(self._on_double)
        lay.addWidget(self.table)
        lay.addWidget(_label("◆ = ربع تون. دبل كليك على نوتة يشغّل من عندها. "
                             "النوتات غير الواضحة بتتكتب كده بدل التخمين.", "dim"))

    def _toggle(self, on):
        self.proxy.hide_unclear = on
        self.proxy.invalidateFilter()

    def _on_double(self, idx):
        n = self.proxy.data(idx, Qt.UserRole)
        if n is not None:
            self.seekRequested.emit(max(0.0, n.start - 0.3))

    def _fit_columns(self):
        hh = self.table.horizontalHeader()
        hh.setMinimumSectionSize(36)
        for i, w in enumerate((54, 112, 52, 82, 48)):
            if i < self.model.columnCount():
                hh.resizeSection(i, w)

    def showEvent(self, ev):
        # الستايل بيتطبق أول ما الجدول يظهر وبيرجّع عرض الأعمدة للافتراضي
        super().showEvent(ev)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._fit_columns)

    def set_result(self, res):
        self.model.set_notes(res.notes)
        self._fit_columns()
        clear = sum(1 for n in res.notes if n.clear)
        self.lbl_count.setText(f"{len(res.notes)} نوتة — {clear} واضحة")
        self._title = res.title

    def _export_csv(self):
        if not self.model.notes:
            return
        path, _ = QFileDialog.getSaveFileName(self, "تصدير النوتات", f"{getattr(self, '_title', 'notes')}.csv",
                                              "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["start", "end", "solfege", "western", "arabic", "deviation_cents",
                        "confidence", "clear"])
            for n in self.model.notes:
                w.writerow([f"{n.start:.3f}", f"{n.end:.3f}", n.name.solfege, n.name.western,
                            n.name.arabic, f"{n.deviation:.1f}", f"{n.confidence:.2f}",
                            "yes" if n.clear else "no"])


# ------------------------------------------------------------------ الإيقاع

class RhythmPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(10)
        card = Card()
        card.lay.addWidget(_label("الإيقاع", "section"))
        self.lbl_name = _label("—", "big")
        self.lbl_info = _label("")
        self.lbl_conf = _label("", "dim")
        for w in (self.lbl_name, self.lbl_info, self.lbl_conf):
            card.lay.addWidget(w)
        lay.addWidget(card)

        dt = Card()
        dt.lay.addWidget(_label("الدم والتك (دورة واحدة)", "section"))
        self.dumtak = DumTakView()
        dt.lay.addWidget(self.dumtak)
        self.lbl_pattern = _label("", "dim")
        dt.lay.addWidget(self.lbl_pattern)
        lay.addWidget(dt)

        org = Card()
        org.lay.addWidget(_label("على الأورج", "section"))
        self.lbl_style = _label("")
        org.lay.addWidget(self.lbl_style)
        lay.addWidget(org)

        alt = Card()
        alt.lay.addWidget(_label("احتمالات تانية", "section"))
        self.lbl_alts = _label("", "dim")
        alt.lay.addWidget(self.lbl_alts)
        lay.addWidget(alt)
        lay.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(inner))

    def set_result(self, res):
        r = res.rhythm
        self.lbl_name.setText(f"{r.iqa.name_ar}  ({r.iqa.name_en})")
        self.lbl_info.setText(f"الميزان: {r.meter}    •    السرعة: {r.bpm:.0f} BPM")
        txt = f"درجة الثقة: {r.confidence * 100:.0f}%"
        if not r.percussion_found:
            txt += " — مافيش إيقاع واضح في الأغنية"
        self.lbl_conf.setText(txt)
        self.dumtak.set_data(r.iqa.cells, r.dum_profile, r.tak_profile)
        self.lbl_pattern.setText("النمط: " + r.iqa.pattern.replace("D", "دم").replace("T", "تك")
                                 + "\nالأعمدة: الأزرق = طاقة الدم، الأبيض = طاقة التك")
        self.lbl_style.setText(f"Style مقترح: {r.iqa.organ_style}\nTempo: {r.organ_tempo()}")
        self.lbl_alts.setText("\n".join(f"• {n}" for n, _ in r.alternatives))


# ------------------------------------------------------------------ الأورج

class OrganPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(10)
        self._res = None

        head = Card()
        head.lay.addWidget(_label(f"الأورج: {ORGAN_MODEL} — Scale Tune", "section"))
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._show)
        head.lay.addWidget(self.combo)
        self.lbl_title = _label("", "title")
        head.lay.addWidget(self.lbl_title)
        lay.addWidget(head)

        tcard = Card()
        self.table = QTableWidget(12, 3)
        self.table.setHorizontalHeaderLabels(["النوتة", "المفتاح", "Cents"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setFixedHeight(12 * 30 + 44)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setShowGrid(False)
        for i in range(12):
            self.table.setRowHeight(i, 30)
        tcard.lay.addWidget(self.table)
        lay.addWidget(tcard)

        info = Card()
        self.lbl_master = _label("")
        self.lbl_style = _label("")
        self.lbl_notes = _label("", "dim")
        for w in (self.lbl_master, self.lbl_style, self.lbl_notes):
            info.lay.addWidget(w)
        lay.addWidget(info)

        ref = Card()
        ref.lay.addWidget(_label("جدول مرجعي لكل المقامات (على قرارها التقليدي)", "section"))
        rows = settings_for_all_maqamat()
        rt = QTableWidget(len(rows), 2)
        rt.setHorizontalHeaderLabels(["المقام", "Scale Tune"])
        rt.verticalHeader().setVisible(False)
        rt.setEditTriggers(QAbstractItemView.NoEditTriggers)
        rt.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        rt.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for i, (t, s) in enumerate(rows):
            rt.setItem(i, 0, QTableWidgetItem(t))
            it = QTableWidgetItem(s)
            it.setTextAlignment(Qt.AlignCenter)
            rt.setItem(i, 1, it)
        rt.resizeRowsToContents()
        rt.setFixedHeight(sum(rt.rowHeight(i) for i in range(len(rows))) + 44)
        rt.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rt.setShowGrid(False)
        rt.setWordWrap(True)
        ref.lay.addWidget(rt)
        lay.addWidget(ref)
        lay.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(inner))

    def set_result(self, res):
        self._res = res
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem(f"الأغنية كلها — {res.maqam.global_best.display_name}")
        for s in res.maqam.sections:
            self.combo.addItem(f"{fmt_clock(s.start)}–{fmt_clock(s.end)}  {s.candidate.display_name}")
        self.combo.blockSignals(False)
        self.combo.setCurrentIndex(0)
        self._show(0)

    def _show(self, idx):
        if self._res is None:
            return
        org = self._res.organ if idx <= 0 else self._res.section_organ[idx - 1]
        self.lbl_title.setText(org.maqam_title)
        bold = QFont(self.font())
        bold.setBold(True)
        for i in range(12):
            c = org.offsets[i]
            items = [QTableWidgetItem(KEYS_12_AR[i]), QTableWidgetItem(KEYS_12[i]),
                     QTableWidgetItem(signed(c) if c else "0")]
            for it in items:
                it.setTextAlignment(Qt.AlignCenter)
                if c:
                    it.setForeground(QBrush(QColor(theme.ACCENT)))
                    it.setFont(bold)
                else:
                    it.setForeground(QBrush(QColor(theme.TEXT_DIM)))
            for j, it in enumerate(items):
                self.table.setItem(i, j, it)
        self.lbl_master.setText(f"Master Tune: {org.master_tune_hz:.1f} هرتز\n"
                                f"الخلاصة: {org.short()}")
        self.lbl_style.setText(f"Style: {org.style}\nTempo: {org.tempo}")
        self.lbl_notes.setText("\n".join("• " + n for n in org.notes))
