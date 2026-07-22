# NETLAB Target Acceptance Runbook

This runbook must be executed on the reference Brev/NVIDIA host. Results must be archived with the run manifest and support bundle. It is intentionally not marked complete in the artifact-building sandbox.

## 1. Clean host preparation

```bash
cd "$HOME"
rm -rf NETLAB
unzip NETLAB.zip
cd NETLAB
./scripts/bootstrap_host.sh --install-packages --non-interactive
```

Expected: bootstrap reaches `READY`, the reference smoke test passes, and no source patch or manual service-by-service startup is required.

## 2. Readiness evidence

```bash
./scripts/netlab status > /tmp/netlab-status.json
./scripts/netlab packet-doctor > /tmp/netlab-packet-doctor.json
./scripts/netlab sync-doctor > /tmp/netlab-sync-doctor.json
./scripts/netlab smoke-test > /tmp/netlab-smoke-test.json
```

Acceptance conditions:

- Sionna API ready and heartbeat fresh;
- ROS container running with restart count zero;
- ROS graph contains the packet-runtime node;
- packet heartbeat fresh and sequence advancing;
- Isaac process and scene heartbeat fresh;
- one committed revision acknowledged by ROS, Sionna, and Isaac;
- telemetry source `LIVE`;
- reference gate `FEASIBLE`.

## 3. Transactional edits

From Mission Control or the API:

1. move one UAV to an exact coordinate;
2. change chain to parallel;
3. rotate one antenna;
4. move one world asset;
5. verify each command remains pending until all required participants acknowledge the same revision and domain hashes;
6. compare desired and observed coordinates/edges/antenna/world transforms.

## 4. Failure and recovery

1. inject a relay failure;
2. verify packet advancement pauses and the exact endpoint/gate reason is recorded;
3. recompute topology or promote a standby;
4. verify the replacement path passes the same gate;
5. verify packet advancement resumes only afterward;
6. archive recovery latency and service-continuity evidence.

## 5. Restart and replay

```bash
./scripts/netlab restart --no-build
./scripts/netlab status
./scripts/netlab sync-doctor
```

Acceptance: no duplicate runtime, latest committed revision replayed, no stale ready badge, and no orphan container/process.

## 6. Evidence export

```bash
./scripts/netlab support-bundle --reason target_acceptance
```

Preserve container logs, image digests, GPU information, ROS graph/QoS evidence, heartbeats, revision ACKs, telemetry, experiment config, screenshots, and WebRTC observations.
