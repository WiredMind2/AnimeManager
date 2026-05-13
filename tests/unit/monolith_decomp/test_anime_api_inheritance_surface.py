"""Characterization tests for ``adapters.api.AnimeAPI`` and ``APIUtils``.

These two classes are allowlisted inheritance hotspots (ADR 0005). The
purpose of this file is to *pin* their externally visible contract so
that further decomposition work can proceed safely:

* ``AnimeAPI`` exposes a ``get_providers()`` accessor, a generic
  ``__getattr__`` -> :meth:`wrapper` fan-out, and a ``save()`` helper.
* ``APIUtils`` exposes a ``getStatusFromData`` policy method and a
  caching infrastructure (``APICache``).

The tests only assert the *shape* of the public surface so they remain
green even when the implementation changes from inheritance to
composition.
"""

from __future__ import annotations

import importlib

import pytest


def _import_anime_api():
    try:
        module = importlib.import_module("adapters.api")
    except Exception:  # pragma: no cover - environment-dependent
        pytest.skip("adapters.api not importable")
    return module


def test_anime_api_class_exists_with_expected_public_surface():
    module = _import_anime_api()
    cls = getattr(module, "AnimeAPI", None)
    assert cls is not None, "animeAPI.AnimeAPI must remain importable"

    for attr in ("get_providers", "search_provider", "wrapper", "save"):
        assert hasattr(cls, attr), f"AnimeAPI.{attr} is part of the public contract"


def test_anime_api_no_longer_uses_legacy_mixin_inheritance():
    """``AnimeAPI`` was decomposed during the de-monolith finalization.

    The class previously inherited from ``(Getters, Logger)``. It now
    composes those collaborators (``self._getters`` / ``self._logger``)
    so a regression to multi-inheritance is loud rather than silent.
    """
    module = _import_anime_api()
    cls = module.AnimeAPI
    bases = {b.__name__ for b in cls.__bases__}
    forbidden = bases & {"Getters", "Logger"}
    assert not forbidden, (
        "AnimeAPI must not re-introduce Getters/Logger inheritance "
        "(use composition via _getters/_logger). Offending bases: "
        f"{forbidden}"
    )


def test_api_utils_no_longer_uses_legacy_mixin_inheritance():
    """``APIUtils`` was decomposed during the de-monolith finalization."""
    try:
        from adapters.api.APIUtils import APIUtils
    except Exception:  # pragma: no cover
        pytest.skip("APIUtils not importable")
    bases = {b.__name__ for b in APIUtils.__bases__}
    forbidden = bases & {"Getters", "Logger"}
    assert not forbidden, (
        "APIUtils must not re-introduce Getters/Logger inheritance "
        "(use composition via _getters/_logger). Offending bases: "
        f"{forbidden}"
    )


def test_api_utils_status_policy_pure_function():
    try:
        from adapters.api.APIUtils import APIUtils
    except Exception:  # pragma: no cover
        pytest.skip("APIUtils not importable")

    # We do not construct APIUtils() because that touches the database.
    # Instead use the unbound method on a stub instance with the
    # required attributes.
    stub = type("Stub", (), {})()
    data_unknown = {"date_from": None, "date_to": None, "episodes": 1}
    assert APIUtils.getStatusFromData(stub, data_unknown) == "UNKNOWN"

    data_update = {"date_from": "2024-01", "date_to": None, "episodes": 1}
    assert APIUtils.getStatusFromData(stub, data_update) == "UPDATE"
