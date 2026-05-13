import hashlib

import bencoding
import pytest

from adapters.legacy.legacy_classes import Episode, Torrent


@pytest.mark.timeout(30)
def test_episode_initialization_with_valid_data():
    """Test initialization of Episode with valid data."""
    episode_data = {
        "title": "Episode 1",
        "path": "/path/to/episode1.mkv",
        "season": 1,
        "episode": 1,
        "anime_id": 123,
        "duration": 24,
        "watched": True,
    }
    ep = Episode(**episode_data)

    assert ep.title == "Episode 1"
    assert ep.path == "/path/to/episode1.mkv"
    assert ep.season == 1
    assert ep.episode == 1
    assert ep.anime_id == 123
    assert ep.duration == 24
    assert ep.watched == True


@pytest.mark.timeout(30)
def test_episode_attribute_access():
    """Test attribute access for Episode."""
    ep = Episode()
    ep.title = "Test Episode"
    ep.path = "/test/path.mp4"
    ep.season = 2
    ep.episode = 5
    ep.anime_id = 456
    ep.duration = 30
    ep.watched = False

    assert ep.title == "Test Episode"
    assert ep.path == "/test/path.mp4"
    assert ep.season == 2
    assert ep.episode == 5
    assert ep.anime_id == 456
    assert ep.duration == 30
    assert ep.watched == False


@pytest.mark.timeout(30)
def test_episode_default_values():
    """Test default values for Episode."""
    ep = Episode()

    assert ep.season == 1
    assert ep.watched == False


@pytest.mark.timeout(30)
def test_episode_edge_cases():
    """Test edge cases for Episode initialization."""
    # Test with None values
    ep1 = Episode(title=None, path=None, episode=None)
    assert ep1.title is None
    assert ep1.path is None
    assert ep1.episode is None
    assert ep1.season == 1  # default
    assert ep1.watched == False  # default

    # Test with empty strings
    ep2 = Episode(title="", path="")
    assert ep2.title == ""
    assert ep2.path == ""

    # Test with invalid types (should still work as dict)
    ep3 = Episode(season="invalid", watched=1)
    assert ep3.season == "invalid"  # no type checking
    assert ep3.watched == 1


def _build_single_file_torrent_payload(
    name: bytes = b"my_anime.mkv",
    length: int = 12345,
    announce: bytes = b"udp://tracker.example.com:6969",
    announce_list: list[list[bytes]] | None = None,
) -> tuple[bytes, str]:
    info = {
        b"name": name,
        b"piece length": 16384,
        b"length": length,
        b"pieces": b"\x00" * 20,
    }
    meta: dict[bytes, object] = {b"announce": announce, b"info": info}
    if announce_list is not None:
        meta[b"announce-list"] = announce_list
    payload = bencoding.bencode(meta)
    expected_hash = hashlib.sha1(bencoding.bencode(info)).hexdigest()
    return payload, expected_hash


@pytest.mark.timeout(30)
def test_torrent_from_torrent_returns_object_for_single_file_payload():
    """Regression: ``from_torrent`` must return the parsed Torrent, not None,
    and must not raise on a valid bencoded payload."""
    payload, expected_hash = _build_single_file_torrent_payload()

    result = Torrent.from_torrent(payload)

    assert result is not None, "from_torrent() must return the parsed Torrent"
    assert isinstance(result, Torrent)
    assert result.hash == expected_hash
    assert len(result.hash) == 40, "BitTorrent infohash is SHA-1 hex (40 chars)"
    assert result.name == "my_anime.mkv"
    assert result.trackers == ["udp://tracker.example.com:6969"]
    assert result.size == 12345


@pytest.mark.timeout(30)
def test_torrent_from_torrent_handles_announce_list():
    """``announce-list`` tiers should be flattened into ``trackers``."""
    payload, _ = _build_single_file_torrent_payload(
        announce=b"udp://primary.example/announce",
        announce_list=[
            [b"udp://primary.example/announce"],
            [b"http://backup.example/announce", b"udp://backup2.example/announce"],
        ],
    )

    result = Torrent.from_torrent(payload)

    assert result is not None
    assert result.trackers == [
        "udp://primary.example/announce",
        "http://backup.example/announce",
        "udp://backup2.example/announce",
    ]


@pytest.mark.timeout(30)
def test_torrent_from_torrent_handles_multi_file_payload():
    """Multi-file torrents have no top-level ``length``; size sums files."""
    info = {
        b"name": b"season_pack",
        b"piece length": 16384,
        b"pieces": b"\x00" * 20,
        b"files": [
            {b"length": 1000, b"path": [b"ep01.mkv"]},
            {b"length": 2500, b"path": [b"ep02.mkv"]},
        ],
    }
    payload = bencoding.bencode({b"announce": b"udp://t.example", b"info": info})

    result = Torrent.from_torrent(payload)

    assert result is not None
    assert result.name == "season_pack"
    assert result.size == 3500


@pytest.mark.timeout(30)
def test_torrent_from_torrent_result_can_round_trip_to_magnet():
    """The parsed Torrent must be usable by the DownloadManager, which calls
    ``to_magnet()`` and feeds the magnet to the torrent client."""
    payload, expected_hash = _build_single_file_torrent_payload()

    torrent = Torrent.from_torrent(payload)
    magnet = torrent.to_magnet()

    assert magnet.startswith(f"magnet:?xt=urn:btih:{expected_hash}")
    assert "dn=my_anime.mkv" in magnet
    assert "tr=udp" in magnet
