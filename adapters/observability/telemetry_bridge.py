"""Bridge in-process TelemetryCollector snapshots to OTLP metrics."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import TYPE_CHECKING

from shared.telemetry import get_telemetry

if TYPE_CHECKING:
    from opentelemetry.sdk.resources import Resource

_LOG = logging.getLogger("animemanager.observability")

_TIMER_STATS = ("count", "min", "p50", "p95", "max", "avg")
_METRICS_THREAD: threading.Thread | None = None
_METRICS_STOP = threading.Event()
_METRICS_LOCK = threading.Lock()


def _metrics_export_interval_ms() -> int:
    raw = os.environ.get("OTEL_METRICS_EXPORT_INTERVAL_MS", "15000").strip()
    try:
        return max(1000, int(raw))
    except ValueError:
        return 15000


def snapshot_to_metrics_data(resource: Resource):
    """Convert a TelemetryCollector snapshot into OTLP MetricsData."""
    from opentelemetry.sdk.metrics.export import (
        AggregationTemporality,
        Gauge,
        Metric,
        MetricsData,
        NumberDataPoint,
        ResourceMetrics,
        ScopeMetrics,
        Sum,
    )
    from opentelemetry.sdk.util.instrumentation import InstrumentationScope

    snap = get_telemetry().snapshot()
    now = int(time.time() * 1_000_000_000)
    metrics: list[Metric] = []

    for name, value in sorted(snap["counters"].items()):
        point = NumberDataPoint(
            attributes={},
            start_time_unix_nano=now,
            time_unix_nano=now,
            value=float(value),
        )
        metrics.append(
            Metric(
                name=name,
                description="",
                unit="1",
                data=Sum(
                    data_points=[point],
                    aggregation_temporality=AggregationTemporality.CUMULATIVE,
                    is_monotonic=True,
                ),
            )
        )

    for name, value in sorted(snap["gauges"].items()):
        point = NumberDataPoint(
            attributes={},
            start_time_unix_nano=now,
            time_unix_nano=now,
            value=float(value),
        )
        metrics.append(
            Metric(
                name=name,
                description="",
                unit="1",
                data=Gauge(data_points=[point]),
            )
        )

    for name, stats in sorted(snap["timers"].items()):
        for stat in _TIMER_STATS:
            raw = stats.get(stat)
            if raw is None:
                continue
            point = NumberDataPoint(
                attributes={"stat": stat},
                start_time_unix_nano=now,
                time_unix_nano=now,
                value=float(raw),
            )
            metrics.append(
                Metric(
                    name=f"{name}.{stat}",
                    description="",
                    unit="ms" if stat != "count" else "1",
                    data=Gauge(data_points=[point]),
                )
            )

    if not metrics:
        return None

    scope = ScopeMetrics(
        scope=InstrumentationScope("animemanager.collector"),
        schema_url="",
        metrics=metrics,
    )
    return MetricsData(resource_metrics=[ResourceMetrics(resource=resource, schema_url="", scope_metrics=[scope])])


def _metrics_export_loop(resource: Resource, interval_ms: int) -> None:
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.metrics.export import MetricExportResult

    exporter = OTLPMetricExporter()
    _LOG.info("TelemetryCollector metrics export started interval_ms=%s", interval_ms)
    while not _METRICS_STOP.wait(interval_ms / 1000.0):
        try:
            metrics_data = snapshot_to_metrics_data(resource)
            if metrics_data is None:
                continue
            result = exporter.export(metrics_data)
            if result is not MetricExportResult.SUCCESS:
                _LOG.debug("TelemetryCollector metrics export result=%s", result)
        except Exception:
            _LOG.exception("TelemetryCollector metrics export failed")


def start_metrics_export(resource: Resource) -> bool:
    """Start a background thread that exports collector snapshots via OTLP."""
    global _METRICS_THREAD
    with _METRICS_LOCK:
        if _METRICS_THREAD is not None and _METRICS_THREAD.is_alive():
            return False
        _METRICS_STOP.clear()
        interval_ms = _metrics_export_interval_ms()
        _METRICS_THREAD = threading.Thread(
            target=_metrics_export_loop,
            args=(resource, interval_ms),
            name="otel-collector-metrics",
            daemon=True,
        )
        _METRICS_THREAD.start()
        return True


def stop_metrics_export() -> None:
    """Signal the metrics export thread to stop (used in tests)."""
    _METRICS_STOP.set()
