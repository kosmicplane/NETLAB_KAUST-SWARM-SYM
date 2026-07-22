# ADR-004: Resolve Containers by Compose Service Metadata

- **Status:** Accepted
- **Date:** 2026-07-15

## Context

Brev produced a ROS container named with a Compose prefix while scripts attempted `docker exec netlab-ros2-core`.

## Decision

Resolve the service container ID through `docker compose ps -q <service>`, inspect the resulting container name, and use a configured name only as a fallback.

## Consequences

The runtime tolerates Compose project prefixes and still supports stable explicit container names.
