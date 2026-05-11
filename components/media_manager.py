"""
MediaManager component for handling media playback.
Implements player factory and state management for media playback.
"""

import threading
from typing import Optional, Any, Dict, List

from ..core import BaseComponent
from media_players import MediaPlayers


class MediaManager(BaseComponent):
    """
    Manages media playback with player factory and state management.
    Handles player selection, initialization, and playback events.
    """

    def __init__(self):
        super().__init__("MediaManager")
        self._media_players = None
        self._current_player = None
        self._players_order = []
        self._player_lock = threading.RLock()

    def _initialize(self) -> None:
        """Initialize the media manager."""
        self.log("MEDIA_MANAGER", "Initializing Media Manager")

        # Subscribe to media-related events
        self.subscribe_event("media.play", self._handle_play)
        self.subscribe_event("media.pause", self._handle_pause)
        self.subscribe_event("media.stop", self._handle_stop)
        self.subscribe_event("media.seek", self._handle_seek)

    def _start(self) -> None:
        """Start the media manager."""
        self.log("MEDIA_MANAGER", "Starting Media Manager")

        # Initialize media players if not in remote mode
        if not self._is_remote_mode():
            self._initialize_media_players()

    def _stop(self) -> None:
        """Stop the media manager."""
        with self._player_lock:
            if self._current_player:
                try:
                    self._current_player.stop()
                except Exception as e:
                    self.log("MEDIA_MANAGER", f"Error stopping player: {e}")

            if self._media_players:
                try:
                    # MediaPlayers cleanup if needed
                    pass
                except Exception as e:
                    self.log("MEDIA_MANAGER", f"Error cleaning up media players: {e}")

        self.log("MEDIA_MANAGER", "Media Manager stopped")

    def set_media_players(self, media_players: MediaPlayers) -> None:
        """
        Set the media players instance.

        Args:
            media_players: MediaPlayers instance
        """
        self._media_players = media_players

    def set_players_order(self, order: List[str]) -> None:
        """
        Set the preferred order of media players.

        Args:
            order: List of player names in preference order
        """
        self._players_order = order
        self._select_player()

    def get_current_player(self) -> Optional[Any]:
        """
        Get the currently selected media player.

        Returns:
            Current player instance or None
        """
        with self._player_lock:
            return self._current_player

    def play_file(self, file_path: str, **kwargs) -> bool:
        """
        Play a media file.

        Args:
            file_path: Path to the media file
            **kwargs: Additional player-specific arguments

        Returns:
            True if playback started successfully, False otherwise
        """
        with self._player_lock:
            if not self._current_player:
                self.log("MEDIA_MANAGER", "[ERROR] - No media player available")
                return False

            try:
                result = self._current_player.play(file_path, **kwargs)
                if result:
                    self.publish_event("media.playback_started", {"file": file_path})
                return result
            except Exception as e:
                self.log("MEDIA_MANAGER", f"Error playing file {file_path}: {e}")
                return False

    def pause(self) -> bool:
        """
        Pause current playback.

        Returns:
            True if paused successfully, False otherwise
        """
        with self._player_lock:
            if not self._current_player:
                return False

            try:
                result = self._current_player.pause()
                if result:
                    self.publish_event("media.playback_paused")
                return result
            except Exception as e:
                self.log("MEDIA_MANAGER", f"Error pausing playback: {e}")
                return False

    def stop(self) -> bool:
        """
        Stop current playback.

        Returns:
            True if stopped successfully, False otherwise
        """
        with self._player_lock:
            if not self._current_player:
                return False

            try:
                result = self._current_player.stop()
                if result:
                    self.publish_event("media.playback_stopped")
                return result
            except Exception as e:
                self.log("MEDIA_MANAGER", f"Error stopping playback: {e}")
                return False

    def seek(self, position: float) -> bool:
        """
        Seek to position in current playback.

        Args:
            position: Position in seconds

        Returns:
            True if seek successful, False otherwise
        """
        with self._player_lock:
            if not self._current_player:
                return False

            try:
                result = self._current_player.seek(position)
                if result:
                    self.publish_event("media.playback_seeked", {"position": position})
                return result
            except Exception as e:
                self.log("MEDIA_MANAGER", f"Error seeking to {position}: {e}")
                return False

    def get_player_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the current player.

        Returns:
            Dictionary with player information or None
        """
        with self._player_lock:
            if not self._current_player:
                return None

            try:
                return {
                    "name": getattr(self._current_player, "__name__", "Unknown"),
                    "type": type(self._current_player).__name__,
                    "playing": getattr(self._current_player, "is_playing", lambda: False)(),
                    "position": getattr(self._current_player, "get_position", lambda: 0)(),
                    "duration": getattr(self._current_player, "get_duration", lambda: 0)(),
                }
            except Exception as e:
                self.log("MEDIA_MANAGER", f"Error getting player info: {e}")
                return None

    def _initialize_media_players(self) -> None:
        """Initialize media players system."""
        try:
            # This would typically initialize MediaPlayers
            # For now, we'll set up the player selection
            self._select_player()
        except Exception as e:
            self.log("MEDIA_MANAGER", f"Error initializing media players: {e}")

    def _select_player(self) -> None:
        """Select the best available media player."""
        with self._player_lock:
            if not self._media_players or not self._players_order:
                self._current_player = None
                return

            for player_name in self._players_order:
                if player_name in self._media_players:
                    self._current_player = self._media_players[player_name]
                    self.log("MEDIA_MANAGER", f"Selected player: {player_name}")
                    break
            else:
                self._current_player = None
                self.log("MEDIA_MANAGER", "[ERROR] - No media player found!")

    def _is_remote_mode(self) -> bool:
        """Check if running in remote mode."""
        # This would check with the application controller
        # For now, assume not remote
        return False

    def _handle_play(self, event_type: str, data: Any) -> None:
        """Handle play event."""
        if isinstance(data, dict) and "file" in data:
            self.play_file(data["file"], **data.get("kwargs", {}))

    def _handle_pause(self, event_type: str, data: Any) -> None:
        """Handle pause event."""
        self.pause()

    def _handle_stop(self, event_type: str, data: Any) -> None:
        """Handle stop event."""
        self.stop()

    def _handle_seek(self, event_type: str, data: Any) -> None:
        """Handle seek event."""
        if isinstance(data, (int, float)):
            self.seek(float(data))