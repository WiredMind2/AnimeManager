Shared Layer
============

The :mod:`shared` package hosts the framework-agnostic technical
helpers consumed by :mod:`application` and :mod:`adapters`. It is
the destination for the cross-cutting concerns that the historical
``Constants`` / ``Getters`` / ``Logger`` multi-inheritance mixins
used to provide implicitly (see ADR 0005). Per ADR 0006, no feature
business logic lives here — that belongs in :mod:`domain`.

Phase 6 of the refactor (see :doc:`/migration/refactor_phases`) has
not yet relocated the legacy root-level helper modules
(:file:`constants.py`, :file:`logger.py`, :file:`general_utils.py`,
:mod:`core.security`). The submodules listed below wrap or re-export
those modules so new code can already write ``from shared.config
import ConfigProvider`` and similar.

Package overview
----------------

.. automodule:: shared
   :members:
   :undoc-members:
   :show-inheritance:

Configuration
-------------

The :mod:`shared.config` subpackage exposes the narrow
:class:`shared.config.ConfigProvider` accessor that wraps the legacy
:class:`constants.Constants` object. The provider is the canonical
constructor-injected collaborator for any class that needs access to
configuration paths (database path, settings JSON path, appdata
directory, icon path) or to the settings dictionary itself.

.. automodule:: shared.config
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: shared.config.config_provider
   :members:
   :undoc-members:
   :show-inheritance:

Telemetry
---------

The :mod:`shared.telemetry` subpackage hosts the
:class:`shared.telemetry.LoggerService` collaborator. It wraps the
legacy :class:`logger.Logger` instance so callers can receive a
logger as a constructor argument instead of inheriting the historical
``Logger`` mixin (ADR 0005). The wrapper is designed to be
side-effect-free if no underlying logger is available.

.. automodule:: shared.telemetry
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: shared.telemetry.logger_service
   :members:
   :undoc-members:
   :show-inheritance:

Security
--------

The :mod:`shared.security` subpackage re-exports the helpers from
:mod:`core.security` so consumer code can depend on the
``shared.security`` namespace while the relocation under Phase 6 is
deferred.

.. automodule:: shared.security
   :members:
   :undoc-members:
   :show-inheritance:

Generic utilities
-----------------

The :mod:`shared.utils` subpackage re-exports selected helpers from
:mod:`general_utils`. New code should depend on this namespace; the
root-level :file:`general_utils.py` remains as the implementation
home until Phase 6 retires it.

.. automodule:: shared.utils
   :members:
   :undoc-members:
   :show-inheritance:
