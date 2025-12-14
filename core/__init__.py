"""
Core infrastructure for the AnimeManager application.
Provides event-driven architecture and dependency injection.
"""

from .event_bus import EventBus, get_event_bus
from .dependency_container import DependencyContainer, get_dependency_container
from .base_component import BaseComponent

__all__ = [
    'EventBus',
    'get_event_bus',
    'DependencyContainer',
    'get_dependency_container',
    'BaseComponent',
]