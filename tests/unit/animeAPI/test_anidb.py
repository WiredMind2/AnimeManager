"""Unit tests for the AniDB provider (titles dump search + HTTP convert)."""

from __future__ import annotations

import gzip
import os
import threading

from adapters.api.AnidbNet import AnidbNetWrapper, _TitlesIndex
from adapters.api.provider_payload import provider_name_for_api_key
from shared.contracts import ProviderName


TITLES_XML = b"""<?xml version="1.0"?>
<animetitles>
  <anime aid="1">
    <title xml:lang="x-jat" type="main">Seikai no Monshou</title>
    <title xml:lang="en" type="official">Crest of the Stars</title>
    <title xml:lang="en" type="synonym">Banner of the Stars Prequel</title>
  </anime>
  <anime aid="2">
    <title xml:lang="x-jat" type="main">Naruto</title>
    <title xml:lang="en" type="official">Naruto</title>
  </anime>
  <anime aid="3">
    <title xml:lang="x-jat" type="main">Naruto Shippuuden</title>
    <title xml:lang="en" type="official">Naruto Shippuden</title>
  </anime>
</animetitles>
"""


DETAIL_XML = """<?xml version="1.0"?>
<anime id="1" restricted="false" episodecount="13">
  <titles>
    <title xml:lang="x-jat" type="main">Seikai no Monshou</title>
    <title xml:lang="en" type="official">Crest of the Stars</title>
  </titles>
  <description>A space opera.[source]AniDB[/source]</description>
  <startdate>1999-01-02</startdate>
  <enddate>1999-03-27</enddate>
  <picture>12345.jpg</picture>
  <categories>
    <category id="1" weight="600">
      <name>Action</name>
    </category>
    <category id="2" weight="400">
      <name>Sci-Fi</name>
    </category>
  </categories>
  <relatedanime>
    <anime id="4" type="Sequel">Seikai no Senki</anime>
  </relatedanime>
  <resources>
    <resource type="2">
      <externalentity>
        <identifier>62604</identifier>
      </externalentity>
    </resource>
    <resource type="43">
      <externalentity>
        <identifier>138380</identifier>
      </externalentity>
    </resource>
  </resources>
</anime>
"""


def _make_wrapper(tmp_path, monkeypatch, *, client: str = "testclient") -> AnidbNetWrapper:
    from adapters.api.APIUtils import APIUtils

    inst = object.__new__(AnidbNetWrapper)
    APIUtils.__init__(inst)
    inst.apiKey = "anidb_id"
    inst.client = client
    inst.clientver = "1"
    inst.cooldown = 0
    inst.last = 0
    inst._titles = _TitlesIndex()
    inst._titles_lock = threading.RLock()
    inst._http_lock = threading.Lock()
    inst._cache_dir = str(tmp_path / "anidb")
    os.makedirs(inst._cache_dir, exist_ok=True)
    inst.session = None
    inst.resolve_catalog_id = lambda ids: 100 + int(ids.get("anidb_id", 0))
    inst.save_pictures = lambda *a, **k: None
    inst.save_genres = lambda *a, **k: None
    inst.save_relations = lambda *a, **k: None
    inst.log = lambda *a, **k: None
    return inst


def test_provider_name_maps_anidb_id():
    assert provider_name_for_api_key("anidb_id") == ProviderName.ANIDB
    assert ProviderName.ANIDB.value == "anidb"


def test_titles_index_search_ranks_exact_and_prefix():
    index = _TitlesIndex()
    count = index.load_xml(TITLES_XML)
    assert count == 3

    hits = index.search("Naruto", limit=10)
    assert hits
    assert hits[0][0] == 2  # exact "Naruto" before Shippuden
    assert hits[0][1] == "Naruto"

    crest = index.search("Crest of the Stars", limit=5)
    assert crest and crest[0][0] == 1


def test_search_anime_uses_titles_dump_without_http(tmp_path, monkeypatch):
    wrapper = _make_wrapper(tmp_path, monkeypatch)
    dump_path = wrapper._titles_dump_path()
    with gzip.open(dump_path, "wb") as fh:
        fh.write(TITLES_XML)

    # Poison session so any HTTP would fail the test.
    class _Boom:
        def request(self, *a, **k):
            raise AssertionError("search must not hit HTTP")

    wrapper.session = _Boom()

    results = list(wrapper.searchAnime("Crest", limit=5))
    assert len(results) == 1
    assert results[0]["title"] == "Seikai no Monshou"
    assert results[0]["id"] == 101
    assert "Crest of the Stars" in results[0]["title_synonyms"]


def test_convert_anime_parses_http_xml(tmp_path, monkeypatch):
    wrapper = _make_wrapper(tmp_path, monkeypatch)
    from xml.etree.ElementTree import fromstring

    root = fromstring(DETAIL_XML)
    anime = wrapper._convertAnime(root)
    assert anime
    assert anime["id"] == 101
    assert anime["title"] == "Seikai no Monshou"
    assert anime["episodes"] == 13
    assert anime["picture"].endswith("12345.jpg")
    assert "space opera" in (anime["synopsis"] or "").lower()
    assert anime["date_from"] is not None
    assert "Action" in anime["genres"]


def test_convert_anime_extracts_cross_provider_ids(tmp_path, monkeypatch):
    wrapper = _make_wrapper(tmp_path, monkeypatch)
    captured = {}

    def _resolve(ids):
        captured.update(ids)
        return 42

    wrapper.resolve_catalog_id = _resolve
    from xml.etree.ElementTree import fromstring

    wrapper._convertAnime(fromstring(DETAIL_XML))
    assert captured["anidb_id"] == 1
    assert captured["mal_id"] == 62604
    assert captured["anilist_id"] == 138380


def test_anime_detail_uses_disk_cache(tmp_path, monkeypatch):
    wrapper = _make_wrapper(tmp_path, monkeypatch)
    cache_path = wrapper._anime_cache_path(1)
    with open(cache_path, "w", encoding="utf-8") as fh:
        fh.write(DETAIL_XML)

    class _Boom:
        def request(self, *a, **k):
            raise AssertionError("cached detail must not hit HTTP")

    wrapper.session = _Boom()
    wrapper.getId = lambda _id: 1

    result = wrapper.anime(999)
    assert result
    assert result["title"] == "Seikai no Monshou"


def test_anime_detail_skips_without_client(tmp_path, monkeypatch):
    wrapper = _make_wrapper(tmp_path, monkeypatch, client="")
    wrapper.getId = lambda _id: 1
    assert wrapper.anime(1) == {}


def test_wrapper_has_no_browse_methods():
    """AniDB must stay out of season/genre/top/schedule fan-out."""
    for name in ("season", "genre", "top", "schedule"):
        assert not hasattr(AnidbNetWrapper, name)
    assert AnidbNetWrapper.parallel_search is False


def test_provider_name_from_spec_anidb():
    from application.services.api_coordinator import _provider_name_from_spec

    assert _provider_name_from_spec("AnidbNetWrapper") == ProviderName.ANIDB
