"""النافذة الرئيسية."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPainter, QPen, QColor
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QProgressBar, QPushButton, QSlider,
                               QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__, paths
from ..audio_io import file_filter, is_supported
from ..pipeline import AnalysisResult, Settings
from ..youtube import is_url, normalize_url
from . import theme
from .icons import icon
from .panels import MaqamPanel, NotesPanel, OrganPanel, RhythmPanel
from .widgets import MelodyView, Panel, fmt_clock
from .mobile_dialog import GuiInvoker, MobileDialog
from .worker import AnalysisWorker, start_worker

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    HAS_MULTIMEDIA = True
except Exception:  # pragma: no cover
    HAS_MULTIMEDIA = False


def tool_button(name: str, tip: str, obj: str = "icon", text: str = "") -> QToolButton:
    b = QToolButton()
    b.setObjectName(obj)
    b.setIcon(icon(name, "#0B1726" if obj == "accent" else theme.TEXT))
    b.setIconSize(QSize(20, 20))
    b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    if text:
        b.setText(text)
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    return b


class DropHint(QWidget):
    """رسالة البداية: اسحب الأغنية هنا أو الصق لينك."""

    def __init__(self, on_open, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        ic = QLabel()
        ic.setPixmap(icon("music", theme.TEXT_DIM, 56).pixmap(56, 56))
        ic.setAlignment(Qt.AlignCenter)
        t1 = QLabel("اسحب ملف الأغنية هنا")
        t1.setObjectName("title")
        t1.setAlignment(Qt.AlignCenter)
        t2 = QLabel("MP3 • WAV • M4A • FLAC • OGG • OPUS • AAC • WMA • AIFF … وأي صيغة صوت أو فيديو\n"
                    "أو الصق لينك يوتيوب في الخانة اللي فوق")
        t2.setObjectName("dim")
        t2.setAlignment(Qt.AlignCenter)
        btn = QPushButton("  اختيار ملف")
        btn.setObjectName("accent")
        btn.setIcon(icon("open", "#0B1726"))
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(on_open)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn)
        row.addStretch(1)
        for w in (ic, t1, t2):
            lay.addWidget(w)
        lay.addSpacing(8)
        lay.addLayout(row)
        lay.addStretch(1)
        self.highlight = False

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        col = QColor(theme.ACCENT if self.highlight else theme.BORDER)
        p.setPen(QPen(col, 1.6, Qt.DashLine))
        p.drawRoundedRect(self.rect().adjusted(14, 14, -14, -14), 22, 22)
        p.end()


class ProgressView(QWidget):
    def __init__(self, on_cancel, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        self.lbl = QLabel("جاري التحليل…")
        self.lbl.setObjectName("title")
        self.lbl.setAlignment(Qt.AlignCenter)
        self.sub = QLabel("")
        self.sub.setObjectName("dim")
        self.sub.setAlignment(Qt.AlignCenter)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setFixedWidth(420)
        self.bar.setFixedHeight(10)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.bar)
        row.addStretch(1)
        self.btn = QPushButton("إلغاء")
        self.btn.clicked.connect(on_cancel)
        row2 = QHBoxLayout()
        row2.addStretch(1)
        row2.addWidget(self.btn)
        row2.addStretch(1)
        lay.addWidget(self.lbl)
        lay.addWidget(self.sub)
        lay.addSpacing(6)
        lay.addLayout(row)
        lay.addSpacing(10)
        lay.addLayout(row2)
        lay.addStretch(1)

    def set_progress(self, frac, msg):
        self.bar.setValue(int(frac * 1000))
        self.sub.setText(f"{msg}   ({frac * 100:.0f}%)")


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("الإعدادات")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(12)
        self.chk_demucs = QCheckBox("استخدم Demucs لفصل صوت المطرب (أدق، أبطأ)")
        self.chk_demucs.setChecked(settings.use_demucs)
        self.cmb_engine = QComboBox()
        self.cmb_engine.addItem("دقيق — CREPE full (موصى به)", "auto")
        self.cmb_engine.addItem("سريع — CREPE tiny", "crepe-tiny")
        self.cmb_engine.addItem("pYIN (librosa)", "pyin")
        self.cmb_engine.setCurrentIndex(max(0, self.cmb_engine.findData(settings.pitch_engine)))
        self.cmb_src = QComboBox()
        self.cmb_src.addItem("تلقائي (صوت المطرب، ولو مافيش غُنا → الآلات)", "auto")
        self.cmb_src.addItem("صوت المطرب بس", "vocals")
        self.cmb_src.addItem("الآلات بس (لو عايز لحن العازف)", "instruments")
        self.cmb_src.addItem("الأغنية كاملة من غير فصل", "mix")
        self.cmb_src.setCurrentIndex(max(0, self.cmb_src.findData(settings.melody_source)))
        form.addRow("فصل الصوت:", self.chk_demucs)
        form.addRow("استخراج اللحن:", self.cmb_engine)
        form.addRow("مصدر اللحن:", self.cmb_src)
        lay.addLayout(form)
        btn_cache = QPushButton("مسح الكاش (الملفات المؤقتة والتحميلات)")
        btn_cache.clicked.connect(self._clear_cache)
        lay.addWidget(btn_cache)
        info = QLabel(f"مجلد البيانات: {paths.user_data_dir()}")
        info.setObjectName("dim")
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(info)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("حفظ")
        bb.button(QDialogButtonBox.Ok).setObjectName("accent")
        bb.button(QDialogButtonBox.Cancel).setText("إلغاء")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _clear_cache(self):
        import shutil

        for d in (paths.cache_dir(), paths.user_data_dir() / "downloads"):
            shutil.rmtree(d, ignore_errors=True)
        QMessageBox.information(self, "الكاش", "تم مسح الملفات المؤقتة.")

    def result_settings(self) -> Settings:
        return Settings(use_demucs=self.chk_demucs.isChecked(),
                        pitch_engine=self.cmb_engine.currentData(),
                        melody_source=self.cmb_src.currentData())


class MainWindow(QMainWindow):
    mobileResult = Signal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — {__version__}")
        self.resize(1440, 880)
        self.setMinimumSize(1080, 680)
        self.setAcceptDrops(True)
        ico = paths.resource_dir() / "packaging" / "icon.ico"
        if ico.exists():
            self.setWindowIcon(QIcon(str(ico)))
        self.qs = QSettings("MaqamAnalyzer", "MaqamAnalyzer")
        self.settings = Settings(
            use_demucs=self.qs.value("use_demucs", True, type=bool),
            pitch_engine=self.qs.value("pitch_engine", "auto", type=str),
            melody_source=self.qs.value("melody_source", "auto", type=str))
        self.result: AnalysisResult | None = None
        self.worker = None
        self.thread = None
        self._build()
        self._build_player()
        self._set_has_result(False)
        self._build_mobile()

    # ------------------------------------------------------------ بناء الواجهة
    def _build(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        # الشريط العلوي
        top = Panel(margins=10)
        top.lay.setDirection(QHBoxLayout.RightToLeft)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        logo = QLabel(f"  {APP_NAME}")
        logo.setObjectName("title")
        self.btn_open = tool_button("open", "فتح ملف أغنية (Ctrl+O)", "icon", "فتح ملف")
        self.btn_open.clicked.connect(self.open_file)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("الصق لينك يوتيوب (أو أي لينك أغنية) هنا واضغط Enter…")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.addAction(icon("link", theme.TEXT_DIM), QLineEdit.LeadingPosition)
        self.url_edit.returnPressed.connect(self.analyze_link)
        self.btn_link = tool_button("download", "تحميل وتحليل الأغنية من اللينك", "accent",
                                    "حلّل اللينك")
        self.btn_link.clicked.connect(self.analyze_link)
        self.btn_midi = tool_button("midi", "تصدير اللحن كملف MIDI", "icon", "MIDI")
        self.btn_midi.clicked.connect(self.export_midi)
        self.btn_pdf = tool_button("pdf", "تصدير التقرير كامل PDF", "icon", "PDF")
        self.btn_pdf.clicked.connect(self.export_pdf)
        self.btn_mobile = tool_button("phone", "افتح البرنامج من الآيفون (وضع الموبايل)", "icon",
                                      "الموبايل")
        self.btn_mobile.clicked.connect(self.open_mobile)
        self.btn_settings = tool_button("settings", "الإعدادات")
        self.btn_settings.clicked.connect(self.open_settings)
        bar.addWidget(logo)
        bar.addSpacing(12)
        bar.addWidget(self.btn_open)
        bar.addWidget(self.url_edit, 1)
        bar.addWidget(self.btn_link)
        bar.addSpacing(10)
        bar.addWidget(self.btn_midi)
        bar.addWidget(self.btn_pdf)
        bar.addWidget(self.btn_mobile)
        bar.addWidget(self.btn_settings)
        top.lay.addLayout(bar)
        root.addWidget(top)

        body = QHBoxLayout()
        body.setSpacing(12)

        # اللوحة الجانبية
        side = Panel(margins=12)
        side.setFixedWidth(470)
        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        self.tab_group = QButtonGroup(self)
        self.stack = QStackedWidget()
        self.maqam_panel = MaqamPanel()
        self.notes_panel = NotesPanel()
        self.rhythm_panel = RhythmPanel()
        self.organ_panel = OrganPanel()
        for i, (name, ic, w) in enumerate([("المقامات", "wave", self.maqam_panel),
                                           ("النوتات", "list", self.notes_panel),
                                           ("الإيقاع", "drum", self.rhythm_panel),
                                           ("الأورج", "keys", self.organ_panel)]):
            b = QToolButton()
            b.setObjectName("tab")
            b.setText(name)
            b.setIcon(icon(ic, theme.TEXT))
            b.setIconSize(QSize(18, 18))
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.tab_group.addButton(b, i)
            tabs.addWidget(b)
            self.stack.addWidget(w)
        self.tab_group.button(0).setChecked(True)
        self.tab_group.idClicked.connect(self.stack.setCurrentIndex)
        side.lay.addLayout(tabs)
        side.lay.addWidget(self.stack, 1)
        self.maqam_panel.seekRequested.connect(self.play_from)
        self.notes_panel.seekRequested.connect(self.play_from)

        # الوسط: رسم اللحن + المشغل
        center = QVBoxLayout()
        center.setSpacing(12)
        self.view_panel = Panel(margins=12)
        head = QHBoxLayout()
        self.lbl_song = QLabel("")
        self.lbl_song.setObjectName("title")
        self.lbl_song.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_chips = QLabel("")
        self.lbl_chips.setObjectName("dim")
        self.lbl_chips.setWordWrap(True)
        head.addWidget(self.lbl_song, 1)
        self.chk_notes = QCheckBox("إظهار النوتات")
        self.chk_notes.setChecked(True)
        self.chk_notes.toggled.connect(self._toggle_notes)
        head.addWidget(self.chk_notes)
        self.view_panel.lay.addLayout(head)
        self.view_panel.lay.addWidget(self.lbl_chips)
        self.center_stack = QStackedWidget()
        self.drop_hint = DropHint(self.open_file)
        self.melody = MelodyView()
        self.melody.seekRequested.connect(self.play_from)
        self.progress_view = ProgressView(self.cancel_analysis)
        self.center_stack.addWidget(self.drop_hint)
        self.center_stack.addWidget(self.melody)
        self.center_stack.addWidget(self.progress_view)
        self.view_panel.lay.addWidget(self.center_stack, 1)
        hint = QLabel("دوس على أي مكان في الرسم أو على اسم المقطع فوق يشتغل من عنده • "
                      "عجلة الماوس للزوم • اسحب للتحريك • دبل كليك يرجّع العرض كامل")
        hint.setObjectName("dim")
        self.view_panel.lay.addWidget(hint)
        center.addWidget(self.view_panel, 1)

        # شريط التشغيل
        tp = Panel(margins=10)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_play = tool_button("play", "تشغيل / إيقاف مؤقت (Space)", "accent")
        self.btn_play.setFixedSize(44, 44)
        self.btn_play.clicked.connect(self.toggle_play)
        self.lbl_time = QLabel("0:00 / 0:00")
        self.lbl_time.setMinimumWidth(110)
        self.lbl_time.setAlignment(Qt.AlignCenter)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setLayoutDirection(Qt.LeftToRight)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(lambda v: self.seek(v / 1000.0))
        self.slider.sliderReleased.connect(lambda: self.seek(self.slider.value() / 1000.0))
        self.cmb_stem = QComboBox()
        self.cmb_stem.setToolTip("تسمع أنهي مسار")
        self.cmb_stem.setMinimumWidth(170)
        self.cmb_stem.currentIndexChanged.connect(self._change_stem)
        self.cmb_speed = QComboBox()
        for r in (0.5, 0.75, 0.9, 1.0, 1.25):
            self.cmb_speed.addItem(f"السرعة ×{r:g}", r)
        self.cmb_speed.setCurrentIndex(3)
        self.cmb_speed.currentIndexChanged.connect(self._change_speed)
        vol_ic = QLabel()
        vol_ic.setPixmap(icon("volume", theme.TEXT_DIM, 18).pixmap(18, 18))
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setLayoutDirection(Qt.LeftToRight)
        self.vol.setRange(0, 100)
        self.vol.setValue(80)
        self.vol.setFixedWidth(90)
        row.addWidget(self.btn_play)
        row.addWidget(self.lbl_time)
        row.addWidget(self.slider, 1)
        row.addWidget(self.cmb_stem)
        row.addWidget(self.cmb_speed)
        row.addWidget(vol_ic)
        row.addWidget(self.vol)
        tp.lay.addLayout(row)
        center.addWidget(tp)

        body.addWidget(side)
        body.addLayout(center, 1)
        root.addLayout(body, 1)

        act = QAction(self)
        act.setShortcut(QKeySequence("Ctrl+O"))
        act.triggered.connect(self.open_file)
        self.addAction(act)
        act2 = QAction(self)
        act2.setShortcut(QKeySequence(Qt.Key_Space))
        act2.triggered.connect(self.toggle_play)
        self.addAction(act2)

    # ------------------------------------------------------------ وضع الموبايل
    def _build_mobile(self):
        from ..mobile.server import MobileServer

        self._gui_invoker = GuiInvoker()
        self.mobile = MobileServer(
            settings_provider=lambda: self.settings,
            on_result=self.mobileResult.emit,
            is_busy_external=lambda: self.worker is not None,
            gui_call=self._gui_invoker)
        self.mobileResult.connect(self._on_mobile_result)
        if self.qs.value("mobile_auto", False, type=bool):
            try:
                self.mobile.start(int(self.qs.value("mobile_port", 8765)))
            except Exception:
                pass
        self._update_mobile_button()

    def _update_mobile_button(self):
        on = self.mobile.running
        self.btn_mobile.setIcon(icon("phone", theme.ACCENT if on else theme.TEXT))
        self.btn_mobile.setText("الموبايل ●" if on else "الموبايل")

    def open_mobile(self):
        def started():
            if self.result is not None:
                self.mobile.set_result(self.result)
        dlg = MobileDialog(self.mobile, self.qs, on_start=started, parent=self)
        dlg.exec()
        self._update_mobile_button()

    def _on_mobile_result(self, res):
        """تحليل اتعمل من الآيفون — بنعرضه على الكمبيوتر كمان."""
        if self.worker is not None:
            return
        self.result = res
        self._set_busy(False)
        self.show_result(res)

    def _build_player(self):
        self.player = None
        if not HAS_MULTIMEDIA:
            return
        try:
            self.player = QMediaPlayer(self)
            self.audio_out = QAudioOutput(self)
            self.player.setAudioOutput(self.audio_out)
            self.audio_out.setVolume(0.8)
            self.vol.valueChanged.connect(lambda v: self.audio_out.setVolume(v / 100.0))
            self.player.positionChanged.connect(self._on_position)
            self.player.durationChanged.connect(lambda d: self.slider.setRange(0, int(d)))
            self.player.playbackStateChanged.connect(self._on_state)
        except Exception:
            self.player = None

    # ------------------------------------------------------------ حالة الواجهة
    def _set_has_result(self, has: bool):
        for w in (self.btn_midi, self.btn_pdf, self.btn_play, self.slider, self.cmb_stem,
                  self.cmb_speed):
            w.setEnabled(has)

    def _set_busy(self, busy: bool):
        for w in (self.btn_open, self.btn_link, self.url_edit, self.btn_settings):
            w.setEnabled(not busy)
        if busy:
            self._set_has_result(False)
            self.center_stack.setCurrentWidget(self.progress_view)
        else:
            self.center_stack.setCurrentWidget(self.melody if self.result else self.drop_hint)
            self._set_has_result(self.result is not None)

    def _toggle_notes(self, on):
        self.melody.show_notes = on
        self.melody.update()

    # ------------------------------------------------------------ السحب والإفلات
    def dragEnterEvent(self, ev):
        md = ev.mimeData()
        if md.hasUrls() or (md.hasText() and is_url(md.text().strip())):
            ev.acceptProposedAction()
            self.drop_hint.highlight = True
            self.drop_hint.update()

    def dragLeaveEvent(self, ev):
        self.drop_hint.highlight = False
        self.drop_hint.update()

    def dropEvent(self, ev):
        self.drop_hint.highlight = False
        self.drop_hint.update()
        md = ev.mimeData()
        if md.hasUrls():
            for u in md.urls():
                if u.isLocalFile():
                    self.analyze_path(u.toLocalFile())
                    return
                if u.scheme().startswith("http"):
                    self.url_edit.setText(u.toString())
                    self.analyze_link()
                    return
        if md.hasText() and is_url(md.text().strip()):
            self.url_edit.setText(md.text().strip())
            self.analyze_link()

    # ------------------------------------------------------------ بدء التحليل
    def open_file(self):
        if self.worker is not None:
            return
        last = self.qs.value("last_dir", str(Path.home()), type=str)
        path, _ = QFileDialog.getOpenFileName(self, "اختار ملف أغنية", last, file_filter())
        if path:
            self.qs.setValue("last_dir", str(Path(path).parent))
            self.analyze_path(path)

    def analyze_path(self, path: str):
        if self.worker is not None:
            return
        p = Path(path)
        if not p.exists():
            QMessageBox.warning(self, "خطأ", "الملف مش موجود.")
            return
        if not is_supported(p):
            ans = QMessageBox.question(
                self, "صيغة غير معروفة",
                f"الامتداد «{p.suffix}» مش في القائمة المعروفة. أجرب أفتحه برضه؟")
            if ans != QMessageBox.Yes:
                return
        self._start(str(p), False, p.stem)

    def analyze_link(self):
        if self.worker is not None:
            return
        text = normalize_url(self.url_edit.text())
        if not is_url(text):
            QMessageBox.information(self, "اللينك", "الصق لينك صحيح (يبدأ بـ https://).")
            return
        self._start(text, True, "تحميل من اللينك…")

    def _start(self, source: str, url: bool, title: str):
        self._stop_player()
        self.lbl_song.setText(title)
        self.lbl_chips.setText("")
        self.progress_view.set_progress(0, "بدء التحليل…")
        self._set_busy(True)
        self.worker = AnalysisWorker(source, url, self.settings)
        self.worker.progress.connect(self.progress_view.set_progress)
        self.worker.finished.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.thread = start_worker(self, self.worker)

    def cancel_analysis(self):
        if self.worker is not None:
            self.worker.cancel()
            self.progress_view.sub.setText("جاري الإلغاء…")

    def _cleanup_worker(self):
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(3000)
        self.worker = None
        self.thread = None

    def _on_cancelled(self):
        self._cleanup_worker()
        self._set_busy(False)
        if self.result:
            self.lbl_song.setText(self.result.title)

    def _on_failed(self, msg: str):
        self._cleanup_worker()
        self._set_busy(False)
        if self.result:
            self.lbl_song.setText(self.result.title)
        try:
            log = paths.user_data_dir() / "errors.log"
            with open(log, "a", encoding="utf-8") as f:
                f.write(msg + "\n" + "-" * 60 + "\n")
        except Exception:
            pass
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("حصلت مشكلة")
        box.setText(msg.split("\n\n")[0])
        box.setDetailedText(msg)
        box.exec()

    def _on_done(self, res: AnalysisResult):
        self._cleanup_worker()
        self.result = res
        self._set_busy(False)
        self.show_result(res)
        if self.mobile.running:
            try:
                self.mobile.set_result(res)
            except Exception:
                pass

    # ------------------------------------------------------------ عرض النتيجة
    def show_result(self, res: AnalysisResult):
        self.lbl_song.setText(res.title)
        b = res.maqam.global_best
        chips = [f"المقام: {b.display_name}", f"القرار: {b.tonic_text}",
                 f"الإيقاع: {res.rhythm.iqa.name_ar} {res.rhythm.meter} — {res.rhythm.bpm:.0f} BPM",
                 res.tuning.describe()]
        if len(res.maqam.sections) > 1:
            chips.append(f"{len(res.maqam.sections)} مقاطع/تحويلات")
        text = "   •   ".join(chips)
        if res.warnings:
            text += "\n⚠ " + "  ".join(res.warnings)
        self.lbl_chips.setText(text)
        self.melody.set_result(res)
        self.center_stack.setCurrentWidget(self.melody)
        self.maqam_panel.set_result(res)
        self.notes_panel.set_result(res)
        self.rhythm_panel.set_result(res)
        self.organ_panel.set_result(res)
        from ..separation import STEM_LABELS

        self.cmb_stem.blockSignals(True)
        self.cmb_stem.clear()
        for key in ("mix", "vocals", "instruments", "drums"):
            if key in res.playback:
                self.cmb_stem.addItem(STEM_LABELS[key], key)
        self.cmb_stem.blockSignals(False)
        self._load_source("mix")
        self.lbl_time.setText(f"0:00 / {fmt_clock(res.duration)}")
        self._set_has_result(True)

    # ------------------------------------------------------------ المشغل
    def _load_source(self, key: str, keep_pos: bool = False):
        if not self.player or not self.result:
            return
        path = self.result.playback.get(key)
        if not path:
            return
        pos = self.player.position() if keep_pos else 0
        playing = self.player.playbackState() == QMediaPlayer.PlayingState
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.player.setPlaybackRate(float(self.cmb_speed.currentData() or 1.0))
        if keep_pos:
            QTimer.singleShot(150, lambda: self.player.setPosition(pos))
        if playing:
            self.player.play()

    def _change_stem(self, idx):
        key = self.cmb_stem.itemData(idx)
        if key:
            self._load_source(key, keep_pos=True)

    def _change_speed(self, idx):
        if self.player:
            self.player.setPlaybackRate(float(self.cmb_speed.itemData(idx)))

    def _stop_player(self):
        if self.player:
            self.player.stop()

    def toggle_play(self):
        if not self.player or not self.result:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def seek(self, seconds: float):
        if self.player:
            self.player.setPosition(int(seconds * 1000))
        self.melody.set_position(seconds)

    def play_from(self, seconds: float):
        if not self.result:
            return
        self.seek(seconds)
        if self.player:
            self.player.play()

    def _on_position(self, ms: int):
        if not self.slider.isSliderDown():
            self.slider.setValue(ms)
        dur = self.result.duration if self.result else 0
        self.lbl_time.setText(f"{fmt_clock(ms / 1000)} / {fmt_clock(dur)}")
        self.melody.set_position(ms / 1000.0)

    def _on_state(self, state):
        playing = state == QMediaPlayer.PlayingState
        self.btn_play.setIcon(icon("pause" if playing else "play", "#0B1726"))

    # ------------------------------------------------------------ التصدير والإعدادات
    def _default_name(self, ext: str) -> str:
        last = self.qs.value("export_dir", str(Path.home()), type=str)
        name = "".join(ch for ch in (self.result.title if self.result else "song")
                       if ch not in '\\/:*?"<>|').strip() or "song"
        return str(Path(last) / f"{name}.{ext}")

    def export_midi(self):
        if not self.result:
            return
        box = QMessageBox(self)
        box.setWindowTitle("تصدير MIDI")
        box.setText("الربع تون في ملف الـ MIDI:")
        b1 = box.addButton("مع Pitch Bend (الربع تون مضبوط في الملف)", QMessageBox.AcceptRole)
        b2 = box.addButton("بدون (هضبط Scale Tune على الأورج)", QMessageBox.AcceptRole)
        box.addButton("إلغاء", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() not in (b1, b2):
            return
        path, _ = QFileDialog.getSaveFileName(self, "حفظ ملف MIDI", self._default_name("mid"),
                                              "MIDI (*.mid)")
        if not path:
            return
        from ..midi_export import export_midi

        try:
            export_midi(self.result.notes, path, bpm=self.result.rhythm.bpm,
                        use_pitch_bend=box.clickedButton() is b1, title=self.result.title)
            self.qs.setValue("export_dir", str(Path(path).parent))
            QMessageBox.information(self, "تم", f"اتحفظ ملف الـ MIDI:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "خطأ", str(e))

    def export_pdf(self):
        if not self.result:
            return
        path, _ = QFileDialog.getSaveFileName(self, "حفظ التقرير PDF", self._default_name("pdf"),
                                              "PDF (*.pdf)")
        if not path:
            return
        from ..report import export_pdf

        try:
            export_pdf(self.result, path)
            self.qs.setValue("export_dir", str(Path(path).parent))
            QMessageBox.information(self, "تم", f"اتحفظ التقرير:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "خطأ", str(e))

    def open_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec() == QDialog.Accepted:
            self.settings = dlg.result_settings()
            self.qs.setValue("use_demucs", self.settings.use_demucs)
            self.qs.setValue("pitch_engine", self.settings.pitch_engine)
            self.qs.setValue("melody_source", self.settings.melody_source)

    def closeEvent(self, ev):
        try:
            self.mobile.stop()
        except Exception:
            pass
        if self.worker is not None:
            self.worker.cancel()
            self._cleanup_worker()
        self._stop_player()
        super().closeEvent(ev)
