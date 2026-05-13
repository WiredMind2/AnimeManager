Composition Root
================

The :mod:`composition` package is the single dependency-wiring point
for the embedded runtime. It is the only layer allowed to import
both :mod:`application` (which knows what ports it needs) and
:mod:`adapters` (which provides concrete implementations of those
ports). Per ADR 0006 this is also the only place where the
ports-and-adapters graph is constructed.

The layering rule for :mod:`composition`:

* It may import from :mod:`adapters`, :mod:`application`,
  :mod:`ports`, :mod:`shared` and :mod:`domain`.
* It must not be imported by :mod:`domain`, :mod:`application` or
  :mod:`ports` — the dependency edge goes in one direction only.

While Phase 3 / Phase 4 are still in progress, the canonical wiring
function lives in :mod:`backend.composition` and the
:func:`composition.root.build_embedded_facade` function delegates to
it. This indirection lets new callers import the canonical
``composition`` path today even though the implementation home will
move later.

Package overview
----------------

.. automodule:: composition
   :members:
   :undoc-members:
   :show-inheritance:

Wiring function
---------------

The :func:`composition.root.build_embedded_facade` function is the
single factory that constructs the embedded backend graph. The Tk
client (:mod:`clients.tk`) and the HTTP client (:mod:`clients.http`)
both call it indirectly through :class:`clients.sdk.ClientSDK`.

.. automodule:: composition.root
   :members:
   :undoc-members:
   :show-inheritance:
