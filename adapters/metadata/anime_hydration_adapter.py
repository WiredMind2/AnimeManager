"""Adapter that hydrates orphan catalogue rows via legacy provider APIs."""

from __future__ import annotations

from typing import Any, Callable, Optional

from application.services.anime_write_service import WriteSource
from ports.interfaces import AnimeHydrationPort


class AnimeHydrationAdapter:
    """Implements :class:`ports.interfaces.AnimeHydrationPort`."""

    def __init__(
        self,
        api: Any,
        database: Any,
        *,
        write_service: Any = None,
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._api = api
        self._db = database
        self._write_service = write_service
        self._log = log_fn

    def catalog_id_exists(self, catalog_id: int) -> bool:
        try:
            rows = self._db.sql(
                "SELECT 1 FROM indexList WHERE id=?",
                (int(catalog_id),),
            )
        except Exception:
            return False
        return bool(rows)

    def hydrate_anime(self, catalog_id: int) -> bool:
        catalog_id = int(catalog_id)
        try:
            result = self._api.anime(catalog_id, _persist=False)
        except Exception as exc:
            if self._log:
                self._log(f"hydrate_anime({catalog_id}) failed: {exc}")
            return False

        title = self._extract_title(result)
        if not title:
            if self._log:
                self._log(f"hydrate_anime({catalog_id}) returned no title")
            return False

        write_service = self._write_service
        if write_service is None:
            return True
        persisted = write_service.persist_legacy_anime(
            result,
            source=WriteSource.HYDRATION,
            catalog_id=catalog_id,
        )
        if not persisted and self._log:
            self._log(f"hydrate_anime({catalog_id}) did not persist")
        return bool(persisted)

    @staticmethod
    def _extract_title(result: Any) -> str:
        if result is None:
            return ""
        if isinstance(result, dict):
            return str(result.get("title") or "").strip()
        getter = getattr(result, "get", None)
        if callable(getter):
            return str(getter("title") or "").strip()
        title = getattr(result, "title", None)
        return str(title or "").strip()
