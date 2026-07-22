# Algorithm Benchmark Protocol

## Experimental unit

An experimental unit is one algorithm, one immutable scenario revision, one fidelity profile, one deterministic seed, one model registry version, and one complete run interval. Algorithms are not ranked across different scenario hashes or fidelity profiles without an explicit incompatibility warning.

## Required phases

1. Validate package and source/dependency hashes.
2. Execute deterministic dry run and negative-output rejection test.
3. Warm up the simulation and discard the configured warm-up interval.
4. Execute the evaluation interval.
5. Inject scheduled faults only at revisioned simulation times.
6. Record fallback, timeout and constraint-rejection events.
7. Stop cleanly and seal the evidence bundle.

## Paired comparison

Use identical scenario revisions, initial UAV state, user demand, world/antenna state, failure schedule, and seed set. For stochastic experiments, use at least the configured replication count and report the paired seed list. Confidence intervals require sufficient independent replications; otherwise NETLAB emits a sample-size warning.

## Required measurements

- algorithm execution mean, p95 and deadline misses;
- action acceptance, rejection, projection and fallback rate;
- objective values and constraint residuals;
- position/velocity/formation error and control effort;
- minimum separation, geofence and collision-risk events;
- algebraic connectivity, articulation points, bridge edges and path diversity;
- packet advancement, delivery, throughput, goodput, delay, jitter and AoI;
- range/SNR/SINR/capacity margins and outage duration;
- energy, reserve violations and energy per delivered bit;
- failure detection, recomputation, standby selection, synchronization and packet-resume latency;
- service-continuity score;
- simulation real-time factor and platform resource utilization.

## Reporting

Every result states the algorithm and source hashes, scenario and configuration hashes, fidelity/model versions, assumptions, validity domain, seed set, run timing, sample count, uncertainty method, and known deviations from a cited baseline. Raw events and metric samples remain exportable with the summary.
