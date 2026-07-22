# ADR-002: Communication Feasibility Is an Execution Gate

- **Status:** Accepted
- **Date:** 2026-07-15

## Context

Animating packets independently from the communication model would produce scientifically misleading results.

## Decision

The packet cursor advances only after a fresh failure-aware feasibility decision passes endpoint, range, hard-outage, SNR/SINR, and capacity predicates. Every rejection has a stable reason and retains the current cursor.

## Alternatives

- Advance packets and annotate bad links afterward: rejected because communication would become post-processing.
- Use range alone: rejected because it omits RF and capacity constraints.

## Consequences

Outages are visible and reproducible. A topology or recovery path can be structurally valid but not operational.
