"""Thin ffmpeg session wrapper."""

from __future__ import annotations

from ports.interfaces import MediaTranscoderPort


class TranscodeSession:
    def __init__(self, transcoder: MediaTranscoderPort) -> None:
        self._transcoder = transcoder

    def start(
        self,
        *,
        session_id: str,
        source_path: str,
        output_dir: str,
        audio_track: int | None,
        subtitle_track: int | None,
        start_segment_index: int,
        segment_seconds: int,
        duration_seconds: float | None,
    ) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "session_id": session_id,
            "source_path": source_path,
            "output_dir": output_dir,
            "audio_track": audio_track,
            "subtitle_track": subtitle_track,
            "start_segment_index": start_segment_index,
            "segment_seconds": segment_seconds,
        }
        if duration_seconds is not None:
            kwargs["duration_seconds"] = duration_seconds
        return dict(self._transcoder.ensure_hls_session(**kwargs))  # type: ignore[arg-type]

    def stop(self, session_id: str) -> None:
        self._transcoder.stop_hls_session(session_id)

    def is_running(self, session_id: str) -> bool:
        probe = getattr(self._transcoder, "is_hls_session_running", None)
        if not callable(probe):
            return True
        try:
            return bool(probe(session_id))
        except Exception:  # noqa: BLE001
            return True


__all__ = ["TranscodeSession"]
