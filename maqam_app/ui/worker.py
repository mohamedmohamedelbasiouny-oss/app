"""تشغيل التحليل في Thread منفصل عشان الواجهة ما تهنجش."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QThread, Signal

from ..pipeline import Cancelled, Settings, analyze_file, analyze_url


class AnalysisWorker(QObject):
    progress = Signal(float, str)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, source: str, is_url: bool, settings: Settings):
        super().__init__()
        self.source = source
        self.is_url = is_url
        self.settings = settings
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            cb = lambda f, m: self.progress.emit(float(f), str(m))  # noqa: E731
            if self.is_url:
                res = analyze_url(self.source, self.settings, cb, cancel=lambda: self._cancel)
            else:
                res = analyze_file(self.source, self.settings, cb, cancel=lambda: self._cancel)
            self.finished.emit(res)
        except Cancelled:
            self.cancelled.emit()
        except Exception as e:
            detail = traceback.format_exc(limit=4)
            self.failed.emit(f"{e}\n\n{detail}")


def start_worker(parent, worker: AnalysisWorker) -> QThread:
    th = QThread(parent)
    worker.moveToThread(th)
    th.started.connect(worker.run)
    worker.finished.connect(th.quit)
    worker.failed.connect(th.quit)
    worker.cancelled.connect(th.quit)
    th.start()
    return th
