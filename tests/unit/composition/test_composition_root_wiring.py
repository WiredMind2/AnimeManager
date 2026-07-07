"""Composition root wiring tests."""

from __future__ import annotations


def test_build_embedded_facade_wires_ports_without_legacy_runtime():
    from composition.root import build_embedded_facade

    facade = build_embedded_facade()
    service = facade._service  # type: ignore[attr-defined]

    assert service._anime_repository is not None
    assert service._metadata_provider is not None
    assert service._download_port is not None
    assert service._user_actions_port is not None
    assert facade.startup_jobs is not None

    assert type(service._anime_repository).__name__ == "AnimeRepositoryAdapter"
    assert type(service._user_actions_port).__name__ == "UserActionsRepository"
    assert type(service._download_port).__name__ == "DownloadAdapter"
    assert type(service._metadata_provider).__name__ == "ApiCoordinatorAdapter"
