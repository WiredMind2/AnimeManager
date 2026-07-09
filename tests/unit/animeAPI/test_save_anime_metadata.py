"""Tests for AnimeAPI.save metadata persistence."""

from __future__ import annotations

import queue
from unittest.mock import MagicMock

import pytest

from adapters.api import AnimeAPI
from adapters.persistence.models import Anime


@pytest.fixture
def anime_api():
    api = AnimeAPI.__new__(AnimeAPI)
    api.sql_queue = queue.Queue()
    api.handle_sql_queue = MagicMock()
    db = MagicMock()
    db.procedure.return_value = ((), [])
    api.getDatabase = MagicMock(return_value=db)
    return api, db


def test_save_anime_persists_metadata(anime_api):
    api, db = anime_api
    anime = Anime()
    anime["id"] = 7
    anime["title"] = "Test Title"
    anime["title_synonyms"] = ["Test Title", "Alt"]
    anime["genres"] = ["Action"]

    api.save(anime)

    db.procedure.assert_called_once()
    db.save_metadata.assert_called_once_with(
        7,
        {"title_synonyms": ["Test Title", "Alt"], "genres": ["Action"]},
    )


def test_save_anime_skips_metadata_when_empty(anime_api):
    api, db = anime_api
    anime = Anime()
    anime["id"] = 8
    anime["title"] = "Only Title"

    api.save(anime)

    db.procedure.assert_called_once()
    db.save_metadata.assert_not_called()
