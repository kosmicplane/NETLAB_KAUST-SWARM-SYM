# ADR-001: Authoritative State and Event Journal

- **Status:** Accepted
- **Date:** 2026-07-15

## Context

The baseline duplicated mission and runtime state across a monolithic browser page, shell scripts, ROS 2, Isaac Sim, JSON snapshots, and telemetry files. A button could update one copy without proving that the runtime applied it.

## Decision

Use a versioned durable experiment configuration and a separate atomic runtime `StateStore`. Commands receive IDs, events are append-only, and service heartbeats/sync acknowledgements are interpreted as runtime evidence. Visual state is a projection of authoritative packet/runtime state.

## Alternatives

- Keep browser state authoritative: rejected because the browser is transient and disconnected from Isaac/ROS execution.
- Make ROS 2 the only durable store: rejected for brownfield compatibility and offline experiment editing.
- Introduce a database immediately: deferred; file contracts are simpler for reproducible single-host research runs and current containers.

## Consequences

Configuration, state, events, commands, and heartbeats have explicit owners. Multi-host scaling will require replacing or wrapping the file transport, but the typed contracts remain reusable.
