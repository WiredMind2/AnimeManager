"""Tests for stable episode file IDs."""

from __future__ import annotations

from application.playback.file_ids import (
    episode_file_id_for_path,
    episode_file_ids_match,
    find_episode_by_file_id,
    progress_for_file_id,
)


def test_episode_file_id_is_path_stable():
    path = "/library/show/Episode 01.mkv"
    assert episode_file_id_for_path(path) == episode_file_id_for_path(path)
    assert episode_file_id_for_path(path).startswith("ep-")


def test_legacy_and_stable_ids_match_by_digest():
    path = "/library/show/Episode 01.mkv"
    stable = episode_file_id_for_path(path)
    digest = stable.split("-", 1)[1]
    legacy = f"ep-0000-{digest}"
    assert episode_file_ids_match(legacy, stable)
    assert episode_file_ids_match(stable, legacy) is True


def test_find_episode_by_file_id_resolves_legacy_request():
    path = "/library/show/Episode 01.mkv"
    stable = episode_file_id_for_path(path)
    digest = stable.split("-", 1)[1]
    episodes = [{"file_id": stable, "path": path, "title": "Episode 01"}]
    found = find_episode_by_file_id(episodes, f"ep-0099-{digest}")
    assert found is not None
    assert found["file_id"] == stable


def test_progress_for_file_id_falls_back_to_legacy_key():
    path = "/library/show/Episode 01.mkv"
    stable = episode_file_id_for_path(path)
    digest = stable.split("-", 1)[1]
    legacy = f"ep-0000-{digest}"
    progress = {legacy: {"status": "IN_PROGRESS", "position_seconds": 42.0}}
    row = progress_for_file_id(progress, stable)
    assert row["status"] == "IN_PROGRESS"
    assert row["position_seconds"] == 42.0
