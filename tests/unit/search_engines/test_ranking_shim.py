"""Tests for the ``search_engines.ranking`` compatibility shim."""

from __future__ import annotations

import importlib
import warnings

def test_ranking_shim_warns_on_reload():
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always", category=DeprecationWarning)
        import search_engines.ranking as ranking_mod

        importlib.reload(ranking_mod)
    assert any("compatibility shim" in str(w.message) for w in recorded)
    assert any(issubclass(w.category, DeprecationWarning) for w in recorded)
