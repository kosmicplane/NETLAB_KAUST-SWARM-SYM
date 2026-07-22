# ADR 0001: Authoritative revision control

## Context
UI, files, ROS, Sionna, and Isaac previously diverged and could report contradictory results.

## Decision
All meaningful changes use a revisioned desired/observed reconciliation protocol and commit only after required participant acknowledgements.

## Consequences
Commands can remain pending, but false success is eliminated. Each change is reproducible and auditable.
