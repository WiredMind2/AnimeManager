"""Tests for duplicate anime folder consolidation."""

from __future__ import annotations

from application.services.anime_folder_consolidation import (
    consolidate_all_duplicate_anime_folders,
    consolidate_duplicate_folders_for_anime,
)


def test_consolidate_merges_title_change_siblings(tmp_path):
    root = tmp_path / "Animes"
    old = root / "Tenkou saki no Seiso - 2210"
    new = root / "Oh Boy Was I Wrong About Her - 2210"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    (old / "ep01.mkv").write_bytes(b"old-ep1")
    (old / "ep02.mkv").write_bytes(b"old-ep2")
    (new / "ep01.mkv").write_bytes(b"old-ep1")  # identical duplicate
    (new / "ep03.mkv").write_bytes(b"new-ep3")

    redirects: list[tuple[str, str]] = []
    result = consolidate_duplicate_folders_for_anime(
        str(root),
        2210,
        preferred_paths=[str(new)],
        redirect_save_paths=lambda src, dst: redirects.append((src, dst)),
    )

    assert result is not None
    assert result.canonical_path == str(new)
    assert not old.exists()
    assert (new / "ep01.mkv").read_bytes() == b"old-ep1"
    assert (new / "ep02.mkv").read_bytes() == b"old-ep2"
    assert (new / "ep03.mkv").read_bytes() == b"new-ep3"
    assert redirects == [(str(old), str(new))]


def test_consolidate_keeps_conflicting_same_name_files(tmp_path):
    root = tmp_path / "Animes"
    a = root / "A Title - 7"
    b = root / "B Title - 7"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / "same.mkv").write_bytes(b"aaaa")
    (b / "same.mkv").write_bytes(b"bbbbbbbb")

    result = consolidate_duplicate_folders_for_anime(
        str(root),
        7,
        preferred_paths=[str(b)],
    )

    assert result is not None
    assert result.canonical_path == str(b)
    assert (b / "same.mkv").read_bytes() == b"bbbbbbbb"
    assert (b / "same (2).mkv").read_bytes() == b"aaaa"
    assert not a.exists()


def test_consolidate_all_skips_single_folder_ids(tmp_path):
    root = tmp_path / "Animes"
    (root / "Solo - 1").mkdir(parents=True)
    (root / "Left - 2").mkdir(parents=True)
    (root / "Right - 2").mkdir(parents=True)
    ((root / "Left - 2") / "a.mkv").write_bytes(b"a")
    ((root / "Right - 2") / "b.mkv").write_bytes(b"b")

    results = consolidate_all_duplicate_anime_folders(str(root))
    assert len(results) == 1
    assert results[0].anime_id == 2
    assert (root / "Solo - 1").is_dir()
