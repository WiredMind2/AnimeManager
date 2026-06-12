from __future__ import annotations

import os
from pathlib import Path

import pytest

import bootstrap


def test_list_modes_includes_web():
    assert "web" in bootstrap.list_modes()


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("0.0.0.0", "127.0.0.1"),
        ("::", "127.0.0.1"),
        ("127.0.0.1", "127.0.0.1"),
        ("192.168.1.5", "192.168.1.5"),
    ],
)
def test_loopback_host(host, expected):
    assert bootstrap._loopback_host(host) == expected


def test_service_origin_uses_loopback_for_wildcard_bind():
    assert bootstrap._service_origin("0.0.0.0", 8081) == "http://127.0.0.1:8081"


def test_web_prerequisite_error_requires_node_modules(tmp_path, monkeypatch):
    next_web_dir = tmp_path / "next-web"
    next_web_dir.mkdir()
    (next_web_dir / "package.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(bootstrap.shutil, "which", lambda _name: "/usr/bin/npm")
    assert bootstrap._web_prerequisite_error(str(next_web_dir)) == 2


def test_web_prerequisite_error_ok_when_ready(monkeypatch):
    repo = Path(bootstrap._repo_root())
    next_web_dir = repo / "next-web"
    if not (next_web_dir / "package.json").is_file():
        pytest.skip("next-web package.json not present")
    if not (next_web_dir / "node_modules").is_dir():
        pytest.skip("next-web node_modules not installed")

    monkeypatch.setattr(bootstrap.shutil, "which", lambda _name: "/usr/bin/npm")
    assert bootstrap._web_prerequisite_error(str(next_web_dir)) is None


def test_main_unknown_mode():
    assert bootstrap.main(mode="not-a-mode") == 2
