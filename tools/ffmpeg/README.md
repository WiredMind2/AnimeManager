# Project-local FFmpeg

AnimeManager prefers `bin/ffmpeg` and `bin/ffprobe` here over system PATH.

## Install (Windows)

From the repo root, with the project venv:

```powershell
.\.venv\Scripts\python.exe scripts/install_ffmpeg.py
```

By default the installer **prefers a build whose NVENC encoder actually opens** on this machine. Newest gyan.dev essentials builds (ffmpeg 8.1+) may require NVIDIA driver **610+** (NVENC API 13.1). If your driver only exposes API 13.0, the installer falls back to ffmpeg **8.0.1**, which still uses GPU encode.

```powershell
# Re-download and pick an NVENC-usable build
.\.venv\Scripts\python.exe scripts/install_ffmpeg.py --force --prefer-gpu

# Always keep the absolute latest release (may force CPU encode via auto-fallback)
.\.venv\Scripts\python.exe scripts/install_ffmpeg.py --force --no-prefer-gpu
```

Then restart the app (`run.py`).

Binaries under `bin/` are gitignored — do not commit them.

## GPU encode (NVENC)

Playback `auto` encoder selection probes whether `h264_nvenc` can open, not merely whether `ffmpeg -encoders` lists it. If the probe fails, the app falls back to `libx264` (or the next usable HW encoder).

To use the GPU after a driver update to 610+, re-run the installer with `--force` so the latest essentials build is tried again.
