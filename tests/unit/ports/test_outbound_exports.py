"""Smoke tests for ``ports.outbound`` re-exports."""

from __future__ import annotations

import ports.interfaces as canonical
import ports.outbound as outbound


def test_outbound_reexports_match_canonical_interfaces():
    assert outbound.AnimeRepositoryPort is canonical.AnimeRepositoryPort
    assert outbound.DownloadPort is canonical.DownloadPort
    assert outbound.MetadataProviderPort is canonical.MetadataProviderPort
    assert outbound.UserActionsPort is canonical.UserActionsPort
