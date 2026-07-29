"""FFmpeg H.264 encoder detection and command-line argument builders."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading

_LOG = logging.getLogger(__name__)

SOFTWARE_ENCODER = "libx264"

SUPPORTED_ENCODERS: tuple[str, ...] = (
    SOFTWARE_ENCODER,
    "h264_nvenc",
    "h264_qsv",
    "h264_amf",
    "h264_mf",
)

AUTO_ENCODER_PRIORITY: tuple[str, ...] = (
    "h264_nvenc",
    "h264_qsv",
    "h264_amf",
    "h264_mf",
    SOFTWARE_ENCODER,
)

_ENCODER_LINE_RE = re.compile(r"^\s*V\S+\s+(\S+)\s+")

# Process-lifetime cache: (resolved ffmpeg path, encoder) -> usable?
_USABLE_CACHE: dict[tuple[str, str], bool] = {}
_USABLE_CACHE_LOCK = threading.Lock()


def list_h264_encoders(ffmpeg_bin: str) -> set[str]:
    """Return H.264 encoder names advertised by ``ffmpeg -encoders``."""
    ffmpeg_cmd = shutil.which(ffmpeg_bin) or ffmpeg_bin
    try:
        result = subprocess.run(
            [ffmpeg_cmd, "-hide_banner", "-encoders"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        output = (result.stdout or "") + (result.stderr or "")
    except Exception:
        return {SOFTWARE_ENCODER}

    found: set[str] = set()
    for line in output.splitlines():
        match = _ENCODER_LINE_RE.match(line)
        if not match:
            continue
        name = match.group(1)
        if name in SUPPORTED_ENCODERS:
            found.add(name)
    if SOFTWARE_ENCODER not in found:
        found.add(SOFTWARE_ENCODER)
    return found


def encoder_is_usable(ffmpeg_bin: str, encoder: str) -> bool:
    """True when ``encoder`` can actually open on this machine.

    ``ffmpeg -encoders`` lists hardware encoders even when the driver/SDK
    is too old (e.g. NVENC API 13.0 vs a build requiring 13.1). A tiny
    lavfi smoke encode catches that before playback session create.
    """
    resolved = encoder if encoder in SUPPORTED_ENCODERS else SOFTWARE_ENCODER
    if resolved == SOFTWARE_ENCODER:
        return True

    ffmpeg_cmd = shutil.which(ffmpeg_bin) or ffmpeg_bin
    cache_key = (ffmpeg_cmd, resolved)
    with _USABLE_CACHE_LOCK:
        cached = _USABLE_CACHE.get(cache_key)
        if cached is not None:
            return cached

    usable = _probe_encoder_open(ffmpeg_cmd, resolved)
    with _USABLE_CACHE_LOCK:
        _USABLE_CACHE[cache_key] = usable
    if not usable:
        _LOG.warning(
            "ffmpeg_video_encoder_unusable encoder=%s ffmpeg=%s",
            resolved,
            ffmpeg_cmd,
        )
    return usable


def _probe_encoder_open(ffmpeg_cmd: str, encoder: str) -> bool:
    command = [
        ffmpeg_cmd,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=256x144:d=0.1",
        "-frames:v",
        "1",
        "-c:v",
        encoder,
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except Exception:
        return False
    if result.returncode == 0:
        return True
    stderr = (result.stderr or "").strip()
    if stderr:
        _LOG.info(
            "ffmpeg_encoder_probe_failed encoder=%s rc=%s err=%s",
            encoder,
            result.returncode,
            stderr.splitlines()[-1][:240],
        )
    return False


def clear_encoder_usable_cache() -> None:
    """Test helper — drop process-lifetime usability cache."""
    with _USABLE_CACHE_LOCK:
        _USABLE_CACHE.clear()


def resolve_video_encoder(*, requested: str, ffmpeg_bin: str) -> str:
    """Resolve a settings value to a concrete FFmpeg video encoder name."""
    normalized = str(requested or "auto").strip().lower()
    available = list_h264_encoders(ffmpeg_bin)

    if normalized == "auto":
        for candidate in AUTO_ENCODER_PRIORITY:
            if candidate not in available:
                continue
            if not encoder_is_usable(ffmpeg_bin, candidate):
                continue
            if candidate != SOFTWARE_ENCODER:
                _LOG.info("ffmpeg_video_encoder_auto_selected encoder=%s", candidate)
            return candidate
        return SOFTWARE_ENCODER

    if normalized not in SUPPORTED_ENCODERS:
        _LOG.warning(
            "ffmpeg_video_encoder_unknown requested=%s fallback=%s",
            requested,
            SOFTWARE_ENCODER,
        )
        return SOFTWARE_ENCODER

    if normalized not in available:
        _LOG.warning(
            "ffmpeg_video_encoder_unavailable requested=%s fallback=%s",
            normalized,
            SOFTWARE_ENCODER,
        )
        return SOFTWARE_ENCODER

    if not encoder_is_usable(ffmpeg_bin, normalized):
        _LOG.warning(
            "ffmpeg_video_encoder_unusable requested=%s fallback=%s",
            normalized,
            SOFTWARE_ENCODER,
        )
        return SOFTWARE_ENCODER

    return normalized


def build_video_encode_args(encoder: str, *, keyframe_expr: str) -> list[str]:
    """Return FFmpeg video encode flags for browser-compatible HLS output.

    Hardware encoders ignore ``-force_key_frames`` unless forced-IDR mode is
    enabled, which leaves seek-restart segments longer than ``hls_time`` and
    desyncs the player timeline from the playlist clock.
    """
    resolved = encoder if encoder in SUPPORTED_ENCODERS else SOFTWARE_ENCODER
    args: list[str] = [
        "-c:v",
        resolved,
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-level:v",
        "4.1",
    ]

    if resolved == SOFTWARE_ENCODER:
        args.extend(["-preset", "veryfast", "-crf", "23"])
    elif resolved == "h264_nvenc":
        # NVENC option spelling is ``-forced-idr`` (hyphen), not ``_``.
        args.extend(
            [
                "-preset",
                "p4",
                "-tune",
                "hq",
                "-rc",
                "vbr",
                "-cq",
                "23",
                "-forced-idr",
                "1",
                "-no-scenecut",
                "1",
            ]
        )
    elif resolved == "h264_qsv":
        args.extend(["-global_quality", "23", "-forced_idr", "1"])
    elif resolved == "h264_amf":
        args.extend(
            [
                "-quality",
                "balanced",
                "-rc",
                "cqp",
                "-qp_i",
                "23",
                "-qp_p",
                "23",
                "-forced_idr",
                "1",
            ]
        )
    elif resolved == "h264_mf":
        args.extend(
            [
                "-rate_control",
                "quality",
                "-quality",
                "50",
                "-forced_idr",
                "1",
            ]
        )

    args.extend(["-force_key_frames", keyframe_expr])
    return args


__all__ = [
    "AUTO_ENCODER_PRIORITY",
    "SOFTWARE_ENCODER",
    "SUPPORTED_ENCODERS",
    "build_video_encode_args",
    "clear_encoder_usable_cache",
    "encoder_is_usable",
    "list_h264_encoders",
    "resolve_video_encoder",
]
