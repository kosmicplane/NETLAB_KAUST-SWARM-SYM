# ADR-006: Incremental Brownfield Compatibility

- **Status:** Accepted
- **Date:** 2026-07-15

## Context

NETLAB already contained valuable Isaac, ROS 2, Sionna, scenario, and deployment assets. A disconnected rewrite would risk losing working behavior.

## Decision

The original v5 modernization introduced modular packages and frontend components while retaining current ROS package/topic names, legacy filenames, and forwarding scripts. NETLAB keeps that controlled compatibility payload while moving authoritative operation to versioned revisions, typed state, and the single orchestrator.

## Removal conditions

The compatibility layer may be removed only after:

1. ROS 2, Sionna, and Isaac consume the the authoritative NETLAB schema/revision contracts natively;
2. all current scenarios migrate successfully;
3. behavioral compatibility tests pass;
4. release documentation provides a migration path.
