# Transactional synchronization protocol

A change to topology, swarm state, antennas, world, traffic, failures, service region, packet cursor, or simulation clock creates a durable candidate revision.

```text
validate candidate
-> persist draft
-> apply to ROS 2
-> receive matching ROS acknowledgement
-> invalidate/recompute Sionna state
-> receive matching Sionna acknowledgement
-> apply to the persistent Isaac bridge
-> receive matching Isaac acknowledgement and scene checksum
-> compare desired and observed hashes
-> commit authoritative revision
-> publish telemetry and evidence
```

Required hashes are `config_hash`, `topology_hash`, `swarm_hash`, `antenna_hash`, `world_hash`, `traffic_hash`, and `failure_hash`. A disconnected participant leaves the command pending or degraded; it is never reported as applied. Reconnection replays the latest desired revision and the reconciler detects drift.
