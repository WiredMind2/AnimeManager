"""Shared HTTP error mapping and FastAPI exception handlers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from domain.errors import (
    AnimeManagerError,
    InfrastructureError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from shared.security.utils import redact
from shared.telemetry import get_telemetry

from .request_context import get_request_id

if TYPE_CHECKING:
    from fastapi import FastAPI

_LOG = logging.getLogger("animemanager.http")


def map_error_to_status(exc: Exception) -> tuple[int, str]:
    """Map a domain or application exception to ``(status_code, detail)``."""
    if isinstance(exc, ValidationError):
        return 400, str(exc)
    if isinstance(exc, UnauthorizedError):
        return 401, str(exc)
    if isinstance(exc, NotFoundError):
        return 404, str(exc)
    if isinstance(exc, InfrastructureError):
        return 502, str(exc)
    if isinstance(exc, AnimeManagerError):
        return 500, str(exc)
    return 500, str(exc) if str(exc) else "Unexpected error"


def map_error_to_http(exc: Exception) -> HTTPException:
    """Map an exception to :class:`HTTPException` for FastAPI routes."""
    status_code, detail = map_error_to_status(exc)
    return HTTPException(status_code=status_code, detail=detail)


def _error_class_name(exc: Exception) -> str:
    return type(exc).__name__


def log_http_error(
    request: Request,
    exc: Exception,
    *,
    status_code: int,
) -> None:
    """Record a handled HTTP error in logs and in-process telemetry."""
    request_id = get_request_id() or request.headers.get("x-request-id", "")
    path = request.url.path
    method = request.method
    detail = redact(str(exc))
    telemetry = get_telemetry()
    telemetry.increment("http.errors")
    telemetry.increment(f"http.errors.{status_code}")
    telemetry.increment(f"http.errors.{_error_class_name(exc)}")

    if status_code >= 500:
        _LOG.error(
            "request_error request_id=%s method=%s path=%s status=%s detail=%s",
            request_id,
            method,
            path,
            status_code,
            detail,
            exc_info=exc,
        )
    elif status_code >= 400:
        _LOG.warning(
            "request_error request_id=%s method=%s path=%s status=%s detail=%s",
            request_id,
            method,
            path,
            status_code,
            detail,
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Install global handlers for domain and unexpected errors."""

    @app.exception_handler(AnimeManagerError)
    async def _handle_anime_manager_error(request: Request, exc: AnimeManagerError):
        status_code, detail = map_error_to_status(exc)
        log_http_error(request, exc, status_code=status_code)
        return JSONResponse(status_code=status_code, content={"detail": detail})

    @app.exception_handler(HTTPException)
    async def _handle_http_exception(request: Request, exc: HTTPException):
        if exc.status_code >= 500:
            log_http_error(request, exc, status_code=exc.status_code)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception):
        log_http_error(request, exc, status_code=500)
        return JSONResponse(status_code=500, content={"detail": "Unexpected error"})
