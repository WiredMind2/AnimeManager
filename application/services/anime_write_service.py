"""Centralized application-layer gateway for anime persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Sequence

from shared.contracts import AnimeRecord
from shared.telemetry import get_telemetry


class WriteSource(str, Enum):
    SEARCH = "search"
    STREAM = "stream"
    SCHEDULE = "schedule"
    SEASON = "season"
    GENRE = "genre"
    HYDRATION = "hydration"
    BACKFILL = "backfill"
    REPAIR = "repair"


@dataclass(frozen=True)
class PersistResult:
    persisted: int = 0
    metadata_keys_written: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _PersistableAnime:
    id: int
    data: dict[str, Any]
    metadata: dict[str, list[str]]

    def save_format(self):
        payload = dict(self.data)
        payload["id"] = self.id
        return payload, dict(self.metadata)


class AnimeWriteService:
    """Gateway that converts records and writes through ``DatabaseManager``."""

    def __init__(
        self,
        *,
        db_manager,
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._db_manager = db_manager
        self._log = log_fn
        self._telemetry = get_telemetry()

    def persist_records(
        self,
        records: Sequence[AnimeRecord],
        *,
        source: WriteSource,
    ) -> PersistResult:
        if not records:
            return PersistResult()

        metadata_counts = {"title_synonyms": 0, "genres": 0}
        animes = []
        for record in records:
            if record.title_synonyms:
                metadata_counts["title_synonyms"] += 1
            if record.genres:
                metadata_counts["genres"] += 1
            animes.append(self._record_to_anime(record))

        try:
            with self._telemetry.time("anime_write.persist_records_ms"):
                persisted = int(self._db_manager.upsert_anime_batch(animes))
            self._telemetry.increment(f"anime_write.source.{source.value}", persisted)
            self._telemetry.increment("anime_write.persisted", persisted)
            return PersistResult(
                persisted=persisted,
                metadata_keys_written=metadata_counts,
            )
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            self._telemetry.increment("anime_write.errors")
            if self._log:
                self._log(
                    f"persist_records failed for source={source.value}: {message}"
                )
            return PersistResult(
                persisted=0,
                metadata_keys_written=metadata_counts,
                errors=[message],
            )

    def persist_legacy_anime(
        self,
        anime,
        *,
        source: WriteSource,
        catalog_id: Optional[int] = None,
        external_ids: Optional[dict[str, int]] = None,
    ) -> bool:
        record = self._legacy_anime_to_record(
            anime,
            catalog_id=catalog_id,
            external_ids=external_ids,
        )
        if record is None:
            return False
        result = self.persist_records([record], source=source)
        return result.persisted > 0 and not result.errors

    @staticmethod
    def _record_to_anime(record: AnimeRecord) -> _PersistableAnime:
        data: dict[str, Any] = {}
        for key in (
            "title",
            "synopsis",
            "episodes",
            "duration",
            "status",
            "rating",
            "date_from",
            "date_to",
            "picture",
            "trailer",
            "broadcast",
        ):
            value = getattr(record, key)
            if value is not None:
                data[key] = value

        metadata: dict[str, list[str]] = {}
        if record.title_synonyms:
            metadata["title_synonyms"] = list(record.title_synonyms)
        if record.genres:
            metadata["genres"] = list(record.genres)

        return _PersistableAnime(id=int(record.id), data=data, metadata=metadata)

    @staticmethod
    def _legacy_anime_to_record(
        anime: Any,
        *,
        catalog_id: Optional[int] = None,
        external_ids: Optional[dict[str, int]] = None,
    ) -> Optional[AnimeRecord]:
        getter = anime.get if isinstance(anime, dict) else None

        def _field(name: str) -> Any:
            if getter is not None:
                return getter(name)
            return getattr(anime, name, None)

        rid = catalog_id if catalog_id is not None else _field("id")
        try:
            rid = int(rid)
        except (TypeError, ValueError):
            return None

        normalized_external = {}
        for key, value in (external_ids or {}).items():
            if value is None:
                continue
            try:
                normalized_external[str(key)] = int(value)
            except (TypeError, ValueError):
                continue

        def _safe_int(value: Any) -> Optional[int]:
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        def _safe_str(value: Any) -> Optional[str]:
            if value is None:
                return None
            text = str(value).strip()
            return text or None

        def _tupled(value: Any) -> tuple[str, ...]:
            if not value:
                return ()
            if isinstance(value, (list, tuple, set)):
                return tuple(str(item) for item in value if item)
            return (str(value),)

        return AnimeRecord(
            id=rid,
            title=str(_field("title") or ""),
            title_synonyms=_tupled(_field("title_synonyms")),
            synopsis=_safe_str(_field("synopsis")),
            episodes=_safe_int(_field("episodes")),
            duration=_safe_int(_field("duration")),
            status=_safe_str(_field("status")),
            rating=_safe_str(_field("rating")),
            date_from=_safe_int(_field("date_from")),
            date_to=_safe_int(_field("date_to")),
            picture=_safe_str(_field("picture")),
            trailer=_safe_str(_field("trailer")),
            broadcast=_safe_str(_field("broadcast")),
            genres=_tupled(_field("genres")),
            external_ids=normalized_external,
        )


__all__ = ["AnimeWriteService", "PersistResult", "WriteSource"]
