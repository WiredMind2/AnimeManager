"""FFmpeg H.264 encoder detection and command-line argument builders."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess

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


def list_h264_encoders(ffmpeg_bin: str) -> set[str]:
    """Return H.264 encoder names advertised by ``ffmpeg -encoders``."""
    ffmpeg_cmd = shutil.which(ffmpeg_bin) or ffmpeg_bin
    try:
        result = subprocess.run(
            [ffmpeg_cmd, "-hide_banner", "-encoders"],
            check=False,
            capture_output=True,
            text=True,
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


def resolve_video_encoder(*, requested: str, ffmpeg_bin: str) -> str:
    """Resolve a settings value to a concrete FFmpeg video encoder name."""
    normalized = str(requested or "auto").strip().lower()
    available = list_h264_encoders(ffmpeg_bin)

    if normalized == "auto":
        for candidate in AUTO_ENCODER_PRIORITY:
            if candidate in available:
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

    return normalized


def build_video_encode_args(encoder: str, *, keyframe_expr: str) -> list[str]:
    """Return FFmpeg video encode flags for browser-compatible HLS output."""
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
        args.extend(["-preset", "p4", "-tune", "hq", "-rc", "vbr", "-cq", "23"])
    elif resolved == "h264_qsv":
        args.extend(["-global_quality", "23"])
    elif resolved == "h264_amf":
        args.extend(
            ["-quality", "balanced", "-rc", "cqp", "-qp_i", "23", "-qp_p", "23"]
        )
    elif resolved == "h264_mf":
        args.extend(["-rate_control", "quality", "-quality", "50"])

    args.extend(["-force_key_frames", keyframe_expr])
    return args


__all__ = [
    "AUTO_ENCODER_PRIORITY",
    "SOFTWARE_ENCODER",
    "SUPPORTED_ENCODERS",
    "build_video_encode_args",
    "list_h264_encoders",
    "resolve_video_encoder",
]
