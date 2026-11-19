"""Atheris harness scaffolded by ClusterFuzz (AST fallback)."""
import sys
from pathlib import Path

import atheris

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from application.services.catalog_enrichment import select_single_provider_ids_for_enrichment, lookup_cross_ids, expand_external_ids_with_mapping  # noqa: E402


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    try:
        select_single_provider_ids_for_enrichment(fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)))
    except Exception:
        pass
    try:
        lookup_cross_ids(fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)), fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)), fdp.ConsumeIntInRange(-10**6, 10**6))
    except Exception:
        pass
    try:
        expand_external_ids_with_mapping(fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)), fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)))
    except Exception:
        pass


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
