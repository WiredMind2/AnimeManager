"""Unit tests for FFmpeg H.264 encoder detection and arg builders."""

from __future__ import annotations

from unittest.mock import patch

from adapters.media.ffmpeg_encoder import (
    SOFTWARE_ENCODER,
    build_video_encode_args,
    list_h264_encoders,
    resolve_video_encoder,
)

_NVENC_AND_QSV_OUTPUT = """
 V....D libx264              libx264 H.264
 V....D h264_nvenc           NVIDIA NVENC H.264 encoder
 V..... h264_qsv              H.264 (Intel Quick Sync Video acceleration)
"""

_NO_HARDWARE_OUTPUT = """
 V....D libx264              libx264 H.264
"""


def test_list_h264_encoders_parses_available_encoders() -> None:
    with patch(
        "adapters.media.ffmpeg_encoder.subprocess.run",
        return_value=type("R", (), {"stdout": _NVENC_AND_QSV_OUTPUT, "stderr": ""})(),
    ):
        found = list_h264_encoders("ffmpeg")
    assert found == {"libx264", "h264_nvenc", "h264_qsv"}


def test_auto_prefers_nvenc_when_available() -> None:
    with patch(
        "adapters.media.ffmpeg_encoder.list_h264_encoders",
        return_value={"libx264", "h264_nvenc", "h264_qsv"},
    ):
        assert resolve_video_encoder(requested="auto", ffmpeg_bin="ffmpeg") == "h264_nvenc"


def test_auto_falls_back_to_libx264() -> None:
    with patch(
        "adapters.media.ffmpeg_encoder.list_h264_encoders",
        return_value={"libx264"},
    ):
        assert resolve_video_encoder(requested="auto", ffmpeg_bin="ffmpeg") == SOFTWARE_ENCODER


def test_explicit_invalid_encoder_falls_back() -> None:
    with patch(
        "adapters.media.ffmpeg_encoder.list_h264_encoders",
        return_value={"libx264"},
    ):
        assert (
            resolve_video_encoder(requested="h264_nvenc", ffmpeg_bin="ffmpeg")
            == SOFTWARE_ENCODER
        )


def test_explicit_libx264_when_available() -> None:
    with patch(
        "adapters.media.ffmpeg_encoder.list_h264_encoders",
        return_value={"libx264", "h264_nvenc"},
    ):
        assert resolve_video_encoder(requested="libx264", ffmpeg_bin="ffmpeg") == SOFTWARE_ENCODER


def test_unknown_requested_value_falls_back() -> None:
    with patch(
        "adapters.media.ffmpeg_encoder.list_h264_encoders",
        return_value={"libx264", "h264_nvenc"},
    ):
        assert resolve_video_encoder(requested="bogus", ffmpeg_bin="ffmpeg") == SOFTWARE_ENCODER


def test_build_video_encode_args_libx264() -> None:
    args = build_video_encode_args(SOFTWARE_ENCODER, keyframe_expr="expr:gte(t,n_forced*4)")
    assert args == [
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-level:v",
        "4.1",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-force_key_frames",
        "expr:gte(t,n_forced*4)",
    ]


def test_build_video_encode_args_nvenc() -> None:
    args = build_video_encode_args("h264_nvenc", keyframe_expr="expr:gte(t,n_forced*4)")
    assert "-c:v" in args
    assert args[args.index("-c:v") + 1] == "h264_nvenc"
    assert "-cq" in args
    assert args[args.index("-cq") + 1] == "23"
    assert "-pix_fmt" in args
    assert args[args.index("-pix_fmt") + 1] == "yuv420p"
    assert "-force_key_frames" in args


def test_build_video_encode_args_qsv() -> None:
    args = build_video_encode_args("h264_qsv", keyframe_expr="expr:gte(t,n_forced*4)")
    assert args[args.index("-c:v") + 1] == "h264_qsv"
    assert "-global_quality" in args
    assert args[args.index("-global_quality") + 1] == "23"
