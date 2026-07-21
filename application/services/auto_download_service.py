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
    ) -> None:
        self._user_actions = user_actions
        self._anime_repository = anime_repository
        self._download_port = download_port
        self._media_library = media_library
        self._parse_title = parse_title
        self._user_id = int(user_id)
        self._log_fn = log_fn
        self._cooldown_s = float(cooldown_s)
        self._last_check: dict[int, float] = {}

    def _log(self, message: str) -> None:
        if self._log_fn is not None:
            try:
                self._log_fn(message)
                return
            except Exception:  # noqa: BLE001
                pass
        _LOG.info(message)

    def list_eligible_anime(self) -> list[int]:
        lister = getattr(self._user_actions, "list_auto_download_eligible", None)
        if callable(lister):
            try:
                return [int(x) for x in (lister(self._user_id) or [])]
            except Exception as exc:  # noqa: BLE001
                self._log(f"list_auto_download_eligible failed: {exc}")
                return []
        # Fallback: WATCHING ∩ per-anime state.auto_download
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

    def infer_preference(self, anime_id: int) -> Optional[ReleasePreference]:
        return infer_preference(
            self._library_torrents(anime_id),
            parse_title=self._parse_title,
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
            # Older ports may not accept profile/limit kwargs.
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
            return bool(
                start(
                    anime_id,
                    url=url,
                    hash_value=hash_value,
                    user_id=self._user_id,
                    source="auto",
                )
            )
        except TypeError:
            # Port without source kwarg — still queue; source may be lost.
            try:
                return bool(
                    start(
                        anime_id,
                        url=url,
                        hash_value=hash_value,
                        user_id=self._user_id,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                self._log(f"anime {anime_id}: start_download failed: {exc}")
                return False
        except Exception as exc:  # noqa: BLE001
            self._log(f"anime {anime_id}: start_download failed: {exc}")
            return False

    def _under_cooldown(self, anime_id: int, now: float) -> bool:
        last = self._last_check.get(anime_id)
        if last is None:
            return False
        return (now - last) < self._cooldown_s

    def process_anime(self, anime_id: int) -> str:
        """Check one anime and optionally queue a download. Returns a status detail."""
        preference = self.infer_preference(anime_id)
        if preference is None:
            return "skipped (no preference)"
        owned = self.owned_episodes(anime_id)
        episode = next_episode(owned)
        if episode is None:
            return "skipped (no owned episodes)"
        candidate = self.find_candidate(anime_id, preference, episode)
        if candidate is None:
            return f"skipped (no match for ep {episode})"
        if self._start_auto_download(anime_id, candidate):
            name = str(candidate.get("name") or candidate.get("infohash") or "torrent")
            return f"queued ep {episode}: {name}"
        return f"failed to queue ep {episode}"

    def run_once(self, *, force: bool = False) -> AutoDownloadOutcome:
        """Process every eligible anime once."""
        outcome = AutoDownloadOutcome()
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
