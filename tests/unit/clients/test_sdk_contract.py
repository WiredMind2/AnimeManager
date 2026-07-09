import importlib

from application.services.anime_hydration import AnimeDetailsResult
from domain.entities import AnimeEntity


sdk_module = importlib.import_module("clients.sdk")


class FakeFacade:
    def __init__(self):
        self.settings = {"anime": {"hideRated": True}}

    def search_anime(self, query: str, limit: int = 50):
        _ = (query, limit)
        return []

    def get_anime_list(self, **kwargs):
        _ = kwargs
        class _Payload:
            items = []
            has_next = False
        return _Payload()

    def get_anime_details(self, anime_id: int):
        return AnimeDetailsResult(
            entity=AnimeEntity(id=anime_id, title="A"),
            metadata_pending=False,
        )

    def start_download(self, anime_id: int, **kwargs):
        _ = (anime_id, kwargs)
        return True

    def get_download_progress(self, anime_id: int):
        return {"anime_id": anime_id, "progress": 42}

    def cancel_download(self, anime_id: int):
        _ = anime_id
        return True

    def get_active_downloads(self):
        return [{"anime_id": 1}]

    def search_torrents(self, terms, profile="interactive", limit=200):
        _ = (profile, limit)
        return [{"name": "t", "terms": terms}]

    def set_tag(self, anime_id: int, tag: str, user_id: int):
        _ = (anime_id, tag, user_id)

    def set_like(self, anime_id: int, user_id: int, liked: bool = True):
        _ = (anime_id, user_id, liked)

    def mark_seen(self, anime_id: int, file_name: str, user_id: int):
        _ = (anime_id, file_name, user_id)

    def get_user_state(self, anime_id: int, user_id: int):
        _ = (anime_id, user_id)
        return {"tag": "WATCHING", "liked": True}

    def get_search_terms(self, anime_id: int):
        _ = anime_id
        return ["foo"]

    def add_search_term(self, anime_id: int, term: str):
        _ = (anime_id, term)
        return True

    def remove_search_term(self, anime_id: int, term: str):
        _ = (anime_id, term)
        return True

    def get_settings(self):
        return self.settings

    def update_settings(self, updates):
        self.settings = updates
        return self.settings

    def get_relations(self, anime_id: int, relation_type: str = "anime"):
        _ = (anime_id, relation_type)
        return [{"id": anime_id, "name": "SEQUEL", "rel_id": 2}]


def test_sdk_extended_contract(monkeypatch):
    monkeypatch.setattr(sdk_module, "_facade", lambda: FakeFacade())
    sdk = sdk_module.ClientSDK()

    assert sdk.cancel_download(1) is True
    assert sdk.get_active_downloads()[0]["anime_id"] == 1
    assert sdk.search_torrents(["naruto"])[0]["name"] == "t"
    assert sdk.get_user_state(1, 7)["tag"] == "WATCHING"
    assert sdk.get_search_terms(1) == ["foo"]
    assert sdk.add_search_term(1, "bar") is True
    assert sdk.remove_search_term(1, "foo") is True
    assert sdk.get_settings()["anime"]["hideRated"] is True
    assert sdk.update_settings({"anime": {"hideRated": False}})["anime"]["hideRated"] is False
    assert sdk.get_relations(1)[0]["name"] == "SEQUEL"
