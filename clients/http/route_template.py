"""Normalize request paths to route templates for telemetry aggregation."""

from __future__ import annotations

import re

from starlette.requests import Request

_NUMERIC_SEGMENT = re.compile(r"^(\d+|[0-9a-f]{32})$", re.IGNORECASE)
_UUID_SEGMENT = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def route_template_for_request(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return str(route.path)
    return normalize_path_template(request.url.path)


def normalize_path_template(path: str) -> str:
    raw = str(path or "").strip()
    if not raw:
        return "/"
    parts = [part for part in raw.split("/") if part]
    normalized: list[str] = []
    for part in parts:
        if _UUID_SEGMENT.match(part):
            normalized.append("{id}")
        elif _NUMERIC_SEGMENT.match(part):
            normalized.append("{id}")
        elif part.startswith("segment_") and part.endswith(".ts"):
            normalized.append("{segment}")
        else:
            normalized.append(part)
    return "/" + "/".join(normalized)


def route_metric_key(method: str, route_template: str) -> str:
    safe = (
        route_template.strip("/")
        .replace("/", ".")
        .replace("{", "")
        .replace("}", "")
        or "root"
    )
    return f"http.route_ms.{method.lower()}.{safe}".lower()
