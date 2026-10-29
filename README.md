# Video Cropper

A local Windows desktop app for browsing, watching, and trimming videos with FFmpeg.

## Launch

Double-click **Launch Video Cropper.cmd**. The local runtime is already set up in this workspace.

On a fresh copy, the launcher runs `Setup.ps1` automatically. Setup downloads Python 3.13 and the pinned dependencies into this folder; it needs internet access for the first run. No system Python installation is required. If you move the project folder, run `Setup.ps1` again to refresh the environment's Python paths.

## Trim a video

1. Click **Open folder…** and select a folder. Videos appear in the sidebar; select one to watch it. Scanning covers that folder, without its subfolders.
2. Drag or click the timeline to seek. Use **Play/Pause**, **−5 s**, **+5 s**, and the volume slider while watching.
3. Enter a **From** timestamp, or click **Use current [I]** to mark the playhead position.
4. Optionally enter a **To** timestamp or click **Use current [O]**. Leave **To** blank to keep everything from **From** to the end.
5. Click **Preview range** to watch the selection, then **Export clip…** and choose a destination.

Accepted timestamps: seconds (`83.5`), minutes and seconds (`01:23.500`), or hours, minutes, and seconds (`00:01:23.500`). Precision is up to milliseconds; actual video boundaries follow the source's frame rate.

Exports use MP4 with H.264 video and AAC audio, with accurate seeking and high quality re-encoding. The first video track and, if present, the first audio track are exported. Subtitles and other tracks are omitted. Odd image dimensions are padded by at most one pixel for encoder compatibility. Re-encoding takes time and is not lossless.

Originals are protected from being selected as the output. The app writes to a temporary file beside the destination and only replaces the destination when FFmpeg succeeds. Cancellation and failures remove the temporary output. You can continue watching during export. The last opened folder is remembered locally in `.state/settings.json`.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| Ctrl+O | Open folder |
| Space | Play / pause |
| Left / Right | Seek backward / forward 5 seconds |
| I / O | Set From / To to current position |
| Ctrl+Enter | Export clip |

Text entry keeps normal typing behavior when a timestamp or filter field has focus.

## FFmpeg and playback

The app uses `ffmpeg` from your `PATH` when available. Otherwise it uses the executable supplied by `imageio-ffmpeg`. To select a particular executable, set `FFMPEG_BINARY` to its full path before launching.

Playback uses Qt Multimedia. Codec availability can vary by file and machine. If playback is unavailable, the app displays the error and still allows export using typed timestamps. Videos remain on your machine; there is no upload service.

## Development

Run setup or launch from PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1
.\.venv\Scripts\python.exe main.py
```

Run the checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The integration checks generate their own short videos and exercise real FFmpeg exports, exact trimming between keyframes, audio retention, video-only files, odd image sizes, cancellation, failed processes, original protection, and the GUI playback/export workflow. They require `ffprobe` on `PATH` and skip if it is absent. GUI tests use Qt's offscreen platform.

Source dependencies are in `requirements.txt`; `requirements.lock` pins the tested versions. The Windows setup uses a local copy of [uv](https://docs.astral.sh/uv/). The GUI uses [Qt for Python](https://doc.qt.io/qtforpython-6/PySide6/QtMultimedia/QMediaPlayer.html), and export uses [FFmpeg](https://ffmpeg.org/).
