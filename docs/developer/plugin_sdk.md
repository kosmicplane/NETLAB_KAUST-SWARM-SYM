# Plugin SDK

A plugin directory contains `manifest.json` and `plugin.py`. The manifest declares ID, version, API version, category, execution mode, timeout, required fidelity, parameters, and fallback.

Supported hooks include `initialize`, `validate`, `reset`, `plan_positions`, `plan_velocities`, `plan_trajectories`, `on_state_update`, `on_topology_update`, `on_link_update`, `on_failure`, `select_standby`, `recompute_topology`, `compute_metric`, and `shutdown`.

Outputs are rejected when they contain unknown entity IDs, non-finite values, an ambiguous coordinate frame, invalid units/timestamps, geofence or dynamics violations, unsafe separation, or schema incompatibility. Untrusted plugins execute in an isolated worker with timeout and resource policy.
