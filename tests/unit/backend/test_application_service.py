from application.services.anime_service import AnimeApplicationService
from domain.dto import AnimeListRequest, DownloadRequest, SearchRequest
from domain.entities import AnimeEntity
from domain.errors import NotFoundError, ValidationError


class FakeRepository:
    def __init__(self):
        self.items = [AnimeEntity(id=1, title="Cowboy Bebop", status="FINISHED")]

    def search(self, query: str, limit: int = 50):
        return self.items if "cowboy" in query.lower() else []

    def list_anime(self, criteria, list_start, list_stop, hide_rated, user_id):
        _ = (criteria, list_start, list_stop, hide_rated, user_id)
        return self.items, False

    def get_anime(self, anime_id: int):
        return self.items[0] if anime_id == 1 else None

    def anime_row_exists(self, anime_id: int):
        return self.get_anime(anime_id) is not None

    def get_search_terms(self, anime_id: int):
        _ = anime_id
        return ["foo"]

    def add_search_term(self, anime_id: int, term: str):
        _ = anime_id
        return term != "foo"

    def remove_search_term(self, anime_id: int, term: str):
        _ = anime_id
        return bool(term)

    def get_settings(self):
        return {"anime": {"hideRated": True}}

    def update_settings(self, updates: dict):
        return updates

    def get_relations(self, anime_id: int, relation_type: str = "anime"):
        _ = (anime_id, relation_type)
        return [{"id": 1, "rel_id": 2, "name": "SEQUEL"}]


class FakeProvider:
    def search(self, query: str, limit: int = 50):
        _ = limit
        if query == "naruto":
            return [AnimeEntity(id=2, title="Naruto", status="FINISHED")]
        if "cowboy" in query.lower():
            return [AnimeEntity(id=99, title="Remote Cowboy", status="FINISHED")]
        return []


class FakeDownload:
    def start_download(self, anime_id: int, url=None, hash_value=None, user_id=None, source=None):
        _ = (anime_id, url, hash_value, user_id, source)
        return {"started": True, "skipped": False, "reason": None}

    def get_download_progress(self, anime_id: int):
        return {"anime_id": anime_id, "progress": 50}

    def cancel_download(self, anime_id: int):
        _ = anime_id
        return True

    def get_active_downloads(self):
        return [{"anime_id": 1, "elapsed_time": 1.0}]

    def search_torrents(self, terms, profile="interactive", limit=200, allow_nsfw=False):
        _ = (profile, limit, allow_nsfw)
        return [{"name": "result", "terms": terms}]


class FakeActions:
    def set_tag(self, anime_id: int, tag: str, user_id: int):
        _ = (anime_id, tag, user_id)

    def set_like(self, anime_id: int, liked: bool, user_id: int):
        _ = (anime_id, liked, user_id)

    def mark_seen(self, anime_id: int, file_name: str, user_id: int):
        _ = (anime_id, file_name, user_id)

    def get_user_state(self, anime_id: int, user_id: int):
        _ = (anime_id, user_id)
        return {"tag": "WATCHING", "liked": True}

    def get_episode_progress_map(self, anime_id: int, user_id: int):
        _ = (anime_id, user_id)
        return {}

    def set_episode_progress(
        self,
        anime_id: int,
        user_id: int,
        file_id: str,
        status: str,
        position_seconds: float | None = None,
    ):
        _ = (anime_id, user_id, file_id, status, position_seconds)

    def delete_episode_progress(self, anime_id: int, user_id: int, file_id: str):
        _ = (anime_id, user_id, file_id)


class FakeMediaStreaming:
    def __init__(self, refs=None):
        self.refs = list(refs or [])

    def list_local_episode_refs(self, anime_id: int):
        _ = anime_id
        return list(self.refs)


def _service(*, media_streaming=None, actions=None, repository=None):
    return AnimeApplicationService(
        anime_repository=repository or FakeRepository(),
        metadata_provider=FakeProvider(),
        download_port=FakeDownload(),
        user_actions_port=actions or FakeActions(),
        media_streaming_service=media_streaming,
    )


def test_search_prefers_repository():
    result = _service().search_anime(SearchRequest(query="cowboy"))
    assert len(result.items) == 2
    assert result.items[0].title == "Cowboy Bebop"
    assert result.items[1].title == "Remote Cowboy"


def test_search_falls_back_to_provider():
    result = _service().search_anime(SearchRequest(query="naruto"))
    assert len(result.items) == 1
    assert result.items[0].id == 2


def test_search_rejects_short_query():
    service = _service()
    try:
        service.search_anime(SearchRequest(query="na"))
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected ValidationError for short query")


def test_get_anime_details_not_found():
    service = _service()
    try:
        service.get_anime_details(999)
    except NotFoundError:
        pass
    else:
        raise AssertionError("Expected NotFoundError when anime is missing")


def test_list_and_download_use_cases():
    service = _service()
    listing = service.get_anime_list(AnimeListRequest())
    assert listing.items[0].id == 1
    started = service.start_download(DownloadRequest(anime_id=1, url="magnet:?xt=urn:btih:abc"))
    assert started["started"] is True


def test_extended_contract_use_cases():
    service = _service()
    assert service.cancel_download(1) is True
    assert service.get_active_downloads()[0]["anime_id"] == 1
    assert service.search_torrents(["naruto"])[0]["name"] == "result"
    assert service.get_user_state(1, 7)["tag"] == "WATCHING"
    assert service.get_search_terms(1) == ["foo"]
    assert service.add_search_term(1, "new term") is True
    assert service.remove_search_term(1, "foo") is True
    assert service.get_settings()["anime"]["hideRated"] is True
    assert service.update_settings({"anime": {"hideRated": False}})["anime"]["hideRated"] is False
    assert service.get_relations(1)[0]["name"] == "SEQUEL"


def test_watching_counts_no_files():
    service = _service(media_streaming=FakeMediaStreaming([]))
    unwatched, left = service._watching_episode_counts(1, 1, 12)
    assert unwatched == 0
    assert left == 12


def test_watching_counts_all_seen():
    from application.dto import LocalEpisodeRef

    class SeenActions(FakeActions):
        def get_episode_progress_map(self, anime_id, user_id):
            _ = (anime_id, user_id)
            return {
                "ep-a": {"status": "SEEN", "position_seconds": 1.0},
                "ep-b": {"status": "SEEN", "position_seconds": 2.0},
            }

    refs = [
        LocalEpisodeRef(file_id="ep-a", episode=1),
        LocalEpisodeRef(file_id="ep-b", episode=2),
    ]
    service = _service(media_streaming=FakeMediaStreaming(refs), actions=SeenActions())
    unwatched, left = service._watching_episode_counts(1, 1, 12)
    assert unwatched == 0
    assert left == 10


def test_watching_counts_in_progress_counts_as_unwatched():
    from application.dto import LocalEpisodeRef

    class MixedActions(FakeActions):
        def get_episode_progress_map(self, anime_id, user_id):
            _ = (anime_id, user_id)
            return {
                "ep-a": {"status": "SEEN", "position_seconds": 100.0},
                "ep-b": {"status": "IN_PROGRESS", "position_seconds": 40.0},
            }

    refs = [
        LocalEpisodeRef(file_id="ep-a", episode=1),
        LocalEpisodeRef(file_id="ep-b", episode=2),
        LocalEpisodeRef(file_id="ep-c", episode=3),
    ]
    service = _service(media_streaming=FakeMediaStreaming(refs), actions=MixedActions())
    unwatched, left = service._watching_episode_counts(1, 1, 12)
    assert unwatched == 2
    assert left == 11


def test_watching_counts_catalog_missing_omits_left():
    from application.dto import LocalEpisodeRef

    refs = [LocalEpisodeRef(file_id="ep-a")]
    service = _service(media_streaming=FakeMediaStreaming(refs))
    unwatched, left = service._watching_episode_counts(1, 1, None)
    assert unwatched == 1
    assert left is None


def test_watching_counts_catalog_less_than_seen():
    from application.dto import LocalEpisodeRef

    class SeenActions(FakeActions):
        def get_episode_progress_map(self, anime_id, user_id):
            _ = (anime_id, user_id)
            return {
                "ep-a": {"status": "SEEN"},
                "ep-b": {"status": "SEEN"},
                "ep-c": {"status": "SEEN"},
            }

    refs = [
        LocalEpisodeRef(file_id="ep-a"),
        LocalEpisodeRef(file_id="ep-b"),
        LocalEpisodeRef(file_id="ep-c"),
    ]
    service = _service(media_streaming=FakeMediaStreaming(refs), actions=SeenActions())
    unwatched, left = service._watching_episode_counts(1, 1, 2)
    assert unwatched == 0
    assert left == 0


def test_get_anime_list_watching_attaches_counts():
    from application.dto import LocalEpisodeRef

    repo = FakeRepository()
    repo.items = [AnimeEntity(id=1, title="Cowboy Bebop", episodes=12, tag="WATCHING")]
    refs = [
        LocalEpisodeRef(file_id="ep-a"),
        LocalEpisodeRef(file_id="ep-b"),
    ]

    class PartialSeen(FakeActions):
        def get_episode_progress_map(self, anime_id, user_id):
            _ = (anime_id, user_id)
            return {"ep-a": {"status": "SEEN"}}

    service = _service(
        repository=repo,
        media_streaming=FakeMediaStreaming(refs),
        actions=PartialSeen(),
    )
    listing = service.get_anime_list(
        AnimeListRequest(filter="WATCHING", user_id=1)
    )
    item = listing.items[0]
    assert item.unwatched_count == 1
    assert item.episodes_left == 11


def test_get_anime_list_other_filter_skips_counts():
    from application.dto import LocalEpisodeRef

    repo = FakeRepository()
    repo.items = [AnimeEntity(id=1, title="Cowboy Bebop", episodes=12, tag="WATCHING")]
    service = _service(
        repository=repo,
        media_streaming=FakeMediaStreaming([LocalEpisodeRef(file_id="ep-a")]),
    )
    listing = service.get_anime_list(AnimeListRequest(filter="DEFAULT", user_id=1))
    item = listing.items[0]
    assert item.unwatched_count is None
    assert item.episodes_left is None

