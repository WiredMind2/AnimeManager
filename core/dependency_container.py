"""
Dependency injection container for managing component dependencies.
Provides centralized service registration and resolution.
"""

import threading
from typing import Any, Dict, Type, TypeVar, Optional, Callable
from weakref import WeakValueDictionary

T = TypeVar('T')


class DependencyContainer:
    """
    IoC container for managing component dependencies.
    Supports singleton and transient registrations.
    """

    def __init__(self):
        self._services: Dict[Type, Any] = {}
        self._factories: Dict[Type, Callable[[], Any]] = {}
        self._singletons: WeakValueDictionary[Type, Any] = WeakValueDictionary()
        self._lock = threading.RLock()

    def register(self, service_type: Type[T], implementation: T) -> None:
        """
        Register a service instance.

        Args:
            service_type: The service interface/type
            implementation: The concrete implementation instance
        """
        with self._lock:
            self._services[service_type] = implementation

    def register_factory(self, service_type: Type[T], factory: Callable[[], T]) -> None:
        """
        Register a factory function for creating service instances.

        Args:
            service_type: The service interface/type
            factory: Function that creates the service instance
        """
        with self._lock:
            self._factories[service_type] = factory

    def register_singleton(self, service_type: Type[T], implementation: T) -> None:
        """
        Register a singleton service instance.

        Args:
            service_type: The service interface/type
            implementation: The singleton instance
        """
        with self._lock:
            self._singletons[service_type] = implementation

    def resolve(self, service_type: Type[T]) -> T:
        """
        Resolve a service instance.

        Args:
            service_type: The service type to resolve

        Returns:
            The service instance

        Raises:
            ValueError: If service is not registered
        """
        with self._lock:
            # Check singletons first
            if service_type in self._singletons:
                return self._singletons[service_type]

            # Check registered services
            if service_type in self._services:
                return self._services[service_type]

            # Check factories
            if service_type in self._factories:
                instance = self._factories[service_type]()
                # Cache as singleton if it's meant to be
                if hasattr(instance, '_singleton') and instance._singleton:
                    self._singletons[service_type] = instance
                return instance

            raise ValueError(f"Service {service_type} is not registered")

    def is_registered(self, service_type: Type[T]) -> bool:
        """
        Check if a service type is registered.

        Args:
            service_type: The service type to check

        Returns:
            True if registered, False otherwise
        """
        with self._lock:
            return (service_type in self._services or
                   service_type in self._factories or
                   service_type in self._singletons)

    def unregister(self, service_type: Type[T]) -> None:
        """
        Unregister a service.

        Args:
            service_type: The service type to unregister
        """
        with self._lock:
            if service_type in self._services:
                del self._services[service_type]
            if service_type in self._factories:
                del self._factories[service_type]
            if service_type in self._singletons:
                del self._singletons[service_type]

    def clear(self) -> None:
        """Clear all registered services."""
        with self._lock:
            self._services.clear()
            self._factories.clear()
            self._singletons.clear()


# Global dependency container instance
_dependency_container = None


def get_dependency_container() -> DependencyContainer:
    """Get the global dependency container instance."""
    global _dependency_container
    if _dependency_container is None:
        _dependency_container = DependencyContainer()
    return _dependency_container