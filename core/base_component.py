"""
Base component class providing common functionality for all components.
Includes lifecycle management, event bus integration, and dependency injection.
"""

import threading
from abc import ABC, abstractmethod
from typing import Optional, Any
from weakref import ref

from .event_bus import get_event_bus, EventBus
from .dependency_container import get_dependency_container, DependencyContainer
from logger import log


class BaseComponent(ABC):
    """
    Base class for all application components.
    Provides lifecycle management, event handling, and dependency resolution.
    """

    def __init__(self, name: str = None):
        """
        Initialize the component.

        Args:
            name: Optional component name for identification
        """
        self._name = name or self.__class__.__name__
        self._initialized = False
        self._started = False
        self._stopped = False
        self._lock = threading.RLock()

        # Get core services
        self._event_bus: EventBus = get_event_bus()
        self._dependency_container: DependencyContainer = get_dependency_container()

        # Logger
        self.log = log

        # Weak reference to self for event callbacks
        self._self_ref = ref(self)

    @property
    def name(self) -> str:
        """Get the component name."""
        return self._name

    @property
    def is_initialized(self) -> bool:
        """Check if component is initialized."""
        return self._initialized

    @property
    def is_started(self) -> bool:
        """Check if component is started."""
        return self._started

    @property
    def is_stopped(self) -> bool:
        """Check if component is stopped."""
        return self._stopped

    def initialize(self) -> None:
        """
        Initialize the component.
        Called once during component lifecycle.
        """
        with self._lock:
            if self._initialized:
                return

            try:
                self._initialize()
                self._initialized = True
                self._event_bus.publish(f"component.{self._name}.initialized")
            except Exception as e:
                self._event_bus.publish(f"component.{self._name}.initialize_failed", str(e))
                raise

    def start(self) -> None:
        """
        Start the component.
        Called after initialization.
        """
        with self._lock:
            if not self._initialized:
                raise RuntimeError(f"Component {self._name} must be initialized before starting")

            if self._started:
                return

            try:
                self._start()
                self._started = True
                self._event_bus.publish(f"component.{self._name}.started")
            except Exception as e:
                self._event_bus.publish(f"component.{self._name}.start_failed", str(e))
                raise

    def stop(self) -> None:
        """
        Stop the component.
        Called during shutdown.
        """
        with self._lock:
            if not self._started:
                return

            if self._stopped:
                return

            try:
                self._stop()
                self._stopped = True
                self._event_bus.publish(f"component.{self._name}.stopped")
            except Exception as e:
                self._event_bus.publish(f"component.{self._name}.stop_failed", str(e))
                raise

    def restart(self) -> None:
        """
        Restart the component.
        Stops and starts the component.
        """
        self.stop()
        self.start()

    @abstractmethod
    def _initialize(self) -> None:
        """
        Component-specific initialization logic.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def _start(self) -> None:
        """
        Component-specific start logic.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def _stop(self) -> None:
        """
        Component-specific stop logic.
        Must be implemented by subclasses.
        """
        pass

    def get_dependency(self, service_type: Any) -> Any:
        """
        Get a dependency from the container.

        Args:
            service_type: The service type to resolve

        Returns:
            The service instance
        """
        return self._dependency_container.resolve(service_type)

    def publish_event(self, event_type: str, data: Any = None, async_publish: bool = False) -> None:
        """
        Publish an event to the event bus.

        Args:
            event_type: The event type
            data: Optional event data
            async_publish: Whether to publish asynchronously
        """
        self._event_bus.publish(event_type, data, async_publish)

    def subscribe_event(self, event_type: str, callback: callable) -> None:
        """
        Subscribe to an event.

        Args:
            event_type: The event type to listen for
            callback: The callback function
        """
        self._event_bus.subscribe(event_type, callback)

    def unsubscribe_event(self, event_type: str, callback: callable) -> None:
        """
        Unsubscribe from an event.

        Args:
            event_type: The event type
            callback: The callback function
        """
        self._event_bus.unsubscribe(event_type, callback)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self._name}', initialized={self._initialized}, started={self._started})"