# Validation

NETLAB is released through a deterministic gate executed from the repository root:

```bash
./scripts/diagnostics/validate_release.sh
```

The gate compiles every Python source file, validates every shell entry point, checks the complete browser ES-module set, parses all JSON/YAML assets, validates the active experiment and every packaged scenario, executes the complete automated suite, runs embedded acceptance, verifies Mission Control and the communication-service APIs, checks documentation links, enforces repository hygiene, validates OpenAPI and the CycloneDX SBOM, and verifies researcher-algorithm and visible-action contracts.

## Executed release evidence

- 135 automated unit, integration, browser, scientific, API, ROS/Compose-contract, Isaac-contract, safety, synchronization, and regression tests passed.
- 193 Python sources compiled.
- 44 experiment scenarios validated.
- 27 algorithm packages and manifests validated.
- 59 visible-action contracts validated.
- 17 primary Mission Control views rendered in Chromium without a blank workspace or JavaScript page error.
- Atomic shared-state replacement, readable modes, revision acknowledgements, drift detection, packet-gate truth tables, parallel branch independence, plugin isolation, paired-seed comparison, and embedded acceptance passed.
- The packaged ZIP is extracted after creation; its root, executable entry points, active configuration, bootstrap guard, ROS environment loader, manifest, and archive integrity are verified.

The machine-readable result is stored in:

```text
reports/validation/v9_test_report.json
```

## Target stack acceptance

The live GPU/ROS 2/Sionna/Isaac acceptance gate is:

```bash
./scripts/netlab target-acceptance
```

It verifies the target environment rather than inferring readiness from static files: Sionna API readiness, ROS container stability and graph readiness, packet and algorithm-runtime heartbeats, Isaac process and scene readiness, participant revision/hash agreement, live telemetry, feasible packet advancement, synchronized edits, fault/outage behavior, recovery, restart, and replay of the latest committed revision.

No `READY`, `LIVE`, `COMMITTED`, or recovery-success state is produced unless the corresponding runtime acknowledgement is observed.
