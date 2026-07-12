"""Telemetry collaborators (logging, metrics).

This package is the **canonical** home of the legacy :class:`Logger`
class, the composed :class:`LoggerService` collaborator, and the
in-process :class:`TelemetryCollector` used by the API->DB pipeline.
"""

from .logger import Logger, log
from .logger_service import LoggerService, get_default_logger_service
from .collector import TelemetryCollector, get_telemetry, reset_telemetry
from .tracer import get_tracer

__all__ = [
    "Logger",
    "log",
    "LoggerService",
    "get_default_logger_service",
    "TelemetryCollector",
    "get_telemetry",
    "reset_telemetry",
    "get_tracer",
]
