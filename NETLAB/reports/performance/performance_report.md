# NETLAB host-side performance benchmark

Platform: `Linux-4.4.0-x86_64-with-glibc2.41`  
Python: `3.13.5`

This benchmark measures the Python control plane, graph analytics, analytical link gate, and packet state machine. It does not substitute for the live Brev target acceptance gate.

| Benchmark | Cold start (ms) | Median (ms) | Mean (ms) | Result |
|---|---:|---:|---:|---|
| `analytical_link_gate_10000` | 197.331 | 211.460 | 204.308 | `{"evaluations":10000,"feasible":10000}` |
| `packet_state_machine_10000` | 890.373 | 756.848 | 745.242 | `{"delivered":500,"events":10500,"steps":10000}` |
| `topology_chain_128` | 26.335 | 30.863 | 33.458 | `{"edge_count":128,"node_count":129}` |
| `topology_chain_16` | 0.546 | 0.504 | 0.515 | `{"edge_count":16,"node_count":17}` |
| `topology_chain_32` | 1.652 | 1.369 | 1.355 | `{"edge_count":32,"node_count":33}` |
| `topology_chain_64` | 689.740 | 8.848 | 9.350 | `{"edge_count":64,"node_count":65}` |
| `topology_chain_8` | 0.601 | 0.249 | 0.303 | `{"edge_count":8,"node_count":9}` |

## Performance controls

- Batched and vectorizable link-service contracts.
- Incremental revision hashes and domain-specific cache invalidation.
- Bounded telemetry history and explicit decimation.
- Independent authoritative simulation and rendering update rates.
- Deterministic approximations for large graph metrics where exact algorithms are not cost-effective.
