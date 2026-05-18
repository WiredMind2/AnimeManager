"""Unit tests for the root launcher ``run.py``."""

from __future__ import annotations

from unittest.mock import MagicMock

import run as run_entry


class _FakeProc:
    def __init__(self, polls: list[int | None]) -> None:
        self._polls = list(polls)
        self.terminated = False
        self.killed = False

    def poll(self):
        if len(self._polls) > 1:
            return self._polls.pop(0)
        return self._polls[0]

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):  # noqa: ARG002
        return 0

    def kill(self):
        self.killed = True


def test_main_both_mode_calls_run_both(monkeypatch):
    called = {}

    def _fake_run_both(args):
        called["mode"] = args.mode
        return 7

    monkeypatch.setattr(run_entry, "_run_both", _fake_run_both)
    rc = run_entry.main(["both"])
    assert rc == 7
    assert called["mode"] == "both"


def test_run_both_returns_error_when_next_dir_missing(monkeypatch):
    parser = run_entry._build_parser()
    args = parser.parse_args(["both", "--next-dir", "missing-dir"])
    monkeypatch.setattr(run_entry.os.path, "isdir", lambda path: False)
    rc = run_entry._run_both(args)
    assert rc == 2


def test_run_both_returns_error_when_npm_missing(monkeypatch):
    parser = run_entry._build_parser()
    args = parser.parse_args(["both"])
    monkeypatch.setattr(run_entry.os.path, "isdir", lambda path: True)
    monkeypatch.setattr(run_entry, "_resolve_npm_executable", lambda _name: None)
    rc = run_entry._run_both(args)
    assert rc == 2


def test_run_both_starts_and_stops_processes(monkeypatch):
    parser = run_entry._build_parser()
    args = parser.parse_args(["both"])
    monkeypatch.setattr(run_entry.os.path, "isdir", lambda path: True)
    monkeypatch.setattr(run_entry, "_resolve_npm_executable", lambda _name: "C:\\nodejs\\npm.cmd")
    monkeypatch.setattr(run_entry.time, "sleep", lambda _: None)

    api = _FakeProc([None, 0])
    nxt = _FakeProc([None, None, 0])
    popen = MagicMock(side_effect=[api, nxt])
    monkeypatch.setattr(run_entry, "_popen_command", popen)

    rc = run_entry._run_both(args)
    assert rc == 0
    assert popen.call_count == 2
    # At least one process exits naturally; launcher should still return cleanly.
    assert api.poll() == 0
