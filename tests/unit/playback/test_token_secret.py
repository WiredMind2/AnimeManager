"""Tests for persistent playback HMAC secret."""

from __future__ import annotations

from application.playback.token_secret import load_or_create_playback_token_secret


def test_load_or_create_playback_token_secret_is_stable(tmp_path):
    first = load_or_create_playback_token_secret(tmp_path)
    second = load_or_create_playback_token_secret(tmp_path)
    assert first == second
    assert len(first) >= 32
    assert (tmp_path / "playback_token_secret").is_file()


def test_load_or_create_playback_token_secret_creates_parent(tmp_path):
    nested = tmp_path / "nested" / "appdata"
    secret = load_or_create_playback_token_secret(nested)
    assert secret
    assert nested.is_dir()
