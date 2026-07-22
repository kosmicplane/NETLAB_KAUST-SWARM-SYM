# NETLAB validation report

The release gate executes Python compilation, shell syntax, JavaScript module syntax, JSON/YAML parsing, active configuration validation, all packaged scenario validation, 135 unit/integration/browser/scientific/contract tests, embedded acceptance, OpenAPI checks, SBOM checks, release hygiene, archive integrity, and extracted-package smoke validation.

Executed browser evidence covers every Mission Control module and verifies that no view produces a blank shell or JavaScript bootstrap failure. Representative screenshots are stored under `reports/validation/screenshots/`.

The live target command is:

```bash
./scripts/netlab target-acceptance
```

It performs bounded checks against the actual Brev stack: Sionna readiness, ROS graph readiness, packet heartbeat, Isaac scene readiness, matching participant revision acknowledgements, live telemetry, feasible packet advancement, and clean lifecycle operation.

Researcher algorithm validation covers 27 packaged algorithms, typed ROS observation/action/status interfaces, the Algorithm Lab API and browser workflow, the Safety and Feasibility Shield, isolated dry runs, explicit negative-output rejection, paired deterministic comparisons, and evidence export contracts.
