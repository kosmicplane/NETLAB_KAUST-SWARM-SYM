# NETLAB Research Playbook

## First experiment

Bootstrap, open Guided Demo, load `first_feasible_relay_chain`, validate, apply the scenario, verify one committed revision, start the packet runtime, and inspect the gate values. Export the run manifest, metrics, events, and revision evidence.

## Controller study

Copy a plugin example, declare parameters in its manifest, implement stable hooks, validate output constraints, run identical scenarios/seeds for baseline and candidate, and compare tracking error, service continuity, packet advancement, energy, and controller execution time.

## Topology study

Create chain, parallel, forest, or manual graphs. Report structural validity separately from physical validity, communication feasibility, synchronization, and operational state. Compare route churn, path diversity, articulation points, bridges, algebraic connectivity, availability, outage, and recovery.

## World and RF study

Import a validated asset, confirm units/frame/scale, assign visual, physical, and electromagnetic materials separately, apply a world revision, wait for Isaac and Sionna acknowledgements, then collect LoS/NLoS, path-loss, capacity, coverage, and service-continuity evidence. Geometry-aware claims require the F3 adapter.

## Antenna study

Define model, frequency, bandwidth, gain, efficiency, pattern provenance, polarization, pose, cable loss, array geometry, weights, and steering. Apply one revision per design point and compare current metrics rather than stale cache entries.

## Failure and recovery

Specify failure type, target, start, duration, severity, detection symptoms, and recovery policy. Record detection, recomputation, standby selection, ROS application, Sionna recalculation, Isaac synchronization, packet-resume, and total recovery latency. Do not report successful recovery until packet advancement resumes on a feasible route.

## Uncertainty and parameter sweeps

Use deterministic run groups. Vary UAV spacing, altitude, thresholds, antenna parameters, traffic, wind, failures, and recovery policy with grid, random, Latin-hypercube, imported, or plugin-defined designs. Report sample size, seed policy, confidence intervals, effect size, and sensitivity. Do not report an interval from one sample.

## Calibration and replay

Import measured traces, preserve provenance and units, fit only parameters supported by the selected model, retain residuals, compare hold-out data, and state the calibrated validity domain. Replay uses simulation time and deterministic event ordering.

## Publication evidence

Retain the exact configuration and hashes, software version, Git state, container image digests, model versions, host/GPU details, seeds, run IDs, metrics, events, plots, screenshots, and limitations. Use SVG for publication figures when available and never label preview data as live.

## Running your own algorithm

### Minimal path

1. Open **Algorithm Lab** and select **Create Algorithm Project**.
2. Choose a lower-snake-case ID and implement only `step(snapshot, parameters)`.
3. Declare parameters and assumptions in the generated manifest.
4. Run **Validate Package**.
5. Run **Deterministic Dry Run** against the authoritative snapshot.
6. Run **Invalid-Output Test** and confirm the proposal is rejected with a safe fallback.
7. Select a validated scenario and fidelity profile.
8. Activate the algorithm. NETLAB creates a revision and waits for ROS 2, Sionna and Isaac acknowledgements.
9. Inspect desired, commanded, simulated, measured and rendered state separately.
10. Inject a relay failure, observe the outage reason, and evaluate the algorithm's response.
11. Compare against `researcher_chain_spacing` using the same seeds.
12. Export the algorithm evidence bundle.

### Canonical readable example

`plugins/research/researcher_chain_spacing/` demonstrates the smallest supported controller. It returns desired ENU positions for active non-failed relays. NETLAB handles process isolation, timeout, source hashing, parameter UI, frame/unit checks, separation and motion limits, communication preview, ROS publication, Sionna reevaluation, Isaac synchronization, packet gating and evidence.

### Connectivity-aware formation experiment

Use `scenarios/examples/connectivity_aware_formation.json` and plugin `connectivity_aware_formation`.

Record:

- formation error and minimum separation;
- algebraic connectivity or the declared connectivity surrogate;
- range/SNR/SINR/capacity margins;
- packet advancement and service continuity;
- controller execution time and fallback rate;
- energy proxy and energy per delivered bit;
- failure detection, topology recomputation and packet-resume latency.

The control result is accepted only if the Safety and Feasibility Shield accepts it. A visually attractive formation that breaks an active relay hop is not operational.

### External ROS 2 algorithm

An external node subscribes to `/netlab/algorithm/observation` and publishes `/netlab/algorithm/action` using `netlab_interfaces`. It should validate through `/netlab/algorithm/validate` and monitor `/netlab/algorithm/status_typed`. The algorithm must not edit Isaac, shared state files or packet cursors directly.

### MARL experiment

Use `NetlabParallelEnv` for simultaneous per-UAV actions. Preserve the seed, curriculum/domain-randomization distributions, checkpoint/source hash and reward decomposition. Evaluate learned policies against deterministic baselines with the Safety and Feasibility Shield enabled in both training and evaluation. Report every reward term rather than only the scalar sum.

### Benchmark protocol

Follow `docs/research/algorithm_benchmark_protocol.md`. Use immutable scenario revisions and paired seeds, separate warm-up from evaluation, preserve deadline misses and fallbacks, and avoid cross-fidelity rankings.
