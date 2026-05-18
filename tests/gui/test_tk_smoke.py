from clients.tk.presenters.anime_browser import AnimeBrowserPresenter


class InlineRunner:
    def submit(self, func, *args, on_success=None, on_error=None, **kwargs):
        try:
            result = func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - smoke path
            if on_error:
                on_error(exc)
            return
        if on_success:
            on_success(result)


class FakeSDK:
    def get_anime_list(self, **kwargs):
        _ = kwargs
        return {"items": [{"id": 1, "title": "Cowboy Bebop"}], "has_next": False}

    def search_anime(self, query: str, limit: int = 50):
        _ = limit
        return [{"id": 2, "title": query}]

    def get_anime(self, anime_id: int):
        return {"id": anime_id, "title": "Item", "synopsis": "text"}

    def search_torrents(self, terms, profile="interactive", limit=200):
        _ = (profile, limit)
        return [{"name": "Torrent", "terms": terms}]

    def start_download(self, anime_id: int, **kwargs):
        _ = (anime_id, kwargs)
        return True

    def cancel_download(self, anime_id: int):
        _ = anime_id
        return True

    def get_download_progress(self, anime_id: int):
        return {"anime_id": anime_id, "progress": 12}

    def set_tag(self, anime_id: int, tag: str, user_id: int):
        _ = (anime_id, tag, user_id)

    def set_like(self, anime_id: int, user_id: int, liked: bool = True):
        _ = (anime_id, user_id, liked)

    def mark_seen(self, anime_id: int, file_name: str, user_id: int):
        _ = (anime_id, file_name, user_id)

    def get_search_terms(self, anime_id: int):
        _ = anime_id
        return ["foo"]

    def add_search_term(self, anime_id: int, term: str):
        _ = (anime_id, term)
        return True

    def remove_search_term(self, anime_id: int, term: str):
        _ = (anime_id, term)
        return True

    def get_last_torrent_search_query(self, anime_id: int):
        _ = anime_id
        return None

    def set_last_torrent_search_query(self, anime_id: int, query: str):
        _ = (anime_id, query)

    def get_settings(self):
        return {"anime": {"hideRated": True}}

    def update_settings(self, updates):
        return updates

    def get_relations(self, anime_id: int):
        _ = anime_id
        return [{"name": "SEQUEL", "rel_id": 3, "type": "anime"}]


def test_tk_presenter_smoke_workflows():
    statuses = []
    out = {}
    p = AnimeBrowserPresenter(FakeSDK(), InlineRunner(), status_cb=statuses.append)

    p.load_list(filter_name="DEFAULT", page=0, hide_rated=True, on_result=lambda r: out.setdefault("list", r), on_error=lambda e: out.setdefault("err", str(e)))
    p.search(query="naruto", limit=25, on_result=lambda r: out.setdefault("search", r), on_error=lambda e: out.setdefault("err", str(e)))
    p.search_torrents(terms=["naruto"], profile="interactive", limit=10, on_result=lambda r: out.setdefault("torrents", r), on_error=lambda e: out.setdefault("err", str(e)))
    p.get_settings(on_result=lambda r: out.setdefault("settings", r), on_error=lambda e: out.setdefault("err", str(e)))

    assert out["list"]["items"][0]["id"] == 1
    assert out["search"][0]["title"] == "naruto"
    assert out["torrents"][0]["name"] == "Torrent"
    assert out["settings"]["anime"]["hideRated"] is True
    assert statuses
