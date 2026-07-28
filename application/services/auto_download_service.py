"""Periodic auto-download of the next episode for WATCHING anime."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from application.services.auto_download_matching import (
    ReleasePreference,
    find_matching_candidate,
    indexed_hashes,
    infer_preference,
    next_episode,
    owned_episodes_from_files,
    owned_episodes_from_torrents,
)
from application.services.auto_download_prefs import (
    DEFAULT_SOURCE_MODE,
    normalize_prefs_row,
    resolve_release_preference,
    select_feeds_for_anime,
)

_LOG = logging.getLogger("animemanager.auto_download")


@dataclass
class AutoDownloadOutcome:
    """Summary of one ``run_once`` pass."""

    checked: int = 0
    downloaded: int = 0
    skipped: int = 0
    errors: int = 0
    details: list[str] = field(default_factory=list)


class AutoDownloadService:
    """Find and queue the next matching episode torrent for eligible anime."""

    DEFAULT_USER_ID = 1
    COOLDOWN_S = 30 * 60

    def __init__(
        self,
        *,
        user_actions: Any,
        anime_repository: Any,
        download_port: Any,
        media_library: Any | None = None,
        parse_title: Callable[[str], Any],
        user_id: int = DEFAULT_USER_ID,
        log_fn: Callable[[str], None] | None = None,
        cooldown_s: float = COOLDOWN_S,
        settings_provider: Callable[[], Mapping[str, Any]] | None = None,
        feed_fetcher: Any | None = None,
        rss_match_fn: Callable[..., Optional[dict[str, Any]]] | None = None,
    ) -> None:
        self._user_actions = user_actions
        self._anime_repository = anime_repository
        self._download_port = download_port
        self._media_library = media_library
        self._parse_title = parse_title
        self._user_id = int(user_id)
        self._log_fn = log_fn
        self._cooldown_s = float(cooldown_s)
        self._settings_provider = settings_provider
        self._feed_fetcher = feed_fetcher
        self._rss_match_fn = rss_match_fn
        self._last_check: dict[int, float] = {}

    def _log(self, message: str) -> None:
        if self._log_fn is not None:
            try:
                self._log_fn(message)
                return
            except Exception:  # noqa: BLE001
                pass
        _LOG.info(message)

    def _settings(self) -> Mapping[str, Any]:
        if self._settings_provider is None:
            return {}
        try:
            data = self._settings_provider()
        except Exception:  # noqa: BLE001
            return {}
        return data if isinstance(data, Mapping) else {}

    def global_enabled(self) -> bool:
        auto_cfg = self._settings().get("auto_download") or {}
        if not isinstance(auto_cfg, Mapping):
            return True
        return bool(auto_cfg.get("enabled", True))

    def list_eligible_anime(self) -> list[int]:
        lister = getattr(self._user_actions, "list_auto_download_eligible", None)
        if callable(lister):
            try:
                return [int(x) for x in (lister(self._user_id) or [])]
            except Exception as exc:  # noqa: BLE001
                self._log(f"list_auto_download_eligible failed: {exc}")
                return []
        list_tag = getattr(self._user_actions, "list_anime_ids_with_tag", None)
        if not callable(list_tag):
            return []
        try:
            watching = list(list_tag("WATCHING") or [])
        except Exception:  # noqa: BLE001
            return []
        out: list[int] = []
        for anime_id in watching:
            try:
                state = self._user_actions.get_user_state(int(anime_id), self._user_id)
            except Exception:  # noqa: BLE001
                continue
            if str(state.get("tag") or "").upper() != "WATCHING":
                continue
            if not bool(state.get("auto_download")):
                continue
            out.append(int(anime_id))
        return out

    def _library_torrents(self, anime_id: int) -> list[dict[str, Any]]:
        getter = getattr(self._anime_repository, "get_anime_torrents", None)
        if not callable(getter):
            return []
        try:
            rows = list(getter(anime_id) or [])
        except Exception:  # noqa: BLE001
            return []
        return [row for row in rows if isinstance(row, dict)]

    def _disk_episodes(self, anime_id: int) -> list[dict[str, Any]]:
        library = self._media_library
        if library is None:
            return []
        lister = getattr(library, "list_episode_files", None)
        if not callable(lister):
            return []
        try:
            rows = list(lister(anime_id) or [])
        except Exception:  # noqa: BLE001
            return []
        return [row for row in rows if isinstance(row, dict)]

    def get_download_preferences(self, anime_id: int) -> dict[str, Any]:
        getter = getattr(self._user_actions, "get_download_preferences", None)
        raw: dict[str, Any] = {}
        if callable(getter):
            try:
                loaded = getter(anime_id, self._user_id) or {}
                if isinstance(loaded, dict):
                    raw = loaded
            except Exception as exc:  # noqa: BLE001
                self._log(f"anime {anime_id}: load prefs failed: {exc}")
        return normalize_prefs_row(raw, settings=self._settings())

    def infer_preference(self, anime_id: int) -> Optional[ReleasePreference]:
        return infer_preference(
            self._library_torrents(anime_id),
            parse_title=self._parse_title,
        )

    def resolve_preference(self, anime_id: int) -> Optional[ReleasePreference]:
        prefs = self.get_download_preferences(anime_id)
        inferred = self.infer_preference(anime_id) if prefs.get("use_inferred") else None
        return resolve_release_preference(
            prefs,
            inferred=inferred,
            settings=self._settings(),
        )

    def owned_episodes(self, anime_id: int) -> set[int]:
        torrents = self._library_torrents(anime_id)
        owned = owned_episodes_from_torrents(torrents, parse_title=self._parse_title)
        owned |= owned_episodes_from_files(self._disk_episodes(anime_id))
        return owned

    def _search_terms(self, anime_id: int) -> list[str]:
        getter = getattr(self._anime_repository, "get_search_terms", None)
        if not callable(getter):
            return []
        try:
            terms = list(getter(anime_id) or [])
        except Exception:  # noqa: BLE001
            return []
        return [str(t).strip() for t in terms if str(t).strip()]

    def find_candidate(
        self,
        anime_id: int,
        preference: ReleasePreference,
        episode: int,
    ) -> Optional[dict[str, Any]]:
        terms = self._search_terms(anime_id)
        if not terms:
            self._log(f"anime {anime_id}: no search terms")
            return None
        try:
            results = list(
                self._download_port.search_torrents(
                    terms,
                    profile="interactive",
                    limit=50,
                    allow_nsfw=False,
                )
                or []
            )
        except TypeError:
            try:
                results = list(self._download_port.search_torrents(terms) or [])
            except Exception as exc:  # noqa: BLE001
                self._log(f"anime {anime_id}: search failed: {exc}")
                return None
        except Exception as exc:  # noqa: BLE001
            self._log(f"anime {anime_id}: search failed: {exc}")
            return None
        exclude = indexed_hashes(self._library_torrents(anime_id))
        return find_matching_candidate(
            results,
            preference=preference,
            episode=episode,
            exclude_hashes=exclude,
        )

    def find_rss_candidate(
        self,
        anime_id: int,
        preference: ReleasePreference,
        episode: int,
        prefs: Mapping[str, Any],
    ) -> Optional[dict[str, Any]]:
        if self._feed_fetcher is None or self._rss_match_fn is None:
            self._log(f"anime {anime_id}: RSS mode unavailable")
            return None
        terms = self._search_terms(anime_id)
        if not terms:
            self._log(f"anime {anime_id}: no search terms")
            return None
        feeds = select_feeds_for_anime(self._settings(), prefs.get("feed_ids") or [])
        if not feeds:
            self._log(f"anime {anime_id}: no enabled RSS feeds")
            return None
        try:
            entries = list(self._feed_fetcher.fetch_many(feeds) or [])
        except Exception as exc:  # noqa: BLE001
            self._log(f"anime {anime_id}: RSS fetch failed: {exc}")
            return None
        seen: set[tuple[str, str]] = set()
        lister = getattr(self._user_actions, "list_rss_feed_seen_keys", None)
        if callable(lister):
            try:
                seen = set(lister([str(f["id"]) for f in feeds]) or set())
            except Exception as exc:  # noqa: BLE001
                self._log(f"anime {anime_id}: load seen RSS keys failed: {exc}")
        return self._rss_match_fn(
            entries,
            search_terms=terms,
            preference=preference,
            episode=episode,
            parse_title=self._parse_title,
            seen_keys=seen,
        )

    def _candidate_url(self, candidate: Mapping[str, Any]) -> Optional[str]:
        for key in ("link", "magnet", "url", "desc_link"):
            value = candidate.get(key)
            if value:
                text = str(value).strip()
                if text:
                    return text
        return None

    def _candidate_hash(self, candidate: Mapping[str, Any]) -> Optional[str]:
        for key in ("infohash", "hash"):
            value = candidate.get(key)
            if value:
                text = str(value).strip()
                if text:
                    return text
        return None

    def _start_auto_download(
        self, anime_id: int, candidate: dict[str, Any]
    ) -> bool:
        url = self._candidate_url(candidate)
        hash_value = self._candidate_hash(candidate)
        if not url and not hash_value:
            return False
        start = getattr(self._download_port, "start_download", None)
        if not callable(start):
            return False
        try:
            result = start(
                anime_id,
                url=url,
                hash_value=hash_value,
                user_id=self._user_id,
                source="auto",
            )
            if isinstance(result, dict):
                return bool(result.get("started"))
            return bool(result)
        except TypeError:
            try:
                result = start(
                    anime_id,
                    url=url,
                    hash_value=hash_value,
                    user_id=self._user_id,
                )
                if isinstance(result, dict):
                    return bool(result.get("started"))
                return bool(result)
            except Exception as exc:  # noqa: BLE001
                self._log(f"anime {anime_id}: start_download failed: {exc}")
                return False
        except Exception as exc:  # noqa: BLE001
            self._log(f"anime {anime_id}: start_download failed: {exc}")
            return False

    def _mark_rss_seen(self, candidate: Mapping[str, Any]) -> None:
        marker = getattr(self._user_actions, "mark_rss_feed_seen", None)
        if not callable(marker):
            return
        feed_id = candidate.get("feed_id")
        item_key = candidate.get("item_key")
        if not feed_id or not item_key:
            return
        try:
            marker(str(feed_id), str(item_key))
        except Exception as exc:  # noqa: BLE001
            self._log(f"mark RSS seen failed: {exc}")

    def _under_cooldown(self, anime_id: int, now: float) -> bool:
        last = self._last_check.get(anime_id)
        if last is None:
            return False
        settings = self._settings().get("auto_download") or {}
        cooldown = self._cooldown_s
        if isinstance(settings, Mapping) and "cooldown_minutes" in settings:
            try:
                cooldown = max(0.0, float(settings.get("cooldown_minutes")) * 60.0)
            except (TypeError, ValueError):
                cooldown = self._cooldown_s
        return (now - last) < cooldown

    def process_anime(self, anime_id: int) -> str:
        """Check one anime and optionally queue a download. Returns a status detail."""
        prefs = self.get_download_preferences(anime_id)
        preference = self.resolve_preference(anime_id)
        if preference is None:
            return "skipped (no preference)"
        owned = self.owned_episodes(anime_id)
        episode = next_episode(owned)
        if episode is None:
            return "skipped (no owned episodes)"
        mode = str(prefs.get("source_mode") or DEFAULT_SOURCE_MODE).lower()
        if mode == "rss":
            candidate = self.find_rss_candidate(anime_id, preference, episode, prefs)
        else:
            candidate = self.find_candidate(anime_id, preference, episode)
        if candidate is None:
            return f"skipped (no match for ep {episode})"
        if self._start_auto_download(anime_id, candidate):
            if mode == "rss":
                self._mark_rss_seen(candidate)
            name = str(candidate.get("name") or candidate.get("infohash") or "torrent")
            return f"queued ep {episode}: {name}"
        return f"failed to queue ep {episode}"

    def run_once(self, *, force: bool = False) -> AutoDownloadOutcome:
        """Process every eligible anime once."""
        outcome = AutoDownloadOutcome()
        if not self.global_enabled():
            outcome.details.append("global auto-download disabled")
            return outcome
        now = time.time()
        for anime_id in self.list_eligible_anime():
            outcome.checked += 1
            if not force and self._under_cooldown(anime_id, now):
                outcome.skipped += 1
                outcome.details.append(f"{anime_id}: cooldown")
                continue
            try:
                detail = self.process_anime(anime_id)
                self._last_check[anime_id] = now
                if detail.startswith("queued"):
                    outcome.downloaded += 1
                else:
                    outcome.skipped += 1
                outcome.details.append(f"{anime_id}: {detail}")
                self._log(f"anime {anime_id}: {detail}")
            except Exception as exc:  # noqa: BLE001
                outcome.errors += 1
                msg = f"{type(exc).__name__}: {exc}"
                outcome.details.append(f"{anime_id}: error {msg}")
                self._log(f"anime {anime_id}: error {msg}")
        return outcome
