"""Tests for domain catalogue helpers."""

from __future__ import annotations

import pytest

from domain.catalog import preferred_catalog_id, preferred_catalog_id_from


def test_preferred_catalog_id_picks_smallest_positive():
    assert preferred_catalog_id(-1426116332, 2808, 5000) == 2808
    assert preferred_catalog_id_from([-99, 1, 2]) == 1


def test_preferred_catalog_id_falls_back_to_smallest_when_all_negative():
    assert preferred_catalog_id(-3, -1, -9) == -9


def test_preferred_catalog_id_requires_ids():
    with pytest.raises(ValueError):
        preferred_catalog_id()
