"""Configuration helpers.

This package is the **canonical** home of the configuration accessors
(:class:`Constants`, :class:`ConfigProvider`, legacy :class:`Getters`).
The legacy root ``constants`` / ``getters`` modules are thin
compatibility shims that re-export from here.
"""

from .config_provider import ConfigProvider, get_default_config_provider
from .constants import Constants
from .getters import Getters

__all__ = [
    "Constants",
    "ConfigProvider",
    "Getters",
    "get_default_config_provider",
]
