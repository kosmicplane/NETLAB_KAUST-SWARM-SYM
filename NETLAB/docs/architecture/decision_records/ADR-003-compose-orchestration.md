# ADR-003: One Authoritative Stack Orchestrator

- **Status:** Accepted
- **Date:** 2026-07-15

## Context

The baseline had overlapping shell and UI startup flows. Compose started idle ROS 2 and Sionna shells, while the packet runtime required a second manual command.

## Decision

`netlab.orchestrator` is authoritative. Compose commands start the link service, packet runtime, and Isaac autoload directly. `scripts/netlab`, Mission Control, and compatibility scripts delegate to the same lifecycle implementation. All waits are bounded.

## Alternatives

- Keep manual runtime startup: rejected because Start Stack did not mean the complete stack.
- Put all orchestration in shell: rejected because typed state, jobs, diagnostics, and API acknowledgement were difficult to share.

## Consequences

One click/command starts the complete required runtime. Environment-specific wrappers remain for setup and compatibility.
