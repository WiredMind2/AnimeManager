"""Logger collaborator (composable).

The legacy ``logger.Logger`` class was used as a mixin by inheriting
from it. The new rule (ADR 0005) is that logging must be received as
a constructor argument. :class:`LoggerService` delegates to the
legacy ``Logger`` instance for now so callers can switch import path
without changing behavior.
"""

from __future__ import annotations

from typing import Any, Optional


def _import_legacy_logger():
    try:
        from shared.telemetry.logger import Logger
    except ImportError:  # pragma: no cover
        from AnimeManager.shared.telemetry.logger import Logger  # type: ignore
    return Logger


class LoggerService:
    """Thin wrapper around :class:`logger.Logger`.

    Exposes a single ``log(category, *args)`` method (mirroring the
    legacy call pattern) without forcing callers to subclass
    ``Logger``.
    """

    def __init__(self, legacy_logger: Optional[Any] = None) -> None:
        self._logger = legacy_logger

    @classmethod
    def from_defaults(cls) -> "LoggerService":
        try:
            Logger = _import_legacy_logger()
            return cls(legacy_logger=Logger())
        except Exception:  # pragma: no cover - legacy logger is best-effort
            return cls(legacy_logger=None)

    def log(self, category: str, *args: Any, **kwargs: Any) -> None:
        if self._logger is None:
            return
        fn = getattr(self._logger, "log", None)
        if fn is None:
            return
        try:
            fn(category, *args, **kwargs)
        except Exception:  # pragma: no cover - logging must never raise
            return


_default_logger: Optional[LoggerService] = None


def get_default_logger_service() -> LoggerService:
    global _default_logger
    if _default_logger is None:
        _default_logger = LoggerService.from_defaults()
    return _default_logger


__all__ = ["LoggerService", "get_default_logger_service"]
