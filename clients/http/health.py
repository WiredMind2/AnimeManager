"""Operational health and metrics endpoints for the HTTP client."""

from __future__ import annotations

import ipaddress
import socket

from fastapi import HTTPException, Request

from shared.telemetry import get_telemetry


def _client_host(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return str(request.client.host).strip()
    return ""


def _host_resolves_to_private_address(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return True
    return False


def is_local_client(request: Request) -> bool:
    """Return True when the caller appears to be on a trusted local/LAN host."""
    host = _client_host(request)
    if not host:
        return False
    if host in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return _host_resolves_to_private_address(host)
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local)


def require_local_client(request: Request) -> None:
    """Raise 403 when the caller is not a trusted local/LAN client."""
    if not is_local_client(request):
        raise HTTPException(status_code=403, detail="Metrics are limited to trusted LAN clients.")


def build_health_snapshot() -> dict:
    """Assemble a health payload from in-process telemetry counters."""
    snap = get_telemetry().snapshot()
    counters = snap["counters"]
    gauges = snap["gauges"]

    persistence_errors = int(counters.get("coordinator.persist_errors", 0))
    queued_write_errors = int(counters.get("db.queued_write_errors", 0))
    http_errors = int(counters.get("http.errors", 0))
    client_errors = int(counters.get("client.errors", 0))
    last_search_failed = float(gauges.get("coordinator.last_search_failed", 0.0))

    degraded_reasons: list[str] = []
    if persistence_errors > 0:
        degraded_reasons.append("persistence_errors")
    if queued_write_errors > 0:
        degraded_reasons.append("queued_write_errors")
    if last_search_failed > 0:
        degraded_reasons.append("last_search_failed_providers")

    status = "degraded" if degraded_reasons else "ok"
    return {
        "status": status,
        "degraded_reasons": degraded_reasons,
        "checks": {
            "last_search_records": gauges.get("coordinator.last_search_records", 0.0),
            "last_search_failed_providers": last_search_failed,
            "persistence_errors": persistence_errors,
            "queued_write_errors": queued_write_errors,
            "http_errors": http_errors,
            "client_errors": client_errors,
            "ffmpeg_active_sessions": gauges.get("ffmpeg.active_sessions", 0.0),
            "download_queue_depth": gauges.get("download.queue_depth", 0.0),
        },
    }


def build_metrics_snapshot() -> dict:
    """Return the full in-process telemetry snapshot."""
    return get_telemetry().snapshot()
