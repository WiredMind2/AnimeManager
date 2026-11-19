"""Atheris harness scaffolded by ClusterFuzz (AST fallback)."""
import sys
from pathlib import Path

import atheris

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from application.services.auto_download_matching import infer_preference, owned_episodes_from_torrents, owned_episodes_from_files, next_episode  # noqa: E402


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    try:
        infer_preference(fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)))
    except Exception:
        pass
    try:
        owned_episodes_from_torrents(fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)))
    except Exception:
        pass
    try:
        owned_episodes_from_files(fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)))
    except Exception:
        pass
    try:
        next_episode(fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)))
    except Exception:
        pass


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
