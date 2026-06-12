"""Per-session player debug log (``_player.log``) for playback diagnostics.

Each playback session writes JSON Lines to ``{output_dir}/_player.log``.
Server-side events (manifest/segment resolution, ffmpeg waits) and
client-side events (buffering, Shaka errors) share one timeline so
buffering incidents can be diagnosed without correlating separate logs.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

_LOG = logging.getLogger(__name__)

_PLAYER_LOG_NAME = "_player.log"
_MAX_FIELD_CHARS = 2048
_MAX_EVENTS_PER_CLIENT_BATCH = 200

# Per-output-dir locks so concurrent segment requests don't corrupt the file.
_dir_locks: dict[str, threading.Lock] = {}
_dir_locks_guard = threading.Lock()

Source = Literal["server", "client"]
Level = Literal["debug", "info", "warn", "error"]


def _lock_for(output_dir: str) -> threading.Lock:
    key = str(Path(output_dir).resolve())
    with _dir_locks_guard:
        lock = _dir_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _dir_locks[key] = lock
        return lock


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= _MAX_FIELD_CHARS:
            return value
        return value[:_MAX_FIELD_CHARS] + "…"
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item) for item in value[:50]]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for idx, (k, v) in enumerate(value.items()):
            if idx >= 50:
                out["_truncated"] = True
                break
            out[str(k)] = _sanitize_value(v)
        return out
    text = str(value)
    if len(text) <= _MAX_FIELD_CHARS:
        return text
    return text[:_MAX_FIELD_CHARS] + "…"


def _level_to_logging(level: str) -> int:
    normalized = str(level or "info").lower()
    if normalized in {"error", "critical"}:
        return logging.ERROR
    if normalized == "warn" or normalized == "warning":
        return logging.WARNING
    if normalized == "debug":
        return logging.DEBUG
    return logging.INFO


def append(
    output_dir: str,
    *,
    source: Source,
    event: str,
    level: Level = "info",
    ts: str | None = None,
    **fields: Any,
) -> None:
    """Append one JSON line to ``{output_dir}/_player.log`` and mirror to the live log viewer."""
    if not output_dir or not str(output_dir).strip():
        return
    record: dict[str, Any] = {
        "ts": ts or _utc_iso(),
        "source": source,
        "event": str(event or "").strip() or "unknown",
        "level": str(level or "info").lower(),
    }
    for key, value in fields.items():
        if value is None:
            continue
        record[str(key)] = _sanitize_value(value)

    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    log_path = Path(output_dir) / _PLAYER_LOG_NAME
    lock = _lock_for(output_dir)
    with lock:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")

    summary_bits = [
        f"source={source}",
        f"event={record['event']}",
    ]
    for key in ("segment", "result", "status", "client_host", "wait_ms", "session_id"):
        if key in record:
            summary_bits.append(f"{key}={record[key]}")
    message = "[PLAYER] " + " ".join(summary_bits)
    _LOG.log(_level_to_logging(record["level"]), message)


def append_client_batch(
    output_dir: str,
    events: list[dict[str, Any]],
) -> int:
    """Ingest a batch of client events; returns the number accepted."""
    if not output_dir or not events:
        return 0
    accepted = 0
    for raw in events[:_MAX_EVENTS_PER_CLIENT_BATCH]:
        if not isinstance(raw, dict):
            continue
        event = str(raw.get("event") or "").strip()
        if not event:
            continue
        level = str(raw.get("level") or "info").lower()
        if level not in {"debug", "info", "warn", "error"}:
            level = "info"
        ts = raw.get("ts")
        ts_str = str(ts).strip() if ts is not None else None
        data = raw.get("data")
        extra: dict[str, Any] = {}
        if isinstance(data, dict):
            extra.update(data)
        for key, value in raw.items():
            if key in {"event", "level", "ts", "data"}:
                continue
            extra[key] = value
        for reserved in ("event", "level", "ts", "source"):
            extra.pop(reserved, None)
        append(
            output_dir,
            source="client",
            event=event,
            level=level,  # type: ignore[arg-type]
            ts=ts_str,
            **extra,
        )
        accepted += 1
    return accepted


def player_log_path(output_dir: str) -> Path:
    return Path(output_dir) / _PLAYER_LOG_NAME
