"""Application orchestration for in-browser media playback sessions.

The service owns the canonical HLS playlist that the browser consumes.
We deliberately *do not* let ffmpeg drive the playlist file because we
need the full list of segments (with ``#EXT-X-ENDLIST``) to be present
before the player loads — otherwise Shaka treats the stream as a live
event and caps the seekable range to the segments produced so far.

The flow is therefore:

1. Probe the source's total duration once.
2. Pre-write ``index.m3u8`` with every segment listed (the file is
   what the player downloads). ffmpeg writes its own internal playlist
   to ``_ffmpeg.m3u8`` and we ignore it.
3. Start ffmpeg encoding from segment 0.
4. When the client asks for ``segment_NNNNN.ts``:

   - if the file already exists on disk, serve it;
   - otherwise wait briefly for ffmpeg to flush the next segment;
   - if it still isn't there, the client has seeked beyond the encode
     head — terminate ffmpeg, restart it with
     ``start_segment_index=N``, and wait again.

When the source's duration is unknown (e.g. a live stream or a
corrupted container) we fall back to the legacy "let ffmpeg own the
playlist" path so playback still works, just without scrubbing.
"""

from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import hmac
import logging
import math
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from application.commands import (
    CreatePlaybackSessionCommand,
    HeartbeatPlaybackSessionCommand,
    StopPlaybackSessionCommand,
)
from application.dto import EpisodeFileDTO, PlaybackSessionDTO
from application.queries import GetPlaybackSessionQuery, ListEpisodeFilesQuery
from application.services.media_probe_cache import MediaProbeCache
from domain.errors import InfrastructureError, NotFoundError, UnauthorizedError, ValidationError
from ports.interfaces import MediaLibraryPort, MediaTranscoderPort

_LOG = logging.getLogger(__name__)

# Default HLS segment size. Mirrors ``FFmpegTranscoderAdapter`` so the
# canonical playlist and the segment files line up. Short enough for
# responsive seeking, long enough to keep request overhead reasonable.
_DEFAULT_SEGMENT_SECONDS = 4

# When a segment is requested and ffmpeg is encoding sequentially from
# an earlier offset, we wait this long before deciding "the user seeked
# too far ahead, restart ffmpeg from the requested segment".
_FORWARD_WAIT_SECONDS = 2.5

# Maximum time spent waiting (after a restart, if any) for the
# requested segment to appear on disk before giving up and returning a
# transient 404.
_SEGMENT_AVAILABILITY_TIMEOUT_SECONDS = 20.0

# If the requested segment is more than this many segments past the
# latest one ffmpeg has produced, we don't bother waiting for the
# sequential encoder to catch up — that's clearly a seek and we
# restart ffmpeg immediately. The slack accommodates the few segments
# the HLS player typically pre-fetches.
_FAR_AHEAD_SEGMENT_THRESHOLD = 3

# Names that ffmpeg may emit alongside segment files but that the
# client should never see.
_RESERVED_INTERNAL_NAMES = frozenset({"_ffmpeg.m3u8"})

_SEGMENT_NAME_RE = re.compile(r"^segment_(\d+)\.ts$")


class MediaStreamingService:
    """Coordinates session-safe playback URLs over HLS artifacts."""

    def __init__(
        self,
        *,
        media_library: MediaLibraryPort,
        transcoder: MediaTranscoderPort,
        token_secret: str | bytes | None = None,
        default_ttl_seconds: int = 900,
        segment_seconds: int = _DEFAULT_SEGMENT_SECONDS,
        probe_parallel_workers: int = 8,
    ) -> None:
        self._media_library = media_library
        self._transcoder = transcoder
        self._default_ttl_seconds = max(60, int(default_ttl_seconds))
        self._segment_seconds = max(2, int(segment_seconds))
        self._probe_parallel_workers = max(1, int(probe_parallel_workers))
        self._probe_cache: MediaProbeCache | None = None
        self._probe_cache_lock = threading.Lock()
        if isinstance(token_secret, bytes):
            self._token_secret = token_secret
        elif isinstance(token_secret, str) and token_secret:
            self._token_secret = token_secret.encode("utf-8")
        else:
            self._token_secret = uuid.uuid4().hex.encode("ascii")
        self._sessions: dict[str, PlaybackSessionDTO] = {}
        self._lock = threading.RLock()
        # Per-session locks guard the "restart ffmpeg at a different
        # offset" path so two concurrent segment requests don't fight
        # over the same ffmpeg process.
        self._restart_locks: dict[str, threading.Lock] = {}

    def _get_probe_cache(self) -> MediaProbeCache | None:
        with self._probe_cache_lock:
            if self._probe_cache is not None:
                return self._probe_cache
            try:
                root = Path(self._media_library.get_stream_cache_root()).resolve()
            except Exception as exc:  # noqa: BLE001
                _LOG.debug("probe_cache_root_unavailable err=%s", exc)
                return None
            try:
                self._probe_cache = MediaProbeCache(root / "_probe_cache")
            except Exception as exc:  # noqa: BLE001
                _LOG.warning("probe_cache_init_failed err=%s", exc)
                return None
            return self._probe_cache

    @staticmethod
    def _path_stat_triple(path: str) -> tuple[str, int, int] | None:
        try:
            st = os.stat(path)
            resolved = os.path.realpath(path)
            return resolved, int(st.st_mtime_ns), int(st.st_size)
        except OSError:
            return None

    def _invoke_transcoder_probe(self, path: str) -> tuple[dict[str, list[dict[str, Any]]], float]:
        meta = getattr(self._transcoder, "probe_media_metadata", None)
        if callable(meta):
            tracks_raw, duration_raw = meta(path)
            tracks = {
                "audio": list((tracks_raw or {}).get("audio") or []),
                "subtitles": list((tracks_raw or {}).get("subtitles") or []),
            }
            try:
                duration = float(duration_raw)
            except (TypeError, ValueError):
                duration = 0.0
            return tracks, max(0.0, duration)
        raw_tracks = self._transcoder.probe_media_tracks(path)
        tracks = {
            "audio": list(raw_tracks.get("audio") or []),
            "subtitles": list(raw_tracks.get("subtitles") or []),
        }
        duration = 0.0
        probe_dur = getattr(self._transcoder, "probe_media_duration", None)
        if callable(probe_dur):
            try:
                duration = max(0.0, float(probe_dur(path)))
            except Exception:  # noqa: BLE001
                duration = 0.0
        return tracks, duration

    def _probe_tracks_and_duration(self, path: str) -> tuple[dict[str, list[dict[str, Any]]], float]:
        triple = self._path_stat_triple(path)
        cache = self._get_probe_cache()
        if triple is not None and cache is not None:
            resolved, mtime_ns, size = triple
            cached = cache.get(resolved, mtime_ns, size)
            if cached is not None:
                tracks, dur_opt = cached
                dur = float(dur_opt) if dur_opt is not None and dur_opt > 0 else 0.0
                return tracks, dur
        tracks, duration = self._invoke_transcoder_probe(path)
        if triple is not None and cache is not None:
            resolved, mtime_ns, size = triple
            try:
                cache.put(
                    resolved,
                    mtime_ns,
                    size,
                    tracks=tracks,
                    duration_seconds=duration if duration > 0 else None,
                )
            except Exception as exc:  # noqa: BLE001
                _LOG.debug("probe_cache_put_failed err=%s", exc)
        return tracks, duration

    def _episode_entry_from_row(self, row: dict[str, Any]) -> EpisodeFileDTO | None:
        file_id = str(row.get("file_id") or "").strip()
        path = str(row.get("path") or "").strip()
        title = str(row.get("title") or row.get("name") or "").strip()
        if not file_id or not path:
            return None
        tracks, duration = self._probe_tracks_and_duration(path)
        duration_val = duration if duration > 0 else None
        return EpisodeFileDTO(
            file_id=file_id,
            title=title or Path(path).name,
            path=path,
            size_bytes=_safe_int(row.get("size_bytes") or row.get("size")),
            season=_safe_int(row.get("season")),
            episode=_safe_int(row.get("episode")),
            audio_tracks=list(tracks.get("audio", []) or []),
            subtitle_tracks=list(tracks.get("subtitles", []) or []),
            duration_seconds=duration_val,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_episode_files(self, query: ListEpisodeFilesQuery) -> list[EpisodeFileDTO]:
        prep: list[dict[str, Any]] = []
        for row in self._media_library.list_episode_files(query.anime_id) or []:
            file_id = str(row.get("file_id") or "").strip()
            path = str(row.get("path") or "").strip()
            if not file_id or not path:
                continue
            prep.append(row)
        if not prep:
            return []
        workers = min(self._probe_parallel_workers, len(prep))
        if workers <= 1:
            out: list[EpisodeFileDTO] = []
            for row in prep:
                dto = self._episode_entry_from_row(row)
                if dto is not None:
                    out.append(dto)
            return out
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            mapped = list(pool.map(self._episode_entry_from_row, prep))
        return [dto for dto in mapped if dto is not None]

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

        now = time.time()
        ttl_seconds = max(60, int(command.ttl_seconds or self._default_ttl_seconds))
        expires_at = now + ttl_seconds
        session_id = uuid.uuid4().hex
        stream_root = Path(self._media_library.get_stream_cache_root()).resolve()
        output_dir = (stream_root / session_id).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = str(output_dir / "index.m3u8")

        # Probe the duration *before* spawning ffmpeg so we can write
        # the canonical playlist atomically. If probing fails we fall
        # back to the legacy "ffmpeg owns the playlist" flow so the
        # session still works (just without scrubbing).
        d_sel = selected.duration_seconds
        if isinstance(d_sel, (int, float)) and float(d_sel) > 0:
            duration = float(d_sel)
        else:
            duration = self._safe_probe_duration(selected.path)
        seg_secs = self._segment_seconds
        total_segments = 0
        if duration > 0:
            total_segments = max(1, math.ceil(duration / seg_secs))
            self._write_vod_playlist(
                manifest_path=manifest_path,
                duration=duration,
                segment_seconds=seg_secs,
            )

        # Convert the optional "start the encoder near this offset"
        # hint into a segment index so a page reload of a previously-
        # watched episode doesn't require an immediate seek-on-demand
        # restart.
        start_segment = self._clamp_start_segment(
            command.start_time_seconds,
            total_segments=total_segments,
            segment_seconds=seg_secs,
        )

        # Extract sidecar WebVTT/ASS *before* the long-running HLS encoder
        # opens the source. On Windows a second ffmpeg reading the same
        # MKV while the first holds it can fail intermittently, which
        # left the session with no subtitle artifacts for the browser.
        subtitle_tracks = self._materialize_soft_subtitles(
            source_path=selected.path,
            output_dir=str(output_dir),
        )

        try:
            artifacts = self._transcoder.ensure_hls_session(
                session_id=session_id,
                source_path=selected.path,
                output_dir=str(output_dir),
                audio_track=command.audio_track,
                subtitle_track=command.subtitle_track,
                start_segment_index=start_segment,
                segment_seconds=seg_secs,
            )
        except TypeError:
            # Older transcoder implementations may not accept the new
            # keyword arguments. Fall back to the legacy call shape so
            # third-party adapters keep working.
            artifacts = self._transcoder.ensure_hls_session(
                session_id=session_id,
                source_path=selected.path,
                output_dir=str(output_dir),
                audio_track=command.audio_track,
                subtitle_track=command.subtitle_track,
            )
        artifact_manifest = str(artifacts.get("manifest_path") or manifest_path)
        if duration > 0:
            # With a pre-written VOD playlist the adapter doesn't need
            # to materialise a manifest itself. The canonical file we
            # serve is the one we wrote.
            manifest_path_to_use = manifest_path
        else:
            manifest_path_to_use = artifact_manifest
        if not os.path.isfile(manifest_path_to_use):
            raise InfrastructureError("Transcoder did not produce a manifest file.")

        token = self._build_token(
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
        )
        with self._lock:
            self._sessions[session_id] = dto
            self._restart_locks[session_id] = threading.Lock()
        _LOG.info(
            "media_session_started anime_id=%s session=%s startup_ms=%s file=%s duration=%.1f",
            command.anime_id,
            session_id,
            int((time.time() - started_at) * 1000),
            selected.title,
            duration,
        )
        return dto

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
        self._teardown_session(session)
        _LOG.info("media_session_stopped session=%s anime_id=%s", session.session_id, session.anime_id)

    def resolve_media_path(self, query: GetPlaybackSessionQuery) -> tuple[PlaybackSessionDTO, str]:
        self.cleanup_stale_sessions()
        with self._lock:
            session = self._sessions.get(query.session_id)
        if session is None:
            raise NotFoundError("Playback session not found.")
        if query.token and not self._verify_token(session.session_id, query.token):
            raise UnauthorizedError("Playback token is invalid or expired.")
        if not query.token and query.segment_name is None:
            raise UnauthorizedError("Playback token is required for manifest access.")

        if query.segment_name:
            segment_name = _validate_segment_name(query.segment_name)
            target = (Path(session.output_dir) / segment_name).resolve()
            if not _is_within_dir(target, Path(session.output_dir).resolve()):
                raise ValidationError("Segment path escapes stream directory.")
            self._ensure_segment_available(session, segment_name, target)
            target_path = str(target)
        else:
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
            self._teardown_session(session)
            _LOG.info(
                "media_session_cleaned session=%s anime_id=%s",
                session.session_id,
                session.anime_id,
            )

    # ------------------------------------------------------------------
    # Implementation details
    # ------------------------------------------------------------------

    def _ensure_segment_available(
        self,
        session: PlaybackSessionDTO,
        segment_name: str,
        target: Path,
    ) -> None:
        """Block until ``target`` exists on disk, restarting ffmpeg if
        the client has seeked beyond the current encode head."""
        if segment_name in _RESERVED_INTERNAL_NAMES:
            raise NotFoundError("Internal stream artifact is not exposed.")
        if target.is_file():
            return

        match = _SEGMENT_NAME_RE.match(segment_name)
        if match is None:
            # Some other artifact (e.g. an init segment we haven't
            # produced yet). Defer to the file-system check below.
            return
        segment_index = int(match.group(1))

        # Sessions whose duration we couldn't probe rely entirely on
        # ffmpeg's sequential output. Wait briefly and fall through;
        # the caller will return a 404 if the file never appears.
        if session.total_segments <= 0 or session.segment_seconds <= 0:
            self._wait_for_file(target, _FORWARD_WAIT_SECONDS)
            return

        if segment_index >= session.total_segments:
            raise NotFoundError("Requested segment is past the end of the stream.")

        # Step 1: short wait — but only if we're "close" to the
        # encoder head. When the user obviously seeked forward (the
        # requested segment is well past the latest one on disk) we
        # skip straight to the restart so we don't burn 2.5s of UI
        # stall on every scrub.
        latest_existing = self._latest_existing_segment(session.output_dir)
        far_ahead = segment_index > latest_existing + _FAR_AHEAD_SEGMENT_THRESHOLD
        if not far_ahead and self._wait_for_file(target, _FORWARD_WAIT_SECONDS):
            return

        # Step 2: still missing. Ask the transcoder to restart at the
        # requested segment. The per-session lock collapses concurrent
        # restart requests into a single ffmpeg relaunch.
        lock = self._restart_lock_for(session.session_id)
        with lock:
            if target.is_file():
                return
            _LOG.info(
                "media_segment_restart session=%s seg=%s latest_existing=%s",
                session.session_id,
                segment_index,
                latest_existing,
            )
            try:
                self._transcoder.ensure_hls_session(
                    session_id=session.session_id,
                    source_path=session.source_path,
                    output_dir=session.output_dir,
                    audio_track=session.audio_track,
                    subtitle_track=session.subtitle_track,
                    start_segment_index=segment_index,
                    segment_seconds=session.segment_seconds,
                )
            except TypeError:
                # Legacy transcoders without seek support can't satisfy
                # this — fall through to the wait below; if the
                # sequential encode happens to reach the segment, great.
                pass
            except Exception as exc:  # noqa: BLE001
                _LOG.warning(
                    "media_segment_restart_failed session=%s seg=%s err=%s",
                    session.session_id,
                    segment_index,
                    exc,
                )

        # Step 3: wait for the segment to materialise. ffmpeg writes
        # segments with the ``temp_file`` flag (rename-on-complete), so
        # ``is_file`` is a safe completion check.
        if self._wait_for_file(target, _SEGMENT_AVAILABILITY_TIMEOUT_SECONDS):
            return

        # The segment never showed up. Log enough context that we can
        # tell apart a slow encoder from a dead one when a user reports
        # a 404. The ``_ffmpeg.log`` file referenced here lives next to
        # the segment files and contains the underlying ffmpeg stderr.
        log_path = Path(session.output_dir) / "_ffmpeg.log"
        log_hint = ""
        try:
            if log_path.is_file():
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
                log_hint = tail.strip()
        except OSError:
            log_hint = ""
        _LOG.warning(
            "media_segment_unavailable session=%s seg=%s latest_existing=%s log_tail=%r",
            session.session_id,
            segment_index,
            self._latest_existing_segment(session.output_dir),
            log_hint,
        )

    def _restart_lock_for(self, session_id: str) -> threading.Lock:
        with self._lock:
            lock = self._restart_locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._restart_locks[session_id] = lock
            return lock

    @staticmethod
    def _latest_existing_segment(output_dir: str) -> int:
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

    @staticmethod
    def _wait_for_file(target: Path, timeout: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            if target.is_file():
                return True
            if time.monotonic() >= deadline:
                return target.is_file()
            time.sleep(0.1)

    @staticmethod
    def _clamp_start_segment(
        start_time_seconds: float | None,
        *,
        total_segments: int,
        segment_seconds: int,
    ) -> int:
        if start_time_seconds is None or total_segments <= 0 or segment_seconds <= 0:
            return 0
        try:
            value = float(start_time_seconds)
        except (TypeError, ValueError):
            return 0
        if value <= 0 or not math.isfinite(value):
            return 0
        # Leave a few seconds of headroom before the requested point
        # so the player can comfortably scrub backwards a little.
        anchored = max(0.0, value - 4.0)
        index = int(anchored // segment_seconds)
        # Never start past the last valid segment.
        return max(0, min(index, total_segments - 1))

    def _safe_probe_duration(self, source_path: str) -> float:
        try:
            _, duration = self._probe_tracks_and_duration(source_path)
            return max(0.0, float(duration))
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("media_duration_probe_failed path=%s err=%s", source_path, exc)
            return 0.0

    def _materialize_soft_subtitles(
        self,
        *,
        source_path: str,
        output_dir: str,
    ) -> list[dict[str, object]]:
        extractor = getattr(self._transcoder, "materialize_subtitle_tracks", None)
        if not callable(extractor):
            return []
        try:
            rows = list(
                extractor(
                    source_path=source_path,
                    output_dir=output_dir,
                )
                or []
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("soft_subtitles_materialize_failed path=%s err=%s", source_path, exc)
            return []
        out: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                sub_id = max(0, int(row.get("id")))
            except (TypeError, ValueError):
                continue
            filename = str(row.get("filename") or "").strip()
            if not filename:
                continue
            entry: dict[str, object] = {
                "id": sub_id,
                "label": str(row.get("label") or f"Subtitle {sub_id}"),
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

    @staticmethod
    def _write_vod_playlist(
        *,
        manifest_path: str,
        duration: float,
        segment_seconds: int,
    ) -> None:
        total = max(1, math.ceil(duration / segment_seconds))
        target_duration = max(1, segment_seconds)
        # The final segment carries the remainder so the total length
        # matches the source rather than rounding up to the next
        # multiple of segment_seconds.
        last_seg_seconds = duration - (total - 1) * segment_seconds
        if last_seg_seconds <= 0 or last_seg_seconds > segment_seconds:
            last_seg_seconds = float(segment_seconds)

        lines: list[str] = [
            "#EXTM3U",
            "#EXT-X-VERSION:6",
            f"#EXT-X-TARGETDURATION:{target_duration}",
            "#EXT-X-PLAYLIST-TYPE:VOD",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXT-X-INDEPENDENT-SEGMENTS",
        ]
        for index in range(total):
            seg_dur = (
                last_seg_seconds if index == total - 1 else float(segment_seconds)
            )
            lines.append(f"#EXTINF:{seg_dur:.3f},")
            lines.append(f"segment_{index:05d}.ts")
        lines.append("#EXT-X-ENDLIST")
        # Atomic-ish write so that a partially-written manifest is
        # never observed by the player.
        tmp_path = manifest_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        os.replace(tmp_path, manifest_path)

    def _teardown_session(self, session: PlaybackSessionDTO) -> None:
        try:
            self._transcoder.stop_hls_session(session.session_id)
        except Exception:
            pass
        try:
            shutil.rmtree(session.output_dir, ignore_errors=True)
        except Exception:
            pass

    def _build_token(self, *, session_id: str, expires_at: float) -> str:
        exp = str(int(expires_at))
        payload = f"{session_id}.{exp}"
        digest = hmac.new(
            self._token_secret,
            payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        signature = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return f"{exp}.{signature}"

    def _verify_token(self, session_id: str, token: str) -> bool:
        if not token or "." not in token:
            return False
        exp_raw, sig = token.split(".", 1)
        try:
            exp = int(exp_raw)
        except ValueError:
            return False
        if time.time() > exp:
            return False
        expected = self._build_token(session_id=session_id, expires_at=float(exp))
        _, expected_sig = expected.split(".", 1)
        return hmac.compare_digest(sig, expected_sig)


def _safe_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _validate_segment_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ValidationError("Segment name is required.")
    if "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise ValidationError("Unsafe segment path.")
    return cleaned


def _is_within_dir(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


__all__ = ["MediaStreamingService"]
