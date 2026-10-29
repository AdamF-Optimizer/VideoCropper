from pathlib import Path
import tempfile
import unittest

from video_cropper.core import format_timestamp, list_videos, parse_timestamp, same_file, validate_range


class TimestampTests(unittest.TestCase):
    def test_supported_formats(self):
        for text, expected in [("0", 0), ("12.345", 12345), ("90", 90000),
                               ("01:23.5", 83500), ("1:02:03.004", 3723004),
                               (" 00:00:01.001 ", 1001)]:
            with self.subTest(text=text):
                self.assertEqual(parse_timestamp(text), expected)

    def test_invalid_formats(self):
        for text in ["", "-1", "1:60", "1:60:00", "NaN", "inf", "1e3", "1,2",
                     "1.2345", "1:2:3:4", "1::2", ".5", "99999999999"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_timestamp(text)

    def test_format_round_trip(self):
        for ms in (0, 1, 59999, 60000, 3600001, 36000000):
            self.assertEqual(parse_timestamp(format_timestamp(ms)), ms)

    def test_start_only(self):
        self.assertEqual(validate_range("12", "", 20000), (12000, None))
        self.assertEqual(validate_range("12", "   "), (12000, None))

    def test_range_validation(self):
        self.assertEqual(validate_range("2", "4", 4000), (2000, 4000))
        for start, end, duration in [("4", "", 4000), ("4", "3", 10000),
                                     ("2", "2", 10000), ("0", "4.001", 4000)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                validate_range(start, end, duration)

    def test_folder_discovery_and_original_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ["b.MP4", "a.mkv", "notes.txt"]:
                (root / name).touch()
            (root / "folder.mp4").mkdir()
            self.assertEqual([p.name for p in list_videos(root)], ["a.mkv", "b.MP4"])
            self.assertTrue(same_file(root / "b.MP4", root / "." / "b.MP4"))
            self.assertFalse(same_file(root / "b.MP4", root / "new.mp4"))


if __name__ == "__main__":
    unittest.main()
