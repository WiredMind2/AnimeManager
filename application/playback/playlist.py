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
    last_seg_seconds = duration - (total - 1) * seg_secs
    if last_seg_seconds <= 0 or last_seg_seconds > seg_secs:
        last_seg_seconds = float(seg_secs)

    latest = latest_existing_segment(session.output_dir)
    complete = latest >= total - 1 and (
        Path(session.output_dir) / f"segment_{total - 1:05d}.ts"
    ).is_file()

    lines: list[str] = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{seg_secs}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD" if complete else "#EXT-X-PLAYLIST-TYPE:EVENT",
    ]
    for index in range(total):
        seg_dur = last_seg_seconds if index == total - 1 else float(seg_secs)
        lines.append(f"#EXTINF:{seg_dur:.3f},")
        lines.append(f"segment_{index:05d}.ts")
    if complete:
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
