"""
UIManager component for managing user interface windows.
Handles window creation, event-driven updates, and UI state management.
"""

import threading
from typing import Optional, Any, Dict, List

from ..core import BaseComponent


class UIManager(BaseComponent):
    """
    Manages all UI windows and event-driven updates.
    Implements window factory pattern and coordinates UI state.
    """

    def __init__(self):
        super().__init__("UIManager")
        self._windows: Dict[str, Any] = {}
        self._window_factories: Dict[str, callable] = {}
        self._root = None
        self._init_window = None
        self._loading_window = None
        self._lock = threading.RLock()

    def _initialize(self) -> None:
        """Initialize the UI manager."""
        self.log("UI_MANAGER", "Initializing UI Manager")

        # Subscribe to UI-related events
        self.subscribe_event("ui.show_window", self._handle_show_window)
        self.subscribe_event("ui.hide_window", self._handle_hide_window)
        self.subscribe_event("ui.update_loading", self._handle_update_loading)
        self.subscribe_event("application.ui_ready", self._handle_application_ui_ready)

    def _start(self) -> None:
        """Start the UI manager."""
        self.log("UI_MANAGER", "Starting UI Manager")

    def _stop(self) -> None:
        """Stop the UI manager and cleanup windows."""
        with self._lock:
            # Close all windows
            for window_name, window in self._windows.items():
                try:
                    if window and hasattr(window, 'winfo_exists') and window.winfo_exists():
                        window.destroy()
                except Exception as e:
                    self.log("UI_MANAGER", f"Error closing window {window_name}: {e}")

            self._windows.clear()

            # Close root window
            if self._root and hasattr(self._root, 'winfo_exists') and self._root.winfo_exists():
                try:
                    self._root.destroy()
                except Exception as e:
                    self.log("UI_MANAGER", f"Error closing root window: {e}")

        self.log("UI_MANAGER", "UI Manager stopped")

    def set_root(self, root) -> None:
        """
        Set the root Tkinter window.

        Args:
            root: The root Tkinter window
        """
        self._root = root

    def register_window_factory(self, window_type: str, factory: callable) -> None:
        """
        Register a window factory function.

        Args:
            window_type: Type/name of the window
            factory: Function that creates the window
        """
        with self._lock:
            self._window_factories[window_type] = factory

    def create_window(self, window_type: str, *args, **kwargs) -> Optional[Any]:
        """
        Create a window using registered factory.

        Args:
            window_type: Type of window to create
            *args: Additional arguments for factory
            **kwargs: Additional keyword arguments for factory

        Returns:
            Created window or None
        """
        with self._lock:
            factory = self._window_factories.get(window_type)
            if not factory:
                self.log("UI_MANAGER", f"No factory registered for window type: {window_type}")
                return None

            try:
                window = factory(*args, **kwargs)
                self._windows[window_type] = window
                self.log("UI_MANAGER", f"Created window: {window_type}")
                return window
            except Exception as e:
                self.log("UI_MANAGER", f"Failed to create window {window_type}: {e}")
                return None

    def get_window(self, window_type: str) -> Optional[Any]:
        """
        Get a window by type.

        Args:
            window_type: Type of window

        Returns:
            Window instance or None
        """
        with self._lock:
            return self._windows.get(window_type)

    def destroy_window(self, window_type: str) -> None:
        """
        Destroy a window.

        Args:
            window_type: Type of window to destroy
        """
        with self._lock:
            window = self._windows.get(window_type)
            if window:
                try:
                    if hasattr(window, 'winfo_exists') and window.winfo_exists():
                        window.destroy()
                    del self._windows[window_type]
                    self.log("UI_MANAGER", f"Destroyed window: {window_type}")
                except Exception as e:
                    self.log("UI_MANAGER", f"Error destroying window {window_type}: {e}")

    def show_loading(self, text: str = "Loading...") -> None:
        """
        Show loading window with message.

        Args:
            text: Loading message
        """
        self.publish_event("ui.show_loading", text)

    def hide_loading(self) -> None:
        """Hide loading window."""
        self.publish_event("ui.hide_loading")

    def update_loading_progress(self, progress: float) -> None:
        """
        Update loading progress.

        Args:
            progress: Progress value (0-100)
        """
        self.publish_event("ui.update_progress", progress)

    def show_error_dialog(self, title: str, message: str) -> None:
        """
        Show error dialog.

        Args:
            title: Dialog title
            message: Error message
        """
        self.publish_event("ui.show_error", {"title": title, "message": message})

    def show_info_dialog(self, title: str, message: str) -> None:
        """
        Show info dialog.

        Args:
            title: Dialog title
            message: Info message
        """
        self.publish_event("ui.show_info", {"title": title, "message": message})

    def _handle_show_window(self, event_type: str, data: Any) -> None:
        """Handle show window event."""
        if isinstance(data, dict):
            window_type = data.get("type")
            if window_type:
                self.create_window(window_type, **data.get("kwargs", {}))

    def _handle_hide_window(self, event_type: str, data: Any) -> None:
        """Handle hide window event."""
        if isinstance(data, str):
            self.destroy_window(data)

    def _handle_update_loading(self, event_type: str, data: Any) -> None:
        """Handle loading update event."""
        # This would be handled by the loading window component
        pass

    def _handle_application_ui_ready(self, event_type: str, data: Any) -> None:
        """Handle application UI ready event."""
        if not self.is_remote_mode() and self._root:
            self.log("UI_MANAGER", "Starting Tkinter mainloop")
            self._root.mainloop()

    def set_init_window(self, window) -> None:
        """Set the initialization window."""
        self._init_window = window

    def get_init_window(self):
        """Get the initialization window."""
        return self._init_window

    def set_loading_window(self, window) -> None:
        """Set the loading window."""
        self._loading_window = window

    def get_loading_window(self):
        """Get the loading window."""
        return self._loading_window

    def get_root(self):
        """Get the root window."""
        return self._root

    def is_remote_mode(self) -> bool:
        """Check if running in remote mode (no GUI)."""
        return self._root is None