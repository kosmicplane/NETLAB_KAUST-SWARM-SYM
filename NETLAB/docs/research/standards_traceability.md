# Standards and primary-source traceability

| Concern | Primary source | NETLAB application | Evidence |
|---|---|---|---|
| Model purpose, credibility, risk, assumptions, acceptance criteria | NASA-STD-7009B; NASA-HDBK-7009B | Fidelity profiles, model metadata, validity domains, test evidence, explicit limitations | `docs/research/model_credibility.md`, model-source matrix, scientific tests |
| Secure development and supply-chain hygiene | NIST SSDF | safe extraction, plugin isolation, redacted support bundles, dependency inventory, SBOM | `netlab/security.py`, `security/sbom.cdx.json`, security tests |
| Terrestrial channel-model selection | 3GPP TR 38.901 | selectable channel profiles with scenario/domain labels | model registry and configuration validation |
| NTN assumptions | 3GPP TR 38.811/TR 38.821 | slant range, delay, frequency/Doppler metadata, explicit NTN profile | `netlab/research_tools.py`, NTN scenarios |
| Free-space attenuation | ITU-R P.525 | F1 reference path loss | `fspl_db`, reference tests |
| Atmospheric/rain/vegetation/clutter components | ITU-R P.676/P.838/P.833/P.2108 | optional, separately labeled loss components; double-counting checks | communication configuration and model composition validation |
| Geometry-aware RF | Sionna RT technical literature and documentation | F3 adapter, geometry/material versions, cache invalidation, path provenance | Sionna service contract, World Lab, Antenna Lab |
| Middleware delivery semantics | ROS 2 Jazzy QoS documentation | typed messages/services/actions and interface-specific QoS policy | `netlab_interfaces`, `docs/architecture/ros_interfaces.md` |
| Embodied scene control | Isaac Sim extension and ROS bridge guidance | persistent headless bridge, revision ACK, scene checksum, observed positions | `netlab.snaas.bridge`, Isaac contract tests |
| Autopilot simulation | PX4 SITL documentation | optional isolated F5 profile; not required for NETLAB startup | PX4 scenario/profile and operator guide |

NETLAB uses these sources as engineering guidance and model provenance. The repository does not imply certification or institutional endorsement.
