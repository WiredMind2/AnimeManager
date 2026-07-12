"""Canonical HLS playlist generation."""

from __future__ import annotations

import math
import os
import re
from pathlib import Path

from application.dto import PlaybackSessionDTO

_SEGMENT_NAME_RE = re.compile(r"^segment_(\d+)\.ts$")


def latest_existing_segment(output_dir: str) -> int:
    latest = -1
    try:
        entries = os.listdir(output_dir)
    except OSError:
        return latest
    for entry in entries:
        match = _SEGMENT_NAME_RE.match(entry)
        if match is None:
            continue
        try:
            idx = int(match.group(1))
        except ValueError:
            continue
        if idx > latest:
            latest = idx
    return latest


def render_manifest(session: PlaybackSessionDTO) -> str:
    total = max(1, session.total_segments)
    seg_secs = max(1, session.segment_seconds)
    duration = max(0.0, session.duration_seconds)
    # Always advertise the full source timeline from segment 0 so the
    # player, seek bar, and subtitle clocks share one absolute clock.
    # FFmpeg may start encoding near the resume point for a fast start;
    # missing earlier segments are materialized on demand via
    # PlaybackService._ensure_segment.
    last_seg_seconds = duration - (total - 1) * seg_secs
    if last_seg_seconds <= 0 or last_seg_seconds > seg_secs:
        last_seg_seconds = float(seg_secs)

    # Always advertise a VOD playlist with EXT-X-ENDLIST, even before
    # transcoding has produced every segment. The canonical playlist lists
    # every segment up front (so arbitrary seeking works via on-demand
    # restarts in PlaybackService._ensure_segment), so it is complete as a
    # *playlist*. Emitting EVENT (no ENDLIST) makes Shaka treat the stream
    # as live: it reports an Infinite (UINT32) duration, probes a mid-stream
    # segment to bootstrap the live timeline, polls the manifest, and — for a
    # resume session anchored near the end — maps the first (near-end)
    # segment to currentTime 0, producing "timeline shows the beginning but
    # the player plays the last few seconds." VOD+ENDLIST makes Shaka seek
    # to the requested startTime (0 for a fresh start) and play linearly.
    lines: list[str] = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{seg_secs}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD",
    ]
    for index in range(0, total):
        seg_dur = last_seg_seconds if index == total - 1 else float(seg_secs)
        lines.append(f"#EXTINF:{seg_dur:.3f},")
        lines.append(f"segment_{index:05d}.ts")
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


def write_manifest_file(session: PlaybackSessionDTO) -> None:
    text = render_manifest(session)
    tmp_path = session.manifest_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp_path, session.manifest_path)


def write_initial_playlist(*, manifest_path: str, duration: float, segment_seconds: int) -> int:
    total = max(1, math.ceil(duration / segment_seconds))
    session = PlaybackSessionDTO(
        session_id="",
        anime_id=0,
        file_id="",
        file_title="",
        manifest_path=manifest_path,
        output_dir=str(Path(manifest_path).parent),
        token="",
        expires_at=0.0,
        created_at=0.0,
        last_seen_at=0.0,
        duration_seconds=duration,
        segment_seconds=segment_seconds,
        total_segments=total,
    )
    write_manifest_file(session)
    return total


__all__ = [
    "latest_existing_segment",
    "render_manifest",
    "write_manifest_file",
    "write_initial_playlist",
]
