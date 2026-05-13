import importlib

from fastapi.testclient import TestClient

http_app_module = importlib.import_module("clients.http.app")


class FakeSDK:
    def get_anime(self, anime_id: int):
        return {"id": anime_id, "title": "Test"}

    def get_anime_list(self, **kwargs):
        _ = kwargs
        return {"items": [{"id": 1, "title": "Test"}], "has_next": False}

    def search_anime(self, query: str, limit: int = 50):
        _ = limit
        return [{"id": 1, "title": query}]

    def start_download(self, anime_id: int, url=None, hash_value=None, user_id=None):
        _ = (anime_id, url, hash_value, user_id)
        return True

    def get_download_progress(self, anime_id: int):
        return {"anime_id": anime_id, "progress": 42}

    def cancel_download(self, anime_id: int):
        _ = anime_id
        return True

    def get_active_downloads(self):
        return [{"anime_id": 1, "elapsed_time": 1.0}]

    def search_torrents(self, terms, profile="interactive", limit=200):
        _ = (profile, limit)
        return [{"name": "mock", "link": "magnet:?xt=urn:btih:abc", "terms": terms}]

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
        return ["foo", "bar"]

    def add_search_term(self, anime_id: int, term: str):
        _ = (anime_id, term)
        return True

    def remove_search_term(self, anime_id: int, term: str):
        _ = (anime_id, term)
        return True

    def get_settings(self):
        return {"anime": {"hideRated": True}}

    def update_settings(self, updates):
        return updates


def test_http_adapter_routes_use_shared_sdk(monkeypatch):
    monkeypatch.setattr(http_app_module, "get_sdk", lambda: FakeSDK())
    client = TestClient(http_app_module.app)

    assert client.get("/").status_code == 200
    assert client.get("/anime/7").json()["id"] == 7
    assert client.get("/animelist").json()["items"][0]["id"] == 1
    assert client.get("/search", params={"query": "bleach"}).json()[0]["title"] == "bleach"
    assert client.post("/download/1", params={"url": "magnet:?xt=urn:btih:abc"}).json()["started"] is True
    assert client.post("/download/cancel/1").json()["cancelled"] is True
    assert client.get("/download/active").json()["items"][0]["anime_id"] == 1
    assert client.get("/torrents/search", params={"term": "naruto"}).json()[0]["name"] == "mock"
    assert client.get("/state/1", params={"user_id": 3}).json()["tag"] == "WATCHING"
    assert client.get("/search-terms/1").json()["items"][0] == "foo"
    assert client.post("/search-terms/1", params={"term": "new"}).json()["added"] is True
    assert client.delete("/search-terms/1", params={"term": "foo"}).json()["removed"] is True
    assert client.get("/settings").json()["anime"]["hideRated"] is True
    assert client.patch("/settings", json={"anime": {"hideRated": False}}).json()["anime"]["hideRated"] is False
