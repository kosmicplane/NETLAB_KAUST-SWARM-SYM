# Researcher Algorithm SDK

## Purpose

The NETLAB Algorithm SDK lets researchers execute controllers, trajectory planners, topology/routing/recovery policies, antenna or traffic decisions, optimizers, MARL policies, and deterministic replays without modifying the simulator core. Research code proposes actions; NETLAB validates, shields, revisions, dispatches, acknowledges, visualizes, and records them.

## Supported execution modes

| Mode | Contract | Isolation | Typical use |
|---|---|---|---|
| `isolated_python` | `step(snapshot, parameters)` or declared hook | subprocess, timeout, memory/output limits | rapid algorithm research |
| `external_ros2` | typed algorithm messages/services/action | separate ROS process | native ROS research nodes |
| `oci_container` | JSON stdin/stdout contract | read-only container, no network by default | dependency-heavy algorithms |
| `pettingzoo_parallel` | `reset`/`step` parallel API | isolated policy process | MARL training/evaluation |
| `replay` | recorded action sequence | read-only replay | reproducibility and debugging |

## Package layout

```text
plugins/researcher/my_algorithm/
├── manifest.json
├── algorithm.py
├── test_algorithm.py
└── requirements.lock       # optional
```

The manifest is validated against `schemas/plugin/plugin-manifest-v1.schema.json`. Required identity and execution fields include the algorithm ID/version/API version, category, entry point, execution mode, parameter schema, observation/action schemas, resource budget, deterministic-seed support, fallback, supported fidelity profiles, assumptions, validity domain, and limitations.

## Minimal implementation

```python
from __future__ import annotations


def step(snapshot, parameters):
    spacing_m = float(parameters.get("spacing_m", 28.0))
    altitude_m = float(parameters.get("altitude_m", 30.0))
    active = [u for u in snapshot["uavs"] if u["active"] and not u["failed"]]
    desired_positions = {
        uav["id"]: [spacing_m * index, 0.0, altitude_m]
        for index, uav in enumerate(active, start=1)
    }
    return {
        "coordinate_frame": "ENU",
        "desired_positions": desired_positions,
        "objective_value": 0.0,
        "constraint_residuals": {},
        "termination_reason": "closed_form",
    }
```

See `plugins/research/researcher_chain_spacing/` for the packaged example.

## Observation contract

The read-only snapshot contains experiment/run/revision identity, wall and simulation time, deterministic seed, desired/commanded/simulated/measured/rendered UAV state, battery/failure/role state, graph and link metrics, packet/flow/queue state, world and weather metadata, antennas, failures/recovery, service requirements, motion/geofence constraints, and uncertainty. The exact serialized model is defined by `netlab.algorithm_contracts.AlgorithmObservation` and the typed ROS message `netlab_interfaces/msg/AlgorithmObservation`.

## Action contract

Algorithms may propose positions, velocities, accelerations, jerks, yaws, trajectories, topology/route/branch candidates, user associations, schedules, standby/recovery choices, antenna commands, transmit-power/channel allocations, metrics, or optimization results. Every action carries algorithm identity, source revision, timestamp, validity horizon, frame, units, computation duration, termination reason, objective value, constraint residuals, uncertainty, and fallback state.

## Safety and Feasibility Shield

Before dispatch, `netlab.safety_shield` enforces:

1. schema and finite-number validity;
2. known entity IDs and non-stale source revision;
3. frame and unit consistency;
4. geofence and altitude bounds;
5. separation and collision-risk checks;
6. speed, acceleration, jerk, climb/descent and command-rate limits;
7. battery reserve;
8. active/non-failed endpoints;
9. analytical communication-feasibility preview for required relay edges;
10. deterministic fallback when the proposal cannot be safely projected.

The shield never weakens the failure-aware link feasibility gate to make an algorithm appear successful.

## Algorithm Lab workflow

1. Create or select a package.
2. Inspect source hash, manifest, citations, assumptions and validity domain.
3. Validate the package.
4. Run a deterministic dry run.
5. Run the invalid-output rejection test.
6. Configure parameters from the generated form.
7. Activate the package; this creates a normal revision.
8. Wait for ROS 2, Sionna and Isaac acknowledgements.
9. Inspect desired/commanded/simulated/measured/rendered state and link margins.
10. Compare algorithms using paired seeds.
11. Export run evidence.

## External ROS 2 algorithms

External nodes use the typed interfaces:

- `/netlab/algorithm/observation` — `AlgorithmObservation`;
- `/netlab/algorithm/action` — `AlgorithmAction`;
- `/netlab/algorithm/status_typed` — `AlgorithmStatus`;
- `/netlab/algorithm/validate` — `ValidateAlgorithm`.

The `netlab_researcher_algorithm_bridge` validates and shields actions before they reach the packet runtime. External nodes must not mutate shared JSON files or the Isaac stage directly.

## PettingZoo-style MARL

`netlab.marl.NetlabParallelEnv` follows the parallel multi-agent shape:

```python
observations, infos = env.reset(seed=seed, options=options)
observations, rewards, terminations, truncations, infos = env.step(actions)
```

Reward terms are exposed separately for formation, connectivity, service continuity, packet delivery, safety, energy, control effort, and Age of Information. Actions remain subject to the same shield and cannot advance packet state directly.

## Reproducibility

Each algorithm run records the package/source/dependency hash, scenario/config/domain hashes, seed, fidelity profile, observations, actions, shield decisions, runtime duration, fallback/timeout state, metrics, and evidence paths. Paired comparisons must use the same scenario revision and seeds.
