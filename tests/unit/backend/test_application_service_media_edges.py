"""Media, streaming, and library use-case tests for :class:`AnimeApplicationService`."""

from __future__ import annotations

import os
import pytest

from application.dto import EpisodeFileDTO, PlaybackSessionDTO
from application.services.anime_service import AnimeApplicationService
from domain.dto import DownloadRequest, SearchRequest
from domain.entities import AnimeEntity
from domain.errors import NotFoundError, ValidationError


class FakeRepository:
    def __init__(self):
        self.items: list[AnimeEntity] = []
        self.calls: list[tuple] = []
        self.search_terms: list[str] = []
        self.last_torrent_query: dict[int, str] = {}
        self.torrent_rows: list[dict] = []
        self.delete_supported = True
        self.folder_value = "/anime/1"
        self.folder_raises = False

    def search(self, query, limit=50):
        self.calls.append(("search", query, limit))
        return list(self.items)

    def list_anime(self, **kwargs):
        self.calls.append(("list_anime", kwargs))
        return list(self.items), False

    def get_anime(self, anime_id):
        for entity in self.items:
            if entity.id == anime_id:
                return entity
        return None

    def get_search_terms(self, anime_id):
        return list(self.search_terms)

    def add_search_term(self, anime_id, term):
        return True

    def remove_search_term(self, anime_id, term):
        return True

    def get_last_torrent_search_query(self, anime_id):
        return self.last_torrent_query.get(anime_id)

    def set_last_torrent_search_query(self, anime_id, query):
        self.last_torrent_query[anime_id] = query

    def get_settings(self):
        return {}

    def update_settings(self, updates):
        return updates

    def get_relations(self, anime_id, relation_type="anime"):
        return []

    def list_anime_characters(self, anime_id):
        return []

    def delete_anime(self, anime_id):
        return self.delete_supported

    def get_anime_folder(self, anime_id):
        if self.folder_raises:
            raise RuntimeError("folder fail")
        return self.folder_value

    def get_anime_torrents(self, anime_id):
        return list(self.torrent_rows)


class FakeProvider:
    def __init__(self):
        self.responses: list[AnimeEntity] = []
        self.stream_items: list[AnimeEntity] = []

    def search(self, query, limit=50):
        return list(self.responses)

    def stream_search(self, query, limit=50):
        for item in self.stream_items:
            yield item


class FakeDownload:
    def __init__(self):
        self.search_rows: list = []
        self.stream_rows: list = []
        self.active: list[dict] = []
        self.overview: dict | None = None
        self.overview_raises = False
        self.redownload_value = 0

    def start_download(self, anime_id, url=None, hash_value=None, user_id=None):
        return True

    def get_download_progress(self, anime_id):
        return {"anime_id": anime_id}

    def cancel_download(self, anime_id):
        return True

    def get_active_downloads(self):
        return list(self.active)

    def search_torrents(self, terms, profile="interactive", limit=200):
        return list(self.search_rows)

    def stream_torrents(self, terms, profile="interactive", limit=200):
        for row in self.stream_rows:
            yield row

    def get_torrents_overview(self):
        if self.overview_raises:
            raise RuntimeError("overview fail")
        return self.overview

    def redownload(self, anime_id):
        return self.redownload_value


class FakeActions:
    def __init__(self):
        self.tag = "NONE"
        self.progress: dict[str, dict] = {}
        self.calls: list[tuple] = []

    def set_tag(self, anime_id, tag, user_id):
        self.tag = tag
        self.calls.append(("set_tag", anime_id, tag, user_id))

    def set_like(self, anime_id, liked, user_id):
        pass

    def mark_seen(self, anime_id, file_name, user_id):
        pass

    def get_user_state(self, anime_id, user_id):
        return {"tag": self.tag, "liked": False}

    def get_episode_progress_map(self, anime_id, user_id):
        return dict(self.progress)

    def set_episode_progress(
        self, anime_id, user_id, file_id, status, position_seconds=None
    ):
        self.calls.append(
            ("set_episode_progress", anime_id, user_id, file_id, status, position_seconds)
        )

    def delete_episode_progress(self, anime_id, user_id, file_id):
        self.calls.append(("delete_episode_progress", anime_id, user_id, file_id))


class FakeMedia:
    def __init__(self, files: list[EpisodeFileDTO] | None = None):
        self.files = list(files or [])
        self.deleted: list[str] = []

    def list_episode_files(self, query):
        return list(self.files)

    def delete_episode_file(self, anime_id, file_id):
        self.deleted.append(file_id)
        return True

    def create_session(self, command):
        return PlaybackSessionDTO(
            session_id="sess-1",
            anime_id=command.anime_id,
            file_id=command.file_id,
            file_title="Episode",
            manifest_path="/tmp/index.m3u8",
            output_dir="/tmp/out",
            token="tok",
            expires_at=9999999999.0,
            created_at=0.0,
            last_seen_at=0.0,
        )

    def heartbeat(self, command):
        return PlaybackSessionDTO(
            session_id=command.session_id,
            anime_id=1,
            file_id="ep-1",
            file_title="Episode",
            manifest_path="/tmp/index.m3u8",
            output_dir="/tmp/out",
            token="tok",
            expires_at=9999999999.0,
            created_at=0.0,
            last_seen_at=0.0,
        )

    def stop_session(self, command):
        return None

    def resolve_media_path(self, query):
        session = PlaybackSessionDTO(
            session_id=query.session_id,
            anime_id=1,
            file_id="ep-1",
            file_title="Episode",
            manifest_path="/tmp/index.m3u8",
            output_dir="/tmp/out",
            token=query.token,
            expires_at=9999999999.0,
            created_at=0.0,
            last_seen_at=0.0,
        )
        return session, "/tmp/segment.ts"

    def cleanup_stale_sessions(self):
        return None


@pytest.fixture
def svc():
    repo = FakeRepository()
    prov = FakeProvider()
    dl = FakeDownload()
    actions = FakeActions()
    media = FakeMedia()
    service = AnimeApplicationService(
        anime_repository=repo,
        metadata_provider=prov,
        download_port=dl,
        user_actions_port=actions,
        media_streaming_service=media,
    )
    service._fakes = (repo, prov, dl, actions, media)
    return service


class TestStreamSearchAnime:
    def test_yields_local_then_remote_deduped(self, svc):
        repo, prov, _, _, _ = svc._fakes
        repo.items = [
            AnimeEntity(id=1, title="Local"),
            AnimeEntity(id=2, title="Local dup path"),
        ]
        prov.stream_items = [
            AnimeEntity(id=2, title="Remote dup"),
            AnimeEntity(id=3, title="Remote"),
        ]
        out = list(svc.stream_search_anime(SearchRequest(query="naruto")))
        assert [e.id for e in out] == [1, 2, 3]

    def test_falls_back_to_search_without_streamer(self, svc):
        repo, _, _, _, _ = svc._fakes
        repo.items = []

        class _BatchOnlyProvider:
            def search(self, query, limit=50):
                _ = (query, limit)
                return [AnimeEntity(id=9, title="Batch")]

        svc._metadata_provider = _BatchOnlyProvider()
        out = list(svc.stream_search_anime(SearchRequest(query="bleach")))
        assert [e.id for e in out] == [9]


class TestRefreshAndDelete:
    def test_refresh_falls_back_on_provider_failure(self, svc):
        repo, prov, _, _, _ = svc._fakes
        repo.items = [AnimeEntity(id=1, title="Stored")]

        def boom(_anime_id):
            raise RuntimeError("provider down")

        prov.refresh_anime = boom
        assert svc.refresh_anime_metadata(1).title == "Stored"

    def test_delete_raises_when_unsupported(self, svc):
        bare_repo = FakeRepository()
        bare_repo.delete_anime = None  # type: ignore[method-assign]
        svc._anime_repository = bare_repo
        with pytest.raises(ValidationError):
            svc.delete_anime(1)

    def test_get_anime_folder_swallows_errors(self, svc):
        repo, _, _, _, _ = svc._fakes
        repo.folder_raises = True
        assert svc.get_anime_folder(1) == ""


class TestTorrentsOverview:
    def test_overview_from_port(self, svc):
        _, _, dl, _, _ = svc._fakes
        dl.overview = {
            "active": [{"hash": "a"}],
            "seeding": [{"hash": "b"}],
            "completed": [],
            "error": [],
            "other": [],
        }
        out = svc.get_torrents_overview()
        assert len(out["active"]) == 1
        assert len(out["seeding"]) == 1

    def test_overview_fallback_on_exception(self, svc):
        _, _, dl, _, _ = svc._fakes
        dl.overview_raises = True
        dl.active = [{"anime_id": 5}]
        out = svc.get_torrents_overview()
        assert out["active"] == [{"anime_id": 5}]
        assert out["seeding"] == []


class TestStreamTorrentsFallback:
    def test_materializes_when_no_streamer(self, svc):
        class _BatchDownload:
            def search_torrents(self, terms, profile="interactive", limit=200):
                _ = (terms, profile, limit)
                return [{"name": "one", "hash": "abc"}]

        svc._download_port = _BatchDownload()
        out = list(svc.stream_torrents(["naruto"]))
        assert out[0]["name"] == "one"


class TestEpisodeLibrary:
    def test_list_episode_files_merges_progress(self, svc):
        _, _, _, actions, media = svc._fakes
        media.files = [
            EpisodeFileDTO(
                file_id="ep-1",
                title="E1",
                path="/v/ep1.mkv",
                watch_status="UNSEEN",
            )
        ]
        actions.progress = {
            "ep-1": {"status": "watching", "position_seconds": 42.5},
        }
        rows = svc.list_episode_files(1, user_id=7)
        assert rows[0].watch_status == "WATCHING"
        assert rows[0].position_seconds == 42.5

    def test_sync_promotes_watchlist_to_watching(self, svc):
        _, _, _, actions, media = svc._fakes
        actions.tag = "WATCHLIST"
        media.files = [
            EpisodeFileDTO(file_id="ep-1", title="E1", path="/v/ep1.mkv"),
        ]
        svc.list_episode_files(1, user_id=7)
        assert ("set_tag", 1, "WATCHING", 7) in actions.calls

    def test_delete_all_and_seen_episodes(self, svc):
        repo, _, _, actions, media = svc._fakes
        media.files = [
            EpisodeFileDTO(file_id="ep-1", title="E1", path="/v/ep1.mkv"),
            EpisodeFileDTO(file_id="ep-2", title="E2", path="/v/ep2.mkv"),
        ]
        repo.items = [
            AnimeEntity(id=1, title="Show", last_seen="/v/ep2.mkv"),
        ]
        assert svc.delete_all_files(1, user_id=7) == 2
        assert set(media.deleted) == {"ep-1", "ep-2"}

        media.deleted.clear()
        media.files = [
            EpisodeFileDTO(file_id="ep-1", title="E1", path="/v/ep1.mkv"),
            EpisodeFileDTO(file_id="ep-2", title="E2", path="/v/ep2.mkv"),
        ]
        assert svc.delete_seen_episodes(1, user_id=7) == 1
        assert media.deleted == ["ep-1"]

    def test_delete_seen_returns_zero_without_last_seen(self, svc):
        repo, _, _, _, media = svc._fakes
        repo.items = [AnimeEntity(id=1, title="Show", last_seen=None)]
        media.files = [
            EpisodeFileDTO(file_id="ep-1", title="E1", path="/v/ep1.mkv"),
        ]
        assert svc.delete_seen_episodes(1, user_id=7) == 0

    def test_redownload_episode_matches_hash_by_path(self, svc, tmp_path):
        repo, _, dl, _, media = svc._fakes
        ep_path = tmp_path / "Show" / "Episode 01.mkv"
        ep_path.parent.mkdir(parents=True)
        ep_path.write_bytes(b"x")
        media.files = [
            EpisodeFileDTO(
                file_id="ep-1",
                title="Episode 01.mkv",
                path=str(ep_path),
            )
        ]
        torrent_root = tmp_path / "torrent"
        torrent_root.mkdir()
        dl.active = [
            {
                "anime_id": 1,
                "hash": "deadbeef",
                "path": str(torrent_root),
                "name": "Show Episode 01",
            }
        ]
        assert svc.redownload_episode(1, "ep-1", user_id=7) is True
        assert media.deleted == ["ep-1"]

    def test_get_anime_torrents_pass_through(self, svc):
        repo, _, _, _, _ = svc._fakes
        repo.torrent_rows = [{"hash": "abc", "state": "COMPLETE"}]
        assert svc.get_anime_torrents(1)[0]["state"] == "COMPLETE"


class TestPlaybackDelegation:
    def test_playback_session_lifecycle(self, svc):
        session = svc.create_playback_session(1, "ep-1", client_host="127.0.0.1")
        assert session.session_id == "sess-1"
        hb = svc.heartbeat_playback_session("sess-1")
        assert hb.session_id == "sess-1"
        svc.stop_playback_session("sess-1")
        resolved, path = svc.resolve_playback_media_path(
            session_id="sess-1", token="tok", segment_name="segment_00001.ts"
        )
        assert path.endswith("segment.ts")

    def test_cleanup_noop_without_media(self):
        bare = AnimeApplicationService(
            anime_repository=FakeRepository(),
            metadata_provider=FakeProvider(),
            download_port=FakeDownload(),
            user_actions_port=FakeActions(),
            media_streaming_service=None,
        )
        bare.cleanup_playback_sessions()

    def test_media_required_for_episode_ops(self):
        bare = AnimeApplicationService(
            anime_repository=FakeRepository(),
            metadata_provider=FakeProvider(),
            download_port=FakeDownload(),
            user_actions_port=FakeActions(),
        )
        with pytest.raises(ValidationError):
            bare.list_episode_files(1)

    def test_create_playback_requires_file_id(self, svc):
        with pytest.raises(ValidationError):
            svc.create_playback_session(1, "")


class TestCanonicalBtih:
    def test_non_standard_hash_fallback(self, svc):
        _, _, dl, _, _ = svc._fakes
        dl.search_rows = [
            {"name": "a", "hash": "custom-hash-token"},
            {"name": "b", "hash": "custom-hash-token"},
        ]
        out = svc.search_torrents(["x"])
        assert len(out) == 1
