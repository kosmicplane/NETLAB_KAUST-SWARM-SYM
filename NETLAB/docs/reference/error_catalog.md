# Error catalog

- `PREFLIGHT_FAILED`: one or more host/configuration gates block startup.
- `COMPOSE_UP_FAILED`: Compose returned non-zero; stdout/stderr are preserved.
- `ROS_COMPOSE_FAILED`, `ROS_CONTAINER_TIMEOUT`, `PACKET_RUNTIME_TIMEOUT`: ROS startup stages failed.
- `ISAAC_COMPOSE_FAILED`, `ISAAC_PROCESS_TIMEOUT`, `ISAAC_SCENE_TIMEOUT`: Isaac startup stages failed.
- `SIONNA_TIMEOUT`: communication service was not ready.
- `REVISION_DRIFT`: desired and observed hashes differ.
- `ROS_ACK_FAILED`, `SIONNA_ACK_FAILED`, `ISAAC_ACK_FAILED`: a participant rejected or timed out.
- Feasibility reasons: `SOURCE_FAILED`, `DESTINATION_FAILED`, `SOURCE_INACTIVE`, `DESTINATION_INACTIVE`, `OUT_OF_RANGE`, `HARD_OUTAGE_DISTANCE`, `SNR_BELOW_THRESHOLD`, `SINR_BELOW_THRESHOLD`, `CAPACITY_BELOW_THRESHOLD`, `STALE_LINK_METRIC`, `NO_ROUTE`, `LINK_SERVICE_UNAVAILABLE`, `ANTENNA_INVALID`, `WORLD_MODEL_UNAVAILABLE`.
- `ALGORITHM_INVALID`: package manifest, source, entry point, API version, or resource budget is invalid.
- `ALGORITHM_NOT_FOUND`: requested algorithm ID is absent from the registry.
- `ALGORITHM_WORKER_TIMEOUT`: isolated worker exceeded the declared execution budget.
- `ALGORITHM_WORKER_PROTOCOL`: worker did not return valid JSON.
- `ALGORITHM_ACTION_INVALID`: action envelope or payload violates the public contract.
- `ALGORITHM_OUTPUT_REJECTED`: the Safety and Feasibility Shield rejected the proposal.
- `UNKNOWN_ENTITY`: an algorithm targeted an entity outside the authoritative snapshot.
- `EXECUTION_MODE_UNSUPPORTED`: the requested plugin execution mode is unavailable.
- `OCI_IMAGE_MISSING`, `OCI_EXECUTION_FAILED`: containerized algorithm configuration or execution failed.
- `REPLAY_EMPTY`: deterministic replay package contains no actions.
