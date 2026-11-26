"""نافذة وضع الموبايل: QR code + اللينك + التعليمات للآيفون."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QRectF, Qt, Signal, Slot
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QVBoxLayout)

from . import theme


class GuiInvoker(QObject):
    """تشغيل دالة في thread الواجهة من thread السيرفر واستنى النتيجة (للـ PDF)."""

    _call = Signal(object)

    def __init__(self):
        super().__init__()
        self._call.connect(self._run, Qt.BlockingQueuedConnection)

    @Slot(object)
    def _run(self, box):
        fn, out = box
        try:
            out["value"] = fn()
        except Exception as e:  # بنرجّع الخطأ للـ thread اللي طلب
            out["error"] = e

    def __call__(self, fn):
        if threading.current_thread() is threading.main_thread():
            return fn()
        out: dict = {}
        self._call.emit((fn, out))
        if "error" in out:
            raise out["error"]
        return out.get("value")


def qr_pixmap(text: str, size: int = 260) -> QPixmap:
    import segno

    qr = segno.make(text, error="m")
    rows = [list(r) for r in qr.matrix]
    n = len(rows)
    border = 3
    cell = size / (n + 2 * border)
    pm = QPixmap(size, size)
    pm.fill(QColor("#FFFFFF"))
    p = QPainter(pm)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#000000"))
    for y, row in enumerate(rows):
        for x, v in enumerate(row):
            if v:
                p.drawRect(QRectF((x + border) * cell, (y + border) * cell, cell + 0.6, cell + 0.6))
    p.end()
    return pm


class MobileDialog(QDialog):
    def __init__(self, server, qsettings, on_start=None, parent=None):
        super().__init__(parent)
        self.server = server
        self.qs = qsettings
        self.on_start = on_start
        self.setWindowTitle("وضع الموبايل (آيفون)")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        from PySide6.QtWidgets import QLayout
        lay.setSizeConstraint(QLayout.SetMinimumSize)   # النصوص الطويلة ما تتداخلش مع الكود

        title = QLabel("افتح البرنامج من الآيفون")
        title.setObjectName("title")
        lay.addWidget(title)
        self.status = QLabel("")
        self.status.setObjectName("dim")
        lay.addWidget(self.status)

        from PySide6.QtWidgets import QWidget

        qbox = QWidget()
        qbox.setFixedHeight(282)
        qrow = QHBoxLayout(qbox)
        qrow.setContentsMargins(0, 6, 0, 6)
        self.qr = QLabel()
        self.qr.setFixedSize(270, 270)
        self.qr.setAlignment(Qt.AlignCenter)
        self.qr.setStyleSheet("background:#fff;border-radius:14px;")
        qrow.addStretch(1)
        qrow.addWidget(self.qr)
        qrow.addStretch(1)
        lay.addWidget(qbox)
        lay.addSpacing(14)
        steps = QLabel(
            "1. الآيفون والكمبيوتر على نفس الواي فاي.\n"
            "2. افتح الكاميرا ووجّهها على الكود، ودوس على اللينك اللي يظهر.\n"
            "3. هيفتح في Safari: الصق لينك يوتيوب أو ارفع ملف، والتحليل بيحصل هنا على الكمبيوتر.\n"
            "4. عشان يبقى زي التطبيق: في Safari دوس زرار المشاركة ⬆︎ ← «Add to Home Screen».\n\n"
            "لو ويندوز سأل عن الـ Firewall اختار «Private networks» واضغط Allow.")
        steps.setWordWrap(True)
        lay.addWidget(steps)

        self.cmb = QComboBox()
        self.cmb.setToolTip("لو الكود ما اشتغلش جرّب عنوان تاني (مثلاً لو عندك أكتر من شبكة)")
        self.cmb.currentIndexChanged.connect(self._show_qr)
        lay.addWidget(self.cmb)

        btns = QHBoxLayout()
        self.btn_toggle = QPushButton("")
        self.btn_toggle.setObjectName("accent")
        self.btn_toggle.clicked.connect(self._toggle)
        btn_copy = QPushButton("نسخ اللينك")
        btn_copy.clicked.connect(self._copy)
        btn_new = QPushButton("كود سري جديد")
        btn_new.setToolTip("اللينكات القديمة (والاختصار على الآيفون) هتبطل تشتغل")
        btn_new.clicked.connect(self._new_token)
        btns.addWidget(self.btn_toggle)
        btns.addWidget(btn_copy)
        btns.addWidget(btn_new)
        lay.addLayout(btns)

        self.chk_auto = QCheckBox("شغّل وضع الموبايل تلقائيًا كل ما أفتح البرنامج")
        self.chk_auto.setChecked(self.qs.value("mobile_auto", False, type=bool))
        self.chk_auto.toggled.connect(lambda v: self.qs.setValue("mobile_auto", v))
        lay.addWidget(self.chk_auto)
        tip = QLabel("من برة البيت: سطّب Tailscale (مجاني) على الكمبيوتر والآيفون بنفس الحساب، "
                     "وهيظهر هنا عنوان يبدأ بـ 100. استخدمه.")
        tip.setObjectName("dim")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        self._refresh()

    def _refresh(self):
        running = self.server.running
        self.btn_toggle.setText("إيقاف وضع الموبايل" if running else "تشغيل وضع الموبايل")
        self.cmb.blockSignals(True)
        self.cmb.clear()
        if running:
            for u in self.server.urls():
                self.cmb.addItem(u)
            self.status.setText(f"شغال على البورت {self.server.port} ✓")
            self.status.setStyleSheet(f"color: {theme.OK};")
        else:
            self.status.setText("وضع الموبايل مقفول")
            self.status.setStyleSheet(f"color: {theme.TEXT_DIM};")
        self.cmb.blockSignals(False)
        self._show_qr()

    def _show_qr(self, *_):
        url = self.cmb.currentText()
        if self.server.running and url:
            self.qr.setPixmap(qr_pixmap(url, 260))
        else:
            self.qr.setPixmap(QPixmap())
            self.qr.setText("—")

    def _toggle(self):
        if self.server.running:
            self.server.stop()
        else:
            try:
                self.server.start(int(self.qs.value("mobile_port", 8765)))
                if self.on_start:
                    self.on_start()
            except Exception as e:
                QMessageBox.warning(self, "مشكلة", str(e))
        self._refresh()

    def _copy(self):
        if self.cmb.currentText():
            QGuiApplication.clipboard().setText(self.cmb.currentText())

    def _new_token(self):
        self.server.new_token()
        self._refresh()
