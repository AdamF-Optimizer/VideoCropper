"""Timestamp validation and FFmpeg commands, independent of the GUI."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
from decimal import Decimal

VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv", ".mpg",
    ".mpeg", ".mts", ".m2ts", ".ts", ".3gp", ".ogv", ".vob", ".flv",
})


def parse_timestamp(value: str) -> int:
    """Accept seconds, MM:SS or HH:MM:SS with up to 3 decimal places."""
    value = value.strip()
    if not re.fullmatch(r"\d+(?::\d{1,2}){0,2}(?:\.\d{1,3})?", value):
        raise ValueError("Use seconds, MM:SS, or HH:MM:SS.mmm (for example 01:23.500).")
    parts = value.split(":")
    if any(Decimal(part) >= 60 for part in parts[1:]):
        raise ValueError("Minutes and seconds after a colon must be below 60.")
    seconds = Decimal(0)
    for part in parts:
        seconds = seconds * 60 + Decimal(part)
    milliseconds = int(seconds * 1000)
    if milliseconds > 2_147_483_647:
        raise ValueError("That timestamp is too large.")
    return milliseconds


def format_timestamp(milliseconds: int) -> str:
    seconds, millis = divmod(max(0, milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{millis:03}"


def validate_range(start: str, end: str, duration_ms: int = 0) -> tuple[int, int | None]:
    start_ms = parse_timestamp(start)
    end_ms = parse_timestamp(end) if end.strip() else None
    if end_ms is not None and end_ms <= start_ms:
        raise ValueError("The To time must be later than the From time.")
    if duration_ms > 0:
        if start_ms >= duration_ms:
            raise ValueError("The From time must be before the end of the video.")
        if end_ms is not None and end_ms > duration_ms:
            raise ValueError("The To time is past the end of the video.")
    return start_ms, end_ms


def list_videos(folder: Path) -> list[Path]:
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS),
        key=lambda p: p.name.casefold(),
    )


def find_ffmpeg() -> str:
    configured = os.environ.get("FFMPEG_BINARY")
    if configured:
        found = shutil.which(configured)
        if found:
            return found
        raise FileNotFoundError("FFMPEG_BINARY does not point to an executable.")
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise FileNotFoundError("FFmpeg was not found. Run Setup.ps1 or add FFmpeg to PATH.") from exc


def same_file(source: Path, destination: Path) -> bool:
    if source.resolve() == destination.resolve():
        return True
    return destination.exists() and os.path.samefile(source, destination)


def ffmpeg_arguments(source: Path, output: Path, start_ms: int, end_ms: int | None) -> list[str]:
    if start_ms < 0 or (end_ms is not None and end_ms <= start_ms):
        raise ValueError("Invalid trim range.")
    args = ["-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-ss", f"{start_ms / 1000:.3f}", "-i", str(source)]
    if end_ms is not None:
        args += ["-t", f"{(end_ms - start_ms) / 1000:.3f}"]
    return args + [
        "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats", str(output),
    ]
