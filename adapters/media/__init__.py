"""Media playback adapters package."""

from __future__ import annotations

from adapters.media.ffmpeg_paths import resolve_ffmpeg_bins
from adapters.media.ffmpeg_transcoder import FFmpegTranscoderAdapter

__all__ = ["FFmpegTranscoderAdapter", "resolve_ffmpeg_bins"]
