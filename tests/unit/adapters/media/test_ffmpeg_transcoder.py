"""Regression tests for :class:`FFmpegTranscoderAdapter`."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from adapters.media.ffmpeg_transcoder import FFmpegTranscoderAdapter
from domain.errors import InfrastructureError


def _build(
    *,
    subtitle_track: int | None,
    start_segment_index: int,
    segment_seconds: int = 4,
) -> list[str]:
    adapter = FFmpegTranscoderAdapter()
    return adapter._build_command(
        ffmpeg_cmd="ffmpeg",
        source_path="/tmp/sample.mkv",
        playlist_output="/tmp/out/index.m3u8",
        output_dir="/tmp/out",
        audio_track=None,
        subtitle_track=subtitle_track,
        start_segment_index=start_segment_index,
        segment_seconds=segment_seconds,
    )


def _input_seek_value(command: list[str]) -> str | None:
    """Return the ``-ss`` value that appears BEFORE the ``-i`` flag."""
    try:
        i_idx = command.index("-i")
    except ValueError:
        return None
    pre = command[:i_idx]
    if "-ss" in pre:
        return pre[pre.index("-ss") + 1]
    return None


def _output_seek_value(command: list[str]) -> str | None:
    """Return the ``-ss`` value that appears AFTER the ``-i`` flag."""
    try:
        i_idx = command.index("-i")
    except ValueError:
        return None
    post = command[i_idx + 1:]
    if "-ss" in post:
        return post[post.index("-ss") + 1]
    return None


def test_segment_zero_uses_no_seek_at_all():
    command = _build(subtitle_track=None, start_segment_index=0)
    assert "-ss" not in command
    assert "-copyts" not in command


def test_seek_with_subtitle_selection_does_not_inject_video_filter():
    command = _build(subtitle_track=1, start_segment_index=0)
    assert "-vf" not in command


def test_seek_with_or_without_subtitle_selection_uses_same_input_seek():
    plain = _build(subtitle_track=None, start_segment_index=10, segment_seconds=4)
    with_sub_choice = _build(subtitle_track=2, start_segment_index=10, segment_seconds=4)
    assert _input_seek_value(plain) == "40"
    assert _input_seek_value(with_sub_choice) == "40"
    assert _output_seek_value(plain) == "40"
    assert _output_seek_value(with_sub_choice) == "40"


def test_seek_without_subtitles_uses_input_seek():
    command = _build(subtitle_track=None, start_segment_index=10, segment_seconds=4)
    assert _input_seek_value(command) == "40"
    assert _output_seek_value(command) == "40"
    assert "-copyts" in command


def test_command_forces_browser_compatible_h264_output():
    command = _build(subtitle_track=None, start_segment_index=0)
    assert "-pix_fmt" in command
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"
    assert "-profile:v" in command
    assert command[command.index("-profile:v") + 1] == "high"


def test_command_uses_nvenc_when_configured_for_nvidia():
    adapter = FFmpegTranscoderAdapter(video_codec="h264_nvenc")
    command = adapter._build_command(
        ffmpeg_cmd="ffmpeg",
        source_path="/tmp/sample.mkv",
        playlist_output="/tmp/out/index.m3u8",
        output_dir="/tmp/out",
        audio_track=None,
        subtitle_track=None,
        start_segment_index=0,
        segment_seconds=4,
    )
    assert "-c:v" in command
    assert command[command.index("-c:v") + 1] == "h264_nvenc"
    assert "-rc:v" in command
    assert command[command.index("-rc:v") + 1] == "vbr"
    assert "-cq:v" in command
    assert command[command.index("-cq:v") + 1] == "23"


def test_ensure_hls_session_fails_fast_when_nvenc_is_required_but_unavailable(
    monkeypatch,
    tmp_path: Path,
):
    adapter = FFmpegTranscoderAdapter(
        video_codec="h264_nvenc",
        require_hardware_acceleration=True,
    )

    def fail_encoder_discovery(*_args, **_kwargs):
        raise RuntimeError("ffmpeg not available")

    monkeypatch.setattr("adapters.media.ffmpeg_transcoder.subprocess.run", fail_encoder_discovery)

    with pytest.raises(InfrastructureError, match="NVIDIA GPU acceleration is required"):
        adapter.ensure_hls_session(
            session_id="s1",
            source_path=str(tmp_path / "episode.mkv"),
            output_dir=str(tmp_path / "out"),
        )


def test_nvenc_validation_uses_supported_probe_frame_size(monkeypatch):
    adapter = FFmpegTranscoderAdapter(
        video_codec="h264_nvenc",
        require_hardware_acceleration=True,
    )
    calls: list[list[str]] = []

    def fake_run(command, check, capture_output, text, timeout):
        calls.append(list(command))
        if "-encoders" in command:
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout="Encoders:\n V....D h264_nvenc NVIDIA NVENC H.264 encoder\n",
                stderr="",
            )
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("adapters.media.ffmpeg_transcoder.subprocess.run", fake_run)
    adapter._validate_required_acceleration("ffmpeg")

    assert len(calls) == 2
    probe_cmd = calls[1]
    assert "-f" in probe_cmd
    assert probe_cmd[probe_cmd.index("-f") + 1] == "lavfi"
    assert "-i" in probe_cmd
    assert probe_cmd[probe_cmd.index("-i") + 1] == "nullsrc=size=1280x720:rate=1"
    assert "-c:v" in probe_cmd
    assert probe_cmd[probe_cmd.index("-c:v") + 1] == "h264_nvenc"


def test_materialize_subtitle_tracks_extracts_vtt(monkeypatch, tmp_path: Path):
    adapter = FFmpegTranscoderAdapter()

    monkeypatch.setattr(
        adapter,
        "probe_media_tracks",
        lambda _src: {
            "audio": [],
            "subtitles": [
                {"id": 0, "label": "ENG", "codec": "subrip"},
                {"id": 1, "label": "SPA", "codec": "ass"},
            ],
        },
    )

    def fake_run(command, check, stdout, stderr, timeout):
        target = Path(command[-1])
        if str(target).endswith(".vtt"):
            target.write_text("WEBVTT\n\n", encoding="utf-8")
        else:
            target.write_text("[Script Info]\nTitle: t\n\n[V4+ Styles]\n\n[Events]\n", encoding="utf-8")
        return None

    monkeypatch.setattr("adapters.media.ffmpeg_transcoder.subprocess.run", fake_run)

    rows = adapter.materialize_subtitle_tracks(
        source_path=str(tmp_path / "episode.mkv"),
        output_dir=str(tmp_path),
    )
    assert [row["id"] for row in rows] == [0, 1]
    assert [row["filename"] for row in rows] == ["subtitle_000.vtt", "subtitle_001.vtt"]
    assert rows[0].get("codec") == "subrip"
    assert rows[0].get("ass_filename") is None
    assert rows[1].get("codec") == "ass"
    assert rows[1].get("ass_filename") == "subtitle_001.ass"
