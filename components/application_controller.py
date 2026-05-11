"""
ApplicationController component for managing application lifecycle.
Coordinates initialization, startup, and shutdown of all components.
"""

import os
import sys
import time
import threading
from typing import Optional, Any

from ..core import BaseComponent
from logger import Logger


class ApplicationController(BaseComponent):
    """
    Manages the overall application lifecycle.
    Coordinates component initialization, startup, and shutdown.
    """

    def __init__(self, remote: bool = False):
        super().__init__("ApplicationController")
        self.remote = remote
        self.start_time = time.time()
        self.closing = False

        # Component references
        self._components = []
        self._initialized_components = []
        self._started_components = []

        # Application state
        self.root = None
        self.init_window = None

    def _initialize(self) -> None:
        """Initialize the application controller."""
        self.log("MAIN_STATE", "Initializing Application Controller")

        # Check for headless mode
        if (self.remote is False and
            sys.platform == "linux" and
            "DISPLAY" not in os.environ):
            self.remote = True
            self.log("MAIN_STATE", "Running in headless mode")

    def start(self) -> None:
        """Start the application controller."""
        super().start()
        if not self.remote:
            self._late_startup()

    def _start(self) -> None:
        """Start the application."""
        self.log("MAIN_STATE", "Starting application")

        # Initialize core components in order
        self._initialize_components()

        # Start components
        self._start_components()

        # Remote startup if remote
        if self.remote:
            self._remote_startup()

        self.log("TIME", "Ready:".ljust(25), round(time.time() - self.start_time, 2), "sec")

    def _stop(self) -> None:
        """Stop the application."""
        self.log("MAIN_STATE", "ApplicationController._stop() called")
        if self.closing:
            self.log("MAIN_STATE", "Application already closing, returning early")
            return

        self.log("MAIN_STATE", "Stopping application")
        self.closing = True

        # Stop components in reverse order
        self.log("MAIN_STATE", "Stopping components in reverse order")
        self._stop_components()

        # Final cleanup
        self.log("MAIN_STATE", "Performing final cleanup")
        self._cleanup()

        self.log("TIME", "Stopping time:".ljust(25),
                round(time.time() - self.start_time, 2), "sec")
        self.log("MAIN_STATE", "Application shutdown complete")

    def register_component(self, component: BaseComponent) -> None:
        """
        Register a component for lifecycle management.

        Args:
            component: The component to register
        """
        if component not in self._components:
            self._components.append(component)

    def unregister_component(self, component: BaseComponent) -> None:
        """
        Unregister a component.

        Args:
            component: The component to unregister
        """
        if component in self._components:
            self._components.remove(component)

    def _initialize_components(self) -> None:
        """Initialize all registered components."""
        for component in self._components:
            try:
                component.initialize()
                self._initialized_components.append(component)
                self.log("MAIN_STATE", f"Initialized component: {component.name}")
            except Exception as e:
                self.log("MAIN_STATE", f"Failed to initialize {component.name}: {e}")
                raise

    def _start_components(self) -> None:
        """Start all initialized components."""
        for component in self._initialized_components:
            try:
                component.start()
                self._started_components.append(component)
                self.log("MAIN_STATE", f"Started component: {component.name}")
            except Exception as e:
                self.log("MAIN_STATE", f"Failed to start {component.name}: {e}")
                raise

    def _stop_components(self) -> None:
        """Stop all started components in reverse order."""
        for component in reversed(self._started_components):
            try:
                component.stop()
                self.log("MAIN_STATE", f"Stopped component: {component.name}")
            except Exception as e:
                self.log("MAIN_STATE", f"Error stopping {component.name}: {e}")

    def _late_startup(self) -> None:
        """Perform late startup tasks for GUI mode."""
        self.log("MAIN_STATE", "Performing late startup for GUI mode")
        # Publish event for UI initialization
        self.log("MAIN_STATE", "Publishing application.ui_ready event")
        self.publish_event("application.ui_ready")

        # Notify for UI initialization (for backward compatibility)
        if hasattr(self, 'on_ui_ready'):
            self.on_ui_ready()

    def _remote_startup(self) -> None:
        """Perform startup tasks for remote/headless mode."""
        # Publish event for remote initialization
        self.publish_event("application.remote_ready")

    def _cleanup(self) -> None:
        """Perform final cleanup."""
        # Close windows if they exist
        if self.init_window is not None and self.init_window.winfo_exists():
            self.init_window.destroy()

        if self.root is not None:
            # Quit the mainloop first, then destroy
            try:
                self.root.quit()
            except Exception as e:
                self.log("MAIN_STATE", f"Error quitting mainloop: {e}")
            try:
                self.root.destroy()
            except Exception as e:
                self.log("MAIN_STATE", f"Error destroying root window: {e}")
            self.root = None

    def quit(self) -> None:
        """Request application shutdown."""
        self.publish_event("application.quit_requested")

    def reload(self) -> None:
        """Request application reload."""
        self.publish_event("application.reload_requested")

    def is_closing(self) -> bool:
        """Check if application is closing."""
        return self.closing

    def get_uptime(self) -> float:
        """Get application uptime in seconds."""
        return time.time() - self.start_time