"""Ingest batched client telemetry events into the server log buffer."""

from __future__ import annotations

import json
import logging
from typing import Any

from shared.telemetry import get_telemetry

_CLIENT_LOG = logging.getLogger("animemanager.client")

_VALID_LEVELS = {"debug", "info", "warn", "warning", "error"}


def _normalize_level(raw: object) -> str:
    level = str(raw or "info").strip().lower()
    if level == "warning":
        return "warn"
    if level in _VALID_LEVELS:
        return level
    return "info"


def _log_level_no(level: str) -> int:
    return {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "error": logging.ERROR,
    }.get(level, logging.INFO)


def ingest_client_events(events: list[Any]) -> int:
    """Persist client events to the log buffer; return accepted count."""
    telemetry = get_telemetry()
    accepted = 0
    for item in events:
        if not isinstance(item, dict):
            continue
        event_name = str(item.get("event") or "client_event")
        level = _normalize_level(item.get("level"))
        data = item.get("data")
        if not isinstance(data, dict):
            data = {}
        ts = item.get("ts")
        message = f"{event_name} {json.dumps(data, default=str)}"
        if ts:
            message = f"[{ts}] {message}"

        log_fn = {
            "debug": _CLIENT_LOG.debug,
            "info": _CLIENT_LOG.info,
            "warn": _CLIENT_LOG.warning,
            "error": _CLIENT_LOG.error,
        }.get(level, _CLIENT_LOG.info)
        log_fn(message)
        telemetry.increment("client.events")
        if level == "error":
            telemetry.increment("client.errors")
        if event_name.startswith("web_vital."):
            metric = event_name.removeprefix("web_vital.")
            value = data.get("value")
            if isinstance(value, (int, float)):
                telemetry.record_ms(f"client.web_vitals.{metric}", float(value))
        accepted += 1
    return accepted
