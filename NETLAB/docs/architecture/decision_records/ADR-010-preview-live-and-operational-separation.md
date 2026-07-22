# ADR-010: Separate Preview, Live, and Operational Evidence

## Status

Accepted for NETLAB.

## Context

Analytical previews and stale file snapshots could be confused with live runtime communication state.

## Decision

Every telemetry/link result carries a source classification. Topology Studio may use an analytical preview for immediate feedback, but operational status additionally requires live packet/runtime readiness, current metrics, and synchronized participant revisions.

## Consequences

- Researchers receive immediate design feedback without false runtime claims.
- UI badges are more verbose but scientifically defensible.
- Tests explicitly prevent preview/stale data from being labeled live.
