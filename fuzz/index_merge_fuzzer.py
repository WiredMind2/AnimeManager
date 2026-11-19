"""Atheris harness scaffolded by ClusterFuzz (AST fallback)."""
import sys
from pathlib import Path

import atheris

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from application.services.index_merge import merge_anime_index_rows, repair_duplicate_index_entries  # noqa: E402


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    try:
        merge_anime_index_rows(fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)))
    except Exception:
        pass
    try:
        repair_duplicate_index_entries(fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)))
    except Exception:
        pass


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
