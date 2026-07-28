"""Unit tests for auto-download preference and candidate matching."""

from __future__ import annotations

from types import SimpleNamespace

from adapters.search.title_parser import parse_title
from application.services.auto_download_matching import (
    ReleasePreference,
    find_matching_candidate,
    infer_preference,
    next_episode,
    owned_episodes_from_files,
    owned_episodes_from_torrents,
)
from application.services.auto_download_service import AutoDownloadService


def test_infer_preference_majority_vote():
    rows = [
        {
            "name": "[SubsPlease] Show - 01 (1080p) [AABBCCDD].mkv",
            "status": "complete",
        },
        {
            "name": "[SubsPlease] Show - 02 (1080p) [AABBCCDE].mkv",
            "status": "complete",
        },
        {
            "name": "[Erai-raws] Show - 03 [720p].mkv",
            "status": "complete",
        },
    ]
    pref = infer_preference(rows, parse_title=parse_title)
    assert pref is not None
    assert pref.publisher == "subsplease"
    assert pref.resolution == "1080p"


def test_infer_preference_tie_uses_most_recent():
    rows = [
        {
            "name": "[SubsPlease] Show - 01 (1080p) [AA].mkv",
            "status": "complete",
        },
        {
            "name": "[Erai-raws] Show - 02 [720p].mkv",
            "status": "complete",
        },
    ]
    pref = infer_preference(rows, parse_title=parse_title)
    assert pref is not None
    assert pref.publisher == "erai-raws"
    assert pref.resolution == "720p"


def test_infer_preference_skips_deleted_and_unparsable():
    rows = [
        {
            "name": "[SubsPlease] Show - 01 (1080p) [AA].mkv",
            "status": "deleted",
        },
        {"name": "random noise without facets", "status": "complete"},
    ]
    assert infer_preference(rows, parse_title=parse_title) is None


def test_owned_and_next_episode():
    rows = [
        {
            "name": "[SubsPlease] Show - 01 (1080p) [AA].mkv",
            "status": "complete",
        },
        {
            "name": "[SubsPlease] Show - 03 (1080p) [BB].mkv",
            "status": "complete",
        },
        {
            "name": "[SubsPlease] Show (01-12) (1080p) [Batch]",
            "status": "complete",
        },
    ]
    owned = owned_episodes_from_torrents(rows, parse_title=parse_title)
    owned |= owned_episodes_from_files([{"episode": "02"}, {"episode": "?"}])
    assert owned == {1, 2, 3}
    assert next_episode(owned) == 4
    assert next_episode([]) == 1


def test_find_matching_candidate_filters_and_picks_seeds():
    preference = ReleasePreference(publisher="subsplease", resolution="1080p")
    results = [
        {
            "name": "low seeds",
            "infohash": "aaa",
            "seeds": 5,
            "link": "magnet:?xt=urn:btih:aaa",
            "parsed": {
                "publisher": "subsplease",
                "resolution": "1080p",
                "episode_kind": "single",
                "episode": 4,
                "is_batch": False,
            },
        },
        {
            "name": "best",
            "infohash": "bbb",
            "seeds": 50,
            "link": "magnet:?xt=urn:btih:bbb",
            "parsed": {
                "publisher": "subsplease",
                "resolution": "1080p",
                "episode_kind": "single",
                "episode": 4,
                "is_batch": False,
            },
        },
        {
            "name": "wrong pub",
            "infohash": "ccc",
            "seeds": 99,
            "link": "magnet:?xt=urn:btih:ccc",
            "parsed": {
                "publisher": "erai-raws",
                "resolution": "1080p",
                "episode_kind": "single",
                "episode": 4,
                "is_batch": False,
            },
        },
        {
            "name": "batch",
            "infohash": "ddd",
            "seeds": 99,
            "link": "magnet:?xt=urn:btih:ddd",
            "parsed": {
                "publisher": "subsplease",
                "resolution": "1080p",
                "episode_kind": "range",
                "episode": None,
                "is_batch": True,
            },
        },
    ]
    match = find_matching_candidate(
        results, preference=preference, episode=4, exclude_hashes={"aaa"}
    )
    assert match is not None
    assert match["infohash"] == "bbb"


def test_auto_download_service_run_once_queues_match():
    started: list[dict] = []

    class FakeUserActions:
        def list_auto_download_eligible(self, user_id=1):
            return [42]

        def get_download_preferences(self, anime_id, user_id):
            return {
                "source_mode": "search",
                "publisher": None,
                "resolution": "1080p",
                "feed_ids": [],
                "use_inferred": True,
            }

    class FakeRepo:
        def get_anime_torrents(self, anime_id):
            return [
                {
                    "hash": "old",
                    "name": "[SubsPlease] Show - 01 (1080p) [AA].mkv",
                    "status": "complete",
                }
            ]

        def get_search_terms(self, anime_id):
            return ["Show"]

    class FakeDownload:
        def search_torrents(self, terms, profile="interactive", limit=None, allow_nsfw=False):
            return [
                {
                    "name": "[SubsPlease] Show - 02 (1080p) [BB].mkv",
                    "infohash": "newhash",
                    "seeds": 10,
                    "link": "magnet:?xt=urn:btih:newhash",
                    "parsed": parse_title(
                        "[SubsPlease] Show - 02 (1080p) [BB].mkv"
                    ).as_dict(),
                }
            ]

        def start_download(
            self,
            anime_id,
            url=None,
            hash_value=None,
            user_id=None,
            source=None,
        ):
            started.append(
                {
                    "anime_id": anime_id,
                    "url": url,
                    "hash_value": hash_value,
                    "user_id": user_id,
                    "source": source,
                }
            )
            return True

    service = AutoDownloadService(
        user_actions=FakeUserActions(),
        anime_repository=FakeRepo(),
        download_port=FakeDownload(),
        media_library=SimpleNamespace(list_episode_files=lambda _id: []),
        parse_title=parse_title,
        cooldown_s=0,
    )
    outcome = service.run_once(force=True)
    assert outcome.checked == 1
    assert outcome.downloaded == 1
    assert started
    assert started[0]["source"] == "auto"
    assert started[0]["anime_id"] == 42


def test_auto_download_service_skips_when_disabled_list_empty():
    class FakeUserActions:
        def list_auto_download_eligible(self, user_id=1):
            return []

    service = AutoDownloadService(
        user_actions=FakeUserActions(),
        anime_repository=SimpleNamespace(),
        download_port=SimpleNamespace(),
        parse_title=parse_title,
        cooldown_s=0,
    )
    outcome = service.run_once(force=True)
    assert outcome.checked == 0
    assert outcome.downloaded == 0


def test_auto_download_service_respects_global_kill_switch():
    class FakeUserActions:
        def list_auto_download_eligible(self, user_id=1):
            return [1]

    service = AutoDownloadService(
        user_actions=FakeUserActions(),
        anime_repository=SimpleNamespace(),
        download_port=SimpleNamespace(),
        parse_title=parse_title,
        cooldown_s=0,
        settings_provider=lambda: {"auto_download": {"enabled": False}},
    )
    outcome = service.run_once(force=True)
    assert outcome.checked == 0
    assert "global auto-download disabled" in outcome.details[0]


def test_auto_download_cold_start_episode_one_with_defaults():
    started: list[dict] = []

    class FakeUserActions:
        def list_auto_download_eligible(self, user_id=1):
            return [7]

        def get_download_preferences(self, anime_id, user_id):
            return {
                "source_mode": "search",
                "publisher": None,
                "resolution": None,
                "feed_ids": [],
                "use_inferred": True,
            }

    class FakeRepo:
        def get_anime_torrents(self, anime_id):
            return []

        def get_search_terms(self, anime_id):
            return ["Brand New Show"]

    class FakeDownload:
        def search_torrents(self, terms, profile="interactive", limit=None, allow_nsfw=False):
            return [
                {
                    "name": "[SubsPlease] Brand New Show - 01 (1080p) [AA].mkv",
                    "infohash": "ep1",
                    "seeds": 20,
                    "link": "magnet:?xt=urn:btih:ep1",
                    "parsed": parse_title(
                        "[SubsPlease] Brand New Show - 01 (1080p) [AA].mkv"
                    ).as_dict(),
                }
            ]

        def start_download(self, anime_id, url=None, hash_value=None, user_id=None, source=None):
            started.append({"anime_id": anime_id, "hash_value": hash_value, "source": source})
            return True

    service = AutoDownloadService(
        user_actions=FakeUserActions(),
        anime_repository=FakeRepo(),
        download_port=FakeDownload(),
        media_library=SimpleNamespace(list_episode_files=lambda _id: []),
        parse_title=parse_title,
        cooldown_s=0,
        settings_provider=lambda: {
            "anime": {"topPublishers": ["SubsPlease"]},
            "auto_download": {"enabled": True, "default_resolution": "1080p"},
        },
    )
    outcome = service.run_once(force=True)
    assert outcome.downloaded == 1
    assert started[0]["hash_value"] == "ep1"


def test_auto_download_rss_mode_queues_match():
    started: list[dict] = []
    seen: list[tuple[str, str]] = []

    class FakeUserActions:
        def list_auto_download_eligible(self, user_id=1):
            return [9]

        def get_download_preferences(self, anime_id, user_id):
            return {
                "source_mode": "rss",
                "publisher": "subsplease",
                "resolution": "1080p",
                "feed_ids": ["subsplease-1080"],
                "use_inferred": False,
            }

        def list_rss_feed_seen_keys(self, feed_ids=None):
            return set()

        def mark_rss_feed_seen(self, feed_id, item_key):
            seen.append((feed_id, item_key))

    class FakeRepo:
        def get_anime_torrents(self, anime_id):
            return [
                {
                    "hash": "old",
                    "name": "[SubsPlease] Show - 01 (1080p) [AA].mkv",
                    "status": "complete",
                }
            ]

        def get_search_terms(self, anime_id):
            return ["Show"]

    class FakeDownload:
        def start_download(self, anime_id, url=None, hash_value=None, user_id=None, source=None):
            started.append({"url": url, "source": source})
            return True

    class FakeFetcher:
        def fetch_many(self, feeds):
            from adapters.feeds.rss_feed_adapter import RssFeedEntry

            assert feeds[0]["id"] == "subsplease-1080"
            return [
                RssFeedEntry(
                    feed_id="subsplease-1080",
                    item_key="g2",
                    title="[SubsPlease] Show - 02 (1080p) [BB].mkv",
                    link="https://example.com/2",
                    enclosure_url="magnet:?xt=urn:btih:rss2",
                )
            ]

    from adapters.feeds.rss_match import find_rss_candidate

    service = AutoDownloadService(
        user_actions=FakeUserActions(),
        anime_repository=FakeRepo(),
        download_port=FakeDownload(),
        media_library=SimpleNamespace(list_episode_files=lambda _id: []),
        parse_title=parse_title,
        cooldown_s=0,
        settings_provider=lambda: {
            "auto_download": {
                "enabled": True,
                "feeds": {
                    "builtin": [
                        {
                            "id": "subsplease-1080",
                            "label": "SP",
                            "url": "https://example.com/rss",
                            "enabled": True,
                        }
                    ],
                    "custom": [],
                },
            }
        },
        feed_fetcher=FakeFetcher(),
        rss_match_fn=find_rss_candidate,
    )
    outcome = service.run_once(force=True)
    assert outcome.downloaded == 1
    assert started[0]["source"] == "auto"
    assert "magnet:" in started[0]["url"]
    assert seen == [("subsplease-1080", "g2")]
