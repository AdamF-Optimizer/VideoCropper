"""Asynchronous FFmpeg export with transactional output files."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

from PySide6.QtCore import QObject, QProcess, Signal

from .core import ffmpeg_arguments, same_file


class ExportJob(QObject):
    progress = Signal(int)
    succeeded = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read_progress)
        self.process.readyReadStandardError.connect(self._read_errors)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self.active = False
        self._cancelled = False
        self._temporary: Path | None = None
        self._destination: Path | None = None
        self._expected_ms = 0
        self._stdout = ""
        self._errors = ""

    def start(self, ffmpeg: str, source: Path, destination: Path,
              start_ms: int, end_ms: int | None, duration_ms: int) -> None:
        if self.active:
            raise RuntimeError("An export is already running.")
        if same_file(source, destination):
            raise ValueError("Choose a different output file. The original video is protected.")
        if not source.is_file():
            raise ValueError("The source video no longer exists.")
        self._cancelled = False
        self._stdout = self._errors = ""
        self._destination = destination
        self._expected_ms = max(0, (end_ms if end_ms is not None else duration_ms) - start_ms)
        # Keep the temporary file beside the destination so replacing it is atomic.
        handle, name = tempfile.mkstemp(prefix=".videocropper-", suffix=".mp4", dir=destination.parent)
        os.close(handle)
        self._temporary = Path(name)
        self.active = True
        self.process.start(ffmpeg, ffmpeg_arguments(source, self._temporary, start_ms, end_ms))

    def cancel(self) -> None:
        if self.active:
            self._cancelled = True
            self.process.kill()

    def _read_progress(self) -> None:
        self._stdout += bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        while "\n" in self._stdout:
            line, self._stdout = self._stdout.split("\n", 1)
            if line.startswith("out_time_us=") and self._expected_ms:
                try:
                    elapsed_ms = int(line.split("=", 1)[1]) / 1000
                    self.progress.emit(min(99, max(0, int(elapsed_ms * 100 / self._expected_ms))))
                except ValueError:
                    pass

    def _read_errors(self) -> None:
        self._errors = (self._errors + bytes(self.process.readAllStandardError()).decode(
            "utf-8", errors="replace"))[-12000:]

    def _cleanup(self) -> str:
        if self._temporary:
            try:
                self._temporary.unlink(missing_ok=True)
            except OSError as exc:
                return f"\nCould not remove temporary file {self._temporary}: {exc}"
            finally:
                self._temporary = None
        return ""

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart and self.active:
            self.active = False
            cleanup_error = self._cleanup()
            self.failed.emit(f"Could not start FFmpeg: {self.process.errorString()}{cleanup_error}")

    def _finished(self, code: int, status: QProcess.ExitStatus) -> None:
        if not self.active:
            return
        self._read_errors()
        self._read_progress()
        self.active = False
        if self._cancelled:
            cleanup_error = self._cleanup()
            if cleanup_error:
                self.failed.emit("Export cancelled." + cleanup_error)
            else:
                self.cancelled.emit()
        elif code != 0 or status != QProcess.ExitStatus.NormalExit:
            cleanup_error = self._cleanup()
            self.failed.emit((self._errors.strip() or "FFmpeg stopped unexpectedly.") + cleanup_error)
        else:
            try:
                if not self._temporary or self._temporary.stat().st_size == 0:
                    raise OSError("FFmpeg produced an empty output file.")
                os.replace(self._temporary, self._destination)
                self._temporary = None
            except OSError as exc:
                cleanup_error = self._cleanup()
                self.failed.emit(f"Could not save the output: {exc}{cleanup_error}")
                return
            self.progress.emit(100)
            self.succeeded.emit(str(self._destination))
