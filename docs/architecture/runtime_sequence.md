# Runtime sequence

```text
bootstrap
  -> validate host, GPU, Docker, ports, disk, configuration, and permissions
  -> start Mission Control
  -> start Sionna and wait for API readiness
  -> start ROS 2 and wait for container, graph, and packet heartbeat
  -> start Isaac and wait for process and scene heartbeat
  -> publish desired scenario revision
  -> wait for ROS, Sionna, and Isaac acknowledgements
  -> compare component hashes and scene checksum
  -> run feasibility-gated packet smoke test
  -> mark READY
```

Every wait has a timeout, last-observed signal, structured error code, logs, and recovery action. Repeated launch is idempotent and must not create duplicate packet runtimes.
