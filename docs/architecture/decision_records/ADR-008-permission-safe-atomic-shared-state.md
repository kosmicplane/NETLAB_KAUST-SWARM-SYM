# ADR-008: Permission-Safe Atomic Shared State

## Status

Accepted for NETLAB.

## Context

Root-run containers used atomic temporary files that defaulted to mode `0600`. After `os.replace`, Mission Control running as the host user could not read heartbeats and acknowledgements.

## Decision

Centralize shared-state writes in `netlab.io`. Use atomic temporary-file write, file and directory `fsync`, explicit file mode, setgid directories, optional host UID/GID normalization, and post-replace metadata application. Add permission diagnostics and safe repair for generated trees.

## Alternatives considered

- World-writable files: rejected for security and provenance reasons.
- Run all containers as the host user: not universally compatible with Isaac and GPU images.
- Non-atomic direct writes: rejected because concurrent readers could observe partial JSON.

## Consequences

- Host and containers can share health/evidence artifacts safely.
- Deployment must pass UID/GID through Compose.
- Imported/source assets are outside automatic permission repair.
