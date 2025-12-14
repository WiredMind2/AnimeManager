import pytest

from classes import Episode


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
