# ADR 0005: Composition Over Inheritance

## Status

Accepted

## Context

A recurring failure pattern in the AnimeManager codebase is the
*god class* style obtained by multiplying responsibilities through
multiple inheritance. The most visible examples are:

- ``animeAPI.AnimeAPI`` inheriting from ``Getters`` *and* ``Logger``;
- ``animeAPI.APIUtils`` inheriting from ``Logger`` *and* ``Getters``;
- ``backend.adapters.legacy_runtime.LegacyRuntime`` inheriting from
  ``Constants`` *and* ``Getters``.

Each of those parents contributes a wide, implicit surface area
(filesystem state, settings, database handles, logging fan-out). The
resulting classes are unbounded: anything reachable from any parent
becomes part of the object's API, making the runtime impossible to
reason about, mock, or migrate. Refactoring is blocked because removing
any parent silently breaks call sites that rely on inherited helpers
they never explicitly imported.

## Decision

New runtime modules **must** use composition (explicit constructor
dependencies) instead of inheritance for cross-cutting concerns.

The rule is:

- A runtime class may inherit at most one non-``Protocol``,
  non-``Exception``, non-``BaseException`` base class.
- Cross-cutting capabilities (configuration, logging, telemetry,
  filesystem, HTTP, database access) **must** be supplied as
  constructor parameters typed by a narrow interface or ``Protocol``
  living in ``ports/`` or ``shared/``.
- New "mixin" classes are not permitted in runtime modules. ``abc.ABC``
  and ``typing.Protocol`` are not counted as inheritance for this rule
  because they declare contracts rather than behavior.
- Existing inheritance hotspots (``AnimeAPI``, ``APIUtils``,
  ``LegacyRuntime``) are placed on an allowlist and shall be
  progressively retired through composed replacements. Each retirement
  must preserve behavior through characterization tests in
  ``tests/unit/monolith_decomp/``.

This rule is enforced by the architecture test suite
(``tests/architecture/test_no_new_multi_inheritance.py``). Any new
runtime class that declares more than one non-allowlisted base class
fails the build.

## Consequences

- Classes become small, single-responsibility units whose dependencies
  are visible at the call site (the composition root).
- Testing improves: collaborators are explicit and trivially mockable.
- The composition root (``composition/root.py``) becomes the single
  place where concrete adapters are wired into application ports.
- Migration cost is non-zero. The allowlist exists precisely to keep
  the cost bounded while old classes are decomposed into
  ``application`` use-cases, ``adapters`` integrations, and ``shared``
  technical helpers.
- This ADR supersedes the *implicit* tolerance for multi-inheritance
  in ADR 0003 (Dependency Direction Rules) and tightens the architecture
  contract end-to-end.
