# NETLAB Security Review

## Scope

This is a source/architecture review, not a penetration test, formal threat assessment, container-image vulnerability scan, or certification.

## Implemented controls

- Mission Control static paths are confined to the frontend root.
- JSON request bodies are bounded.
- Browser actions map to explicit commands; there is no arbitrary shell endpoint.
- Python Docker/process calls use argument lists rather than `shell=True` in the core.
- Compose services are resolved by service metadata, not untrusted arbitrary container names.
- Candidate revisions and command IDs provide audit correlation.
- Shared runtime writes are atomic, fsynced, and permission-controlled.
- Support bundles redact environment keys matching secret/token/password patterns.
- Plugin discovery is directory-constrained; invocation can run in an isolated process with timeout and output validation.
- Asset/import paths are contained and extension-allowlisted in current compatibility paths.
- Generated results, caches, local `.env`, and archives are excluded from source control/release packaging.
- Software/image inventory is recorded under `reports/security/`.

## Static observations

Targeted source scans found no embedded private keys or obvious credentials in the release source. The new core contains no intentional `os.system` or `subprocess(..., shell=True)` path. Dynamic code loading remains a trust boundary for plugins and Isaac extensions.

The Brev compatibility setup may rely on external package installation mechanisms. Controlled environments should use pinned package repositories/artifacts and verify provenance rather than executing unpinned remote scripts.

## Residual risks

### Mission Control authentication and authorization

The built-in server does not provide complete multi-user authentication, role authorization, TLS termination, CSRF protection, tenant isolation, or regulated audit identity. Operate on a private/trusted network or behind an authenticated TLS reverse proxy.

### Plugins

Process isolation and timeout are fault-containment measures, not a hostile-code sandbox. Untrusted plugins require dedicated containers/users, read-only mounts, CPU/memory/GPU quotas, network policy, dependency review, and administrative approval.

### Uploaded worlds and assets

Production upload requires size quotas, archive-safe extraction, mesh/texture complexity limits, importer timeout, malware scanning, format validation, and resource accounting. A valid extension alone is insufficient.

### Container and dependency supply chain

Generate SPDX/CycloneDX SBOMs and scan host/container dependencies in CI/target deployment. Pin publication campaigns to image digests and preserve vulnerability reports with run provenance.

### Remote control and physical systems

Commands can change swarm state, failures, and future autopilot outputs. Real-aircraft/HITL integration requires an independent safety architecture, least privilege, command authorization, geofencing, emergency stop, and hardware interlocks.

### Shared filesystem

The current single-host profile depends on mounted shared directories. Validate UID/GID, setgid semantics, filesystem atomic-replace behavior, quotas, and backup policy on each deployment platform.

### Support bundles and evidence

Bundles/logs may include hostnames, paths, model parameters, and experiment data. Review/redact before external sharing. Secrets must not be placed in experiment JSON.

## Recommended release/deployment gates

1. Run filesystem and image scanners such as Trivy/Grype or an equivalent controlled tool.
2. Generate SBOMs for the host package and each image.
3. Pin images by digest for publication/benchmark campaigns.
4. Deploy Mission Control behind authenticated TLS termination.
5. Run untrusted plugins in restricted worker containers.
6. Add upload quotas, safe extraction, and content scanning before browser asset upload is enabled.
7. Add security headers and CSRF controls when an authenticated web session is introduced.
8. Verify support-bundle redaction with deployment-specific secret names.
9. Perform a target penetration test before public/shared exposure.
10. Treat F6 hardware control as a separate safety/security program.
