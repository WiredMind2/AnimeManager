# Project-local FFmpeg

AnimeManager prefers `bin/ffmpeg` and `bin/ffprobe` here over system PATH.

## Install (Windows)

From the repo root, with the project venv:

```powershell
.\.venv\Scripts\python.exe scripts/install_ffmpeg.py
```

Then restart the app (`run.py`).

Binaries under `bin/` are gitignored — do not commit them.
