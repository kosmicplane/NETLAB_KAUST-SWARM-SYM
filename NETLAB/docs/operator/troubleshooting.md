# Troubleshooting

```bash
./scripts/netlab doctor --repair
./scripts/netlab status
./scripts/netlab packet-doctor
./scripts/netlab sync-doctor
./scripts/netlab logs ros2-core
./scripts/netlab logs isaac
./scripts/netlab support-bundle --reason "describe the failure"
```

`AMENT_TRACE_SETUP_FILES: unbound variable` is prevented by `netlab_ros_env.sh`, which disables nounset while ROS setup files are sourced. Heartbeats are written with mode 0664 through atomic replacement. A `PENDING_ISAAC` revision means the change is durable but not committed to embodied execution.
