"""Automated multi-seek playback test for anime 2215 (runtime debug evidence)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ANIME_ID = 2215
FILE_ID = os.environ.get("DEBUG_FILE_ID", "ep-11ea96cb606eb469")
LOG_PATH = Path("debug-ba0308.log")
SEEK_TARGETS = [0, 30, 120, 300, 45, 0, 180]


def segment_name(index: int) -> str:
    return f"segment_{index:05d}.ts"


def main() -> int:
    from clients.sdk import ClientSDK

    sdk = ClientSDK()
    results: list[dict] = []

    if LOG_PATH.is_file():
        LOG_PATH.unlink()

    session = sdk.create_playback_session(
        ANIME_ID,
        file_id=FILE_ID,
        client_host="127.0.0.1",
        start_time_seconds=30.0,
    )
    sid = session["session_id"]
    token = session["token"]

    try:
        manifest_path = sdk.resolve_playback_media_path(
            session_id=sid,
            token=token,
            segment_name=None,
        )[1]
        manifest_text = Path(manifest_path).read_text(encoding="utf-8")
        results.append(
            {
                "phase": "initial_manifest",
                "media_sequence": _media_sequence(manifest_text),
                "first_segment": _first_segment(manifest_text),
                "has_endlist": "#EXT-X-ENDLIST" in manifest_text,
                "playback_start_seconds": session.get("playback_start_seconds"),
                "hls_anchor_segment": session.get("hls_anchor_segment"),
            }
        )

        for target_seconds in SEEK_TARGETS:
            seg_idx = max(0, int(target_seconds // 4))
            seg = segment_name(seg_idx)
            t0 = time.monotonic()
            _session, seg_path = sdk.resolve_playback_media_path(
                session_id=sid,
                token=token,
                segment_name=seg,
            )
            elapsed = time.monotonic() - t0
            manifest_path = sdk.resolve_playback_media_path(
                session_id=sid,
                token=token,
                segment_name=None,
            )[1]
            manifest_text = Path(manifest_path).read_text(encoding="utf-8")
            results.append(
                {
                    "phase": "seek",
                    "target_seconds": target_seconds,
                    "segment": seg,
                    "segment_bytes": os.path.getsize(seg_path),
                    "elapsed_s": round(elapsed, 3),
                    "media_sequence": _media_sequence(manifest_text),
                    "first_segment": _first_segment(manifest_text),
                    "segment_00000_listed": "segment_00000.ts" in manifest_text,
                }
            )

        debug_logs = []
        if LOG_PATH.is_file():
            for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        debug_logs.append(json.loads(line))
                    except json.JSONDecodeError:
                        debug_logs.append({"raw": line})

        print(
            json.dumps(
                {
                    "anime_id": ANIME_ID,
                    "file_id": FILE_ID,
                    "session_id": sid,
                    "results": results,
                    "debug_log_count": len(debug_logs),
                    "debug_logs": debug_logs,
                },
                indent=2,
            )
        )
        return 0
    finally:
        try:
            sdk.stop_playback_session(sid)
        except Exception:
            pass


def _media_sequence(manifest: str) -> int | None:
    for line in manifest.splitlines():
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            return int(line.split(":", 1)[1].strip())
    return None


def _first_segment(manifest: str) -> str | None:
    for line in manifest.splitlines():
        if line.endswith(".ts") and not line.startswith("#"):
            return line.strip()
    return None


if __name__ == "__main__":
    sys.exit(main())
