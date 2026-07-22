# ROS 2 interfaces

The `netlab_interfaces` package defines typed entity, link, packet, revision, command, algorithm, and service-health contracts. JSON topics remain only as documented compatibility boundaries.

## Research algorithm interfaces

- `/netlab/algorithm/observation` — `netlab_interfaces/msg/AlgorithmObservation`
- `/netlab/algorithm/action` — `netlab_interfaces/msg/AlgorithmAction`
- `/netlab/algorithm/status_typed` — `netlab_interfaces/msg/AlgorithmStatus`
- `/netlab/algorithm/validate` — `netlab_interfaces/srv/ValidateAlgorithm`
- `RunAlgorithm.action` — bounded long-running execution contract

`netlab_researcher_algorithm_bridge` builds canonical snapshots, invokes or receives researcher actions, applies the Safety and Feasibility Shield, publishes accepted/fallback actions, and writes a readable heartbeat. The packet runtime consumes accepted actions but remains the only component that advances packet cursors.

## QoS registry

- Commands and acknowledgements: reliable.
- Configuration, committed revision and static topology: reliable, transient-local where appropriate.
- Critical failures and recovery events: reliable.
- UAV state and high-rate visualization: configurable best-effort or reliable according to the experiment.
- Link metrics and packet events: reliable when required by the active service contract; freshness is checked independently.
- Telemetry: bounded-history stream with dropped-sample accounting.

Readiness requires the container, ROS graph, packet runtime, revision agent and researcher algorithm bridge to be observable. A running container alone is not a ready ROS service.
