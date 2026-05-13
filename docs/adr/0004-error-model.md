# ADR 0004: Unified Error Model

## Status

Accepted

## Context

Legacy code commonly returns `None`, logs errors, or raises heterogeneous exceptions directly from integrations. Client adapters need deterministic error behavior across runtime modes.

## Decision

Introduce a unified application error model:

- Domain/application errors derive from a small shared hierarchy.
- Adapter exceptions are translated to typed application errors.
- HTTP adapter maps application errors to status codes.
- Tk/Qt adapters map application errors to client notifications/dialogs.

## Consequences

- Error handling is consistent across all client adapters.
- Transport layers remain thin and predictable.
