"""Adapters layer.

Concrete IO / framework integrations live under this package. The
composition root is the only place allowed to import individual
adapter subpackages and wire them into ports.

This package is the **canonical** home of the integration adapters.
``adapters.legacy`` holds the bridge between the legacy
``classes``/``getters``/``components`` graph and the new port
protocols. Sibling subpackages (``adapters.api``,
``adapters.persistence``, ``adapters.torrent``, ``adapters.file``,
``adapters.media``, ``adapters.search``) re-export or directly hold
the canonical integration code.
"""

from __future__ import annotations

__all__ = [
    "LegacyRuntime",
    "LegacyAnimeRepositoryAdapter",
    "LegacyMetadataProviderAdapter",
    "LegacyDownloadAdapter",
    "LegacyUserActionsAdapter",
]


def __getattr__(name: str):  # PEP 562
    if name in __all__:
        from adapters.legacy.runtime import (
            LegacyAnimeRepositoryAdapter,
            LegacyDownloadAdapter,
            LegacyMetadataProviderAdapter,
            LegacyRuntime,
            LegacyUserActionsAdapter,
        )

        mapping = {
            "LegacyRuntime": LegacyRuntime,
            "LegacyAnimeRepositoryAdapter": LegacyAnimeRepositoryAdapter,
            "LegacyMetadataProviderAdapter": LegacyMetadataProviderAdapter,
            "LegacyDownloadAdapter": LegacyDownloadAdapter,
            "LegacyUserActionsAdapter": LegacyUserActionsAdapter,
        }
        value = mapping[name]
        globals()[name] = value
        return value
    raise AttributeError(name)
