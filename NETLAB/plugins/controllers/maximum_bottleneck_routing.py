"""Maximum-bottleneck feasible routing policy.

Uses only link records explicitly marked feasible and maximizes the minimum
capacity along the path. The returned route still requires NETLAB's normal
failure-aware feasibility gate at execution time.
"""
from __future__ import annotations
import heapq

PLUGIN_MANIFEST = {
    "plugin_id": "maximum_bottleneck_routing",
    "name": "Maximum-Bottleneck Routing",
    "version": "1.0.0",
    "api_version": "1.0",
    "description": "Selects a feasible path that maximizes bottleneck link capacity.",
    "execution_mode": "isolated_worker",
    "timeout_s": 0.25,
    "required_fidelity": "F1_ANALYTICAL",
    "safety_fallback": "ordered_path",
    "parameters": {"minimum_capacity_mbps": {"type": "number", "default": 1.0, "minimum": 0.0}},
}


def plan_route(context):
    source = str(context.get("source", "station"))
    destination = str(context.get("destination", ""))
    minimum = float(context.get("parameters", {}).get("minimum_capacity_mbps", 1.0))
    graph = {}
    for link in context.get("links", []):
        if not link.get("feasible", link.get("link_ok", False)):
            continue
        capacity = float(link.get("capacity_mbps", 0.0))
        if capacity < minimum:
            continue
        graph.setdefault(str(link.get("src")), []).append((str(link.get("dst")), capacity))
    best = {source: float("inf")}
    parent = {}
    queue = [(-best[source], source)]
    while queue:
        negative, node = heapq.heappop(queue)
        score = -negative
        if node == destination:
            break
        if score < best.get(node, 0.0):
            continue
        for neighbor, capacity in graph.get(node, []):
            candidate = min(score, capacity)
            if candidate > best.get(neighbor, -1.0):
                best[neighbor] = candidate
                parent[neighbor] = node
                heapq.heappush(queue, (-candidate, neighbor))
    if destination not in best:
        return {"route": [], "reason": "NO_FEASIBLE_ROUTE", "bottleneck_capacity_mbps": 0.0}
    route = [destination]
    while route[-1] != source:
        route.append(parent[route[-1]])
    route.reverse()
    return {"route": route, "reason": "CANDIDATE_ROUTE", "bottleneck_capacity_mbps": best[destination]}


def recompute_topology(context):
    return plan_route(context)
