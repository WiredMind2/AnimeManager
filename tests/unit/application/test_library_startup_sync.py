"""Tests for :class:`LibraryStartupSyncService`."""

from __future__ import annotations

from pathlib import Path

from application.services.library_startup_sync import LibraryStartupSyncService


class _FakeUserActions:
    def __init__(self) -> None:
        self.tags: dict[tuple[int, int], str] = {}
        self.cleared: list[tuple[int, int]] = []

    def get_user_state(self, anime_id: int, user_id: int) -> dict:
        tag = self.tags.get((anime_id, user_id), "NONE")
        return {"tag": tag, "liked": False}

    def set_tag(self, anime_id: int, tag: str, user_id: int) -> None:
        self.tags[(anime_id, user_id)] = tag

    def list_anime_ids_by_tag(self, tag: str, user_id: int) -> list[int]:
        tag_u = str(tag).upper()
        return sorted(
            anime_id
            for (anime_id, uid), value in self.tags.items()
            if uid == user_id and str(value).upper() == tag_u
        )

    def clear_episode_progress(self, anime_id: int, user_id: int) -> None:
        self.cleared.append((anime_id, user_id))


class _FakeMediaLibrary:
    def __init__(self) -> None:
        self.deleted: list[int] = []

    def delete_anime_folder(self, anime_id: int) -> bool:
        self.deleted.append(anime_id)
        return True


def _service(
    tmp_path: Path,
    *,
    user_actions: _FakeUserActions | None = None,
    media_library: _FakeMediaLibrary | None = None,
    folders: list[str] | None = None,
) -> tuple[LibraryStartupSyncService, _FakeUserActions, _FakeMediaLibrary]:
    anime_path = tmp_path / "Animes"
    anime_path.mkdir(parents=True, exist_ok=True)
    actions = user_actions or _FakeUserActions()
    media = media_library or _FakeMediaLibrary()
    service = LibraryStartupSyncService(
        user_actions=actions,
        media_library=media,
        anime_path=str(anime_path),
        list_anime_folders=lambda: folders or [],
        cancel_download=lambda _aid: True,
        purge_torrents_for_anime=lambda aid: 2 if aid == 1407 else 1,
    )
    return service, actions, media


def test_promote_watching_tags_updates_none_and_watchlist(tmp_path):
    folder = "Show A - 10"
    (tmp_path / "Animes" / folder).mkdir(parents=True)
    (tmp_path / "Animes" / folder / "ep01.mkv").write_bytes(b"x")

    actions = _FakeUserActions()
    actions.tags[(10, 1)] = "NONE"
    actions.tags[(11, 1)] = "WATCHLIST"
    actions.tags[(12, 1)] = "SEEN"
    actions.tags[(13, 1)] = "WATCHING"

    service, actions, _ = _service(
        tmp_path,
        user_actions=actions,
        folders=[
            "Show A - 10",
            "Show B - 11",
            "Show C - 12",
            "Show D - 13",
            "No Videos - 14",
        ],
    )
    for name in ("Show B - 11", "Show C - 12", "Show D - 13"):
        (tmp_path / "Animes" / name).mkdir(parents=True, exist_ok=True)
        (tmp_path / "Animes" / name / "ep01.mkv").write_bytes(b"x")

    result = service.promote_watching_tags(1)
    assert result.promoted == 2
    assert result.scanned == 4
    assert actions.tags[(10, 1)] == "WATCHING"
    assert actions.tags[(11, 1)] == "WATCHING"
    assert actions.tags[(12, 1)] == "SEEN"
    assert actions.tags[(13, 1)] == "WATCHING"


def test_promote_watching_tags_skips_when_anime_path_missing(tmp_path):
    service = LibraryStartupSyncService(
        user_actions=_FakeUserActions(),
        media_library=_FakeMediaLibrary(),
        anime_path="",
    )
    result = service.promote_watching_tags(1)
    assert result.promoted == 0
    assert result.scanned == 0


def test_purge_seen_libraries_removes_torrents_folders_and_progress(tmp_path):
    actions = _FakeUserActions()
    actions.tags[(1407, 1)] = "SEEN"
    actions.tags[(2000, 1)] = "WATCHING"
    media = _FakeMediaLibrary()
    cancelled: list[int] = []
    purged: list[int] = []

    service = LibraryStartupSyncService(
        user_actions=actions,
        media_library=media,
        anime_path=str(tmp_path / "Animes"),
        cancel_download=lambda aid: cancelled.append(aid) or True,
        purge_torrents_for_anime=lambda aid: purged.append(aid) or 3,
    )

    result = service.purge_seen_libraries(1)
    assert result.seen_candidates == 1
    assert result.purged_folders == 1
    assert result.purged_torrents == 3
    assert cancelled == [1407]
    assert purged == [1407]
    assert media.deleted == [1407]
    assert actions.cleared == [(1407, 1)]


def test_purge_seen_libraries_rechecks_tag_before_delete(tmp_path):
    actions = _FakeUserActions()
    actions.tags[(99, 1)] = "SEEN"

    class _WatchingAtPurgeActions(_FakeUserActions):
        def get_user_state(self, anime_id: int, user_id: int) -> dict:
            if anime_id == 99:
                return {"tag": "WATCHING", "liked": False}
            return super().get_user_state(anime_id, user_id)

    media = _FakeMediaLibrary()
    service = LibraryStartupSyncService(
        user_actions=_WatchingAtPurgeActions(),
        media_library=media,
        anime_path=str(tmp_path / "Animes"),
        cancel_download=lambda _aid: True,
        purge_torrents_for_anime=lambda _aid: 1,
    )
    result = service.purge_seen_libraries(1)
    assert result.purged_folders == 0
    assert media.deleted == []
