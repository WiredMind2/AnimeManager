"""On-demand HLS playback orchestration."""

from __future__ import annotations

import logging
import math
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from application.commands import (
    CreatePlaybackSessionCommand,
    HeartbeatPlaybackSessionCommand,
    StopPlaybackSessionCommand,
)
from application.dto import EpisodeFileDTO, PlaybackSessionDTO
from application.playback.contract import (
    FORWARD_WAIT_SECONDS,
    RESERVED_INTERNAL_NAMES,
    RESUME_SEGMENT_WAIT_SECONDS,
    SEGMENT_SECONDS,
    SEGMENT_WAIT_SECONDS,
    SESSION_CREATE_WAIT_SECONDS,
)
from application.playback.playlist import (
    latest_existing_segment,
    write_initial_playlist,
    write_manifest_file,
)
from application.playback.resume import (
    anchor_segment,
    clamp_resume_seconds,
    resume_segment_index,
    wait_for_file,
)
from application.playback.session_store import SessionTokenStore
from application.playback.transcode_session import TranscodeSession
from application.queries import GetPlaybackSessionQuery, ListEpisodeFilesQuery
from application.services import player_session_log
from domain.errors import InfrastructureError, NotFoundError, UnauthorizedError, ValidationError
from ports.interfaces import MediaLibraryPort, MediaTranscoderPort
from shared.telemetry import get_telemetry

_LOG = logging.getLogger(__name__)

_SEGMENT_NAME_RE = re.compile(r"^segment_(\d+)\.ts$")


def _safe_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _validate_segment_name(name: str) -> str:
    if not name or "/" in name or "\\" in name or ".." in name:
        raise ValidationError("Invalid segment name.")
    return name


def _is_within_dir(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class PlaybackService:
    """Coordinates session-safe HLS playback."""

    def __init__(
        self,
        *,
        media_library: MediaLibraryPort,
        transcoder: MediaTranscoderPort,
        token_secret: str | bytes | None = None,
        default_ttl_seconds: int = 900,
        segment_seconds: int = SEGMENT_SECONDS,
    ) -> None:
        self._media_library = media_library
        self._transcode = TranscodeSession(transcoder)
        self._transcoder = transcoder
        self._tokens = SessionTokenStore(token_secret)
        self._default_ttl_seconds = max(60, int(default_ttl_seconds))
        self._segment_seconds = max(2, int(segment_seconds))
        self._sessions: dict[str, PlaybackSessionDTO] = {}
        self._restart_locks: dict[str, threading.Lock] = {}
        self._lock = threading.Lock()
        self._telemetry = get_telemetry()

    def list_episode_files(self, query: ListEpisodeFilesQuery) -> list[EpisodeFileDTO]:
        out: list[EpisodeFileDTO] = []
        for row in self._media_library.list_episode_files(query.anime_id) or []:
            file_id = str(row.get("file_id") or "").strip()
            path = str(row.get("path") or "").strip()
            title = str(row.get("title") or row.get("name") or "").strip()
            if not file_id or not path:
                continue
            tracks = self._transcoder.probe_media_tracks(path)
            duration = self._probe_duration(path)
            out.append(
                EpisodeFileDTO(
                    file_id=file_id,
                    title=title or Path(path).name,
                    path=path,
                    size_bytes=_safe_int(row.get("size_bytes") or row.get("size")),
                    season=_safe_int(row.get("season")),
                    episode=_safe_int(row.get("episode")),
                    audio_tracks=list(tracks.get("audio", []) or []),
                    subtitle_tracks=list(tracks.get("subtitles", []) or []),
                    duration_seconds=duration if duration > 0 else None,
                )
            )
        return out

    def delete_episode_file(self, anime_id: int, file_id: str) -> bool:
        return bool(self._media_library.delete_episode_file(anime_id, file_id))

    def create_session(self, command: CreatePlaybackSessionCommand) -> PlaybackSessionDTO:
        started_at = time.time()
        self.cleanup_stale_sessions()
        episodes = self.list_episode_files(ListEpisodeFilesQuery(anime_id=command.anime_id))
        selected = next((ep for ep in episodes if ep.file_id == command.file_id), None)
        if selected is None:
            raise NotFoundError("Requested episode file was not found.")
        if not os.path.isfile(selected.path):
            raise NotFoundError("Episode file is missing from disk.")

        duration = self._probe_duration(selected.path)
        if duration <= 0 and selected.duration_seconds is not None and selected.duration_seconds > 0:
            duration = float(selected.duration_seconds)
        if duration <= 0 and not selected.audio_tracks and not selected.subtitle_tracks:
            raise ValidationError(
                "This episode can't be played yet — the file looks incomplete "
                "(its download may still be in progress). Wait for the torrent "
                "to finish and try again."
            )

        now = time.time()
        ttl_seconds = max(60, int(command.ttl_seconds or self._default_ttl_seconds))
        expires_at = now + ttl_seconds
        session_id = uuid.uuid4().hex
        stream_root = Path(self._media_library.get_stream_cache_root()).resolve()
        output_dir = (stream_root / session_id).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = str(output_dir / "index.m3u8")
        seg_secs = self._segment_seconds

        playback_start = clamp_resume_seconds(
            command.start_time_seconds,
            max_duration=duration if duration > 0 else None,
        )
        total_segments = 0
        if duration > 0:
            total_segments = write_initial_playlist(
                manifest_path=manifest_path,
                duration=duration,
                segment_seconds=seg_secs,
            )

        resume_seg = (
            resume_segment_index(
                playback_start,
                total_segments=total_segments,
                segment_seconds=seg_secs,
            )
            if playback_start > 0 and total_segments > 0
            else 0
        )
        start_segment = anchor_segment(resume_seg) if resume_seg > 0 else 0

        if playback_start > 0 and (duration <= 0 or resume_seg <= 0):
            raise ValidationError(
                "Cannot resume playback — episode duration is unknown."
            )

        artifacts = self._transcode.start(
            session_id=session_id,
            source_path=selected.path,
            output_dir=str(output_dir),
            audio_track=command.audio_track,
            subtitle_track=command.subtitle_track,
            start_segment_index=start_segment,
            segment_seconds=seg_secs,
            duration_seconds=duration if duration > 0 else None,
        )

        if duration > 0:
            wait_segment = resume_seg if resume_seg > 0 else start_segment
            wait_target = output_dir / f"segment_{wait_segment:05d}.ts"
            wait_timeout = (
                RESUME_SEGMENT_WAIT_SECONDS if playback_start > 0 else SESSION_CREATE_WAIT_SECONDS
            )
            playhead_exists = wait_for_file(wait_target, wait_timeout)
            if not playhead_exists:
                raise InfrastructureError(
                    f"Resume segment {wait_segment:05d} was not ready within {wait_timeout:.0f}s "
                    f"(anchor={start_segment})."
                )

        else:
            wait_segment = 0
            playhead_exists = False

        subtitle_tracks = self._materialize_subtitles(
            source_path=selected.path,
            output_dir=str(output_dir),
        )

        if duration <= 0:
            artifact_manifest = str(artifacts.get("manifest_path") or manifest_path)
            if not os.path.isfile(artifact_manifest):
                raise InfrastructureError("Transcoder did not produce a manifest file.")
            manifest_path_to_use = artifact_manifest
        elif not os.path.isfile(manifest_path):
            raise InfrastructureError("Transcoder did not produce a manifest file.")
        else:
            manifest_path_to_use = manifest_path

        token = self._tokens.build(
            session_id=session_id,
            expires_at=now + max(ttl_seconds, 12 * 3600),
        )
        dto = PlaybackSessionDTO(
            session_id=session_id,
            anime_id=command.anime_id,
            file_id=selected.file_id,
            file_title=selected.title,
            manifest_path=manifest_path_to_use,
            output_dir=str(output_dir),
            token=token,
            expires_at=expires_at,
            created_at=now,
            last_seen_at=now,
            audio_track=command.audio_track,
            subtitle_track=command.subtitle_track,
            subtitle_tracks=subtitle_tracks,
            source_path=selected.path,
            duration_seconds=duration,
            segment_seconds=seg_secs if duration > 0 else 0,
            total_segments=total_segments,
            hls_anchor_segment=start_segment,
            transcode_start_segment=start_segment,
            playback_start_seconds=playback_start,
        )
        with self._lock:
            self._sessions[session_id] = dto
            self._restart_locks[session_id] = threading.Lock()
        if duration > 0 and (start_segment > 0 or playback_start > 0):
            write_manifest_file(dto)

        startup_ms = int((time.time() - started_at) * 1000)
        self._telemetry.record_ms("playback.session_create_ms", float(startup_ms))
        self._telemetry.increment("playback.sessions_created")
        self._telemetry.set_gauge("playback.active_sessions", float(len(self._sessions)))
        _LOG.info(
            "media_session_started anime_id=%s session=%s startup_ms=%s file=%s duration=%.1f",
            command.anime_id,
            session_id,
            startup_ms,
            selected.title,
            duration,
        )
        player_session_log.append(
            str(output_dir),
            source="server",
            event="session_started",
            session_id=session_id,
            anime_id=command.anime_id,
            file_id=selected.file_id,
            file_title=selected.title,
            startup_ms=startup_ms,
            duration_seconds=duration,
            total_segments=total_segments,
            hls_anchor_segment=start_segment,
            transcode_start_segment=start_segment,
            resume_segment_index=resume_seg,
            wait_segment=wait_segment,
            playhead_exists=playhead_exists,
            subtitle_track_count=len(subtitle_tracks),
            client_host=command.client_host or "",
        )
        return dto

    def get_session(self, session_id: str) -> PlaybackSessionDTO | None:
        with self._lock:
            return self._sessions.get(session_id)

    def heartbeat(self, command: HeartbeatPlaybackSessionCommand) -> PlaybackSessionDTO:
        with self._lock:
            session = self._sessions.get(command.session_id)
            if session is None:
                raise NotFoundError("Playback session not found.")
            now = time.time()
            session.last_seen_at = now
            session.expires_at = now + self._default_ttl_seconds
            return session

    def stop_session(self, command: StopPlaybackSessionCommand) -> None:
        with self._lock:
            session = self._sessions.pop(command.session_id, None)
            self._restart_locks.pop(command.session_id, None)
        if session is None:
            return
        self._teardown(session, remove_output_dir=False)
        _LOG.info("media_session_stopped session=%s anime_id=%s", session.session_id, session.anime_id)

    def resolve_media_path(self, query: GetPlaybackSessionQuery) -> tuple[PlaybackSessionDTO, str]:
        self.cleanup_stale_sessions()
        with self._lock:
            session = self._sessions.get(query.session_id)
        if session is None:
            raise NotFoundError("Playback session not found.")
        if query.token and not self._tokens.verify(query.session_id, query.token):
            raise UnauthorizedError("Playback token is invalid or expired.")
        if not query.token and query.segment_name is None:
            raise UnauthorizedError("Playback token is required for manifest access.")

        if query.segment_name:
            segment_name = _validate_segment_name(query.segment_name)
            resolve_started = time.perf_counter()
            target = (Path(session.output_dir) / segment_name).resolve()
            if not _is_within_dir(target, Path(session.output_dir).resolve()):
                raise ValidationError("Segment path escapes stream directory.")
            self._ensure_segment(session, segment_name, target)
            target_path = str(target)
            self._telemetry.record_ms(
                "playback.segment_resolve_ms",
                (time.perf_counter() - resolve_started) * 1000.0,
            )
        else:
            if session.total_segments > 0:
                write_manifest_file(session)
            target_path = session.manifest_path

        if not os.path.isfile(target_path):
            raise NotFoundError("Requested media artifact is not available.")

        with self._lock:
            live = self._sessions.get(query.session_id)
            if live is not None:
                live.last_seen_at = time.time()
                session = live
        return session, target_path

    def cleanup_stale_sessions(self) -> None:
        now = time.time()
        stale: list[PlaybackSessionDTO] = []
        with self._lock:
            for session_id, session in list(self._sessions.items()):
                if session.expires_at <= now:
                    stale.append(session)
                    self._sessions.pop(session_id, None)
                    self._restart_locks.pop(session_id, None)
        for session in stale:
            self._teardown(session, remove_output_dir=True)
            _LOG.info(
                "media_session_cleaned session=%s anime_id=%s",
                session.session_id,
                session.anime_id,
            )

    def _ensure_segment(
        self,
        session: PlaybackSessionDTO,
        segment_name: str,
        target: Path,
    ) -> None:
        if segment_name in RESERVED_INTERNAL_NAMES:
            raise NotFoundError("Internal stream artifact is not exposed.")
        if target.is_file():
            return

        match = _SEGMENT_NAME_RE.match(segment_name)
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

        wait_secs = self._segment_wait_seconds(session, segment_index)
        latest = latest_existing_segment(session.output_dir)
        in_prefetch = segment_index <= latest + 3

        if in_prefetch:
            if not self._transcode.is_running(session.session_id):
                # Restart at the requested segment, not the anchor: the
                # output dir may already contain later segments from a
                # previous seek-on-demand run (e.g. a Shaka probe at 110
                # fills 110-217), so ``latest`` can be far ahead of the
                # requested segment. Restarting at ``latest+1`` would
                # skip the requested segment entirely; restarting at the
                # anchor re-encodes existing segments and underruns the
                # buffer. Seeking to ``segment_index`` emits the missing
                # segment in ~2s and fills forward from there.
                self._restart_at(session, segment_index)
            if wait_for_file(target, wait_secs):
                return

        lock = self._restart_lock(session.session_id)
        with lock:
            if target.is_file():
                return
            self._restart_at(session, segment_index)
            if not wait_for_file(target, wait_secs):
                _LOG.warning(
                    "media_segment_unavailable session=%s seg=%s latest=%s",
                    session.session_id,
                    segment_index,
                    latest_existing_segment(session.output_dir),
                )
                raise NotFoundError("Requested media artifact is not available.")

    def _segment_wait_seconds(
        self,
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

    def _restart_at(self, session: PlaybackSessionDTO, segment_index: int) -> None:
        _LOG.info(
            "media_segment_restart session=%s seg=%s",
            session.session_id,
            segment_index,
        )
        duration = session.duration_seconds if session.duration_seconds > 0 else None
        try:
            self._transcode.start(
                session_id=session.session_id,
                source_path=session.source_path,
                output_dir=session.output_dir,
                audio_track=session.audio_track,
                subtitle_track=session.subtitle_track,
                start_segment_index=segment_index,
                segment_seconds=session.segment_seconds,
                duration_seconds=duration,
            )
            with self._lock:
                live = self._sessions.get(session.session_id)
                if live is not None:
                    live.transcode_start_segment = segment_index
        except Exception as exc:  # noqa: BLE001
            _LOG.warning(
                "media_segment_restart_failed session=%s seg=%s err=%s",
                session.session_id,
                segment_index,
                exc,
            )

    def _restart_lock(self, session_id: str) -> threading.Lock:
        with self._lock:
            lock = self._restart_locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._restart_locks[session_id] = lock
            return lock

    def _probe_duration(self, path: str) -> float:
        probe = getattr(self._transcoder, "probe_media_duration", None)
        if callable(probe):
            try:
                value = float(probe(path))
                if value > 0 and math.isfinite(value):
                    return value
            except Exception:  # noqa: BLE001
                pass
        return 0.0

    def _materialize_subtitles(self, *, source_path: str, output_dir: str) -> list[dict[str, object]]:
        materialize = getattr(self._transcoder, "materialize_subtitle_tracks", None)
        if not callable(materialize):
            return []
        try:
            rows = materialize(source_path=source_path, output_dir=output_dir)
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("subtitle_materialize_failed path=%s err=%s", source_path, exc)
            return []
        out: list[dict[str, object]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            try:
                track_id = int(row.get("id"))
            except (TypeError, ValueError):
                continue
            filename = str(row.get("filename") or f"subtitle_{track_id:03d}.vtt")
            entry: dict[str, object] = {
                "id": track_id,
                "label": str(row.get("label") or f"Subtitle {track_id}"),
                "filename": filename,
            }
            codec = str(row.get("codec") or "").strip()
            if codec:
                entry["codec"] = codec
            ass_fn = str(row.get("ass_filename") or "").strip()
            if ass_fn:
                entry["ass_filename"] = ass_fn
            out.append(entry)
        return out

    def _teardown(self, session: PlaybackSessionDTO, *, remove_output_dir: bool) -> None:
        try:
            self._transcode.stop(session.session_id)
        except Exception:
            pass
        if not remove_output_dir:
            return
        try:
            shutil.rmtree(session.output_dir, ignore_errors=True)
        except Exception:
            pass


# Backward-compatible alias used by composition and tests during migration.
MediaStreamingService = PlaybackService

__all__ = ["PlaybackService", "MediaStreamingService"]
