# ADR 0001: Embedded Runtime Model

## Status

Accepted

## Context

The current application runtime is centered around `Manager`, which combines UI, domain orchestration, and infrastructure concerns in one object graph. This makes it difficult to support multiple clients (Tk, Qt, HTTP) without duplicating logic or leaking infrastructure into client code.

## Decision

Use an embedded backend runtime as the primary architecture:

- A single composition root constructs domain services, use-cases, and infrastructure adapters in-process.
- Client adapters (Tk, Qt, HTTP) are peers and consume the same embedded client facade/SDK.
- The HTTP adapter is not a privileged backend layer. It behaves as a client adapter over the same use-case boundary.

## Consequences

- Core business logic becomes UI-framework agnostic.
- Multiple client adapters can be added without backend rewrites.
- Existing `Manager` can be retired progressively once feature parity is reached.
