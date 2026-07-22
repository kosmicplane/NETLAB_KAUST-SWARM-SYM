# ADR-007: Transactional Runtime Synchronization

## Status

Accepted for NETLAB.

## Context

A configuration or topology file could be saved while ROS 2, the link service, or Isaac Sim had not applied it. The UI could therefore imply success while the embodied scene and communication runtime diverged.

## Decision

Represent runtime-significant changes as immutable revisions with per-domain hashes. Require explicit acknowledgement from ROS 2, Sionna, and Isaac before commit. Preserve incomplete revisions as pending drafts and expose reconcile and rollback operations.

## Alternatives considered

- Treat file write as success: rejected because it does not prove runtime application.
- Make ROS the only source of truth: rejected because world/link/scene participants still need independent acknowledgement.
- Use distributed two-phase commit: rejected for the current single-host research stack because participants are not transactional databases; a durable saga/reconciliation pattern is more practical.

## Consequences

- UI status is more precise but operations may remain pending.
- Participant adapters must report revision/hash state.
- Revision history adds evidence and storage cost.
- Reconciliation can recover after participant restart.

## Migration impact

Existing save APIs return durable-save and runtime-application status separately. Compatibility consumers continue receiving the active configuration path.
