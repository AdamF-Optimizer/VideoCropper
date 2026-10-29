from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QSignalBlocker, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QSlider, QSplitter, QStackedWidget,
    QVBoxLayout, QWidget,
)

from .core import find_ffmpeg, format_timestamp, list_videos, validate_range
from .export import ExportJob


STYLE = """
QWidget { background: #14171d; color: #e9edf5; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow { background: #14171d; }
QLabel { background: transparent; }
QLabel#brand { font-size: 24px; font-weight: 700; }
QLabel#eyebrow { color: #8ab4ff; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#muted { color: #929cac; }
QLabel#section { font-size: 16px; font-weight: 600; }
QLabel#videoTitle { font-size: 18px; font-weight: 600; }
QLabel#emptyTitle { font-size: 25px; font-weight: 600; }
QFrame#panel { background: #1c2028; border: 1px solid #2b323e; border-radius: 12px; }
QPushButton { background: #282f3b; border: 1px solid #364051; border-radius: 7px;
              padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: #333e50; border-color: #607797; }
QPushButton:pressed { background: #1f2735; }
QPushButton:disabled { color: #647083; background: #202630; border-color: #2c3340; }
QPushButton#primary { background: #91b9ff; color: #111b2d; border-color: #91b9ff; }
QPushButton#primary:hover { background: #b0ccff; }
QPushButton#primary:disabled { background: #34445d; border-color: #34445d; color: #7d8da5; }
QPushButton#compact { padding: 4px 8px; font-size: 12px; }
QLineEdit { background: #11151c; border: 1px solid #374151; border-radius: 7px;
            padding: 9px 11px; selection-background-color: #496da6; }
QLineEdit:focus { border: 1px solid #91b9ff; }
QLineEdit:disabled { color: #647083; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { border-radius: 7px; padding: 12px 9px; margin-bottom: 4px; color: #b9c3d2; }
QListWidget::item:selected { background: #2a3b57; color: #e9f1ff; }
QListWidget::item:hover:!selected { background: #242b36; }
QSlider::groove:horizontal { height: 5px; border-radius: 2px; background: #354050; }
QSlider::sub-page:horizontal { background: #91b9ff; border-radius: 2px; }
QSlider::handle:horizontal { background: #e2edff; width: 13px; margin: -4px 0; border-radius: 6px; }
QProgressBar { border: none; background: #11151c; border-radius: 4px; height: 8px; text-align: center; }
QProgressBar::chunk { background: #91b9ff; border-radius: 4px; }
QToolTip { background: #29364a; color: #ffffff; border: 1px solid #51647f; padding: 5px; }
QSplitter::handle { background: #14171d; width: 14px; }
QScrollBar:vertical { background: #1c2028; width: 9px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #424f63; min-height: 24px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def button(text: str, callback, primary: bool = False) -> QPushButton:
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.clicked.connect(callback)
    return widget


class MainWindow(QMainWindow):
    def __init__(self, state_dir: Path | None = None, restore: bool = True):
        super().__init__()
        self.state_dir = state_dir or Path(__file__).resolve().parent.parent / ".state"
        self.state = self._read_state()
        self.folder: Path | None = None
        self.current_video: Path | None = None
        self.duration_ms = 0
        self.preview_end: int | None = None
        self.last_export: Path | None = None
        self._close_after_cancel = False
        self.ffmpeg = ""
        self.setWindowTitle("Video Cropper")
        self.resize(1240, 880)
        self.setMinimumSize(980, 680)
        self.setStyleSheet(STYLE)

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.7)
        self.player.setAudioOutput(self.audio)
        self.job = ExportJob(self)
        self._build_ui()
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.playbackStateChanged.connect(self._playback_changed)
        self.player.errorOccurred.connect(self._media_error)
        self.job.progress.connect(self._export_progress)
        self.job.succeeded.connect(self._export_succeeded)
        self.job.failed.connect(self._export_failed)
        self.job.cancelled.connect(self._export_cancelled)
        self._shortcuts()
        self._validate()
        try:
            self.ffmpeg = find_ffmpeg()
            self.engine_label.setText("FFmpeg ready  ·  H.264 + AAC export")
            self.engine_label.setToolTip(self.ffmpeg)
        except FileNotFoundError as exc:
            self.engine_label.setText(str(exc))
        if restore and self.state.get("folder"):
            QTimer.singleShot(0, lambda: self.open_folder(Path(self.state["folder"])))

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(26, 23, 26, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(3)
        heading.addWidget(label("VIDEO TOOLS", "eyebrow"))
        heading.addWidget(label("Video Cropper", "brand"))
        header.addLayout(heading)
        header.addStretch()
        header.addWidget(label("Find your moment. Keep the part you want.", "muted"))
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(16)
        layout.addWidget(splitter, 1)
        sidebar = QFrame()
        sidebar.setObjectName("panel")
        sidebar.setMinimumWidth(255)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 18, 16, 16)
        side.setSpacing(12)
        side.addWidget(label("Your videos", "section"))
        self.open_button = button("Open folder…", self.choose_folder, True)
        side.addWidget(self.open_button)
        self.folder_label = label("Choose a folder to get started.", "muted", True)
        side.addWidget(self.folder_label)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter videos…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        side.addWidget(self.search)
        self.file_count = label("0 videos", "muted")
        side.addWidget(self.file_count)
        self.files = QListWidget()
        self.files.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.files.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.files.currentItemChanged.connect(self._select_video)
        side.addWidget(self.files, 1)
        self.refresh_button = button("Refresh folder", self.refresh_folder)
        self.refresh_button.setEnabled(False)
        side.addWidget(self.refresh_button)
        splitter.addWidget(sidebar)

        workspace = QWidget()
        work = QVBoxLayout(workspace)
        work.setContentsMargins(0, 0, 0, 0)
        work.setSpacing(10)
        self.video_title = label("No video selected", "videoTitle")
        self.video_title.setWordWrap(True)
        work.addWidget(self.video_title)
        self.video_meta = label("Open a folder, then select a video from the list.", "muted")
        work.addWidget(self.video_meta)

        self.viewer = QStackedWidget()
        self.viewer.setMinimumHeight(160)
        empty = QFrame()
        empty.setObjectName("emptyViewer")
        empty.setStyleSheet("QFrame#emptyViewer { background: #0b0e13; border: 1px solid #2b323e; border-radius: 10px; }")
        empty_layout = QVBoxLayout(empty)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(label("Your next cut starts here", "emptyTitle"))
        empty_layout.addWidget(label("Open a folder to preview and trim your videos.", "muted"))
        self.viewer.addWidget(empty)
        self.video = QVideoWidget()
        self.video.setStyleSheet("background: black;")
        self.viewer.addWidget(self.video)
        work.addWidget(self.viewer, 1)

        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, 0)
        self.timeline.setTracking(True)
        self.timeline.valueChanged.connect(self._seek)
        work.addWidget(self.timeline)
        transport = QHBoxLayout()
        self.play_button = button("Play", self.toggle_play)
        self.play_button.setToolTip("Play / pause (Space)")
        self.back_button = button("−5 s", lambda: self.seek_relative(-5000))
        self.forward_button = button("+5 s", lambda: self.seek_relative(5000))
        transport.addWidget(self.play_button)
        transport.addWidget(self.back_button)
        transport.addWidget(self.forward_button)
        self.time_label = label("00:00:00.000 / 00:00:00.000", "muted")
        transport.addWidget(self.time_label)
        transport.addStretch()
        transport.addWidget(label("Volume", "muted"))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(70)
        self.volume.setFixedWidth(80)
        self.volume.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        transport.addWidget(self.volume)
        work.addLayout(transport)
        self.player_notice = label("", "muted", True)
        self.player_notice.hide()
        work.addWidget(self.player_notice)

        self.trim_panel = QFrame()
        self.trim_panel.setObjectName("panel")
        trim = QVBoxLayout(self.trim_panel)
        trim.setContentsMargins(18, 16, 18, 16)
        trim.setSpacing(11)
        trim_header = QHBoxLayout()
        trim_header.addWidget(label("Trim range", "section"))
        trim_header.addStretch()
        self.reset_button = button("Reset", self.reset_range)
        self.reset_button.setObjectName("compact")
        trim_header.addWidget(self.reset_button)
        trim.addLayout(trim_header)
        fields = QHBoxLayout()
        fields.setSpacing(18)
        from_column = QVBoxLayout()
        from_header = QHBoxLayout()
        from_header.addWidget(label("FROM", "eyebrow"))
        from_header.addStretch()
        self.mark_from = button("Use current  [ I ]", self.set_from_current)
        self.mark_from.setObjectName("compact")
        from_header.addWidget(self.mark_from)
        from_column.addLayout(from_header)
        self.from_input = QLineEdit("00:00:00.000")
        self.from_input.setAccessibleName("From timestamp")
        self.from_input.setToolTip("Seconds, MM:SS, or HH:MM:SS.mmm")
        self.from_input.textChanged.connect(self._range_edited)
        from_column.addWidget(self.from_input)
        fields.addLayout(from_column, 1)
        to_column = QVBoxLayout()
        to_header = QHBoxLayout()
        to_header.addWidget(label("TO  ·  OPTIONAL", "eyebrow"))
        to_header.addStretch()
        self.mark_to = button("Use current  [ O ]", self.set_to_current)
        self.mark_to.setObjectName("compact")
        to_header.addWidget(self.mark_to)
        to_column.addLayout(to_header)
        self.to_input = QLineEdit()
        self.to_input.setAccessibleName("To timestamp, optional")
        self.to_input.setPlaceholderText("Leave blank for end of video")
        self.to_input.setToolTip("Leave blank to keep everything after From")
        self.to_input.textChanged.connect(self._range_edited)
        to_column.addWidget(self.to_input)
        fields.addLayout(to_column, 1)
        trim.addLayout(fields)
        self.range_note = label("", "muted", True)
        trim.addWidget(self.range_note)
        actions = QHBoxLayout()
        self.preview_button = button("Preview range", self.preview_range)
        actions.addWidget(self.preview_button)
        actions.addStretch()
        self.export_button = button("Export clip…", self.export_clip, True)
        self.export_button.setToolTip("Save trimmed video as MP4 (Ctrl+Enter)")
        actions.addWidget(self.export_button)
        trim.addLayout(actions)
        work.addWidget(self.trim_panel)

        self.export_status = QFrame()
        self.export_status.setObjectName("panel")
        status_layout = QVBoxLayout(self.export_status)
        status_layout.setContentsMargins(14, 10, 14, 10)
        status_row = QHBoxLayout()
        self.status_label = label("", "muted", True)
        status_row.addWidget(self.status_label, 1)
        self.reveal_button = button("Show in folder", self.reveal_export)
        self.reveal_button.hide()
        status_row.addWidget(self.reveal_button)
        self.cancel_button = button("Cancel", self.cancel_export)
        status_row.addWidget(self.cancel_button)
        status_layout.addLayout(status_row)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        status_layout.addWidget(self.progress)
        self.export_status.hide()
        work.addWidget(self.export_status)
        splitter.addWidget(workspace)
        splitter.setSizes([275, 885])
        splitter.setStretchFactor(1, 1)
        self.engine_label = label("Finding FFmpeg…", "muted")
        layout.addWidget(self.engine_label)

    def _shortcuts(self) -> None:
        for key, callback in [("Ctrl+O", self.choose_folder), ("Space", self.toggle_play),
                              ("I", self.set_from_current), ("O", self.set_to_current),
                              ("Left", lambda: self.seek_relative(-5000)),
                              ("Right", lambda: self.seek_relative(5000)),
                              ("Ctrl+Return", self.export_clip)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)

    def choose_folder(self) -> None:
        if self.job.active:
            return
        folder = QFileDialog.getExistingDirectory(self, "Open video folder", str(self.folder or Path.home()))
        if folder:
            self.open_folder(Path(folder))

    def open_folder(self, folder: Path) -> None:
        if self.job.active:
            return
        try:
            videos = list_videos(folder)
        except OSError as exc:
            QMessageBox.warning(self, "Cannot open folder", str(exc))
            return
        previous = self.current_video
        self.player.stop()
        self.player.setSource(QUrl())
        self.current_video = None
        self.duration_ms = 0
        self.preview_end = None
        self.files.clear()
        self.search.clear()
        self.folder = folder.resolve()
        self.folder_label.setText(folder.name or str(folder))
        self.folder_label.setToolTip(str(folder))
        self.refresh_button.setEnabled(True)
        chosen_row = 0
        for index, path in enumerate(videos):
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.files.addItem(item)
            if path == previous:
                chosen_row = index
        self._filter()
        if videos:
            self.files.setCurrentRow(chosen_row)
        else:
            self.viewer.setCurrentIndex(0)
            self.video_title.setText("No videos in this folder")
            self.video_meta.setText("Choose another folder or add videos, then click Refresh folder.")
            self.player_notice.hide()
            self.reset_range()
        self._validate()

    def refresh_folder(self) -> None:
        if self.folder:
            self.open_folder(self.folder)

    def _filter(self) -> None:
        query = self.search.text().casefold()
        count = 0
        for index in range(self.files.count()):
            item = self.files.item(index)
            matches = query in item.text().casefold()
            item.setHidden(not matches)
            count += matches
        total = self.files.count()
        self.file_count.setText(f"{count} of {total} videos" if query else f"{total} video{'s' if total != 1 else ''}")

    def _select_video(self, current: QListWidgetItem | None, _previous=None) -> None:
        if current is None:
            return
        self.player.stop()
        self.current_video = Path(current.data(Qt.ItemDataRole.UserRole))
        self.duration_ms = 0
        self.preview_end = None
        self.timeline.setRange(0, 0)
        self.video_title.setText(self.current_video.name)
        self.video_title.setToolTip(str(self.current_video))
        try:
            size = self.current_video.stat().st_size / (1024 * 1024)
            self.video_meta.setText(f"{self.current_video.suffix[1:].upper()}  ·  {size:,.1f} MB")
        except OSError:
            self.video_meta.setText("File unavailable")
        self.player_notice.hide()
        self.viewer.setCurrentIndex(1)
        self.reset_range()
        self.player.setSource(QUrl.fromLocalFile(str(self.current_video)))
        self.player.play()

    def toggle_play(self) -> None:
        if not self.current_video or isinstance(QApplication.focusWidget(), QLineEdit):
            return
        self.preview_end = None
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if self.duration_ms and self.player.position() >= self.duration_ms - 10:
                self.player.setPosition(0)
            self.player.play()

    def _seek(self, position: int) -> None:
        self.preview_end = None
        self.player.setPosition(position)

    def seek_relative(self, delta: int) -> None:
        if self.current_video and not isinstance(QApplication.focusWidget(), QLineEdit):
            self._seek(max(0, min(self.duration_ms, self.player.position() + delta)))

    def _position_changed(self, position: int) -> None:
        if not self.timeline.isSliderDown():
            with QSignalBlocker(self.timeline):
                self.timeline.setValue(position)
        self.time_label.setText(f"{format_timestamp(position)} / {format_timestamp(self.duration_ms)}")
        if self.preview_end is not None and position >= self.preview_end:
            end = self.preview_end
            self.preview_end = None
            self.player.pause()
            self.player.setPosition(end)

    def _duration_changed(self, duration: int) -> None:
        self.duration_ms = duration
        with QSignalBlocker(self.timeline):
            self.timeline.setRange(0, min(duration, 2_147_483_647))
        self._position_changed(self.player.position())
        self._validate()

    def _playback_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self.play_button.setText("Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play")

    def _media_error(self, _error, message: str) -> None:
        self.preview_end = None
        self.player_notice.setText(f"Playback unavailable: {message} You can still export using typed timestamps.")
        self.player_notice.show()

    def set_from_current(self) -> None:
        if self.current_video and not self.job.active:
            self.from_input.setText(format_timestamp(self.player.position()))

    def set_to_current(self) -> None:
        if self.current_video and not self.job.active:
            self.to_input.setText(format_timestamp(self.player.position()))

    def reset_range(self) -> None:
        if self.job.active:
            return
        self.preview_end = None
        self.from_input.setText("00:00:00.000")
        self.to_input.clear()
        self._validate()

    def _range_edited(self) -> None:
        self.preview_end = None
        self._validate()

    def _validate(self) -> bool:
        has_video = self.current_video is not None
        valid = False
        try:
            start, end = validate_range(self.from_input.text(), self.to_input.text(), self.duration_ms)
            valid = True
            if not has_video:
                note = "Set a start time and, optionally, an end time."
            elif end is None:
                note = f"Keep from {format_timestamp(start)} to the end of the video."
            else:
                note = f"Clip length: {format_timestamp(end - start)}"
            self.range_note.setStyleSheet("color: #929cac;")
        except ValueError as exc:
            note = str(exc)
            self.range_note.setStyleSheet("color: #ffb4a6;")
        self.range_note.setText(note)
        available = has_video and not self.job.active
        self.export_button.setEnabled(available and valid)
        self.preview_button.setEnabled(available and valid and self.duration_ms > 0)
        for control in (self.from_input, self.to_input, self.mark_from, self.mark_to, self.reset_button):
            control.setEnabled(available)
        for control in (self.play_button, self.back_button, self.forward_button, self.timeline):
            control.setEnabled(has_video)
        return valid and has_video

    def preview_range(self) -> None:
        if self.job.active or not self._validate() or not self.duration_ms:
            return
        start, end = validate_range(self.from_input.text(), self.to_input.text(), self.duration_ms)
        self.player.pause()
        self.player.setPosition(start)
        self.preview_end = end if end is not None else self.duration_ms
        self.player.play()

    def export_clip(self) -> None:
        if self.job.active or not self._validate():
            return
        if not self.ffmpeg:
            QMessageBox.warning(self, "FFmpeg unavailable", self.engine_label.text())
            return
        start, end = validate_range(self.from_input.text(), self.to_input.text(), self.duration_ms)
        source = self.current_video
        stamp = format_timestamp(start).replace(":", "-").replace(".", "-")
        end_stamp = format_timestamp(end).replace(":", "-").replace(".", "-") if end is not None else "end"
        default = source.with_name(f"{source.stem}_clip_{stamp}_to_{end_stamp}.mp4")
        destination, _ = QFileDialog.getSaveFileName(self, "Export trimmed clip", str(default), "MP4 video (*.mp4)")
        if not destination:
            return
        path = Path(destination)
        if path.suffix.lower() != ".mp4":
            path = path.with_name(path.name + ".mp4")
            if path.exists() and QMessageBox.question(
                self, "Replace file?", f"{path.name} already exists. Replace it?"
            ) != QMessageBox.StandardButton.Yes:
                return
        try:
            self.job.start(self.ffmpeg, source, path, start, end, self.duration_ms)
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Cannot export", str(exc))
            return
        self._set_busy(True)
        self.status_label.setText(f"Exporting {path.name}…")
        self.progress.setRange(0, 100 if (end is not None or self.duration_ms > start) else 0)
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.reveal_button.hide()
        self.export_status.show()

    def _set_busy(self, busy: bool) -> None:
        self.open_button.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy and self.folder is not None)
        self.files.setEnabled(not busy)
        self.search.setEnabled(not busy)
        self._validate()

    def cancel_export(self) -> None:
        self.status_label.setText("Cancelling export…")
        self.cancel_button.setEnabled(False)
        self.job.cancel()

    def _export_progress(self, value: int) -> None:
        if self.progress.maximum():
            self.progress.setValue(value)
        if self.job.active:
            self.status_label.setText(f"Exporting clip… {value}%")

    def _finish_export_ui(self) -> None:
        self._set_busy(False)
        self.cancel_button.hide()
        self.progress.hide()
        if self._close_after_cancel:
            QTimer.singleShot(0, self.close)

    def _export_succeeded(self, destination: str) -> None:
        self.last_export = Path(destination)
        self._finish_export_ui()
        self.status_label.setText(f"Saved: {self.last_export.name}")
        self.status_label.setToolTip(destination)
        self.reveal_button.show()

    def _export_failed(self, message: str) -> None:
        self._finish_export_ui()
        self.status_label.setText("Export failed. Your source video has not been changed.")
        dialog = QMessageBox(QMessageBox.Icon.Warning, "Export failed", "The clip could not be exported.", parent=self)
        dialog.setDetailedText(message)
        dialog.exec()

    def _export_cancelled(self) -> None:
        self._finish_export_ui()
        self.status_label.setText("Export cancelled. No output file was saved.")

    def reveal_export(self) -> None:
        if self.last_export:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_export.parent)))

    def _read_state(self) -> dict:
        try:
            state = json.loads((self.state_dir / "settings.json").read_text(encoding="utf-8"))
            return state if isinstance(state, dict) and isinstance(state.get("folder", ""), str) else {}
        except (OSError, ValueError):
            return {}

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.job.active:
            answer = QMessageBox.question(self, "Export in progress", "Cancel the current export and close?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                self._close_after_cancel = True
                self.cancel_export()
            event.ignore()
            return
        self.player.stop()
        self.player.setSource(QUrl())
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            (self.state_dir / "settings.json").write_text(json.dumps({"folder": str(self.folder) if self.folder else ""}), encoding="utf-8")
        except OSError:
            pass
        event.accept()
