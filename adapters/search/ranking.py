"""Result ranking utilities.

Streaming consumers (the GUI) get results in arrival order so the UI can
populate progressively. Batch consumers (the REST API) want deterministic,
sorted output. The helpers in this module implement that ordering without
mutating producer code paths.
"""

from __future__ import annotations

from typing import Iterable, List

from .parser import TorrentResult


def sort_results(results: Iterable[TorrentResult]) -> List[TorrentResult]:
    """Return ``results`` sorted by (seeds desc, size desc, name asc).

    The ordering is stable for ties on all three keys and is unaffected by
    the order in which engines produced results, which makes API responses
    reproducible for golden tests.
    """
    return sorted(
        results,
        key=lambda r: (-r.seeds, -r.size, r.name.casefold(), r.engine_url),
    )
