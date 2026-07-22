# Changelog

## 9.0.0

- Added the Researcher Algorithm Runtime with isolated Python, external ROS 2, OCI, PettingZoo-style MARL, and replay execution modes.
- Added typed ROS 2 algorithm observation, action, status, validation, and run interfaces.
- Added the safety and communication-feasibility shield, live algorithm bridge, Algorithm Lab workflow, paper-derived reference baselines, paired-seed benchmarking, and evidence export.
- Preserved communication-gated packet advancement and transactional ROS 2/Sionna/Isaac synchronization.

## 8.0.0

- Unified Mission Control and CLI behind one bootstrap/orchestration path.
- Replaced the fragile minimal frontend with a 17-module scientific operations interface and browser-tested bootstrap guard.
- Added explicit JavaScript module identity, correct static MIME/HEAD handling, cache-safe delivery, and visible startup failures instead of a blank page.
- Eliminated the ROS environment `nounset` restart loop and built the complete ROS workspace, including typed interfaces.
- Added a supervised ROS revision agent and packet runtime with canonical heartbeat and acknowledgement files.
- Centralized permission-safe atomic I/O and shared-tree repair for host/container coordination.
- Added exact desired/observed revision tracking, participant acknowledgements, domain hashes, drift detection, reconciliation, and rollback.
- Made topology plus coordinate inventory changes one atomic transaction.
- Added analytical per-edge link previews and separate structural, physical, communication, synchronization, and operational states.
- Hardened Sionna and Isaac revision acknowledgement contracts.
- Prevented Docker/containerd package conflicts on managed Brev hosts.
- Added dynamic container recovery, stale-heartbeat removal, force-recreation of unhealthy services, and bounded startup diagnostics.
- Added browser end-to-end coverage for every Mission Control module and expanded unit/integration/scientific regression coverage.
- Normalized plugin categories and retained fourteen isolated research examples.
- Removed Pegasus from the repository and required execution path; optional PX4 remains isolated.
- Updated research traceability to current NASA model-and-simulation guidance, 3GPP channel-model references, Sionna RT literature, and ROS 2 Jazzy guidance.
