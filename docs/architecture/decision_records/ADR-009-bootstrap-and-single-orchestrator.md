# ADR-009: Near-Automatic Bootstrap and One Orchestrator

## Status

Accepted for NETLAB.

## Context

Operators previously applied manual patches, repaired permissions, built services individually, and started runtime components through divergent scripts.

## Decision

Use `Bootstrapper` for generated-state preparation and `Orchestrator` for all stack lifecycle operations. CLI and Mission Control invoke the same Python implementation. Compatibility shell scripts remain forwarding or diagnostic adapters.

## Consequences

- First-run setup is reproducible and idempotent.
- Startup failures generate structured evidence.
- Mission Control remains available for diagnostics when stack startup fails.
- Environment-specific installation of Docker/NVIDIA drivers remains an operator prerequisite; bootstrap diagnoses rather than silently changing critical system drivers.
