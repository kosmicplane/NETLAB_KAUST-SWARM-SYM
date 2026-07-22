# ADR-005: Isaac Readiness Requires Fresh Heartbeat and Scene Acknowledgement

- **Status:** Accepted
- **Date:** 2026-07-15

## Context

A historical “Full Streaming App is loaded” log line did not prove that the current SNaaS scene was alive or had consumed the latest configuration.

## Decision

Isaac writes a periodic heartbeat with scene readiness and writes an acknowledgement for each configuration revision. The orchestrator requires a running service, a fresh heartbeat, scene readiness, and a matching sync acknowledgement.

## Consequences

Mission Control can distinguish process running, scene ready, synchronized, stale, and failed states. WebRTC viewing remains optional.
