"""Tests for top-by-popularity domain policies."""

from __future__ import annotations

import pytest

from domain.errors import ValidationError
from domain.policies.top import (
    TOP_CATEGORIES,
    format_top_label,
    local_status_for,
    normalize_top_category,
)


def test_normalize_top_category_accepts_known_values():
    assert normalize_top_category("All") == "all"
    assert normalize_top_category(" AIRING ") == "airing"
    assert normalize_top_category("upcoming") == "upcoming"


def test_normalize_top_category_rejects_unknown():
    with pytest.raises(ValidationError):
        normalize_top_category("movie")


def test_local_status_for_maps_seedable_categories():
    assert local_status_for("all") is None
    assert local_status_for("airing") == "AIRING"
    assert local_status_for("upcoming") == "UPCOMING"


def test_format_top_label():
    assert format_top_label("airing") == "Airing"
    assert format_top_label("all") == "All"


def test_top_categories_registry():
    assert TOP_CATEGORIES == frozenset({"all", "airing", "upcoming"})
