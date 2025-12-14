"""
Application components for the AnimeManager system.
Provides modular, event-driven architecture.
"""

from .application_controller import ApplicationController
from .database_manager import DatabaseManager
from .api_coordinator import APICoordinator
from .ui_manager import UIManager
from .media_manager import MediaManager
from .download_manager import DownloadManager
from .settings_manager import SettingsManager

__all__ = [
    'ApplicationController',
    'DatabaseManager',
    'APICoordinator',
    'UIManager',
    'MediaManager',
    'DownloadManager',
    'SettingsManager',
]