"""Atheris harness scaffolded by ClusterFuzz (AST fallback)."""
import sys
from pathlib import Path

import atheris

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from application.services.player_session_log import append, append_client_batch, player_log_path  # noqa: E402


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    try:
        append(fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)))
    except Exception:
        pass
    try:
        append_client_batch(fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)), fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)))
    except Exception:
        pass
    try:
        player_log_path(fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)))
    except Exception:
        pass


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
