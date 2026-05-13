# Architecture Decision Records

Architecture Decision Records (ADRs) capture the *why* behind the
shape of the codebase. Each file documents a single decision: the
context that made it necessary, the choice that was made and the
consequences we accepted as a result.

New ADRs should be numbered sequentially (`NNNN-short-title.md`) and
follow the same template as the existing entries:

```
# ADR NNNN: <title>

## Status

Proposed | Accepted | Superseded by ADR NNNN | Deprecated

## Context

What problem prompted this decision? What constraints were in play?

## Decision

The decision in one or two short paragraphs.

## Consequences

What changes because of this decision? Trade-offs we accept.
```

Status transitions (e.g. **Proposed → Accepted**, **Accepted →
Superseded**) should be recorded by editing the existing ADR; never
delete or rewrite history. Supersede an old decision with a new ADR
and cross-link the two.

## Index

| ADR | Title | Status |
| --- | --- | --- |
| [0001](0001-embedded-runtime-model.md) | Embedded Runtime Model | Accepted |
| [0002](0002-application-contracts.md) | Application Contracts First | Accepted |
| [0003](0003-dependency-rules.md) | Dependency Direction Rules | Accepted |
| [0004](0004-error-model.md) | Unified Error Model | Accepted |
| [0005](0005-composition-over-inheritance.md) | Composition Over Inheritance | Accepted |
| [0006](0006-package-layout-and-single-entrypoint.md) | Package Layout and Single Entrypoint | Accepted |

The decisions above are mutually reinforcing. Read them in order: the
embedded runtime (ADR 0001) is the runtime container, application
contracts (ADR 0002) define what crosses its boundary, dependency
rules (ADR 0003) keep that boundary intact, the error model (ADR
0004) makes failure modes consistent across the boundary,
composition-over-inheritance (ADR 0005) bans the multi-inheritance
patterns that historically blurred those boundaries, and the package
layout decision (ADR 0006) fixes a single launcher (``run.py``) and a
canonical folder structure for every layer.
