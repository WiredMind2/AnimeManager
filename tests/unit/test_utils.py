import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from shared.utils.general import (dict_merge, merge_iter, new_iter, parse_args, peek,
                   persist_manager_settings, project_modules, project_stats)


class TestParseArgs:
    @pytest.mark.timeout(30)
    def test_parse_args_valid_keys(self):
        """Test parse_args with valid widget config keys."""
        mock_widget = MagicMock()
        mock_widget.config.return_value = {
            "bg": ("bg", "background", "Background", "", "white"),
            "fg": ("fg", "foreground", "Foreground", "", "black"),
            "text": ("text", "text", "Text", "", ""),
        }

        kwargs = {"bg": "red", "fg": "blue", "invalid": "ignored"}
        result = parse_args(mock_widget, kwargs)

        assert result == {"bg": "red", "fg": "blue"}
        assert "invalid" not in result

    @pytest.mark.timeout(30)
    def test_parse_args_no_valid_keys(self):
        """Test parse_args with no valid keys."""
        mock_widget = MagicMock()
        mock_widget.config.return_value = {"bg": ("bg", "", "", "", "")}

        kwargs = {"invalid1": "val1", "invalid2": "val2"}
        result = parse_args(mock_widget, kwargs)

        assert result == {}


class TestDictMerge:
    @pytest.mark.timeout(30)
    def test_dict_merge_basic(self):
        """Test basic dict_merge functionality."""
        a = {"x": 1, "y": 2}
        b = {"y": 3, "z": 4}
        result = dict_merge(a, b)

        assert result == {"x": 1, "y": 3, "z": 4}

    @pytest.mark.timeout(30)
    def test_dict_merge_empty(self):
        """Test dict_merge with empty dicts."""
        a = {}
        b = {"a": 1}
        result = dict_merge(a, b)

        assert result == {"a": 1}

    @pytest.mark.timeout(30)
    def test_dict_merge_no_overlap(self):
        """Test dict_merge with no overlapping keys."""
        a = {"a": 1}
        b = {"b": 2}
        result = dict_merge(a, b)

        assert result == {"a": 1, "b": 2}


class TestNewIter:
    @pytest.mark.timeout(30)
    def test_new_iter_basic(self):
        """Test new_iter yields first then rest."""
        first = "a"
        iter_list = ["b", "c", "d"]
        result = list(new_iter(first, iter(iter_list)))

        assert result == ["a", "b", "c", "d"]

    @pytest.mark.timeout(30)
    def test_new_iter_empty_iter(self):
        """Test new_iter with empty iterator."""
        first = "a"
        result = list(new_iter(first, iter([])))

        assert result == ["a"]


class TestMergeIter:
    @pytest.mark.timeout(30)
    def test_merge_iter_basic(self):
        """Test merge_iter yields from both iters."""
        a = ["x", "y"]
        b = ["z", "w"]
        result = list(merge_iter(iter(a), iter(b)))

        assert result == ["x", "y", "z", "w"]

    @pytest.mark.timeout(30)
    def test_merge_iter_empty_first(self):
        """Test merge_iter with empty first iter."""
        a = []
        b = ["a", "b"]
        result = list(merge_iter(iter(a), iter(b)))

        assert result == ["a", "b"]


class TestPeek:
    @pytest.mark.timeout(30)
    def test_peek_with_items(self):
        """Test peek returns first item and new iter."""
        items = ["a", "b", "c"]
        first, new_iter_obj = peek(iter(items))

        assert first == "a"
        assert list(new_iter_obj) == ["a", "b", "c"]

    @pytest.mark.timeout(30)
    def test_peek_empty_iter(self):
        """Test peek with empty iterator."""
        first, new_iter_obj = peek(iter([]))

        assert first is None
        assert list(new_iter_obj) == [None]


class TestProjectModules:
    @pytest.mark.timeout(30)
    def test_project_modules_basic(self):
        """Test project_modules analyzes imports."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test Python file
            test_file = os.path.join(tmpdir, "test.py")
            with open(test_file, "w") as f:
                f.write("from os import path\nimport sys\n")

            result = project_modules(tmpdir)

            assert "os" in result
            assert "sys" in result
            assert result["os"] == [(test_file, 1)]
            assert result["sys"] == [(test_file, 2)]

    @pytest.mark.timeout(30)
    def test_project_modules_ignore_dirs(self):
        """Test project_modules ignores specified directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create __pycache__ dir
            pycache_dir = os.path.join(tmpdir, "__pycache__")
            os.makedirs(pycache_dir)
            pycache_file = os.path.join(pycache_dir, "test.pyc")
            with open(pycache_file, "w") as f:
                f.write("dummy")

            # Create valid py file
            test_file = os.path.join(tmpdir, "valid.py")
            with open(test_file, "w") as f:
                f.write("import os\n")

            result = project_modules(tmpdir)

            assert "__pycache__" not in [
                os.path.basename(f[0]) for files in result.values() for f in files
            ]
            assert "os" in result


class TestPersistManagerSettings:
    @pytest.mark.timeout(30)
    def test_persist_manager_settings_basic(self):
        """Test persist_manager_settings saves to json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("shared.config.constants.Constants") as mock_constants:
                mock_constants.getAppdata.return_value = tmpdir
                settings_file = os.path.join(tmpdir, "settings.json")

                persist_manager_settings(
                    "file_managers", "test_manager", {"key": "value"}
                )

                assert os.path.exists(settings_file)
                with open(settings_file, "r") as f:
                    data = json.load(f)

                assert "file_managers" in data
                assert "test_manager" in data["file_managers"]
                assert data["file_managers"]["test_manager"]["key"] == "value"
                assert data["file_managers"]["last_fm_used"] == "test_manager"

    @pytest.mark.timeout(30)
    def test_persist_manager_settings_torrent_managers(self):
        """Test persist_manager_settings for torrent_managers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("shared.config.constants.Constants") as mock_constants:
                mock_constants.getAppdata.return_value = tmpdir
                settings_file = os.path.join(tmpdir, "settings.json")

                persist_manager_settings(
                    "torrent_managers", "test_tm", {"setting": "val"}
                )

                with open(settings_file, "r") as f:
                    data = json.load(f)

                assert "torrent_managers" in data
                assert data["torrent_managers"]["last_tm_used"] == "test_tm"


class TestProjectStats:
    @pytest.mark.timeout(30)
    def test_project_stats_basic(self):
        """Test project_stats counts files and lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            py_file = os.path.join(tmpdir, "test.py")
            with open(py_file, "w") as f:
                f.write("line1\nline2\nline3\n")

            txt_file = os.path.join(tmpdir, "test.txt")
            with open(txt_file, "w") as f:
                f.write("not counted")

            lines, files, folders, size = project_stats(tmpdir)

            assert lines == 4  # 3 lines + 1 for the file
            assert files == 1  # Only .py files
            assert folders == 0  # No subfolders
            assert size > 0

    @pytest.mark.timeout(30)
    def test_project_stats_ignore_dirs(self):
        """Test project_stats ignores specified directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create ignored dir
            ignore_dir = os.path.join(tmpdir, "__pycache__")
            os.makedirs(ignore_dir)
            ignored_file = os.path.join(ignore_dir, "ignored.py")
            with open(ignored_file, "w") as f:
                f.write("ignored\n")

            # Create valid file
            valid_file = os.path.join(tmpdir, "valid.py")
            with open(valid_file, "w") as f:
                f.write("valid\n")

            lines, files, folders, size = project_stats(tmpdir)

            assert lines == 2  # Only valid.py
            assert files == 1
