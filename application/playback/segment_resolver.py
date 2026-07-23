"""Seek-on-demand HLS segment resolution and speculative-probe gating."""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from application.dto import PlaybackSessionDTO
from application.playback.contract import (
    FORWARD_WAIT_SECONDS,
    MAX_FORWARD_JUMP_SEGMENTS,
    PREFETCH_MARGIN,
    RESERVED_INTERNAL_NAMES,
    RESUME_SEGMENT_WAIT_SECONDS,
    SEGMENT_WAIT_SECONDS,
)
from application.playback.playlist import latest_existing_segment
from application.playback.resume import resume_segment_index, wait_for_file
from application.services import player_session_log
from domain.errors import NotFoundError

_LOG = logging.getLogger(__name__)

_SEGMENT_NAME_RE = re.compile(r"^segment_(\d+)\.ts$")


class _TranscodeProbe(Protocol):
    def is_running(self, session_id: str) -> bool:
        ...


class SegmentResolver:
    """Resolve on-demand segment requests and gate Shaka live-edge probes."""

    def __init__(
        self,
        *,
        transcode: _TranscodeProbe,
        restart_at: Callable[[PlaybackSessionDTO, int], None],
        restart_lock: Callable[[str], threading.Lock],
    ) -> None:
        self._transcode = transcode
        self._restart_at = restart_at
        self._restart_lock = restart_lock

    def ensure_segment(
        self,
        session: PlaybackSessionDTO,
        segment_name: str,
        target: Path,
    ) -> None:
        if segment_name in RESERVED_INTERNAL_NAMES:
            raise NotFoundError("Internal stream artifact is not exposed.")

        match = _SEGMENT_NAME_RE.match(segment_name)
        if target.is_file():
            if match is not None:
                self.note_playhead_segment(session, int(match.group(1)))
            return

        if match is None:
            wait_for_file(target, FORWARD_WAIT_SECONDS)
            return

        segment_index = int(match.group(1))
        if session.total_segments <= 0 or session.segment_seconds <= 0:
            wait_for_file(target, FORWARD_WAIT_SECONDS)
            return
        if segment_index >= session.total_segments:
            raise NotFoundError("Requested segment is past the end of the stream.")

        if segment_index < session.hls_anchor_segment:
            if target.is_file():
                return
            player_session_log.append(
                session.output_dir,
                source="server",
                event="segment_before_anchor",
                level="warn",
                session_id=session.session_id,
                segment=segment_name,
                segment_index=segment_index,
                hls_anchor_segment=session.hls_anchor_segment,
            )
            raise NotFoundError("Requested segment is before the stream anchor.")

        wait_secs = self.segment_wait_seconds(session, segment_index)
        latest = latest_existing_segment(session.output_dir)
        in_prefetch = segment_index <= latest + 3

        if in_prefetch:
            if not self._transcode.is_running(session.session_id):
                self._restart_at(session, segment_index)
            if wait_for_file(target, wait_secs):
                self.note_playhead_segment(session, segment_index)
                return

        if self.is_speculative_far_request(session, segment_index, latest):
            player_session_log.append(
                session.output_dir,
                source="server",
                event="segment_speculative_rejected",
                level="warn",
                session_id=session.session_id,
                segment=segment_name,
                segment_index=segment_index,
                playhead_segment=self.playhead_head_segment(session, latest),
                transcode_start_segment=session.transcode_start_segment,
                latest_segment=latest,
                live_playhead_segment=session.live_playhead_segment,
            )
            raise NotFoundError("Requested segment is too far ahead of the playhead.")

        lock = self._restart_lock(session.session_id)
        with lock:
            if target.is_file():
                self.note_playhead_segment(session, segment_index)
                return
            if self.is_speculative_far_request(session, segment_index, latest):
                raise NotFoundError(
                    "Requested segment is too far ahead of the playhead."
                )
            self._restart_at(session, segment_index)
            if not wait_for_file(target, wait_secs):
                _LOG.warning(
                    "media_segment_unavailable session=%s seg=%s latest=%s",
                    session.session_id,
                    segment_index,
                    latest_existing_segment(session.output_dir),
                )
                raise NotFoundError("Requested media artifact is not available.")
            self.note_playhead_segment(session, segment_index)

    @staticmethod
    def playhead_head_segment(session: PlaybackSessionDTO, latest: int) -> int:
        """Best estimate of the current encode/playhead head (segment index)."""
        return max(latest, max(0, session.live_playhead_segment))

    @staticmethod
    def note_playhead_segment(session: PlaybackSessionDTO, segment_index: int) -> None:
        session.live_playhead_segment = max(
            session.live_playhead_segment,
            segment_index,
        )

    def is_speculative_far_request(
        self,
        session: PlaybackSessionDTO,
        segment_index: int,
        latest: int,
    ) -> bool:
        """True when a far-ahead probe would yank a healthy playhead encode."""
        if not self._transcode.is_running(session.session_id):
            return False
        head = self.playhead_head_segment(session, latest)
        encode_near_head = session.transcode_start_segment <= head + PREFETCH_MARGIN
        too_far = segment_index > head + MAX_FORWARD_JUMP_SEGMENTS
        return encode_near_head and too_far

    @staticmethod
    def segment_wait_seconds(
        session: PlaybackSessionDTO,
        segment_index: int,
    ) -> float:
        if session.playback_start_seconds <= 0:
            return SEGMENT_WAIT_SECONDS
        playhead = resume_segment_index(
            session.playback_start_seconds,
            total_segments=session.total_segments,
            segment_seconds=session.segment_seconds,
        )
        if (
            segment_index == playhead
            or session.hls_anchor_segment <= segment_index <= playhead
        ):
            return RESUME_SEGMENT_WAIT_SECONDS
        return SEGMENT_WAIT_SECONDS


__all__ = ["SegmentResolver"]
