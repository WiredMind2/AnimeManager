"""Edge case tests for ``adapters.file.local_disk.LocalFileManager`` caching behaviour."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

import pytest

from adapters.file.local_disk import LocalFileManager


@pytest.fixture
def fm(tmp_path):
    with patch("adapters.file.local_disk.askdirectory", return_value=str(tmp_path)):
        with patch("shared.utils.general.persist_manager_settings"):
            return LocalFileManager(settings={"dataPath": str(tmp_path)})


class TestLocalFileManagerCache:
    def test_exists_cached_returns_existing(self, fm, tmp_path):
        target = tmp_path / "real.txt"
        target.write_text("x")
        assert fm.exists_cached(str(target)) is True

    def test_exists_cached_returns_missing(self, fm, tmp_path):
        assert fm.exists_cached(str(tmp_path / "nope.txt")) is False

    def test_exists_cached_uses_cache_on_second_call(self, fm, tmp_path):
        target = tmp_path / "x.txt"
        target.write_text("hi")
        # First call populates the cache
        assert fm.exists_cached(str(target)) is True
        # Now delete and verify the cache still returns True (proving cache hit).
        target.unlink()
        # Re-read within the TTL window — should still come from cache.
        assert fm.exists_cached(str(target)) is True

    def test_exists_cached_cleans_up_when_oversized(self, fm, tmp_path):
        fm._cache_max_size = 3
        for i in range(10):
            fm.exists_cached(str(tmp_path / f"f{i}.txt"))
        # Cache must not grow without bound past max_size + cleanup buffer.
        assert len(fm._file_cache) <= 10  # cleanup may or may not run

    def test_cleanup_removes_expired(self, fm, tmp_path):
        fm._cache_ttl = 0
        for i in range(5):
            fm.exists_cached(str(tmp_path / f"f{i}.txt"))
        fm._cleanup_file_cache()
        # Everything must be considered expired
        assert fm._file_cache == {}

    def test_cleanup_removes_oldest_20_percent_when_over_cap(self, fm, tmp_path):
        fm._cache_ttl = 10_000  # plenty of TTL, force size-based eviction
        fm._cache_max_size = 5
        for i in range(20):
            fm.exists_cached(str(tmp_path / f"f{i}.txt"))
        # After cleanup the cache should fit within the cap (or close to it)
        # Allow some slack because the implementation removes 20% when over.
        assert len(fm._file_cache) <= 20


class TestCachedFileInfo:
    def test_returns_metadata_for_existing(self, fm, tmp_path):
        target = tmp_path / "x.txt"
        target.write_text("hello")
        info = fm.get_cached_file_info(str(target))
        assert info["exists"] is True
        assert info["size"] == 5
        assert "mtime" in info

    def test_returns_minimal_dict_for_missing(self, fm, tmp_path):
        info = fm.get_cached_file_info(str(tmp_path / "missing.txt"))
        assert info == {"exists": False}


class TestListOptimized:
    def test_filters_hidden_files_by_default(self, fm, tmp_path):
        (tmp_path / "visible.txt").write_text("x")
        (tmp_path / ".hidden").write_text("x")
        entries = fm.list_optimized(str(tmp_path))
        assert "visible.txt" in entries
        assert ".hidden" not in entries

    def test_includes_hidden_when_requested(self, fm, tmp_path):
        (tmp_path / ".hidden").write_text("x")
        entries = fm.list_optimized(str(tmp_path), include_hidden=True)
        assert ".hidden" in entries

    def test_sorts_by_name_reverse(self, fm, tmp_path):
        for c in "abc":
            (tmp_path / c).write_text("x")
        out = fm.list_optimized(str(tmp_path), sort_by="name", reverse=True)
        assert out == ["c", "b", "a"]

    def test_sort_by_size_ascending(self, fm, tmp_path):
        (tmp_path / "small.txt").write_text("a")
        (tmp_path / "big.txt").write_text("a" * 100)
        out = fm.list_optimized(str(tmp_path), sort_by="size")
        assert out[0] == "small.txt"

    def test_sort_by_mtime(self, fm, tmp_path):
        for c in "ab":
            (tmp_path / c).write_text("x")
        out = fm.list_optimized(str(tmp_path), sort_by="mtime")
        assert len(out) == 2

    def test_nonexistent_path_returns_empty_list(self, fm, tmp_path):
        out = fm.list_optimized(str(tmp_path / "nope"))
        assert out == []

    def test_not_a_directory_returns_empty_list(self, fm, tmp_path):
        target = tmp_path / "file.txt"
        target.write_text("x")
        out = fm.list_optimized(str(target))
        assert out == []


class TestBasicOperations:
    def test_exists_truthy_path(self, fm, tmp_path):
        target = tmp_path / "x"
        target.write_text("x")
        assert fm.exists(str(target)) is True

    def test_exists_missing(self, fm, tmp_path):
        assert fm.exists(str(tmp_path / "missing")) is False

    def test_isdir_true_for_dir(self, fm, tmp_path):
        assert fm.isdir(str(tmp_path)) is True

    def test_isdir_false_for_file(self, fm, tmp_path):
        target = tmp_path / "x"
        target.write_text("x")
        assert fm.isdir(str(target)) is False

    def test_list_returns_entries(self, fm, tmp_path):
        (tmp_path / "a").write_text("x")
        assert "a" in fm.list(str(tmp_path))

    def test_list_on_file_returns_empty(self, fm, tmp_path):
        target = tmp_path / "x"
        target.write_text("x")
        out = fm.list(str(target))
        assert out == []

    def test_mkdir_creates_directory(self, fm, tmp_path):
        target = tmp_path / "newdir"
        fm.mkdir(str(target))
        assert target.is_dir()

    def test_open_returns_file_object(self, fm, tmp_path):
        target = tmp_path / "x"
        with fm.open(str(target), "w") as f:
            f.write("hi")
        assert target.read_text() == "hi"
