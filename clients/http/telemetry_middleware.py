"""HTTP request telemetry: correlation IDs, latency timers, slow-request logs."""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Callable

from starlette.requests import Request
from starlette.responses import Response

from shared.telemetry import get_telemetry

from .request_context import REQUEST_ID_HEADER, reset_request_id, set_request_id
from .route_template import route_metric_key, route_template_for_request

_LOG = logging.getLogger("animemanager.http")

DEFAULT_SLOW_REQUEST_MS = 2000.0


def _slow_request_threshold_ms() -> float:
    raw = os.environ.get("TELEMETRY_SLOW_REQUEST_MS", "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return DEFAULT_SLOW_REQUEST_MS


def install_telemetry_middleware(app) -> None:
    """Register telemetry middleware on the FastAPI/Starlette app."""

    @app.middleware("http")
    async def _telemetry_middleware(request: Request, call_next: Callable) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = incoming or str(uuid.uuid4())
        token = set_request_id(request_id)
        started = time.perf_counter()
        status_code = 500
        route_template = route_template_for_request(request)
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        except Exception:
            status_code = 500
            raise
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            telemetry = get_telemetry()
            telemetry.increment("http.requests")
            telemetry.increment(f"http.responses.{status_code}")
            telemetry.record_ms("http.request_ms", elapsed_ms)
            telemetry.record_ms(route_metric_key(request.method, route_template), elapsed_ms)
            threshold = _slow_request_threshold_ms()
            if elapsed_ms >= threshold:
                _LOG.warning(
                    "slow_request request_id=%s method=%s route=%s path=%s status=%s duration_ms=%.1f",
                    request_id,
                    request.method,
                    route_template,
                    request.url.path,
                    status_code,
                    elapsed_ms,
                    extra={
                        "request_id": request_id,
                        "http.method": request.method,
                        "http.route": route_template,
                        "http.path": request.url.path,
                        "http.status_code": status_code,
                        "duration_ms": elapsed_ms,
                    },
                )
                telemetry.increment("http.slow_requests")
            reset_request_id(token)
