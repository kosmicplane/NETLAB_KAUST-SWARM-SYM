"""Latency-aware feasible routing policy using Dijkstra's algorithm."""
from __future__ import annotations
import heapq

PLUGIN_MANIFEST = {
    "plugin_id": "latency_aware_routing",
    "name": "Latency-Aware Routing",
    "version": "1.0.0",
    "api_version": "1.0",
    "description": "Minimizes cumulative model-derived delay over currently feasible links.",
    "execution_mode": "isolated_worker",
    "timeout_s": 0.25,
    "required_fidelity": "F1_ANALYTICAL",
    "safety_fallback": "ordered_path",
    "parameters": {"hop_penalty_ms": {"type": "number", "default": 0.1, "minimum": 0.0}},
}


def plan_route(context):
    source = str(context.get("source", "station"))
    destination = str(context.get("destination", ""))
    penalty = float(context.get("parameters", {}).get("hop_penalty_ms", 0.1))
    graph = {}
    for link in context.get("links", []):
        if not link.get("feasible", link.get("link_ok", False)):
            continue
        delay = float(link.get("total_delay_ms", link.get("propagation_delay_ms", 0.0))) + penalty
        graph.setdefault(str(link.get("src")), []).append((str(link.get("dst")), max(0.0, delay)))
    distance = {source: 0.0}
    parent = {}
    queue = [(0.0, source)]
    while queue:
        cost, node = heapq.heappop(queue)
        if node == destination:
            break
        if cost != distance.get(node):
            continue
        for neighbor, weight in graph.get(node, []):
            candidate = cost + weight
            if candidate < distance.get(neighbor, float("inf")):
                distance[neighbor] = candidate
                parent[neighbor] = node
                heapq.heappush(queue, (candidate, neighbor))
    if destination not in distance:
        return {"route": [], "reason": "NO_FEASIBLE_ROUTE", "estimated_delay_ms": None}
    route = [destination]
    while route[-1] != source:
        route.append(parent[route[-1]])
    route.reverse()
    return {"route": route, "reason": "CANDIDATE_ROUTE", "estimated_delay_ms": distance[destination]}


def recompute_topology(context):
    return plan_route(context)
