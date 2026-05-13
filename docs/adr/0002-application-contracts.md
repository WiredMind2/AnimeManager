# ADR 0002: Application Contracts First

## Status

Accepted

## Context

Business behavior is currently spread across Tk windows, utility mixins, and integration modules. This prevents clean boundaries and makes reuse between clients unreliable.

## Decision

Define and enforce application-level contracts before client behavior:

- Application layer exposes use-cases with explicit request/response DTOs.
- Domain errors are mapped to typed application errors.
- Clients consume a shared SDK surface, not infrastructure or repository classes.

## Consequences

- Contract tests become the main safety mechanism for client parity.
- Client adapters remain thin and transport-focused.
- Backend internals can evolve without changing client behavior as long as contracts remain stable.
