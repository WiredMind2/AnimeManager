"""Unit tests for per-session player debug logging."""

from __future__ import annotations

import json
from pathlib import Path

from application.services import player_session_log


def test_append_writes_jsonl(tmp_path: Path) -> None:
    output_dir = str(tmp_path / "sess-abc")
    Path(output_dir).mkdir(parents=True)

    player_session_log.append(
        output_dir,
        source="server",
        event="session_started",
        session_id="sess-abc",
        duration_seconds=1200.5,
    )
    player_session_log.append_client_batch(
        output_dir,
        [
            {
                "ts": "2026-06-12T12:00:00.000Z",
                "event": "buffering_started",
                "level": "info",
                "data": {"current_time": 0},
            }
        ],
    )

    log_path = player_session_log.player_log_path(output_dir)
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    server_row = json.loads(lines[0])
    assert server_row["source"] == "server"
    assert server_row["event"] == "session_started"
    assert server_row["session_id"] == "sess-abc"

    client_row = json.loads(lines[1])
    assert client_row["source"] == "client"
    assert client_row["event"] == "buffering_started"
    assert client_row["current_time"] == 0


def test_append_client_batch_ignores_reserved_data_keys(tmp_path: Path) -> None:
    """Regression: nested data must not duplicate append() reserved kwargs."""
    output_dir = str(tmp_path / "sess-dup")
    Path(output_dir).mkdir(parents=True)

    accepted = player_session_log.append_client_batch(
        output_dir,
        [
            {
                "ts": "2026-06-12T12:00:00.000Z",
                "event": "status_changed",
                "level": "info",
                "data": {
                    "ts": 1718190000000,
                    "event": "ignored",
                    "level": "error",
                    "source": "client",
                    "status": "Buffering…",
                },
            }
        ],
    )
    assert accepted == 1
    row = json.loads(
        player_session_log.player_log_path(output_dir).read_text(encoding="utf-8").strip()
    )
    assert row["event"] == "status_changed"
    assert row["level"] == "info"
    assert row["status"] == "Buffering…"
    assert "ignored" not in row.get("event", "")
