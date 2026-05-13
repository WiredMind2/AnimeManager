# ADR 0003: Dependency Direction Rules

## Status

Accepted

## Context

Current imports allow UI code to reach DB/API/torrent/file layers directly, and utility modules mix pure policy with side effects.

## Decision

Adopt strict layered dependency rules:

- `domain` depends on nothing except Python stdlib and domain modules.
- `application` depends on `domain` and `ports`.
- `adapters` depend on `application` ports and external libraries.
- `clients` depend on the embedded interface/SDK only.
- No client adapter imports `db_managers`, `animeAPI`, `torrent_managers`, or `file_managers` directly.

## Consequences

- Import boundaries can be validated with tests/lint checks.
- Refactoring is safer because side effects are isolated to adapter modules.
