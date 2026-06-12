"""Regression tests for :class:`FFmpegTranscoderAdapter`."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

from adapters.media.ffmpeg_transcoder import FFmpegTranscoderAdapter, _ActiveTranscode


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
    assert _output_seek_value(plain) is None
    assert _output_seek_value(with_sub_choice) is None


def test_seek_without_subtitles_uses_input_seek():
    command = _build(subtitle_track=None, start_segment_index=10, segment_seconds=4)
    assert _input_seek_value(command) == "40"
    assert _output_seek_value(command) is None
    assert "-copyts" in command


def test_seek_keyframe_expression_is_offset_from_seek_point():
    command = _build(subtitle_track=None, start_segment_index=10, segment_seconds=4)
    idx = command.index("-force_key_frames")
    assert command[idx + 1] == "expr:gte(t,40+n_forced*4)"


def test_start_keyframe_expression_starts_at_zero():
    command = _build(subtitle_track=None, start_segment_index=0, segment_seconds=4)
    idx = command.index("-force_key_frames")
    assert command[idx + 1] == "expr:gte(t,n_forced*4)"


def test_command_forces_browser_compatible_h264_output():
    command = _build(subtitle_track=None, start_segment_index=0)
    assert "-pix_fmt" in command
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"
    assert "-profile:v" in command
    assert command[command.index("-profile:v") + 1] == "high"


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


def test_ensure_hls_evicts_oldest_when_at_capacity(monkeypatch, tmp_path: Path):
    """A third concurrent session must not fail with 'server busy'."""
    adapter = FFmpegTranscoderAdapter(max_active_sessions=2)
    out = tmp_path / "out"
    out.mkdir()

    def fake_spawn(command, log_path):
        proc = MagicMock()
        proc.poll.return_value = None
        return proc

    monkeypatch.setattr(adapter, "_spawn_ffmpeg", fake_spawn)
    monkeypatch.setattr(adapter, "_write_spawn_record", lambda *_a, **_k: None)

    now = time.time()
    adapter._active["old"] = _ActiveTranscode(
        session_id="old",
        output_dir=str(out),
        manifest_path=str(out / "index.m3u8"),
        process=fake_spawn([], ""),
        started_at=now - 10,
        start_segment_index=0,
        segment_seconds=4,
        source_path=str(tmp_path / "a.mkv"),
        audio_track=None,
        subtitle_track=None,
    )
    adapter._active["mid"] = _ActiveTranscode(
        session_id="mid",
        output_dir=str(out),
        manifest_path=str(out / "index.m3u8"),
        process=fake_spawn([], ""),
        started_at=now - 5,
        start_segment_index=0,
        segment_seconds=4,
        source_path=str(tmp_path / "b.mkv"),
        audio_track=None,
        subtitle_track=None,
    )
    (out / "index.m3u8").write_text("#EXTM3U\n", encoding="utf-8")
    source = tmp_path / "c.mkv"
    source.write_bytes(b"x")

    adapter.ensure_hls_session(
        session_id="new",
        source_path=str(source),
        output_dir=str(out),
    )

    assert "old" not in adapter._active
    assert "new" in adapter._active
    assert adapter._active["new"].process.poll() is None
