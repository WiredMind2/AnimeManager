"""Build and export the versioned AnimeManager Kibana dashboard bundle.

This developer utility creates saved objects through Kibana's public API and
then exports the resulting objects. The exported NDJSON is the installable
artifact; do not hand-edit it.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


VEGA_LITE_SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"
TRACE_INDEX = "traces-*.otel-*"
METRIC_INDEX = "metrics-*.otel-*"
LOG_INDEX = "logs-*.otel-*"
# Include an index that always exists so log panels return empty aggregations
# before the first OTEL log data stream is created.
LOG_QUERY_INDEX = f"{LOG_INDEX},{TRACE_INDEX}"

DATA_VIEWS = {
    "animemanager-traces": ("AnimeManager OTEL traces", TRACE_INDEX),
    "animemanager-metrics": ("AnimeManager OTEL metrics", METRIC_INDEX),
    "animemanager-logs": ("AnimeManager OTEL logs", LOG_INDEX),
}


def _date_histogram() -> dict[str, Any]:
    return {
        "field": "@timestamp",
        "fixed_interval": "5m",
        "extended_bounds": {
            "min": {"%timefilter%": "min"},
            "max": {"%timefilter%": "max"},
        },
        "min_doc_count": 0,
    }


def _data(index: str, aggs: dict[str, Any], property_path: str) -> dict[str, Any]:
    return {
        "url": {
            "%context%": True,
            "%timefield%": "@timestamp",
            "index": index,
            "body": {"size": 0, "aggs": aggs},
        },
        "format": {"property": property_path},
    }


def _base_spec(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": VEGA_LITE_SCHEMA,
        "autosize": {"type": "fit", "contains": "padding"},
        "width": "container",
        "height": "container",
        "data": data,
        "config": {
            "axis": {"labelLimit": 140, "titleFontSize": 12},
            "legend": {"labelLimit": 160, "orient": "bottom"},
            "view": {"stroke": None},
        },
    }


def _request_volume() -> dict[str, Any]:
    aggs = {
        "http": {
            "filter": {"exists": {"field": "http.response.status_code"}},
            "aggs": {"timeline": {"date_histogram": _date_histogram()}},
        }
    }
    spec = _base_spec(_data(TRACE_INDEX, aggs, "aggregations.http.timeline.buckets"))
    spec.update(
        {
            "mark": {"type": "area", "line": True, "opacity": 0.25},
            "encoding": {
                "x": {
                    "field": "key",
                    "type": "temporal",
                    "title": "Time",
                    "axis": {"format": "%H:%M"},
                },
                "y": {
                    "field": "doc_count",
                    "type": "quantitative",
                    "title": "HTTP spans",
                },
                "tooltip": [
                    {"field": "key_as_string", "type": "nominal", "title": "Time"},
                    {"field": "doc_count", "type": "quantitative", "title": "Requests"},
                ],
            },
        }
    )
    return spec


def _latency_p95() -> dict[str, Any]:
    aggs = {
        "http": {
            "filter": {"exists": {"field": "http.response.status_code"}},
            "aggs": {
                "timeline": {
                    "date_histogram": _date_histogram(),
                    "aggs": {
                        "latency": {
                            "percentiles": {
                                "field": "span.duration.us",
                                "percents": [50, 95],
                            }
                        }
                    },
                }
            },
        }
    }
    spec = _base_spec(_data(TRACE_INDEX, aggs, "aggregations.http.timeline.buckets"))
    spec.update(
        {
            "transform": [
                {"calculate": "datum.latency.values['50.0'] / 1000", "as": "p50_ms"},
                {"calculate": "datum.latency.values['95.0'] / 1000", "as": "p95_ms"},
                {"fold": ["p50_ms", "p95_ms"], "as": ["percentile", "latency_ms"]},
            ],
            "mark": {"type": "line", "point": False},
            "encoding": {
                "x": {"field": "key", "type": "temporal", "title": "Time"},
                "y": {
                    "field": "latency_ms",
                    "type": "quantitative",
                    "title": "Latency (ms)",
                },
                "color": {
                    "field": "percentile",
                    "type": "nominal",
                    "title": "Percentile",
                },
                "tooltip": [
                    {"field": "key_as_string", "type": "nominal", "title": "Time"},
                    {
                        "field": "percentile",
                        "type": "nominal",
                        "title": "Percentile",
                    },
                    {
                        "field": "latency_ms",
                        "type": "quantitative",
                        "title": "Latency (ms)",
                        "format": ".1f",
                    },
                ],
            },
        }
    )
    return spec


def _status_distribution() -> dict[str, Any]:
    aggs = {
        "http": {
            "filter": {"exists": {"field": "http.response.status_code"}},
            "aggs": {
                "statuses": {
                    "terms": {"field": "http.response.status_code", "size": 20}
                }
            },
        }
    }
    spec = _base_spec(_data(TRACE_INDEX, aggs, "aggregations.http.statuses.buckets"))
    spec.update(
        {
            "mark": {"type": "arc", "innerRadius": 45},
            "encoding": {
                "theta": {"field": "doc_count", "type": "quantitative"},
                "color": {
                    "field": "key",
                    "type": "nominal",
                    "title": "HTTP status",
                },
                "tooltip": [
                    {"field": "key", "type": "nominal", "title": "Status"},
                    {"field": "doc_count", "type": "quantitative", "title": "Count"},
                ],
            },
        }
    )
    return spec


def _service_activity() -> dict[str, Any]:
    aggs = {
        "timeline": {
            "date_histogram": _date_histogram(),
            "aggs": {
                "services": {"terms": {"field": "service.name", "size": 10}}
            },
        }
    }
    spec = _base_spec(_data(TRACE_INDEX, aggs, "aggregations.timeline.buckets"))
    spec.update(
        {
            "transform": [
                {"flatten": ["services.buckets"], "as": ["service"]},
            ],
            "mark": {"type": "line"},
            "encoding": {
                "x": {"field": "key", "type": "temporal", "title": "Time"},
                "y": {
                    "field": "service.doc_count",
                    "type": "quantitative",
                    "title": "Spans",
                },
                "color": {
                    "field": "service.key",
                    "type": "nominal",
                    "title": "Service",
                },
                "tooltip": [
                    {"field": "key_as_string", "type": "nominal", "title": "Time"},
                    {"field": "service.key", "type": "nominal", "title": "Service"},
                    {
                        "field": "service.doc_count",
                        "type": "quantitative",
                        "title": "Spans",
                    },
                ],
            },
        }
    )
    return spec


def _top_routes(metric: str = "count") -> dict[str, Any]:
    route_aggs: dict[str, Any] = {}
    if metric == "latency":
        route_aggs["avg_latency"] = {"avg": {"field": "span.duration.us"}}
    aggs = {
        "http": {
            "filter": {"exists": {"field": "http.response.status_code"}},
            "aggs": {
                "routes": {
                    "terms": {
                        "field": "url.path",
                        "size": 10,
                        **(
                            {"order": {"avg_latency": "desc"}}
                            if metric == "latency"
                            else {}
                        ),
                    },
                    "aggs": route_aggs,
                }
            },
        }
    }
    spec = _base_spec(_data(TRACE_INDEX, aggs, "aggregations.http.routes.buckets"))
    if metric == "latency":
        spec["transform"] = [
            {"calculate": "datum.avg_latency.value / 1000", "as": "value"}
        ]
        title = "Average latency (ms)"
    else:
        spec["transform"] = [{"calculate": "datum.doc_count", "as": "value"}]
        title = "Requests"
    spec.update(
        {
            "mark": {"type": "bar"},
            "encoding": {
                "y": {
                    "field": "key",
                    "type": "nominal",
                    "sort": "-x",
                    "title": "Route",
                    "axis": {"labelLimit": 220},
                },
                "x": {"field": "value", "type": "quantitative", "title": title},
                "tooltip": [
                    {"field": "key", "type": "nominal", "title": "Route"},
                    {
                        "field": "value",
                        "type": "quantitative",
                        "title": title,
                        "format": ".1f",
                    },
                ],
            },
        }
    )
    return spec


def _operational_gauges() -> dict[str, Any]:
    fields = {
        "playback": "metrics.playback.active_sessions",
        "ffmpeg": "metrics.ffmpeg.active_sessions",
        "downloads": "metrics.download.queue_depth",
    }
    aggs = {
        "timeline": {
            "date_histogram": _date_histogram(),
            "aggs": {
                name: {"max": {"field": field}} for name, field in fields.items()
            },
        }
    }
    spec = _base_spec(_data(METRIC_INDEX, aggs, "aggregations.timeline.buckets"))
    spec.update(
        {
            "transform": [
                {"calculate": "datum.playback.value", "as": "Playback sessions"},
                {"calculate": "datum.ffmpeg.value", "as": "FFmpeg sessions"},
                {"calculate": "datum.downloads.value", "as": "Download queue"},
                {
                    "fold": [
                        "Playback sessions",
                        "FFmpeg sessions",
                        "Download queue",
                    ],
                    "as": ["metric", "value"],
                },
                {"filter": "isValid(datum.value)"},
            ],
            "mark": {"type": "line", "interpolate": "step-after"},
            "encoding": {
                "x": {"field": "key", "type": "temporal", "title": "Time"},
                "y": {"field": "value", "type": "quantitative", "title": "Active"},
                "color": {"field": "metric", "type": "nominal", "title": "Metric"},
                "tooltip": [
                    {"field": "key_as_string", "type": "nominal", "title": "Time"},
                    {"field": "metric", "type": "nominal", "title": "Metric"},
                    {"field": "value", "type": "quantitative", "title": "Value"},
                ],
            },
        }
    )
    return spec


def _client_errors() -> dict[str, Any]:
    aggs = {
        "errors": {
            "filter": {"term": {"attributes.telemetry.level": "error"}},
            "aggs": {"timeline": {"date_histogram": _date_histogram()}},
        }
    }
    spec = _base_spec(
        _data(LOG_QUERY_INDEX, aggs, "aggregations.errors.timeline.buckets")
    )
    spec.update(
        {
            "mark": {"type": "bar"},
            "encoding": {
                "x": {"field": "key", "type": "temporal", "title": "Time"},
                "y": {
                    "field": "doc_count",
                    "type": "quantitative",
                    "title": "Client errors",
                },
                "tooltip": [
                    {"field": "key_as_string", "type": "nominal", "title": "Time"},
                    {"field": "doc_count", "type": "quantitative", "title": "Errors"},
                ],
            },
        }
    )
    return spec


def _client_terms(field: str, axis_title: str) -> dict[str, Any]:
    aggs = {
        "client": {
            "filter": {"term": {"attributes.telemetry.source": "client"}},
            "aggs": {"values": {"terms": {"field": field, "size": 12}}},
        }
    }
    spec = _base_spec(
        _data(LOG_QUERY_INDEX, aggs, "aggregations.client.values.buckets")
    )
    spec.update(
        {
            "mark": {"type": "bar"},
            "encoding": {
                "y": {
                    "field": "key",
                    "type": "nominal",
                    "sort": "-x",
                    "title": axis_title,
                    "axis": {"labelLimit": 220},
                },
                "x": {
                    "field": "doc_count",
                    "type": "quantitative",
                    "title": "Events",
                },
                "tooltip": [
                    {"field": "key", "type": "nominal", "title": axis_title},
                    {"field": "doc_count", "type": "quantitative", "title": "Events"},
                ],
            },
        }
    )
    return spec


def _web_vital_summary() -> dict[str, Any]:
    aggs = {
        "vitals": {
            "filter": {"exists": {"field": "attributes.telemetry.web_vital"}},
            "aggs": {
                "metrics": {
                    "terms": {
                        "field": "attributes.telemetry.web_vital",
                        "size": 10,
                    },
                    "aggs": {
                        "p75": {
                            "percentiles": {
                                "field": "attributes.telemetry.web_vital_value",
                                "percents": [75],
                            }
                        }
                    },
                }
            },
        }
    }
    spec = _base_spec(
        _data(LOG_QUERY_INDEX, aggs, "aggregations.vitals.metrics.buckets")
    )
    spec.update(
        {
            "transform": [
                {"calculate": "datum.p75.values['75.0']", "as": "value"}
            ],
            "mark": {"type": "bar"},
            "encoding": {
                "x": {
                    "field": "key",
                    "type": "nominal",
                    "title": "Web vital",
                },
                "y": {
                    "field": "value",
                    "type": "quantitative",
                    "title": "p75 value",
                },
                "color": {"field": "key", "type": "nominal", "legend": None},
                "tooltip": [
                    {"field": "key", "type": "nominal", "title": "Metric"},
                    {
                        "field": "value",
                        "type": "quantitative",
                        "title": "p75",
                        "format": ".2f",
                    },
                    {
                        "field": "doc_count",
                        "type": "quantitative",
                        "title": "Samples",
                    },
                ],
            },
        }
    )
    return spec


def _web_vital_trend() -> dict[str, Any]:
    aggs = {
        "vitals": {
            "filter": {"exists": {"field": "attributes.telemetry.web_vital"}},
            "aggs": {
                "timeline": {
                    "date_histogram": _date_histogram(),
                    "aggs": {
                        "metrics": {
                            "terms": {
                                "field": "attributes.telemetry.web_vital",
                                "size": 10,
                            },
                            "aggs": {
                                "average": {
                                    "avg": {
                                        "field": "attributes.telemetry.web_vital_value"
                                    }
                                }
                            },
                        }
                    },
                }
            },
        }
    }
    spec = _base_spec(
        _data(LOG_QUERY_INDEX, aggs, "aggregations.vitals.timeline.buckets")
    )
    spec.update(
        {
            "transform": [
                {"flatten": ["metrics.buckets"], "as": ["metric"]},
            ],
            "mark": {"type": "line", "point": True},
            "encoding": {
                "x": {"field": "key", "type": "temporal", "title": "Time"},
                "y": {
                    "field": "metric.average.value",
                    "type": "quantitative",
                    "title": "Average value",
                },
                "color": {
                    "field": "metric.key",
                    "type": "nominal",
                    "title": "Web vital",
                },
                "tooltip": [
                    {"field": "key_as_string", "type": "nominal", "title": "Time"},
                    {
                        "field": "metric.key",
                        "type": "nominal",
                        "title": "Metric",
                    },
                    {
                        "field": "metric.average.value",
                        "type": "quantitative",
                        "title": "Average",
                        "format": ".2f",
                    },
                ],
            },
        }
    )
    return spec


def _metric_field(name: str) -> str:
    return f"metrics.{name}"


def _time_x(title: str = "Time") -> dict[str, Any]:
    return {"field": "key", "type": "temporal", "title": title, "axis": {"format": "%H:%M"}}


def _single_metric_over_time(
    metric: str, y_title: str, *, mark: str = "line", interpolate: str | None = None
) -> dict[str, Any]:
    """One counter (cumulative max) or gauge plotted over a date histogram."""
    aggs = {
        "timeline": {
            "date_histogram": _date_histogram(),
            "aggs": {"value": {"max": {"field": _metric_field(metric)}}},
        }
    }
    spec = _base_spec(_data(METRIC_INDEX, aggs, "aggregations.timeline.buckets"))
    mark_def: dict[str, Any] = {"type": mark}
    if mark == "area":
        mark_def = {"type": "area", "line": True, "opacity": 0.25}
    if interpolate:
        mark_def["interpolate"] = interpolate
    spec.update(
        {
            "transform": [{"calculate": "datum.value.value", "as": "value"}],
            "mark": mark_def,
            "encoding": {
                "x": _time_x(),
                "y": {"field": "value", "type": "quantitative", "title": y_title},
                "tooltip": [
                    {"field": "key_as_string", "type": "nominal", "title": "Time"},
                    {
                        "field": "value",
                        "type": "quantitative",
                        "title": y_title,
                        "format": ".1f",
                    },
                ],
            },
        }
    )
    return spec


def _multi_metric_over_time(
    series: list[tuple[str, str]],
    y_title: str,
    *,
    mark: str = "line",
    interpolate: str | None = None,
    stacked: bool = False,
) -> dict[str, Any]:
    """Several metrics folded into colored series over a date histogram.

    ``series`` is a list of ``(label, metric_name)`` tuples. Counters are
    visualized as their cumulative max per bucket; gauges as their max.
    """
    sub_aggs = {label: {"max": {"field": _metric_field(name)}} for label, name in series}
    aggs = {"timeline": {"date_histogram": _date_histogram(), "aggs": sub_aggs}}
    spec = _base_spec(_data(METRIC_INDEX, aggs, "aggregations.timeline.buckets"))
    calc = [{"calculate": f"datum.{label}.value", "as": label} for label, _ in series]
    fold = [
        {"fold": [label for label, _ in series], "as": ["metric", "value"]},
        {"filter": "isValid(datum.value)"},
    ]
    mark_def: dict[str, Any] = {"type": mark}
    if interpolate:
        mark_def["interpolate"] = interpolate
    if stacked and mark == "bar":
        mark_def["stack"] = "zero"
    spec.update(
        {
            "transform": calc + fold,
            "mark": mark_def,
            "encoding": {
                "x": _time_x(),
                "y": {"field": "value", "type": "quantitative", "title": y_title},
                "color": {"field": "metric", "type": "nominal", "title": "Metric"},
                "tooltip": [
                    {"field": "key_as_string", "type": "nominal", "title": "Time"},
                    {"field": "metric", "type": "nominal", "title": "Metric"},
                    {
                        "field": "value",
                        "type": "quantitative",
                        "title": y_title,
                        "format": ".1f",
                    },
                ],
            },
        }
    )
    return spec


def _metric_max_bar(
    series: list[tuple[str, str]], x_title: str, *, size: int | None = None
) -> dict[str, Any]:
    """Horizontal bar: one bar per metric, value = max over the time range.

    Used for dimensions baked into metric names (job / source / status) where
    the OTel ``otel`` mapping mode exposes no ``metric.name`` keyword to terms
    on, so the known dimension values are enumerated explicitly.
    """
    aggs = {label: {"max": {"field": _metric_field(name)}} for label, name in series}
    spec = _base_spec(_data(METRIC_INDEX, aggs, "aggregations"))
    calc = [{"calculate": f"datum.{label}.value", "as": label} for label, _ in series]
    fold = [
        {"fold": [label for label, _ in series], "as": ["metric", "value"]},
        {"filter": "isValid(datum.value)"},
    ]
    spec.update(
        {
            "transform": calc + fold,
            "mark": {"type": "bar"},
            "encoding": {
                "y": {
                    "field": "metric",
                    "type": "nominal",
                    "sort": "-x",
                    "title": None,
                    "axis": {"labelLimit": 220},
                },
                "x": {"field": "value", "type": "quantitative", "title": x_title},
                "tooltip": [
                    {"field": "metric", "type": "nominal", "title": "Metric"},
                    {
                        "field": "value",
                        "type": "quantitative",
                        "title": x_title,
                        "format": ".1f",
                    },
                ],
            },
        }
    )
    return spec


def _timer_stat_over_time(timer: str, stat: str, y_title: str) -> dict[str, Any]:
    """One timer stat (e.g. p95) over time. Field is ``metrics.<timer>.<stat>``."""
    return _single_metric_over_time(f"{timer}.{stat}", y_title, mark="line")


def _traces_name_donut(
    prefixes: list[str], title: str, size: int = 12
) -> dict[str, Any]:
    """Donut of trace span counts grouped by ``span.name`` prefix."""
    should = [{"prefix": {"span.name": prefix}} for prefix in prefixes]
    aggs = {
        "spans": {
            "filter": {"bool": {"should": should, "minimum_should_match": 1}},
            "aggs": {"names": {"terms": {"field": "span.name", "size": size}}},
        }
    }
    spec = _base_spec(_data(TRACE_INDEX, aggs, "aggregations.spans.names.buckets"))
    spec.update(
        {
            "mark": {"type": "arc", "innerRadius": 45},
            "encoding": {
                "theta": {"field": "doc_count", "type": "quantitative"},
                "color": {"field": "key", "type": "nominal", "title": title},
                "tooltip": [
                    {"field": "key", "type": "nominal", "title": "Span"},
                    {"field": "doc_count", "type": "quantitative", "title": "Count"},
                ],
            },
        }
    )
    return spec


def _logs_filter_bar(exists_field: str, y_title: str) -> dict[str, Any]:
    """Bar of log record counts over time where ``exists_field`` is present."""
    aggs = {
        "filtered": {
            "filter": {"exists": {"field": exists_field}},
            "aggs": {"timeline": {"date_histogram": _date_histogram()}},
        }
    }
    spec = _base_spec(
        _data(LOG_QUERY_INDEX, aggs, "aggregations.filtered.timeline.buckets")
    )
    spec.update(
        {
            "mark": {"type": "bar"},
            "encoding": {
                "x": _time_x(),
                "y": {"field": "doc_count", "type": "quantitative", "title": y_title},
                "tooltip": [
                    {"field": "key_as_string", "type": "nominal", "title": "Time"},
                    {"field": "doc_count", "type": "quantitative", "title": y_title},
                ],
            },
        }
    )
    return spec


# Bounded dimensions baked into metric names (OTel ``otel`` mapping mode has no
# ``metric.name`` keyword, so dimension values are enumerated explicitly).
_HTTP_ERROR_STATUSES = ["400", "401", "404", "500", "502"]
_HTTP_ERROR_CLASSES = [
    "NotFoundError",
    "ValidationError",
    "InfrastructureError",
    "UnauthorizedError",
    "AnimeManagerError",
    "HTTPException",
]
_STARTUP_JOBS = [
    "repair_date_from",
    "fetch_latest_anime",
    "update_status",
    "sync_watching_tags",
    "purge_seen_libraries",
    "purge_deleted_torrents",
    "restore_libtorrent_sessions",
    "repair_torrent_index",
    "reconcile_deleted_torrents",
]
_WRITE_SOURCES = [
    "search",
    "stream",
    "schedule",
    "season",
    "genre",
    "hydration",
    "backfill",
    "repair",
]


VISUALIZATIONS: dict[str, tuple[str, dict[str, Any], str]] = {
    "am-request-volume": (
        "HTTP request volume",
        _request_volume(),
        "HTTP spans over time from OTEL traces.",
    ),
    "am-latency-p95": (
        "HTTP latency p50 / p95",
        _latency_p95(),
        "HTTP span latency percentiles.",
    ),
    "am-status-distribution": (
        "HTTP status distribution",
        _status_distribution(),
        "Response status codes from traced HTTP spans.",
    ),
    "am-service-activity": (
        "Service activity",
        _service_activity(),
        "Trace span volume by AnimeManager service.",
    ),
    "am-top-routes": (
        "Top HTTP routes",
        _top_routes(),
        "Most frequently traced HTTP routes.",
    ),
    "am-slowest-routes": (
        "Slowest HTTP routes",
        _top_routes("latency"),
        "Routes ranked by average traced latency.",
    ),
    "am-operational-gauges": (
        "Playback and download activity",
        _operational_gauges(),
        "Active playback/FFmpeg sessions and download queue depth.",
    ),
    "am-client-errors": (
        "Client errors over time",
        _client_errors(),
        "Browser error events ingested as OTEL logs.",
    ),
    "am-client-events": (
        "Client event types",
        _client_terms("attributes.telemetry.event", "Event"),
        "Most common structured browser telemetry events.",
    ),
    "am-client-error-paths": (
        "Client events by path",
        _client_terms("attributes.telemetry.path", "Path"),
        "Browser telemetry grouped by application path.",
    ),
    "am-client-error-names": (
        "Client errors by name",
        _client_terms("attributes.telemetry.error_name", "Error"),
        "Browser telemetry grouped by error name.",
    ),
    "am-web-vital-summary": (
        "Core Web Vitals p75",
        _web_vital_summary(),
        "75th percentile LCP, INP, CLS, and TTFB values.",
    ),
    "am-web-vital-trend": (
        "Core Web Vitals trend",
        _web_vital_trend(),
        "Average browser web-vital values over time.",
    ),
    # --- Database & persistence -------------------------------------------
    "am-db-commits": (
        "DB commits over time",
        _single_metric_over_time("db.commits", "Commits", mark="area"),
        "Cumulative database commits scraped from OTEL metrics.",
    ),
    "am-db-queries": (
        "DB queries over time",
        _single_metric_over_time("db.queries", "Queries", mark="area"),
        "Cumulative database queries scraped from OTEL metrics.",
    ),
    "am-db-upserts": (
        "DB upserts committed",
        _single_metric_over_time("db.upserts_committed", "Upserts", mark="line"),
        "Cumulative anime upserts committed through the DB gateway.",
    ),
    "am-db-write-errors": (
        "DB queued write errors vs flushed",
        _multi_metric_over_time(
            [
                ("errors", "db.queued_write_errors"),
                ("flushed", "db.queued_writes_flushed"),
            ],
            "Count",
            mark="bar",
            stacked=True,
        ),
        "Background write-queue failures versus successful flushes.",
    ),
    "am-db-upsert-latency": (
        "DB upsert batch latency (p95)",
        _timer_stat_over_time("db.upsert_anime_batch_ms", "p95", "Latency (ms)"),
        "95th percentile anime batch upsert latency.",
    ),
    # --- Metadata ingestion & coordinator --------------------------------
    "am-ingestion-records": (
        "Ingestion records collected vs persisted",
        _multi_metric_over_time(
            [
                ("collected", "ingestion.records_collected"),
                ("persisted", "ingestion.records_persisted"),
            ],
            "Records",
            mark="line",
        ),
        "Cumulative metadata records collected versus persisted.",
    ),
    "am-ingestion-failed-providers": (
        "Ingestion failed providers",
        _single_metric_over_time(
            "ingestion.failed_providers", "Failures", mark="bar"
        ),
        "Cumulative provider failures during ingestion runs.",
    ),
    "am-ingestion-latency": (
        "Ingestion latency (p95)",
        _multi_metric_over_time(
            [
                ("total", "ingestion.total_ms.p95"),
                ("sink_flush", "ingestion.sink_flush_ms.p95"),
            ],
            "Latency (ms)",
            mark="line",
        ),
        "95th percentile total ingestion and sink-flush latency.",
    ),
    "am-coordinator-search": (
        "Coordinator last search records vs failed",
        _multi_metric_over_time(
            [
                ("records", "coordinator.last_search_records"),
                ("failed", "coordinator.last_search_failed"),
            ],
            "Count",
            mark="line",
            interpolate="step-after",
        ),
        "Last search-run record count and provider failures.",
    ),
    "am-coordinator-schedule-genre": (
        "Coordinator schedule/season/genre records",
        _multi_metric_over_time(
            [
                ("schedule", "coordinator.last_schedule_records"),
                ("season", "coordinator.last_season_records"),
                ("genre", "coordinator.last_genre_records"),
            ],
            "Records",
            mark="bar",
        ),
        "Record counts from the last schedule, season, and genre runs.",
    ),
    # --- Startup jobs -----------------------------------------------------
    "am-startup-total": (
        "Startup total time (max)",
        _timer_stat_over_time("startup.total_ms", "max", "Duration (ms)"),
        "Maximum total startup-job wall-clock duration.",
    ),
    "am-startup-jobs-bar": (
        "Startup job duration by job (max)",
        _metric_max_bar(
            [(job, f"startup.job.{job}_ms.max") for job in _STARTUP_JOBS],
            "Duration (ms)",
        ),
        "Per-job maximum duration across startup runs.",
    ),
    "am-startup-errors": (
        "Startup job errors by job",
        _metric_max_bar(
            [(job, f"startup.job.{job}_errors") for job in _STARTUP_JOBS],
            "Errors",
        ),
        "Per-job cumulative error count.",
    ),
    "am-startup-commits": (
        "Startup job commits by job",
        _metric_max_bar(
            [(job, f"startup.job.{job}_commits") for job in _STARTUP_JOBS],
            "Commits",
        ),
        "Per-job cumulative commit count.",
    ),
    "am-startup-failed": (
        "Startup failed vs total jobs",
        _multi_metric_over_time(
            [
                ("failed", "startup.failed_jobs"),
                ("total", "startup.total_jobs"),
            ],
            "Jobs",
            mark="line",
            interpolate="step-after",
        ),
        "Failed versus total startup jobs per run.",
    ),
    # --- Playback & transcoding -------------------------------------------
    "am-playback-sessions": (
        "Playback sessions created",
        _single_metric_over_time(
            "playback.sessions_created", "Sessions", mark="line"
        ),
        "Cumulative HLS playback sessions created.",
    ),
    "am-playback-active": (
        "Active playback and FFmpeg sessions",
        _multi_metric_over_time(
            [
                ("playback", "playback.active_sessions"),
                ("ffmpeg", "ffmpeg.active_sessions"),
            ],
            "Active",
            mark="line",
            interpolate="step-after",
        ),
        "Concurrent playback and FFmpeg transcode sessions.",
    ),
    "am-playback-create-latency": (
        "Playback session create latency (p95)",
        _timer_stat_over_time(
            "playback.session_create_ms", "p95", "Latency (ms)"
        ),
        "95th percentile playback session creation latency.",
    ),
    "am-playback-segment-latency": (
        "Playback segment resolve latency (p95)",
        _timer_stat_over_time(
            "playback.segment_resolve_ms", "p95", "Latency (ms)"
        ),
        "95th percentile segment resolve / ensure latency.",
    ),
    "am-ffmpeg-started-failed": (
        "FFmpeg transcodes started vs failures",
        _multi_metric_over_time(
            [
                ("started", "ffmpeg.transcodes_started"),
                ("failures", "ffmpeg.failures"),
            ],
            "Count",
            mark="bar",
            stacked=True,
        ),
        "Cumulative FFmpeg transcodes started versus failures.",
    ),
    "am-playback-spans": (
        "Playback and FFmpeg spans",
        _traces_name_donut(["playback.", "ffmpeg."], "Span"),
        "Trace span volume for playback and FFmpeg operations.",
    ),
    # --- Downloads & torrents ---------------------------------------------
    "am-download-queue": (
        "Download queue depth",
        _single_metric_over_time(
            "download.queue_depth", "Queued", mark="line", interpolate="step-after"
        ),
        "Pending downloads waiting for a worker slot.",
    ),
    "am-download-active": (
        "Active downloads",
        _single_metric_over_time("download.active", "Active", mark="line"),
        "Concurrent in-flight downloads.",
    ),
    "am-download-lifecycle": (
        "Download lifecycle (started/completed/failed)",
        _multi_metric_over_time(
            [
                ("started", "download.started"),
                ("completed", "download.completed"),
                ("failed", "download.failed"),
            ],
            "Count",
            mark="bar",
            stacked=True,
        ),
        "Cumulative downloads started, completed, and failed.",
    ),
    "am-download-enqueue-latency": (
        "Download enqueue latency (p95)",
        _timer_stat_over_time("download.enqueue_ms", "p95", "Latency (ms)"),
        "95th percentile download enqueue latency.",
    ),
    "am-torrent-active": (
        "Active torrents (LibTorrent)",
        _single_metric_over_time("torrent.active", "Torrents", mark="line"),
        "Active torrent handles reported by the LibTorrent daemon.",
    ),
    "am-torrent-ops": (
        "Torrent restore and reconcile ops",
        _multi_metric_over_time(
            [
                ("restore", "torrent.restore_count"),
                ("reconcile_deleted", "torrent.reconcile_deleted"),
            ],
            "Count",
            mark="bar",
            stacked=True,
        ),
        "Cumulative LibTorrent session restores and deleted-torrent reconciles.",
    ),
    # --- HTTP errors & slow requests --------------------------------------
    "am-http-errors-trend": (
        "HTTP errors over time",
        _single_metric_over_time("http.errors", "Errors", mark="line"),
        "Cumulative handled HTTP errors.",
    ),
    "am-http-errors-status": (
        "HTTP errors by status code",
        _multi_metric_over_time(
            [(f"HTTP {s}", f"http.errors.{s}") for s in _HTTP_ERROR_STATUSES],
            "Errors",
            mark="bar",
            stacked=True,
        ),
        "Cumulative HTTP errors broken down by response status code.",
    ),
    "am-http-errors-exception": (
        "HTTP errors by exception class",
        _multi_metric_over_time(
            [(cls, f"http.errors.{cls}") for cls in _HTTP_ERROR_CLASSES],
            "Errors",
            mark="bar",
            stacked=True,
        ),
        "Cumulative HTTP errors broken down by exception class.",
    ),
    "am-slow-requests": (
        "Slow requests over time",
        _single_metric_over_time("http.slow_requests", "Slow requests", mark="line"),
        "Cumulative requests exceeding the slow-request threshold.",
    ),
    "am-slow-request-logs": (
        "Slow request log records",
        _logs_filter_bar("attributes.duration_ms", "Slow request logs"),
        "Backend slow_request log records (have attributes.duration_ms).",
    ),
    # --- Catalog & anime writes -------------------------------------------
    "am-catalog-ops": (
        "Catalog merge and identity operations",
        _multi_metric_over_time(
            [
                ("merge", "catalog.merge"),
                ("identity_conflict", "catalog.identity.conflict"),
                ("enrichment_merges", "catalog.enrichment.merges"),
                ("enrichment_lookups", "catalog.enrichment.lookups"),
            ],
            "Count",
            mark="bar",
            stacked=True,
        ),
        "Cumulative catalog merge, identity-conflict, and enrichment operations.",
    ),
    "am-anime-write-source": (
        "Anime writes by source",
        _metric_max_bar(
            [(src, f"anime_write.source.{src}") for src in _WRITE_SOURCES],
            "Writes",
        ),
        "Cumulative anime writes grouped by ingestion source.",
    ),
    "am-anime-write-persisted": (
        "Anime writes persisted vs errors",
        _multi_metric_over_time(
            [
                ("persisted", "anime_write.persisted"),
                ("errors", "anime_write.errors"),
            ],
            "Count",
            mark="line",
        ),
        "Cumulative anime records persisted versus write errors.",
    ),
    "am-anime-write-latency": (
        "Anime write persist latency (p95)",
        _timer_stat_over_time(
            "anime_write.persist_records_ms", "p95", "Latency (ms)"
        ),
        "95th percentile anime persist-records latency.",
    ),
}

DASHBOARDS: dict[str, tuple[str, str, list[str]]] = {
    "animemanager-overview": (
        "AnimeManager Overview",
        "Full-stack health across traces, runtime metrics, and browser telemetry.",
        [
            "am-request-volume",
            "am-latency-p95",
            "am-status-distribution",
            "am-operational-gauges",
            "am-download-lifecycle",
            "am-startup-failed",
            "am-client-errors",
            "am-web-vital-summary",
        ],
    ),
    "animemanager-http-apm": (
        "AnimeManager HTTP & APM Health",
        "Request throughput, status, latency, services, and route performance.",
        [
            "am-request-volume",
            "am-latency-p95",
            "am-status-distribution",
            "am-service-activity",
            "am-top-routes",
            "am-slowest-routes",
        ],
    ),
    "animemanager-client-ux": (
        "AnimeManager Client UX & Errors",
        "Browser errors, event dimensions, and Core Web Vitals.",
        [
            "am-client-errors",
            "am-web-vital-summary",
            "am-client-events",
            "am-client-error-paths",
            "am-client-error-names",
            "am-web-vital-trend",
        ],
    ),
    "animemanager-database": (
        "AnimeManager Database & Persistence Health",
        "DB commits, queries, upserts, write-queue errors, and upsert latency.",
        [
            "am-db-commits",
            "am-db-queries",
            "am-db-upserts",
            "am-db-write-errors",
            "am-db-upsert-latency",
        ],
    ),
    "animemanager-ingestion": (
        "AnimeManager Metadata Ingestion & Coordinator",
        "Ingestion throughput, provider failures, latency, and coordinator run gauges.",
        [
            "am-ingestion-records",
            "am-ingestion-failed-providers",
            "am-ingestion-latency",
            "am-coordinator-search",
            "am-coordinator-schedule-genre",
        ],
    ),
    "animemanager-startup": (
        "AnimeManager Startup Jobs",
        "Per-job duration, errors, commits, and overall startup success rate.",
        [
            "am-startup-total",
            "am-startup-jobs-bar",
            "am-startup-errors",
            "am-startup-commits",
            "am-startup-failed",
        ],
    ),
    "animemanager-playback": (
        "AnimeManager Playback & Transcoding",
        "Playback session volume, active sessions, create/segment latency, and FFmpeg spans.",
        [
            "am-playback-sessions",
            "am-playback-active",
            "am-playback-create-latency",
            "am-playback-segment-latency",
            "am-ffmpeg-started-failed",
            "am-playback-spans",
        ],
    ),
    "animemanager-downloads": (
        "AnimeManager Downloads & Torrents",
        "Download queue, active downloads, lifecycle, enqueue latency, and torrent operations.",
        [
            "am-download-queue",
            "am-download-active",
            "am-download-lifecycle",
            "am-download-enqueue-latency",
            "am-torrent-active",
            "am-torrent-ops",
        ],
    ),
    "animemanager-http-errors": (
        "AnimeManager HTTP Errors & Slow Requests",
        "Error trends by status and exception class, slow requests, and slow-request logs.",
        [
            "am-http-errors-trend",
            "am-http-errors-status",
            "am-http-errors-exception",
            "am-slow-requests",
            "am-slow-request-logs",
        ],
    ),
    "animemanager-catalog": (
        "AnimeManager Catalog & Anime Writes",
        "Catalog merge/identity/enrichment operations and anime write throughput by source.",
        [
            "am-catalog-ops",
            "am-anime-write-source",
            "am-anime-write-persisted",
            "am-anime-write-latency",
        ],
    ),
}


class KibanaClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "kbn-xsrf": "true",
        }

    def request(
        self, method: str, path: str, payload: object | None = None
    ) -> bytes:
        data = None if payload is None else json.dumps(payload).encode()
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers=self.headers,
        )
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(
                f"Kibana API {method} {path} failed ({exc.code}): {detail}"
            ) from exc

    def upsert(
        self,
        object_type: str,
        object_id: str,
        attributes: dict[str, Any],
        references: list[dict[str, str]] | None = None,
    ) -> None:
        path = (
            f"/api/saved_objects/{quote(object_type)}/{quote(object_id)}"
            "?overwrite=true"
        )
        self.request(
            "POST",
            path,
            {"attributes": attributes, "references": references or []},
        )


def _visualization_attributes(
    title: str, spec: dict[str, Any], description: str
) -> dict[str, Any]:
    vis_state = {
        "title": title,
        "type": "vega",
        "aggs": [],
        "params": {"spec": json.dumps(spec, separators=(",", ":"))},
    }
    return {
        "title": title,
        "description": description,
        "visState": json.dumps(vis_state, separators=(",", ":")),
        "uiStateJSON": "{}",
        "version": 1,
        "kibanaSavedObjectMeta": {
            "searchSourceJSON": json.dumps(
                {"query": {"query": "", "language": "kuery"}, "filter": []},
                separators=(",", ":"),
            )
        },
    }


def _dashboard_attributes(
    title: str, description: str, panel_ids: list[str]
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    panels: list[dict[str, Any]] = []
    references: list[dict[str, str]] = []
    for index, panel_id in enumerate(panel_ids):
        ref_name = f"panel_{index}"
        panels.append(
            {
                "version": "9.3.1",
                "type": "visualization",
                "gridData": {
                    "x": 0 if index % 2 == 0 else 24,
                    "y": (index // 2) * 13,
                    "w": 24,
                    "h": 13,
                    "i": panel_id,
                },
                "panelIndex": panel_id,
                "embeddableConfig": {},
                "panelRefName": ref_name,
            }
        )
        references.append(
            {"name": ref_name, "type": "visualization", "id": panel_id}
        )

    attributes = {
        "title": title,
        "description": description,
        "hits": 0,
        "panelsJSON": json.dumps(panels, separators=(",", ":")),
        "optionsJSON": json.dumps(
            {
                "useMargins": True,
                "syncColors": False,
                "syncCursor": True,
                "syncTooltips": True,
                "hidePanelTitles": False,
            },
            separators=(",", ":"),
        ),
        "timeRestore": True,
        "timeFrom": "now-24h",
        "timeTo": "now",
        "refreshInterval": {"pause": False, "value": 30000},
        "kibanaSavedObjectMeta": {
            "searchSourceJSON": json.dumps(
                {"query": {"query": "", "language": "kuery"}, "filter": []},
                separators=(",", ":"),
            )
        },
    }
    return attributes, references


_MIGRATION_VERSIONS = {
    "index-pattern": ("8.8.0", "8.0.0"),
    "visualization": ("8.8.0", "8.5.0"),
    "dashboard": ("8.8.0", "10.3.0"),
}


def _saved_object_line(
    object_type: str, object_id: str, attributes: dict[str, Any], references: list[dict[str, str]]
) -> str:
    core, type_migration = _MIGRATION_VERSIONS.get(object_type, ("8.8.0", "10.3.0"))
    record = {
        "attributes": attributes,
        "coreMigrationVersion": core,
        "id": object_id,
        "managed": False,
        "references": references,
        "type": object_type,
        "typeMigrationVersion": type_migration,
    }
    return json.dumps(record, separators=(",", ":"))


def build_offline(output_path: Path) -> None:
    """Write the NDJSON bundle directly from the in-memory definitions.

    Avoids a round-trip through Kibana's create-then-export API so the bundle
    can be regenerated in CI / on hosts without a reachable Kibana. The line
    format matches what ``GET /api/saved_objects/_export`` produces and is
    accepted by ``POST /api/saved_objects/_import``.
    """
    lines: list[str] = []
    for object_id, (title, spec, description) in VISUALIZATIONS.items():
        lines.append(
            _saved_object_line(
                "visualization",
                object_id,
                _visualization_attributes(title, spec, description),
                [],
            )
        )
    for object_id, (title, description, panels) in DASHBOARDS.items():
        attributes, references = _dashboard_attributes(title, description, panels)
        lines.append(_saved_object_line("dashboard", object_id, attributes, references))
    for object_id, (name, title) in DATA_VIEWS.items():
        lines.append(
            _saved_object_line(
                "index-pattern",
                object_id,
                {"title": title, "name": name, "timeFieldName": "@timestamp"},
                [],
            )
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"Wrote {len(DASHBOARDS)} dashboards, "
        f"{len(VISUALIZATIONS)} visualizations, and "
        f"{len(DATA_VIEWS)} data views to {output_path}"
    )


def build(client: KibanaClient, output_path: Path) -> None:
    for object_id, (name, title) in DATA_VIEWS.items():
        client.upsert(
            "index-pattern",
            object_id,
            {"title": title, "name": name, "timeFieldName": "@timestamp"},
        )

    for object_id, (title, spec, description) in VISUALIZATIONS.items():
        client.upsert(
            "visualization",
            object_id,
            _visualization_attributes(title, spec, description),
        )

    for object_id, (title, description, panels) in DASHBOARDS.items():
        attributes, references = _dashboard_attributes(title, description, panels)
        client.upsert("dashboard", object_id, attributes, references)

    export_objects = [
        *[
            {"type": "dashboard", "id": object_id}
            for object_id in DASHBOARDS
        ],
        *[
            {"type": "index-pattern", "id": object_id}
            for object_id in DATA_VIEWS
        ],
    ]
    bundle = client.request(
        "POST",
        "/api/saved_objects/_export",
        {
            "objects": export_objects,
            "includeReferencesDeep": True,
            "excludeExportDetails": True,
        },
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(bundle)
    print(
        f"Exported {len(DASHBOARDS)} dashboards, "
        f"{len(VISUALIZATIONS)} visualizations, and "
        f"{len(DATA_VIEWS)} data views to {output_path}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kibana-url", default="http://127.0.0.1:5601")
    parser.add_argument("--username", default="elastic")
    parser.add_argument("--password", default="elastic")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("animemanager.ndjson"),
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Write the NDJSON bundle directly without a running Kibana.",
    )
    args = parser.parse_args()
    if args.offline:
        build_offline(args.output)
        return
    build(
        KibanaClient(args.kibana_url, args.username, args.password),
        args.output,
    )


if __name__ == "__main__":
    main()
