# System architecture

NETLAB uses eight bounded layers.

1. Mission Control provides operator and researcher workflows.
2. The application layer owns commands, state, revisions, jobs, bootstrap, and reconciliation.
3. ROS 2 owns high-rate state coordination, packet execution, failures, and runtime acknowledgements.
4. The communication layer evaluates links and enforces the failure-aware feasibility gate.
5. Isaac Sim embodies the scene and acknowledges the applied revision and scene checksum.
6. Optional adapters connect protocol simulators and PX4 SITL without owning the authoritative experiment state.
7. The evidence layer records configurations, events, metrics, revisions, versions, and provenance.
8. The plugin layer isolates research algorithms from the core.

Mission Control does not infer readiness independently. The CLI, UI, diagnostics, and command notifications consume one observed readiness model. A container can be alive while its application is not ready; these states are represented separately.
