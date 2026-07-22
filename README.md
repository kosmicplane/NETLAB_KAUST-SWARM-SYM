# NETLAB — Swarm Network-as-a-Service Research Platform

NETLAB is a modular research platform in which coordinated UAV swarms operate as reconfigurable airborne communication infrastructure. It couples embodied execution in Isaac Sim, ROS 2 coordination, Sionna-compatible link evaluation, communication-gated packet forwarding, researcher-defined algorithms, runtime failures, fault-aware recovery, scientific telemetry, and reproducible evidence collection.

## Execution invariant

Communication feasibility is an execution gate, not a post-processing statistic. For an active hop \((i,j)\), packet advancement requires active non-failed endpoints, a valid route, fresh link metrics, operational and hard-outage range compliance, SNR or SINR above threshold, capacity above threshold, and valid antenna/world state. A failed predicate pauses the authoritative cursor and records the exact reason. Recovery is acknowledged only after the replacement path passes the same gate and ROS 2, the communication service, and Isaac Sim acknowledge one revision.

## What researchers can change

Researchers can configure or replace, without editing NETLAB core code:

- swarm controllers, trajectory planners, formation and connectivity controllers;
- topology generators, routing policies, recovery policies, and standby selection;
- propagation, antenna, traffic, scheduling, energy, metric, and optimization plugins;
- exact UAV positions, formations, relay branches, service regions, worlds, materials, antennas, users, traffic flows, faults, and recovery schedules;
- Python algorithms, external ROS 2 nodes, isolated OCI plugins, PettingZoo-style MARL policies, and deterministic replay traces.

Algorithm outputs remain advisory until they pass the Safety and Feasibility Shield. The shield validates schemas, units, frames, identities, freshness, geofence, altitude, separation, motion limits, battery reserve, and predicted communication feasibility before a revision can be dispatched to ROS 2, Sionna, and Isaac.

## Runtime stack

- **Mission Control** — experiment design, Algorithm Lab, topology, swarm control, antennas, worlds, traffic, failures, telemetry, synchronization, diagnostics, and evidence.
- **ROS 2 Jazzy** — typed algorithm observations/actions/status, packet runtime, revision application, UAV state, failure events, and acknowledgements.
- **Sionna-compatible link service** — path loss, received power, noise, SNR/SINR, capacity, delay, model provenance, feasibility, and revision acknowledgement.
- **Isaac Sim 5.1 profile** — headless embodied execution, persistent bridge, UAV/world/antenna state, packet markers, coverage/status overlays, and optional WebRTC viewing.
- **Evidence layer** — versioned configuration, hashes, JSONL events, CSV metrics, algorithm manifests/source hashes, run manifests, logs, plots, and support bundles.

Pegasus is not part of the required execution path. PX4 SITL remains optional and isolated.

## Clean installation on Brev

Place `NETLAB.zip` in `/home/ubuntu`, then run:

```bash
cd "$HOME"

if [ -d "$HOME/NETLAB/Docker/compose" ]; then
  cd "$HOME/NETLAB/Docker/compose"
  docker compose --env-file .env -f docker-compose.yml down --remove-orphans 2>/dev/null || true
fi

cd "$HOME"
rm -rf "$HOME/NETLAB"
unzip NETLAB.zip
cd NETLAB
chmod +x scripts/netlab scripts/*.sh Docker/scripts/*.sh Docker/workspace/ros2/*.sh

# Safe on managed Brev images: existing Docker/containerd packages are preserved.
./scripts/bootstrap_host.sh --non-interactive
```

Use `--install-packages` only on an unmanaged host that lacks basic utilities. The bootstrap detects an existing Docker installation and does not install a conflicting `containerd.io` package.

## Daily operation

```bash
cd ~/NETLAB
./scripts/netlab launch
./scripts/netlab status
./scripts/netlab packet-doctor
./scripts/netlab sync-doctor
./scripts/netlab smoke-test
./scripts/netlab stop
```

Mission Control is served on port `8765`. The WebRTC client is a viewer, not a control-plane dependency.

## Running a researcher algorithm

The minimal Python contract is:

```python
def step(snapshot, parameters):
    spacing_m = float(parameters.get("spacing_m", 28.0))
    altitude_m = float(parameters.get("altitude_m", 30.0))
    active = [u for u in snapshot["uavs"] if u["active"] and not u["failed"]]
    return {
        "coordinate_frame": "ENU",
        "desired_positions": {
            uav["id"]: [spacing_m * index, 0.0, altitude_m]
            for index, uav in enumerate(active, start=1)
        },
    }
```

NETLAB supplies the manifest template, parameter UI, isolated worker, typed snapshot, ROS adapter, safety validation, revisioning, Sionna reevaluation, Isaac synchronization, telemetry, fallback, and evidence. The complete example is in `plugins/research/researcher_chain_spacing/`.

From Mission Control:

```text
Algorithm Lab
→ select researcher_chain_spacing or connectivity_aware_formation
→ inspect manifest and assumptions
→ validate package
→ deterministic dry run
→ invalid-output rejection test
→ activate and synchronize
→ compare against a baseline using paired seeds
→ inject a failure
→ verify feasibility-gated recovery
→ export evidence
```

## Authoritative lifecycle

```text
PREFLIGHT
→ REPAIRING
→ BUILDING
→ STARTING_MISSION_CONTROL
→ STARTING_SIONNA
→ WAITING_FOR_SIONNA
→ STARTING_ROS
→ WAITING_FOR_ROS_CONTAINER
→ WAITING_FOR_ROS_GRAPH
→ WAITING_FOR_PACKET_RUNTIME
→ STARTING_ISAAC
→ WAITING_FOR_ISAAC_PROCESS
→ WAITING_FOR_ISAAC_SCENE
→ SYNCHRONIZING
→ SMOKE_TESTING
→ READY / RUNNING
```

Every wait is bounded and exposes the expected signal, last observation, elapsed time, timeout, retry state, and relevant logs.

## Transactional synchronization

Topology, swarm, algorithm, antenna, world, traffic, failure, and recovery changes produce a revision with domain hashes:

```text
Validate candidate
→ Save durable draft
→ Apply to ROS 2
→ Recompute or invalidate communication state
→ Apply to Isaac Sim
→ Compare desired and observed hashes and scene checksum
→ Commit revision
```

If a participant is unavailable, the change remains pending and can be reconciled or rolled back. It is not reported as operational merely because a file was written or a path was drawn.

## Algorithm library

The packaged registry includes readable examples and paper-informed reference modules for:

- chain spacing and connectivity-aware formation;
- distributed placement and user association;
- joint trajectory/communication optimization;
- rotary-wing energy-aware planning;
- graph-connectivity control and Voronoi coverage;
- distributed flocking and CBF safety filtering;
- data-driven connectivity maintenance;
- spectrum-sharing mobility;
- collaborative beamforming abstraction;
- Age-of-Information scheduling;
- maximum-bottleneck and latency-aware routing;
- failure-aware standby selection and Monte Carlo sampling.

Each package declares model assumptions, validity domain, resource budget, deterministic seed support, citations, source hash, supported fidelity profiles, fallback, and known limitations.

## Fidelity profiles

- **F0** — layout preview only.
- **F1** — analytical communication and motion abstractions.
- **F2** — stochastic channel, traffic, failures, and uncertainty.
- **F3** — geometry-aware Sionna RT adapter.
- **F4** — protocol-aware external co-simulation adapter.
- **F5** — optional PX4 SITL/autopilot execution.

Results carry fidelity, model identity, version, timestamp, source, freshness, quality, assumptions, and uncertainty. Preview and stale data are never labeled live.

## Repository structure

```text
apps/mission_control/       Mission Control backend, modular frontend, action registry
netlab/                     Core state, synchronization, models, algorithm runtime and shield
Docker/                     Compose, Isaac, ROS 2, Sionna, optional PX4 profile
plugins/                    Built-in and researcher algorithm packages
scenarios/                  Validated experiments and regression scenarios
schemas/                    Experiment, plugin, and API contracts
openapi/                    Mission Control API specification
security/                   SBOM and security metadata
tests/                      Unit, integration, browser, scientific, ROS/Compose contracts
docs/                       Architecture, operator, developer, and research guides
```

## Verification

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tests/run_all.py
./scripts/diagnostics/validate_release.sh
./scripts/netlab target-acceptance --embedded
```

On the Brev target, run the live acceptance gate:

```bash
./scripts/netlab target-acceptance
```

## Documentation

- `docs/operator/installation.md`
- `docs/operator/operator_guide.md`
- `docs/architecture/system_architecture.md`
- `docs/architecture/synchronization_protocol.md`
- `docs/developer/algorithm_sdk.md`
- `docs/research/algorithm_benchmark_protocol.md`
- `docs/research/research_playbook.md`
- `docs/research/model_credibility.md`
- `docs/reference/metrics_catalog.md`

## License

See `LICENSE`.
