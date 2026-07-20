"""Resolve anime library folders and scan on-disk episode files."""

from __future__ import annotations

import os
import re
from typing import Any

from adapters.persistence.models import Anime
from shared.utils.folder_names import (
    choose_canonical_anime_folder_name,
    format_anime_folder_name,
    match_anime_folder_names,
)


class LocalEpisodeScanner:
    """Filesystem scanner for locally downloaded anime episodes."""

    def __init__(
        self,
        *,
        file_manager: Any,
        database: Any,
        anime_path: str,
    ) -> None:
        self._fm = file_manager
        self._database = database
        self._anime_path = str(anime_path or "").strip()

    def resolve_anime_folder(self, anime_id: int) -> str:
        """Return the on-disk folder path for ``anime_id``."""
        if not self._anime_path or self._fm is None:
            return ""

        anime = self._database.get(id=anime_id, table="anime")
        if anime is None:
            return ""

        if not isinstance(anime, Anime):
            anime = Anime(anime)

        try:
            folder_names = self._fm.list(self._anime_path)
        except Exception:
            folder_names = []

        existing = [
            name
            for name in match_anime_folder_names(folder_names or [], anime_id)
            if self._fm.isdir(f"{self._anime_path}/{name}")
        ]
        if existing:
            folder_name = choose_canonical_anime_folder_name(
                existing,
                animes_root=self._anime_path,
            )
            return f"{self._anime_path}/{folder_name}"

        folder_name = format_anime_folder_name(anime.title, anime_id)
        return f"{self._anime_path}/{folder_name}"

    def scan_episodes(self, folder: str) -> list[dict[str, Any]]:
        """List video files under ``folder`` with parsed season/episode metadata."""
        if not folder or folder in ("", None) or self._fm is None:
            return []
        if not self._fm.exists(folder):
            return []

        def folder_lister(root: str):
            if root in {"", None} or not self._fm.exists(root):
                return
            files: list[str] = []
            folders: list[str] = []
            for entry in self._fm.list(root):
                path = f"{root}/{entry}"
                if self._fm.isdir(path):
                    folders.append(path)
                else:
                    files.append(path)
            yield files
            for sub in folders:
                yield from folder_lister(sub)

        out: list[dict[str, Any]] = []
        video_suffixes = ("mkv", "mp4", "avi")
        root = folder.rstrip("/") + "/"
        publisher_pattern = re.compile(r"^\[(.*?)\]")
        eps_patterns = [
            re.compile(p)
            for p in (r"-\s(\d+)", r"(?:E|Episode|Ep|Eps)(\d+)", r" (\d+) ")
        ]
        season_patterns = [
            re.compile(p)
            for p in (
                r"(?:S|Season|Seasons)\s?([0-9]{1,2})",
                r"([0-9])(?:|st|nd|rd|th)\s?(?:S|Season|Seasons)",
            )
        ]

        for file_batch in folder_lister(root):
            eps: list[dict[str, Any]] = []
            for file_path in file_batch:
                if not self._fm.isfile(file_path):
                    continue
                if file_path.rsplit(".", 1)[-1].lower() not in video_suffixes:
                    continue

                filename = os.path.basename(file_path)
                episode = "?"
                for pattern in eps_patterns:
                    match = re.findall(pattern, filename)
                    if match:
                        episode = match[0]
                        break
                if episode == "?":
                    episode = str(len(eps) + 1).zfill(2)

                season = 0
                for pattern in season_patterns:
                    match = re.findall(pattern, file_path)
                    if match:
                        season = match[0]
                        break

                title = filename.rsplit(".", 1)[0]
                title = re.sub(r"([\._])", " ", title)
                title = re.sub(r"  +?", "", title)
                eps.append(
                    {
                        "title": title,
                        "path": file_path,
                        "season": season,
                        "episode": episode,
                    }
                )

            eps.sort(
                key=lambda row: int(
                    str(row["season"]).zfill(5) + str(row["episode"]).zfill(5)
                )
            )
            out.extend(eps)

        return out
