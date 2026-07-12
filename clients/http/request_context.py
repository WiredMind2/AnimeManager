"""Request-scoped context for HTTP correlation IDs."""

from __future__ import annotations

import contextvars

REQUEST_ID_HEADER = "x-request-id"

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)


def get_request_id() -> str | None:
    """Return the active request ID for the current async/task context."""
    return _request_id.get()


def set_request_id(value: str | None) -> contextvars.Token[str | None]:
    """Bind ``value`` as the active request ID; returns a reset token."""
    return _request_id.set(value)


def reset_request_id(token: contextvars.Token[str | None]) -> None:
    """Restore the previous request ID after middleware teardown."""
    _request_id.reset(token)
