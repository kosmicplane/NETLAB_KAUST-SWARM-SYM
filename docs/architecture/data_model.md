# Authoritative data model

The principal typed records are SystemState, ServiceState, ReadinessState, ExperimentState, RevisionState, CommandState, UAVState, GroundEntityState, TopologyState, EdgeState, LinkState, PacketState, FlowState, AntennaState, WorldState, FailureState, RecoveryState, PluginState, TelemetryState, and EvidenceState.

Coordinates carry an explicit frame. SI units are authoritative internally. Every runtime event carries wall time, simulation time, experiment ID, run ID, command ID, revision ID, source component, affected entity, severity, and payload.
