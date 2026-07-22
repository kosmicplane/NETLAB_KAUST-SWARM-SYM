# Research and standards foundation

NETLAB separates implementation claims from model credibility. A model result is useful only when its intended use, assumptions, inputs, equations, numerical implementation, uncertainty, validity domain, verification evidence, and validation evidence are visible to the researcher.

## Modeling and simulation credibility

The credibility framework follows the discipline described by **NASA-STD-7009B, Standard for Models and Simulations** (approved 2024-03-05) and the companion **NASA-HDBK-7009B** (approved 2026-02-03). These references motivate explicit acceptance criteria, model-management factors, assumptions, uncertainty, risk, evidence, caveats, and use-specific credibility assessments. NETLAB does not claim NASA certification; it applies comparable traceability concepts to research simulations.

Primary references:

- NASA-STD-7009B: <https://standards.nasa.gov/sites/default/files/standards/NASA/B/1/NASA-STD-7009B-Final-3-5-2024.pdf>
- NASA-HDBK-7009B: <https://standards.nasa.gov/system/files/tmp/NASA-HDBK-7009B_Final%2002-03-2026.pdf>
- NIST Secure Software Development Framework: <https://csrc.nist.gov/Projects/ssdf>

## Wireless channel and NTN models

The platform treats 3GPP and ITU-R documents as model-selection references rather than universal formulas. **3GPP TR 38.901** is a study of channel models from 0.5 to 100 GHz and remains under change control. Its scenarios and assumptions must be selected deliberately. NTN studies such as TR 38.811 and TR 38.821 inform geometry, delay, Doppler, and deployment assumptions; they do not automatically make an analytical calculation a standards-compliant end-to-end NTN simulation.

Primary references:

- 3GPP TR 38.901 specification record: <https://www.3gpp.org/dynareport/38901.htm>
- 3GPP 38-series index: <https://www.3gpp.org/dynareport/38-series.htm>
- 3GPP NTN overview and specification links: <https://www.3gpp.org/technologies/ntn-overview>
- ITU-R P.525 free-space attenuation: <https://www.itu.int/rec/R-REC-P.525>
- ITU-R P.676 atmospheric gases: <https://www.itu.int/rec/R-REC-P.676>
- ITU-R P.838 rain attenuation: <https://www.itu.int/rec/R-REC-P.838>
- ITU-R P.833 vegetation attenuation: <https://www.itu.int/rec/R-REC-P.833>
- ITU-R P.2108 clutter loss: <https://www.itu.int/rec/R-REC-P.2108>

## Geometry-aware propagation

Sionna RT provides a GPU-accelerated, differentiable ray-tracing foundation for geometry-aware radio propagation. NETLAB therefore maintains distinct fidelity labels for analytical, stochastic, and geometry-aware results. A rendered coverage cone is not an RF result, and a free-space link budget is not labeled as urban ray tracing.

Primary references:

- Sionna RT publication page: <https://research.nvidia.com/publication/2023-12_sionna-rt-differentiable-ray-tracing-radio-propagation-modeling>
- Sionna documentation: <https://nvlabs.github.io/sionna/>

## ROS 2 and embodied execution

ROS 2 QoS is selected per contract: durable configuration and critical failure events require reliable semantics; high-rate visualization streams may use best-effort delivery when loss is preferable to latency. NETLAB distinguishes container liveness, ROS graph readiness, packet-runtime readiness, Isaac process readiness, Isaac scene readiness, and scenario acknowledgement.

Primary references:

- ROS 2 Jazzy QoS concepts: <https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Quality-of-Service-Settings.html>
- Isaac Sim ROS 2 integration: <https://docs.isaacsim.omniverse.nvidia.com/>
- PX4 simulation documentation: <https://docs.px4.io/main/en/simulation/>

## UAV networking, control, and co-simulation

The architecture is informed by synchronized UAV/network simulation, multi-UAV trajectory and communication co-design, graph connectivity control, flocking and consensus, rotary-wing energy modeling, Age of Information, and protocol-level simulators. External protocol simulators are integrated through adapters only when their additional fidelity justifies synchronization and maintenance cost.

Representative research anchors:

- FlyNetSim: synchronized UAV/network simulation based on ns-3 and ArduPilot.
- UavNetSim-v1: modular UAV-network simulation.
- 5G-LENA: NR system-level simulation for ns-3.
- Simu5G: OMNeT++-based 5G and MEC studies.
- Joint trajectory and communication design for multi-UAV networks.
- Rotary-wing UAV energy-minimization models.
- Graph-theoretic connectivity control and multi-agent flocking.
- Age of Information for time-sensitive update systems.

## Implementation rule

No equation is copied into the executable model without recording:

1. phenomenon and intended use;
2. source and model version;
3. assumptions and validity domain;
4. parameters and SI units;
5. implementation location;
6. verification test;
7. calibration or validation status;
8. metrics influenced by the model;
9. known limitations and uncertainty.

## Researcher-defined algorithm execution

NETLAB treats algorithm interchangeability as a first-class research requirement. PettingZoo motivates a stable multi-agent API that improves reuse and reproducibility; NETLAB implements compatible parallel-step semantics while retaining one authoritative simulator state. The MARL environment therefore exposes simultaneous per-UAV actions, explicit reward decomposition, deterministic reset/replay, and the same Safety and Feasibility Shield used by deterministic controllers.

The executable baseline library maps research questions to code rather than using citations decoratively:

- **Distributed placement and user association:** `learn_as_you_fly_placement` provides a traceable deterministic reference for three-dimensional placement and user-association studies.
- **Joint trajectory and communications:** `joint_trajectory_communication_optimizer` exposes trajectory, association and power-control objectives with explicit solver/fallback status.
- **Energy-aware flight:** `rotary_wing_energy_optimizer` separates propulsion and communication energy and requires calibration for vehicle-specific claims.
- **Connectivity and coverage:** `graph_connectivity_controller`, `connectivity_aware_formation` and `voronoi_coverage_controller` expose graph and service-region objectives while the link gate remains authoritative.
- **Collective motion and safety:** `distributed_flocking_controller` supplies a distributed baseline; `cbf_safety_filter` provides a constrained safety layer or a conservative deterministic fallback.
- **Learning communication quality:** `data_driven_connectivity_controller` distinguishes predicted and observed link state and exposes uncertainty.
- **Spectrum, beamforming and information freshness:** `mobility_resilient_spectrum_sharing`, `collaborative_beamforming` and `aoi_aware_scheduler` provide clearly fidelity-labelled research abstractions.

`docs/research/algorithm_source_matrix.csv` records the paper-to-code disposition, assumptions, validity domain, implementation location, tests and deviations for every adopted work. A plugin is not described as an exact reproduction unless its mathematical objective, constraints, initialization, termination and benchmark conditions match the cited method.

## Simulator interoperability evidence

FlyNetSim, Ns3Sionna and related digital-network-twin work motivate explicit synchronization between mobility, channel and protocol time scales. NETLAB keeps a lightweight native packet/runtime model for interactive studies and provides adapter boundaries for future ns-3/5G-LENA or Simu5G use. The external simulator does not become authoritative merely by being connected: revisions, timestamps, channel age and packet events must remain traceable to the NETLAB experiment clock.

RotorPy and Aerial Gym are used as dynamics and scalability references. Their existence does not turn NETLAB's analytical dynamics into calibrated aerodynamics; vehicle-specific claims require parameters and validation data. Isaac remains the embodied scene executor, while model provenance and fidelity labels prevent render quality from being confused with physical validity.
