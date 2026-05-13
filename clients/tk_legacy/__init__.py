"""Legacy Tk UI widgets.

This package is a transitional home for the old ``windows.*`` Tk views
that are being collapsed into the modern Tk client adapter
(``clients.tk``). Phase 5 of the architecture refactor (ADR 0006)
relocates those views here; the current state of the codebase has the
``windows/`` tree empty, so this package is also empty.

New UI code MUST go to ``clients/tk`` (with use-case calls into
``application``). Anything that lands in ``clients/tk_legacy`` is, by
definition, a deprecation target.
"""

__all__: list[str] = []
