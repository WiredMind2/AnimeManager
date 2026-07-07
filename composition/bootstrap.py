"""Bootstrap helpers for the embedded runtime dependency graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from adapters.api import AnimeAPI
from adapters.file.local_episode_scanner import LocalEpisodeScanner
from application.services.database_manager import DatabaseManager
from shared.config import ConfigProvider
from shared.config.constants import Constants
from shared.config.getters import Getters
from shared.telemetry import LoggerService


@dataclass
class EmbeddedDeps:
    """Explicit collaborators wired at composition time."""

    constants: Constants
    config: ConfigProvider
    logger: LoggerService
    database: Any
    db_manager: DatabaseManager
    file_manager: Any
    torrent_manager: Any
    api: AnimeAPI
    scanner: LocalEpisodeScanner
    anime_path: str


class _BootstrapHost:
    """Minimal Getters host for one-shot manager initialization."""

    def __init__(
        self,
        *,
        constants: Constants,
        config: ConfigProvider,
        logger: LoggerService,
        api: AnimeAPI,
    ) -> None:
        self._config = config
        self._logger = logger
        self.__dict__.update(constants.__dict__)
        self.database = Getters.getDatabase(self)
        self.api = api

    def setSettings(self, settings):  # noqa: N802 - legacy naming
        updated = self._config.update_settings(settings)
        self.settings = updated
        return updated

    def log(self, *_args, **_kwargs):
        try:
            if _args:
                self._logger.log(*_args, **_kwargs)
        except Exception:  # pragma: no cover
            pass
        return None


def bootstrap_embedded_deps(*, api: Optional[AnimeAPI] = None) -> EmbeddedDeps:
    """Initialize database, file, and torrent managers for the embedded runtime."""
    constants = Constants()
    config = ConfigProvider(constants=constants)
    logger = LoggerService.from_defaults()
    api_instance = api if api is not None else AnimeAPI(apis="all")

    host = _BootstrapHost(
        constants=constants,
        config=config,
        logger=logger,
        api=api_instance,
    )
    Getters.getFileManager(host)
    Getters.getTorrentManager(host)

    db_manager = DatabaseManager()
    db_manager.set_database(host.database)

    anime_path = str(getattr(host, "animePath", "") or "")
    scanner = LocalEpisodeScanner(
        file_manager=host.fm,
        database=host.database,
        anime_path=anime_path,
    )

    return EmbeddedDeps(
        constants=constants,
        config=config,
        logger=logger,
        database=host.database,
        db_manager=db_manager,
        file_manager=host.fm,
        torrent_manager=host.tm,
        api=host.api,
        scanner=scanner,
        anime_path=anime_path,
    )
