"""Lazy OpenTelemetry tracer accessor with a no-op fallback.

Manual span instrumentation in the application and adapter layers goes through
:func:`get_tracer` so the code stays harmless when the ``opentelemetry`` package
is not installed or no :class:`TracerProvider` has been configured.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

try:
    from opentelemetry import trace as _trace  # type: ignore

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    _trace = None  # type: ignore
    _OTEL_AVAILABLE = False


class _NoOpSpan:
    """Minimal span surface used by call sites (attributes / exception / status)."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        pass

    def record_exception(self, exception: BaseException) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass

    def end(self) -> None:
        pass

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class _NoOpTracer:
    @contextmanager
    def start_as_current_span(
        self, name: str, *args: Any, **kwargs: Any
    ) -> Iterator[_NoOpSpan]:
        yield _NoOpSpan()


def get_tracer(name: str) -> Any:
    """Return an OpenTelemetry tracer for ``name`` or a no-op fallback."""
    if not _OTEL_AVAILABLE:
        return _NoOpTracer()
    try:
        return _trace.get_tracer(name)  # type: ignore[union-attr]
    except Exception:  # pragma: no cover - defensive
        return _NoOpTracer()


__all__ = ["get_tracer"]
