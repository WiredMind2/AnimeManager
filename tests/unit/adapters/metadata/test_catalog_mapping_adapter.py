"""Tests for catalog mapping HTTP adapter."""

from __future__ import annotations

from adapters.metadata.catalog_mapping_adapter import CatalogMappingAdapter


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payloads):
        self._payloads = payloads
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(("GET", url, timeout))
        return _FakeResponse(self._payloads["get"])

    def post(self, url, json=None, timeout=None):
        self.calls.append(("POST", url, json, timeout))
        return _FakeResponse(self._payloads["post"])


def test_lookup_kitsu_mappings_parses_cross_provider_ids():
    session = _FakeSession(
        {
            "get": {
                "included": [
                    {
                        "type": "mappings",
                        "attributes": {
                            "externalSite": "myanimelist/anime",
                            "externalId": "46488",
                        },
                    },
                    {
                        "type": "mappings",
                        "attributes": {
                            "externalSite": "anilist/anime",
                            "externalId": "128757",
                        },
                    },
                ]
            },
            "post": {},
        }
    )
    adapter = CatalogMappingAdapter(session=session)
    result = adapter.lookup_kitsu_mappings(44021)
    assert result == {
        "kitsu_id": 44021,
        "mal_id": 46488,
        "anilist_id": 128757,
    }


def test_lookup_mal_cross_ids_reads_anilist_idmal():
    session = _FakeSession(
        {
            "get": {},
            "post": {"data": {"Media": {"id": 128757, "idMal": 46488}}},
        }
    )
    adapter = CatalogMappingAdapter(session=session)
    result = adapter.lookup_mal_cross_ids(46488)
    assert result == {"mal_id": 46488, "anilist_id": 128757}
