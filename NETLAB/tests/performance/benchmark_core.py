#!/usr/bin/env python3
"""Host-side core microbenchmark.

This benchmark measures Python control-plane algorithms only. It is not an
Isaac, ROS 2, Sionna RT, GPU, or end-to-end scalability benchmark.
"""
from __future__ import annotations

import json
import platform
import statistics
import time
from pathlib import Path

from netlab.link import LinkRequest, compute_analytical_link, evaluate_feasibility
from netlab.packet import PacketRuntime
from netlab.topology import branches_to_edges, topology_metrics


def timed(fn, repetitions: int = 5):
    # Record cold-start/import cost separately, then report steady-state samples.
    cold_started = time.perf_counter()
    result = fn()
    cold_ms = (time.perf_counter() - cold_started) * 1000.0
    samples = []
    for _ in range(repetitions):
        started = time.perf_counter()
        result = fn()
        samples.append((time.perf_counter() - started) * 1000.0)
    return {
        "cold_start_ms": cold_ms,
        "median_ms": statistics.median(samples),
        "mean_ms": statistics.mean(samples),
        "min_ms": min(samples),
        "max_ms": max(samples),
        "repetitions": repetitions,
        "result_summary": result,
    }


def benchmark():
    report = {
        "scope": "host_side_python_core_only",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "benchmarks": {},
    }

    for count in (8, 16, 32, 64, 128):
        branches = [list(range(1, count + 1))]
        nodes = ["station"] + [f"drone_{i}" for i in range(1, count + 1)]
        edges = branches_to_edges(branches)
        report["benchmarks"][f"topology_chain_{count}"] = timed(
            lambda n=nodes, e=edges, c=count: {
                "node_count": topology_metrics(n, e, "station", [f"drone_{c}"])["node_count"],
                "edge_count": len(e),
            }
        )

    request = LinkRequest(
        src="station",
        dst="drone_1",
        tx_position=[0.0, 0.0, 1.5],
        rx_position=[28.0, 0.0, 30.0],
        frequency_hz=3.5e9,
        bandwidth_hz=20e6,
        tx_power_dbm=23.0,
        tx_gain_dbi=8.0,
        rx_gain_dbi=2.5,
    )

    def link_batch(size=10000):
        feasible = 0
        for index in range(size):
            request.rx_position = [28.0 + (index % 10), float(index % 3), 30.0]
            metric = compute_analytical_link(request)
            decision = evaluate_feasibility(
                metric,
                source_active=True,
                destination_active=True,
                source_failed=False,
                destination_failed=False,
                operational_range_m=90.0,
                hard_outage_distance_m=220.0,
                min_snr_db=3.0,
                min_sinr_db=3.0,
                min_capacity_mbps=1.0,
                metric_ttl_s=2.0,
            )
            feasible += int(decision.feasible)
        return {"evaluations": size, "feasible": feasible}

    report["benchmarks"]["analytical_link_gate_10000"] = timed(link_batch, repetitions=3)

    runtime = PacketRuntime.from_branches([list(range(1, 21))], mode="chain")
    metric = compute_analytical_link(request)
    decision = evaluate_feasibility(
        metric,
        source_active=True,
        destination_active=True,
        source_failed=False,
        destination_failed=False,
        operational_range_m=90.0,
        hard_outage_distance_m=220.0,
        min_snr_db=3.0,
        min_sinr_db=3.0,
        min_capacity_mbps=1.0,
        metric_ttl_s=2.0,
    )

    def packet_steps(size=10000):
        local = PacketRuntime.from_branches([list(range(1, 21))], mode="chain")
        for _ in range(size):
            local.step(lambda _src, _dst: decision)
        return {"steps": size, "events": local.event_sequence, "delivered": local.summary()["delivered_packets"]}

    report["benchmarks"]["packet_state_machine_10000"] = timed(packet_steps, repetitions=3)
    return report


if __name__ == "__main__":
    result = benchmark()
    print(json.dumps(result, indent=2, sort_keys=True))
