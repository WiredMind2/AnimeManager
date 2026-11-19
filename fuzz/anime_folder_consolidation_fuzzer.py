"""Atheris harness scaffolded by ClusterFuzz (AST fallback)."""
import sys
from pathlib import Path

import atheris

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from application.services.anime_folder_consolidation import consolidate_duplicate_folders_for_anime, consolidate_all_duplicate_anime_folders  # noqa: E402


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    try:
        consolidate_duplicate_folders_for_anime(fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)), fdp.ConsumeIntInRange(-10**6, 10**6))
    except Exception:
        pass
    try:
        consolidate_all_duplicate_anime_folders(fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)))
    except Exception:
        pass


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
