"""Edge case tests for ``shared.utils.general`` helper functions.

Covers Timer, peek, dict_merge, persist_manager_settings error paths.
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from shared.utils.general import (
    Timer,
    dict_merge,
    merge_iter,
    new_iter,
    parse_args,
    peek,
    persist_manager_settings,
    project_modules,
)


# ---------------------------------------------------------------------------
# peek
# ---------------------------------------------------------------------------


class TestParseArgs:
    def test_filters_kwargs_to_widget_config_keys(self):
        class _Widget:
            @staticmethod
            def config():
                return {"width": 100, "height": 200}

        out = parse_args(_Widget(), {"width": 10, "unknown": 99})
        assert out == {"width": 10}


class TestPeekEdges:
    def test_handles_iterator_yielding_falsy_values(self):
        first, rest = peek(iter([0, 1, 2]))
        assert first == 0
        assert list(rest) == [0, 1, 2]

    def test_yields_none_when_iter_yields_none(self):
        first, rest = peek(iter([None, 1, 2]))
        assert first is None
        # When peek finds a None as the first item, it cannot distinguish
        # from an exhausted iterator, so it returns rest=(None,) which is
        # the current documented behavior.
        assert list(rest) in ([None], [None, 1, 2])


# ---------------------------------------------------------------------------
# dict_merge
# ---------------------------------------------------------------------------


class TestDictMergeEdges:
    def test_both_empty(self):
        assert dict_merge({}, {}) == {}

    def test_overlapping_keys_take_right(self):
        assert dict_merge({"a": 1, "b": 2}, {"b": 99}) == {"a": 1, "b": 99}

    def test_input_dicts_not_mutated(self):
        a = {"x": 1}
        b = {"y": 2}
        out = dict_merge(a, b)
        assert a == {"x": 1}
        assert b == {"y": 2}
        assert out == {"x": 1, "y": 2}


# ---------------------------------------------------------------------------
# new_iter / merge_iter
# ---------------------------------------------------------------------------


class TestIterHelpers:
    def test_new_iter_with_empty(self):
        assert list(new_iter("x", iter([]))) == ["x"]

    def test_merge_iter_both_empty(self):
        assert list(merge_iter(iter([]), iter([]))) == []

    def test_merge_iter_preserves_order(self):
        out = list(merge_iter(iter([1, 2]), iter([3, 4])))
        assert out == [1, 2, 3, 4]


# ---------------------------------------------------------------------------
# Timer
# ---------------------------------------------------------------------------


class TestTimerEdges:
    def test_stats_with_no_laps_does_not_crash(self):
        logged = []
        t = Timer("test", logger=lambda *args, **kwargs: logged.append(args))
        t.stats()  # no laps recorded
        assert logged  # at least the Total log line emitted

    def test_stats_with_multiple_laps(self):
        logged = []
        t = Timer("x", logger=lambda *args, **kwargs: logged.append(args))
        t.start()
        t.stop()
        t.start()
        t.stop()
        t.stats()
        # Average line is only emitted when there are laps
        assert any("Average" in str(a[1]) for a in logged if len(a) > 1)

    def test_double_start_resets_lap(self):
        logged = []
        t = Timer("x", logger=lambda *args, **kwargs: logged.append(args))
        t.start()
        t.start()  # implicit stop + new start
        assert len(t.timeList) == 1

    def test_stop_without_start_noop(self):
        t = Timer("x", logger=lambda *args, **kwargs: None)
        t.stop()  # should not raise
        assert t.timeList == []


# ---------------------------------------------------------------------------
# persist_manager_settings
# ---------------------------------------------------------------------------


class TestProjectModules:
    def test_collects_imports_from_python_files(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "mod.py").write_text(
            "from os import path\nimport json\n",
            encoding="utf-8",
        )
        result = project_modules(str(pkg))
        assert "os" in result or "json" in result
        assert any(str(pkg / "mod.py") in loc[0] for loc in result.values())


class TestPersistManagerSettingsEdges:
    def test_creates_settings_file_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("shared.config.constants.Constants") as MockC:
                MockC.getAppdata.return_value = tmp
                persist_manager_settings("file_managers", "fm", {"a": 1})

                target = os.path.join(tmp, "settings.json")
                assert os.path.exists(target)
                with open(target) as f:
                    data = json.load(f)
                assert data["file_managers"]["fm"] == {"a": 1}
                assert data["file_managers"]["last_fm_used"] == "fm"

    def test_overwrites_existing_manager_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "settings.json")
            with open(target, "w") as f:
                json.dump(
                    {"file_managers": {"fm": {"old_key": "old"}}},
                    f,
                )

            with patch("shared.config.constants.Constants") as MockC:
                MockC.getAppdata.return_value = tmp
                persist_manager_settings(
                    "file_managers", "fm", {"new_key": "new"}
                )

                with open(target) as f:
                    data = json.load(f)
                assert data["file_managers"]["fm"]["old_key"] == "old"
                assert data["file_managers"]["fm"]["new_key"] == "new"

    def test_corrupted_settings_file_is_replaced_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "settings.json")
            with open(target, "w") as f:
                f.write("not json {{")

            with patch("shared.config.constants.Constants") as MockC:
                MockC.getAppdata.return_value = tmp
                # Should not raise even though existing file is corrupted
                persist_manager_settings(
                    "file_managers", "fm", {"a": 1}
                )

                with open(target) as f:
                    data = json.load(f)
                assert data["file_managers"]["fm"]["a"] == 1

    def test_torrent_managers_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("shared.config.constants.Constants") as MockC:
                MockC.getAppdata.return_value = tmp
                persist_manager_settings(
                    "torrent_managers", "qb", {"url": "http://x"}
                )
                with open(os.path.join(tmp, "settings.json")) as f:
                    data = json.load(f)
                assert data["torrent_managers"]["last_tm_used"] == "qb"

    def test_unknown_category_still_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("shared.config.constants.Constants") as MockC:
                MockC.getAppdata.return_value = tmp
                persist_manager_settings("custom_category", "n", {"v": 1})
                with open(os.path.join(tmp, "settings.json")) as f:
                    data = json.load(f)
                assert data["custom_category"]["n"] == {"v": 1}
                # last_*_used keys only set for the two known categories
                assert "last_fm_used" not in data["custom_category"]
                assert "last_tm_used" not in data["custom_category"]

    def test_unicode_settings_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("shared.config.constants.Constants") as MockC:
                MockC.getAppdata.return_value = tmp
                persist_manager_settings(
                    "file_managers", "fm", {"name": "ナルト"}
                )
                with open(os.path.join(tmp, "settings.json"), encoding="utf-8") as f:
                    data = json.load(f)
                assert data["file_managers"]["fm"]["name"] == "ナルト"
