"""نقطة تشغيل البرنامج: python main.py"""
from __future__ import annotations

import multiprocessing
import sys
import traceback


def main() -> int:
    import os

    # في نسخة exe من غير كونسول، stdout/stderr بيبقوا None — بعض المكتبات بتكتب عليهم
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    from maqam_app import paths

    paths.setup_runtime_env()

    if "--selftest" in sys.argv:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from maqam_app.selftest import run

        i = sys.argv.index("--selftest")
        out = sys.argv[i + 1] if len(sys.argv) > i + 1 else None
        return run(out)

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    from maqam_app import APP_NAME_EN
    from maqam_app.ui import theme
    from maqam_app.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME_EN)
    app.setOrganizationName("MaqamAnalyzer")
    app.setLayoutDirection(Qt.RightToLeft)
    families = set(QFontDatabase.families())
    for fam in theme.FONT_FAMILIES:
        if fam in families:
            app.setFont(QFont(fam, 10))
            break
    app.setStyle("Fusion")
    app.setStyleSheet(theme.STYLESHEET)

    def excepthook(exc_type, exc, tb):
        msg = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            with open(paths.user_data_dir() / "errors.log", "a", encoding="utf-8") as f:
                f.write(msg + "\n" + "-" * 60 + "\n")
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = excepthook

    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.startswith("http"):
            win.url_edit.setText(arg)
            win.analyze_link()
        else:
            win.analyze_path(arg)
    return app.exec()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
