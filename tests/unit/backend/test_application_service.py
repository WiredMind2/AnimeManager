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

    def get_search_terms(self, anime_id: int):
        _ = anime_id
        return ["foo"]

    def add_search_term(self, anime_id: int, term: str):
        _ = anime_id
        return term != "foo"

    def remove_search_term(self, anime_id: int, term: str):
        _ = anime_id
        return bool(term)

    def get_last_torrent_search_query(self, anime_id: int):
        _ = anime_id
        return None

    def set_last_torrent_search_query(self, anime_id: int, query: str):
        _ = (anime_id, query)

    def get_settings(self):
        return {"anime": {"hideRated": True}}

    def update_settings(self, updates: dict):
        return updates

    def get_relations(self, anime_id: int, relation_type: str = "anime"):
        _ = (anime_id, relation_type)
        return [{"id": 1, "rel_id": 2, "name": "SEQUEL"}]

    def list_anime_characters(self, anime_id: int):
        _ = anime_id
        return [{"id": 1, "name": "Renji", "role": "supporting", "picture": None, "synopsis": None}]

    def delete_anime(self, anime_id: int):
        _ = anime_id
        return True

    def get_anime_folder(self, anime_id: int):
        return f"/anime/{anime_id}"


class FakeProvider:
    def search(self, query: str, limit: int = 50):
        _ = limit
        if query == "naruto":
            return [AnimeEntity(id=2, title="Naruto", status="FINISHED")]
        return []

    def refresh_anime(self, anime_id: int):
        return AnimeEntity(id=anime_id, title="Refreshed", status="AIRING")


class FakeDownload:
    def start_download(self, anime_id: int, url=None, hash_value=None, user_id=None):
        _ = (anime_id, url, hash_value, user_id)
        return True

    def get_download_progress(self, anime_id: int):
        return {"anime_id": anime_id, "progress": 50}

    def cancel_download(self, anime_id: int):
        _ = anime_id
        return True

    def get_active_downloads(self):
        return [{"anime_id": 1, "elapsed_time": 1.0}]

    def search_torrents(self, terms, profile="interactive", limit=200):
        _ = (profile, limit)
        return [{"name": "result", "terms": terms}]

    def redownload(self, anime_id: int):
        _ = anime_id
        return 1


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


def _service():
    return AnimeApplicationService(
        anime_repository=FakeRepository(),
        metadata_provider=FakeProvider(),
        download_port=FakeDownload(),
        user_actions_port=FakeActions(),
    )


def test_search_prefers_repository():
    result = _service().search_anime(SearchRequest(query="cowboy"))
    assert len(result) == 1
    assert result[0].title == "Cowboy Bebop"


def test_search_falls_back_to_provider():
    result = _service().search_anime(SearchRequest(query="naruto"))
    assert len(result) == 1
    assert result[0].id == 2


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
    assert started is True


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
    assert service.list_anime_characters(1)[0]["name"] == "Renji"
    assert service.redownload(1) == 1
    assert service.delete_anime(1) is True
    assert service.get_anime_folder(1) == "/anime/1"
    assert service.refresh_anime_metadata(1).title == "Refreshed"
