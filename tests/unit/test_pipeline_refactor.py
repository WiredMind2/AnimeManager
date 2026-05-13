from unittest.mock import patch

from ...application.services.database_manager import DatabaseManager
from ...application.services.download_manager import DownloadManager
from ...adapters.api.AnilistCo import AnilistCoWrapper


def test_download_manager_blocks_non_https_and_private_hosts():
    dm = DownloadManager()

    with patch("socket.gethostbyname", return_value="8.8.8.8"):
        assert dm._is_url_allowed("https://example.com/file.torrent") is True

    assert dm._is_url_allowed("http://example.com/file.torrent") is False

    with patch("socket.gethostbyname", return_value="127.0.0.1"):
        assert dm._is_url_allowed("https://localhost/file.torrent") is False


def test_database_manager_query_builder_sanitizes_unknown_criteria():
    manager = DatabaseManager()
    args = manager._build_query_args(
        criteria="UNTRUSTED",
        listrange=(-10, 0),
        hide_rated=True,
        user_id=4,
    )
    assert "anime.status != 'UPCOMING'" in args["filter"]
    assert args["range"] == (0, 1)


def test_anilist_iterate_respects_max_pages():
    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeSession:
        def __init__(self):
            self.page = 0

        def request(self, method, url, json):
            self.page += 1
            payload = {
                "data": {
                    "Page": {
                        "media": [{"id": self.page}],
                        "pageInfo": {
                            "currentPage": self.page,
                            "hasNextPage": True,
                        },
                    }
                }
            }
            return FakeResponse(payload)

    wrapper = AnilistCoWrapper.__new__(AnilistCoWrapper)
    wrapper.session = FakeSession()
    wrapper.url = "https://graphql.anilist.co"
    wrapper.log = lambda *args, **kwargs: None

    out = list(wrapper.iterate("query {}", {"max_pages": 2, "page": 1}))
    assert [item["id"] for item in out] == [1, 2]
