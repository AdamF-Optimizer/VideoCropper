"""Real FFmpeg + Qt workflow tests. No downloaded sample videos required."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QProcess
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog

from video_cropper.app import MainWindow
from video_cropper.core import find_ffmpeg
from video_cropper.export import ExportJob


APP = QApplication.instance() or QApplication([])
FFMPEG = find_ffmpeg()
FFPROBE = shutil.which("ffprobe")


def wait_for(predicate, timeout=20000):
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return
        QTest.qWait(20)
    raise AssertionError("Timed out waiting for the Qt/FFmpeg operation")


def run(*args):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@unittest.skipUnless(FFPROBE, "FFprobe is required for the media integration checks")
class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="video-cropper-test-")
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / "sample ü & spaces.mp4"
        run(FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=red:s=320x180:r=30:d=1",
            "-f", "lavfi", "-i", "color=blue:s=320x180:r=30:d=1",
            "-f", "lavfi", "-i", "color=green:s=320x180:r=30:d=1",
            "-f", "lavfi", "-i", "color=yellow:s=320x180:r=30:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-filter_complex", "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[v]",
            "-map", "[v]", "-map", "4:a", "-c:v", "libx264", "-g", "120",
            "-sc_threshold", "0", "-pix_fmt", "yuv420p", "-c:a", "aac", str(cls.source))
        cls.silent = cls.root / "silent odd size.mkv"
        run(FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
            "testsrc=size=321x241:rate=20:duration=2", "-c:v", "ffv1", str(cls.silent))
        cls.original_hash = hashlib.sha256(cls.source.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def probe(self, path):
        return json.loads(run(FFPROBE, "-v", "error", "-show_format", "-show_streams",
                              "-of", "json", str(path)).stdout)

    def start_job(self, source, destination, start, end, duration):
        job = ExportJob()
        outcomes = []
        job.succeeded.connect(lambda path: outcomes.append(("success", path)))
        job.failed.connect(lambda error: outcomes.append(("failed", error)))
        job.cancelled.connect(lambda: outcomes.append(("cancelled", "")))
        job.start(FFMPEG, source, destination, start, end, duration)
        return job, outcomes

    def test_accurate_range_preserves_audio_and_source(self):
        destination = self.root / "range result.mp4"
        job, outcomes = self.start_job(self.source, destination, 1250, 2750, 4000)
        progress = []
        job.progress.connect(progress.append)
        wait_for(lambda: bool(outcomes))
        self.assertEqual(outcomes[0][0], "success", outcomes)
        info = self.probe(destination)
        self.assertAlmostEqual(float(info["format"]["duration"]), 1.5, delta=0.08)
        self.assertEqual([s["codec_type"] for s in info["streams"]], ["video", "audio"])
        first = run(FFMPEG, "-v", "error", "-i", str(destination), "-vf", "scale=1:1",
                    "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1").stdout
        last = run(FFMPEG, "-v", "error", "-ss", "1.4", "-i", str(destination), "-vf", "scale=1:1",
                   "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1").stdout
        self.assertGreater(first[2], 200, "First frame should be in the blue second")
        self.assertGreater(last[1], 100, "Last frame should be in the green second")
        self.assertEqual(progress[-1], 100)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.original_hash)

    def test_start_only_exports_to_eof(self):
        destination = self.root / "start only.mp4"
        job, outcomes = self.start_job(self.source, destination, 1500, None, 4000)
        wait_for(lambda: bool(outcomes))
        self.assertEqual(outcomes[0][0], "success", outcomes)
        self.assertAlmostEqual(float(self.probe(destination)["format"]["duration"]), 2.5, delta=0.08)

    def test_silent_video_and_odd_dimensions(self):
        destination = self.root / "silent result.mp4"
        job, outcomes = self.start_job(self.silent, destination, 250, 1250, 2000)
        wait_for(lambda: bool(outcomes))
        self.assertEqual(outcomes[0][0], "success", outcomes)
        info = self.probe(destination)
        self.assertEqual(len(info["streams"]), 1)
        self.assertEqual((info["streams"][0]["width"], info["streams"][0]["height"]), (322, 242))

    def test_cancel_preserves_existing_destination_and_cleans_up(self):
        destination = self.root / "do not replace.mp4"
        destination.write_bytes(b"existing destination")
        job, outcomes = self.start_job(self.source, destination, 0, None, 4000)
        job.cancel()
        wait_for(lambda: bool(outcomes))
        self.assertEqual(outcomes[0][0], "cancelled", outcomes)
        self.assertEqual(destination.read_bytes(), b"existing destination")
        self.assertEqual(list(self.root.glob(".videocropper-*")), [])

    def test_ffmpeg_error_preserves_existing_destination(self):
        invalid = self.root / "broken.mp4"
        invalid.write_bytes(b"not a video")
        destination = self.root / "keep on failure.mp4"
        destination.write_bytes(b"existing destination")
        job, outcomes = self.start_job(invalid, destination, 0, None, 0)
        wait_for(lambda: bool(outcomes))
        self.assertEqual(outcomes[0][0], "failed", outcomes)
        self.assertEqual(destination.read_bytes(), b"existing destination")
        self.assertEqual(list(self.root.glob(".videocropper-*")), [])

    def test_missing_executable_cleans_up(self):
        job = ExportJob()
        errors = []
        job.failed.connect(errors.append)
        destination = self.root / "never created.mp4"
        job.start(str(self.root / "missing-ffmpeg.exe"), self.source, destination, 0, None, 4000)
        wait_for(lambda: bool(errors))
        self.assertFalse(job.active)
        self.assertFalse(destination.exists())
        self.assertEqual(list(self.root.glob(".videocropper-*")), [])

    def test_original_and_hard_link_protected(self):
        job = ExportJob()
        with self.assertRaises(ValueError):
            job.start(FFMPEG, self.source, self.source, 0, None, 4000)
        alias = self.root / "hardlink.mp4"
        os.link(self.source, alias)
        with self.assertRaises(ValueError):
            job.start(FFMPEG, self.source, alias, 0, None, 4000)

    def test_gui_folder_playback_marks_preview_and_export(self):
        window = MainWindow(state_dir=self.root / "state", restore=False)
        window.show()
        try:
            window.open_folder(self.root)
            source_item = next(window.files.item(i) for i in range(window.files.count())
                               if window.files.item(i).text() == self.source.name)
            window.files.setCurrentItem(source_item)
            wait_for(lambda: window.duration_ms >= 3900)
            wait_for(lambda: window.player.position() > 100)
            window.player.pause()
            window.timeline.setValue(1250)
            self.assertAlmostEqual(window.player.position(), 1250, delta=100)
            window.mark_from.click()
            self.assertEqual(window.from_input.text(), "00:00:01.250")
            window.timeline.setValue(2750)
            window.mark_to.click()
            self.assertEqual(window.to_input.text(), "00:00:02.750")
            window.to_input.setText("1")
            self.assertFalse(window.export_button.isEnabled())
            window.to_input.setText("2.750")
            self.assertTrue(window.export_button.isEnabled())
            window.preview_button.click()
            wait_for(lambda: window.preview_end is None, timeout=6000)
            self.assertAlmostEqual(window.player.position(), 2750, delta=100)
            destination = self.root / "gui export.mp4"
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(destination), "")):
                window.export_button.click()
            self.assertTrue(window.job.active)
            self.assertFalse(window.files.isEnabled())
            wait_for(lambda: not window.job.active)
            self.assertTrue(destination.exists())
            self.assertTrue(window.files.isEnabled())
            self.assertEqual(window.last_export, destination)
            self.assertAlmostEqual(float(self.probe(destination)["format"]["duration"]), 1.5, delta=0.08)
            window.search.setText("no matches please")
            self.assertEqual(window.file_count.text().split()[0], "0")
            empty = self.root / "empty"
            empty.mkdir(exist_ok=True)
            window.open_folder(empty)
            self.assertEqual(window.files.count(), 0)
            self.assertFalse(window.export_button.isEnabled())
        finally:
            window.close()
            QCoreApplication.processEvents()


if __name__ == "__main__":
    unittest.main()
