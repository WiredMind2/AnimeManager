"""
EventBus for decoupled communication between components.
Provides publish-subscribe pattern for event-driven architecture.
"""

import threading
from typing import Any, Callable, Dict, List
from collections import defaultdict


class EventBus:
    """
    Centralized event bus for component communication.
    Supports synchronous and asynchronous event handling.
    """

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = threading.RLock()
        self._async_executor = None

    def subscribe(self, event_type: str, callback: Callable) -> None:
        """
        Subscribe to an event type.

        Args:
            event_type: The event type to listen for
            callback: Function to call when event is published
        """
        with self._lock:
            self._listeners[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """
        Unsubscribe from an event type.

        Args:
            event_type: The event type to stop listening for
            callback: The callback function to remove
        """
        with self._lock:
            listeners = self._listeners[event_type]
            self._listeners[event_type] = [
                cb for cb in listeners if cb is not callback
            ]

    def publish(self, event_type: str, data: Any = None, async_publish: bool = False) -> None:
        """
        Publish an event to all subscribers.

        Args:
            event_type: The event type to publish
            data: Optional data to pass to listeners
            async_publish: Whether to publish asynchronously
        """
        if async_publish:
            self._publish_async(event_type, data)
        else:
            self._publish_sync(event_type, data)

    def _publish_sync(self, event_type: str, data: Any = None) -> None:
        """Publish event synchronously."""
        # Call listeners outside the lock to prevent deadlocks
        for callback in self._listeners[event_type]:
            try:
                callback(event_type, data)
            except Exception as e:
                # Log error but continue with other listeners
                print(f"Error in event listener for {event_type}: {e}")

    def _publish_async(self, event_type: str, data: Any = None) -> None:
        """Publish event asynchronously."""
        if self._async_executor is None:
            import concurrent.futures
            self._async_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

        self._async_executor.submit(self._publish_sync, event_type, data)


    def clear(self) -> None:
        """Clear all listeners."""
        with self._lock:
            self._listeners.clear()

    def get_listener_count(self, event_type: str) -> int:
        """Get the number of active listeners for an event type."""
        with self._lock:
            return len(self._listeners[event_type])


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    if not hasattr(get_event_bus, '_bus'):
        get_event_bus._bus = EventBus()
    return get_event_bus._bus