"""
Lightweight base class shared by the long-lived application components.

The previous incarnation of this module implemented a full lifecycle
(``initialize``/``start``/``stop``), a global event-bus contract, and a
service container. After the move to the hexagonal package layout those
layers are no longer driven; components are simple objects created by
adapters. ``BaseComponent`` keeps just enough to remain a useful,
dependency-friendly base:

* a stable ``name`` used by ``log`` routing,
* a lock for guarding shared mutable state,
* a default ``log`` callable,
* optional ``initialize``/``start``/``stop`` hooks for callers that
  still want to drive a lifecycle.

Subclasses should do their setup work in ``__init__`` and expose a
``close()`` method for cleanup.
"""

import threading
from typing import Optional

from shared.telemetry.logger import log


class BaseComponent:
    """Base class for application components."""

    def __init__(self, name: Optional[str] = None):
        self._name = name or self.__class__.__name__
        self._initialized = False
        self._started = False
        self._stopped = False
        self._lock = threading.RLock()
        self.log = log

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
        """Optional lifecycle hook. Subclasses can override `_initialize`."""
        with self._lock:
            if self._initialized:
                return
            self._initialize()
            self._initialized = True

    def start(self) -> None:
        """Optional lifecycle hook. Subclasses can override `_start`."""
        with self._lock:
            if self._started:
                return
            self._start()
            self._started = True

    def stop(self) -> None:
        """Optional lifecycle hook. Subclasses can override `_stop`."""
        with self._lock:
            if self._stopped:
                return
            self._stop()
            self._stopped = True

    def _initialize(self) -> None:
        return None

    def _start(self) -> None:
        return None

    def _stop(self) -> None:
        return None

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name='{self._name}', "
            f"initialized={self._initialized}, started={self._started})"
        )
