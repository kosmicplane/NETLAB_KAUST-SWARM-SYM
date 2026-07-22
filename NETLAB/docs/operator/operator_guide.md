# Operator guide

Use `./scripts/netlab launch` for normal startup. Open Mission Control on port 8765. The Overview reports independent readiness for Sionna, ROS 2, packet runtime, Isaac process, Isaac scene, synchronization, and telemetry.

Use Mission Designer to validate and save a complete experiment. Saving a draft does not apply it. Apply Transactionally creates a revision and waits for participant acknowledgements.

Topology Studio supports chain, parallel, forest, manual, and graph-oriented research layouts. A graph can be structurally valid but physically invalid, communication-infeasible, unsynchronized, or non-operational.

Use Fault & Recovery to inject explicit failures. Service restoration requires a feasible replacement route and observed packet resumption.

## Researcher algorithms

Open **Algorithm Lab** to create, validate, dry-run, activate, compare and export algorithms. Activation is a transactional runtime change. The UI reports whether the selection is merely saved, pending ROS/Sionna/Isaac, in sync or committed. Do not interpret a selected package as active until participant acknowledgements match the revision.

Use **Run Invalid-Output Test** before live execution. It verifies that the safety layer rejects an unknown/unsafe target and applies the configured fallback. During a live run, inspect the algorithm heartbeat, source hash, execution duration, deadline/fallback count and desired-versus-observed state.
