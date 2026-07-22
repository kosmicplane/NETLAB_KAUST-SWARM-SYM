# NETLAB critical regression results

| Regression | Permanent control | Executed evidence | Result |
|---|---|---|---|
| Packaged configuration referenced missing antenna IDs | Generated reference marker, complete scenario validation, conservative repair | config/bootstrap/release tests | PASS |
| ROS crashed while sourcing setup under `nounset` | base-only ROS loader; nounset restored only after base and overlay setup | ROS entrypoint and shell tests | PASS |
| ROS built only part of the workspace | complete `colcon build` including `netlab_interfaces` and `netlab_swarm_demo` | source and Compose contract tests | PASS |
| Heartbeats became unreadable after atomic replace | one permission-safe atomic writer, setgid runtime trees, repair diagnostics | atomic I/O and concurrent-reader tests | PASS |
| Existing Brev Docker conflicted with `containerd.io` installation | host bootstrap preserves existing Docker and installs no `containerd.io` package | host-bootstrap contract tests | PASS |
| Frontend displayed only an empty shell | module identity, explicit MIME/HEAD support, bootstrap guard, browser navigation of every view | Playwright Chromium test | PASS |
| Readiness surfaces contradicted each other | single observed readiness model and typed command results | readiness, API, and frontend contract tests | PASS |
| Topology and coordinates were saved through separate operations | one atomic topology/inventory API and one revision | API and frontend tests | PASS |
| Offline runtime could be reported as committed | required ROS/Sionna/Isaac ACKs and component hashes | revision and synchronization tests | PASS |
| Repeated Start Stack could duplicate or preserve unhealthy state | observed-state idempotence and unhealthy-service recreation | orchestrator tests | PASS |
| Packet animation could diverge from runtime | authoritative packet state machine and failure-aware execution gate | link/packet tests | PASS |
| Preview or stale telemetry could appear live | source/freshness classification with no synthetic live fallback | telemetry/API/browser tests | PASS |

Additional researcher-algorithm regressions cover manifest validation, canonical observation/action contracts, isolated execution, timeout handling, invalid-output fallback, PettingZoo-style parallel semantics, ROS algorithm bridge contracts, paired-seed comparisons, and complete visible-action mapping.

Aggregate automated result: **135 tests passed, 0 failures, 0 errors**.
