"""Round-trip tests for SQLite ``save_metadata`` diff semantics."""

from __future__ import annotations

from adapters.persistence.dbManager import db_instance


def test_save_metadata_sqlite_insert_delete_diff_roundtrip(tmp_path):
    _ = tmp_path  # keep fixture for parity with other db-manager tests
    db = db_instance(":memory:")
    ensure_connection = getattr(db, "_ensure_connection", None) or getattr(
        db, "_create_connection", None
    )
    if callable(ensure_connection):
        ensure_connection()
    # ``db_instance`` historically bypasses BaseDB.__init__; prime cache fields
    # so BaseDB.sql() can run in isolation here.
    db._query_cache = {}
    db._cache_timestamps = {}
    db._cache_ttl = 300
    db._cache_max_size = 1000
    db._cache_stats = {"hits": 0, "misses": 0, "evictions": 0}

    def _flush_caches() -> None:
        if hasattr(db, "invalidate_cache"):
            db.invalidate_cache()
        cache = getattr(db, "query_cache", None)
        if cache is not None and hasattr(cache, "clear"):
            cache.clear()

    def _select_values(anime_id: int):
        db.execute(
            "SELECT value FROM title_synonyms WHERE id=? ORDER BY value",
            (anime_id,),
        )
        return [row[0] for row in db.cur.fetchall()]

    try:
        db.sql(
            "CREATE TABLE title_synonyms(id INTEGER NOT NULL, value TEXT NOT NULL)",
            (),
            save=False,
            use_cache=False,
        )
        anime_id = 2210
        db.save_metadata(
            anime_id,
            {
                "title_synonyms": ["Chaos;Head", "ChaoSHEAd"],
            },
        )
        db.save()
        _flush_caches()

        first_synonyms = _select_values(anime_id)
        assert first_synonyms == ["ChaoSHEAd", "Chaos;Head"]

        db.save_metadata(
            anime_id,
            {
                "title_synonyms": ["Chaos;Head", "CHAOS HEAD NOAH"],
            },
        )
        db.save()
        _flush_caches()

        second_synonyms = _select_values(anime_id)
        assert second_synonyms == [
            "CHAOS HEAD NOAH",
            "Chaos;Head",
        ]
    finally:
        if hasattr(db, "cur"):
            db.close()
        if hasattr(db, "con"):
            db.con.close()
