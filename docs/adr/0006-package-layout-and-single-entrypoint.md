# ADR 0006: Package Layout and Single Entrypoint

## Status

Accepted

## Context

The repository historically had several startup paths:

- ``__main__.py`` at the repository root,
- ``launch/__main__.py`` as an alternate launcher,
- ``API_server.py`` as a separate HTTP entrypoint,
- ad-hoc scripts at the repository root (``classes.py``,
  ``getters.py``, ``constants.py``, ``logger.py``, ``general_utils.py``,
  ``dialog_components.py``, ``import_manager.py``, ``IRC.py``,
  ``sitecustomize.py``).

Multiple entrypoints duplicate process bootstrap logic, drift in their
PYTHONPATH manipulation, and force every new client (GUI, HTTP, future
CLI) to re-implement startup. The proliferation of root-level scripts
also obscures the boundary between *runtime code* and *configuration*,
which makes packaging and IDE tooling unreliable.

## Decision

The repository root contains **exactly one** Python startup script:
``run.py``. All other runtime code lives inside the existing repo-root
package, organised under the following layout:

```text
animemanager_repo_root/
  run.py                      # only root .py startup script
  __init__.py                 # package marker (repo root IS the package)
  bootstrap.py                # canonical mode dispatcher
  composition/                # dependency wiring
    root.py
  domain/                     # pure business logic
    entities/ value_objects/ services/ errors/ policies/
  application/                # use-cases, DTOs, orchestration
    use_cases/ dto/ services/ commands/ queries/
  ports/                      # interfaces consumed by application
    inbound/ outbound/
  adapters/                   # IO / framework / vendor integrations
    api/ persistence/ search/ media/ torrent/ legacy/ file/
  clients/                    # protocol adapters (Tk / HTTP / SDK)
    tk/ http/ sdk/ tk_legacy/
  shared/                     # cross-cutting technical helpers
    config/ telemetry/ security/ utils/
```

``run.py`` performs argument parsing only and delegates to
``bootstrap.main(mode=...)``. ``bootstrap.main`` dispatches to one of
the supported modes (``gui``, ``api``, future ``cli`` tasks) and is the
single integration point with ``composition.root``.

The legacy entrypoints (``__main__.py``, ``launch/__main__.py``,
``API_server.py``) remain as thin re-export shims that emit a
``DeprecationWarning`` and forward to ``run.py`` / ``bootstrap``. They
will be removed once their callers have migrated. Likewise, the root
scripts ``classes.py`` / ``getters.py`` / ``constants.py`` /
``logger.py`` / ``general_utils.py`` / ``dialog_components.py`` /
``import_manager.py`` / ``IRC.py`` / ``sitecustomize.py`` survive as
re-export shims pointing at their new homes in ``shared/`` (or, for
domain-shaped types like ``classes.py``, into ``domain/``).

## Consequences

- New code can rely on a single, stable startup path.
- Packaging (``pip install -e .``, PyInstaller) is simplified because
  there is exactly one ``python_requires`` entrypoint to bundle.
- Architecture tests can enforce that no new ``.py`` files appear at
  the repository root.
- The shim layer is deliberately temporary. ADR 0006 obliges every
  shim added during the migration to carry a ``DeprecationWarning`` so
  that callers see the deprecation at import time.
- This ADR supersedes the implicit "multiple roots are fine" stance
  of pre-refactor builds and pairs with ADR 0005 to lock the target
  architecture end-to-end.
