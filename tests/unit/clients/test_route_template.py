"""Tests for HTTP route template normalization."""

from __future__ import annotations

from clients.http.route_template import normalize_path_template, route_metric_key


def test_normalize_path_template_replaces_numeric_ids():
    assert normalize_path_template("/anime/2215/episode-files") == "/anime/{id}/episode-files"


def test_normalize_path_template_replaces_stream_segments():
    session_id = "d31b19041cc04620988a930a2bfc3a5a"
    assert (
        normalize_path_template(f"/ui/stream/{session_id}/segment_00022.ts")
        == "/ui/stream/{id}/{segment}"
    )


def test_route_metric_key_is_stable():
    assert route_metric_key("GET", "/anime/{anime_id}") == "http.route_ms.get.anime.anime_id"
