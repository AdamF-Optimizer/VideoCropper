"""Run with python main.py, or double-click Launch Video Cropper.cmd."""

import sys
import traceback
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from video_cropper.app import MainWindow


def report_error(kind, value, tb):
    details = "".join(traceback.format_exception(kind, value, tb))
    try:
        state_dir = Path(__file__).resolve().parent / ".state"
        state_dir.mkdir(exist_ok=True)
        (state_dir / "crash.log").write_text(details, encoding="utf-8")
    except OSError:
        pass
    dialog = QMessageBox(QMessageBox.Icon.Critical, "Video Cropper", str(value))
    dialog.setDetailedText(details)
    dialog.exec()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Video Cropper")
    app.setOrganizationName("VideoCropper")
    app.setStyle("Fusion")
    sys.excepthook = report_error
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
