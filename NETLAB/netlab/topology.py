"""Relay-topology generation, editing validation, and graph analytics."""
from __future__ import annotations

import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .models import TopologyMode


@dataclass
class TopologyValidation:
    structurally_valid: bool
    physically_valid: bool
    communication_feasible: Optional[bool]
    operational: bool
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "structurally_valid": self.structurally_valid,
            "physically_valid": self.physically_valid,
            "communication_feasible": self.communication_feasible,
            "operational": self.operational,
            "errors": self.errors,
            "warnings": self.warnings,
            "metrics": self.metrics,
        }


def sanitize_branches(branches: Any, relay_count: int, *, allow_shared: bool = True) -> List[List[int]]:
    if not isinstance(branches, list):
        return []
    result: List[List[int]] = []
    used: Set[int] = set()
    for raw_branch in branches:
        if not isinstance(raw_branch, list):
            continue
        branch: List[int] = []
        local: Set[int] = set()
        for raw in raw_branch:
            try:
                idx = int(raw)
            except Exception:
                continue
            if idx < 1 or idx > relay_count or idx in local:
                continue
            if not allow_shared and idx in used:
                continue
            branch.append(idx)
            local.add(idx)
            used.add(idx)
        if branch:
            result.append(branch)
    return result


def generate_branches(relay_count: int, branch_count: int, mode: str) -> List[List[int]]:
    relay_count = max(1, int(relay_count))
    branch_count = max(1, min(int(branch_count), relay_count))
    mode = str(mode).lower()
    if mode == TopologyMode.CHAIN.value:
        return [list(range(1, relay_count + 1))]
    if mode == TopologyMode.PARALLEL.value:
        branches: List[List[int]] = [[] for _ in range(branch_count)]
        for offset, idx in enumerate(range(1, relay_count + 1)):
            branches[offset % branch_count].append(idx)
        return [b for b in branches if b]
    if mode == TopologyMode.FOREST.value:
        # A compact rooted-forest encoding. Each branch is a source-to-leaf path.
        # The first relay can be shared as a root when enough relays exist.
        if relay_count == 1:
            return [[1]]
        roots = min(branch_count, max(1, relay_count // 3))
        branches = []
        remaining = list(range(roots + 1, relay_count + 1))
        buckets: List[List[int]] = [[] for _ in range(branch_count)]
        for i, idx in enumerate(remaining):
            buckets[i % branch_count].append(idx)
        for i in range(branch_count):
            root = 1 + (i % roots)
            branch = [root] + buckets[i]
            branches.append(branch)
        return [b for b in branches if b]
    # Manual starts from a deterministic editable chain instead of an empty graph.
    return [list(range(1, relay_count + 1))]


def branches_to_edges(branches: Sequence[Sequence[int]], source: str = "station") -> List[Tuple[str, str]]:
    edges: List[Tuple[str, str]] = []
    for branch in branches:
        prev = source
        for idx in branch:
            node = f"drone_{int(idx)}"
            edges.append((prev, node))
            prev = node
    return edges


def normalize_manual_edges(value: Any) -> List[Tuple[str, str]]:
    if not isinstance(value, list):
        return []
    edges: List[Tuple[str, str]] = []
    for item in value:
        if isinstance(item, Mapping):
            src, dst = item.get("src"), item.get("dst")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            src, dst = item
        else:
            continue
        src_text, dst_text = str(src or "").strip(), str(dst or "").strip()
        if src_text and dst_text:
            edges.append((src_text, dst_text))
    return edges


def adjacency(nodes: Iterable[str], edges: Iterable[Tuple[str, str]], *, directed: bool = True) -> Dict[str, Set[str]]:
    graph: Dict[str, Set[str]] = {n: set() for n in nodes}
    for src, dst in edges:
        graph.setdefault(src, set()).add(dst)
        graph.setdefault(dst, set())
        if not directed:
            graph[dst].add(src)
    return graph


def reachable(graph: Mapping[str, Set[str]], source: str) -> Set[str]:
    seen: Set[str] = set()
    queue = deque([source])
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        queue.extend(graph.get(node, set()) - seen)
    return seen


def has_cycle(graph: Mapping[str, Set[str]]) -> bool:
    white = set(graph)
    gray: Set[str] = set()
    black: Set[str] = set()

    def visit(node: str) -> bool:
        white.discard(node)
        gray.add(node)
        for nxt in graph.get(node, set()):
            if nxt in black:
                continue
            if nxt in gray or (nxt in white and visit(nxt)):
                return True
        gray.discard(node)
        black.add(node)
        return False

    while white:
        if visit(next(iter(white))):
            return True
    return False


def connected_components(nodes: Iterable[str], edges: Iterable[Tuple[str, str]]) -> List[Set[str]]:
    graph = adjacency(nodes, edges, directed=False)
    remaining = set(graph)
    components: List[Set[str]] = []
    while remaining:
        start = next(iter(remaining))
        component = reachable(graph, start)
        components.append(component)
        remaining -= component
    return components


def shortest_path(graph: Mapping[str, Set[str]], source: str, target: str) -> Optional[List[str]]:
    queue = deque([(source, [source])])
    seen = {source}
    while queue:
        node, path = queue.popleft()
        if node == target:
            return path
        for nxt in graph.get(node, set()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, path + [nxt]))
    return None


def articulation_points(nodes: Iterable[str], edges: Iterable[Tuple[str, str]]) -> Set[str]:
    graph = adjacency(nodes, edges, directed=False)
    discovery: Dict[str, int] = {}
    low: Dict[str, int] = {}
    parent: Dict[str, Optional[str]] = {}
    points: Set[str] = set()
    counter = 0

    def dfs(node: str) -> None:
        nonlocal counter
        counter += 1
        discovery[node] = low[node] = counter
        children = 0
        for nxt in graph.get(node, set()):
            if nxt not in discovery:
                parent[nxt] = node
                children += 1
                dfs(nxt)
                low[node] = min(low[node], low[nxt])
                if parent.get(node) is None and children > 1:
                    points.add(node)
                if parent.get(node) is not None and low[nxt] >= discovery[node]:
                    points.add(node)
            elif nxt != parent.get(node):
                low[node] = min(low[node], discovery[nxt])

    for node in graph:
        if node not in discovery:
            parent[node] = None
            dfs(node)
    return points


def bridge_edges(nodes: Iterable[str], edges: Iterable[Tuple[str, str]]) -> Set[Tuple[str, str]]:
    graph = adjacency(nodes, edges, directed=False)
    discovery: Dict[str, int] = {}
    low: Dict[str, int] = {}
    parent: Dict[str, Optional[str]] = {}
    bridges: Set[Tuple[str, str]] = set()
    counter = 0

    def dfs(node: str) -> None:
        nonlocal counter
        counter += 1
        discovery[node] = low[node] = counter
        for nxt in graph.get(node, set()):
            if nxt not in discovery:
                parent[nxt] = node
                dfs(nxt)
                low[node] = min(low[node], low[nxt])
                if low[nxt] > discovery[node]:
                    bridges.add(tuple(sorted((node, nxt))))
            elif nxt != parent.get(node):
                low[node] = min(low[node], discovery[nxt])

    for node in graph:
        if node not in discovery:
            parent[node] = None
            dfs(node)
    return bridges



def _all_pairs_diameter(nodes: Sequence[str], edges: Sequence[Tuple[str, str]]) -> Optional[int]:
    graph = adjacency(nodes, edges, directed=False)
    if not nodes:
        return 0

    def farthest(start: str) -> tuple[str, int, int]:
        queue = deque([(start, 0)])
        seen = {start}
        far_node, far_distance = start, 0
        while queue:
            node, distance = queue.popleft()
            if distance > far_distance:
                far_node, far_distance = node, distance
            for nxt in graph.get(node, set()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append((nxt, distance + 1))
        return far_node, far_distance, len(seen)

    # Trees are common in chain/forest editing. Their diameter is exact with two
    # breadth-first traversals instead of one traversal per node.
    undirected_edges = {tuple(sorted((src, dst))) for src, dst in edges if src != dst}
    first, _, reached = farthest(nodes[0])
    if reached != len(nodes):
        return None
    if len(undirected_edges) == max(0, len(nodes) - 1):
        _, diameter, _ = farthest(first)
        return diameter

    diameter = 0
    for source in nodes:
        _, distance, reached = farthest(source)
        if reached != len(nodes):
            return None
        diameter = max(diameter, distance)
    return diameter


def _brandes_betweenness(
    nodes: Sequence[str],
    edges: Sequence[Tuple[str, str]],
    *,
    max_exact_nodes: int = 256,
    sample_sources: int = 128,
) -> Tuple[Dict[str, float], str, int]:
    """Unweighted node betweenness on the undirected physical graph.

    Exact Brandes centrality is O(VE). For larger swarms, the operator-facing
    analytics path uses a deterministic source sample and reports the method and
    sample count so an approximation is never mistaken for an exact result.
    """
    graph = adjacency(nodes, edges, directed=False)
    centrality = {node: 0.0 for node in nodes}
    sources = list(nodes)
    method = "exact_brandes"
    if len(nodes) > max_exact_nodes and sample_sources < len(nodes):
        count = max(2, min(sample_sources, len(nodes)))
        # Even deterministic coverage keeps repeated experiments reproducible.
        indices = sorted({round(i * (len(nodes) - 1) / (count - 1)) for i in range(count)})
        sources = [nodes[index] for index in indices]
        method = "deterministic_sampled_brandes"

    for source in sources:
        stack: List[str] = []
        predecessors: Dict[str, List[str]] = {node: [] for node in nodes}
        sigma = {node: 0.0 for node in nodes}
        sigma[source] = 1.0
        distance = {node: -1 for node in nodes}
        distance[source] = 0
        queue = deque([source])
        while queue:
            node = queue.popleft()
            stack.append(node)
            for nxt in graph.get(node, set()):
                if distance[nxt] < 0:
                    queue.append(nxt)
                    distance[nxt] = distance[node] + 1
                if distance[nxt] == distance[node] + 1:
                    sigma[nxt] += sigma[node]
                    predecessors[nxt].append(node)
        dependency = {node: 0.0 for node in nodes}
        while stack:
            node = stack.pop()
            for previous in predecessors[node]:
                if sigma[node] > 0:
                    dependency[previous] += (sigma[previous] / sigma[node]) * (1.0 + dependency[node])
            if node != source:
                centrality[node] += dependency[node]

    sample_correction = (len(nodes) / len(sources)) if sources else 1.0
    scale = 0.5 * sample_correction  # undirected paths are counted from both endpoints
    if len(nodes) > 2:
        scale /= ((len(nodes) - 1) * (len(nodes) - 2) / 2.0)
    return ({node: value * scale for node, value in centrality.items()}, method, len(sources))


def _max_flow(capacity: Mapping[str, Mapping[str, int]], source: str, sink: str) -> int:
    residual: Dict[str, Dict[str, int]] = defaultdict(dict)
    for node, neighbors in capacity.items():
        for nxt, value in neighbors.items():
            residual[node][nxt] = int(value)
            residual[nxt].setdefault(node, 0)
    total = 0
    while True:
        parent: Dict[str, Optional[str]] = {source: None}
        queue = deque([source])
        while queue and sink not in parent:
            node = queue.popleft()
            for nxt, value in residual.get(node, {}).items():
                if value > 0 and nxt not in parent:
                    parent[nxt] = node
                    queue.append(nxt)
        if sink not in parent:
            break
        increment = 10**9
        node = sink
        while parent[node] is not None:
            previous = parent[node]
            increment = min(increment, residual[previous][node])
            node = previous
        node = sink
        while parent[node] is not None:
            previous = parent[node]
            residual[previous][node] -= increment
            residual[node][previous] = residual[node].get(previous, 0) + increment
            node = previous
        total += increment
    return total


def _edge_disjoint_count(nodes: Sequence[str], edges: Sequence[Tuple[str, str]], source: str, sink: str) -> int:
    capacity: Dict[str, Dict[str, int]] = defaultdict(dict)
    for src, dst in edges:
        capacity[src][dst] = capacity[src].get(dst, 0) + 1
    return _max_flow(capacity, source, sink)


def _node_disjoint_count(nodes: Sequence[str], edges: Sequence[Tuple[str, str]], source: str, sink: str) -> int:
    # Node-splitting reduction. Source and sink receive effectively unlimited capacity.
    capacity: Dict[str, Dict[str, int]] = defaultdict(dict)
    maximum = max(1, len(nodes))
    for node in nodes:
        capacity[f"{node}:in"][f"{node}:out"] = maximum if node in {source, sink} else 1
    for src, dst in edges:
        capacity[f"{src}:out"][f"{dst}:in"] = 1
    return _max_flow(capacity, f"{source}:in", f"{sink}:out")


def _simple_path_count(graph: Mapping[str, Set[str]], source: str, sink: str, *, limit: int = 1000) -> int:
    count = 0
    stack: List[Tuple[str, Set[str]]] = [(source, {source})]
    while stack and count < limit:
        node, seen = stack.pop()
        if node == sink:
            count += 1
            continue
        for nxt in graph.get(node, set()):
            if nxt not in seen:
                stack.append((nxt, seen | {nxt}))
    return count


def _algebraic_connectivity(nodes: Sequence[str], edges: Sequence[Tuple[str, str]]) -> Optional[float]:
    if len(nodes) < 2:
        return 0.0
    index = {node: i for i, node in enumerate(nodes)}
    unique_edges = {tuple(sorted((src, dst))) for src, dst in edges if src in index and dst in index and src != dst}
    try:
        # Sparse eigensolution prevents the live topology editor from performing
        # a dense O(n^3) decomposition for large research swarms.
        if len(nodes) >= 64:
            import numpy as np
            from scipy.sparse import coo_matrix, diags
            from scipy.sparse.linalg import eigsh

            rows: List[int] = []
            cols: List[int] = []
            data: List[float] = []
            degree = np.zeros(len(nodes), dtype=float)
            for src, dst in unique_edges:
                i, j = index[src], index[dst]
                rows.extend((i, j)); cols.extend((j, i)); data.extend((1.0, 1.0))
                degree[i] += 1.0; degree[j] += 1.0
            matrix = coo_matrix((data, (rows, cols)), shape=(len(nodes), len(nodes))).tocsr()
            laplacian = diags(degree) - matrix
            # The two smallest eigenvalues contain λ1≈0 and λ2. Shift-invert is
            # avoided for singular Laplacians; smallest-magnitude is stable for
            # the sparse symmetric matrix at the swarm sizes targeted here.
            values = eigsh(laplacian, k=2, which="SM", return_eigenvectors=False, tol=1e-6)
            values.sort()
            return float(max(0.0, values[1]))

        import numpy as np
        adjacency_matrix = np.zeros((len(nodes), len(nodes)), dtype=float)
        for src, dst in unique_edges:
            adjacency_matrix[index[src], index[dst]] = 1.0
            adjacency_matrix[index[dst], index[src]] = 1.0
        laplacian = np.diag(adjacency_matrix.sum(axis=1)) - adjacency_matrix
        eigenvalues = np.linalg.eigvalsh(laplacian)
        eigenvalues.sort()
        return float(max(0.0, eigenvalues[1])) if len(eigenvalues) > 1 else 0.0
    except Exception:
        return None

def topology_metrics(nodes: Sequence[str], edges: Sequence[Tuple[str, str]], source: str, sinks: Sequence[str]) -> Dict[str, Any]:
    node_set = set(nodes)
    valid_edges = [(src, dst) for src, dst in edges if src in node_set and dst in node_set]
    graph = adjacency(nodes, valid_edges, directed=True)
    degrees = Counter()
    for src, dst in valid_edges:
        degrees[src] += 1
        degrees[dst] += 1
    paths = {sink: shortest_path(graph, source, sink) for sink in sinks}
    path_lengths = [len(path) - 1 for path in paths.values() if path]
    components = connected_components(nodes, valid_edges)
    articulation = sorted(articulation_points(nodes, valid_edges))
    bridges = [list(x) for x in sorted(bridge_edges(nodes, valid_edges))]
    edge_disjoint = {sink: _edge_disjoint_count(nodes, valid_edges, source, sink) for sink in sinks}
    node_disjoint = {sink: _node_disjoint_count(nodes, valid_edges, source, sink) for sink in sinks}
    path_diversity = {sink: _simple_path_count(graph, source, sink) for sink in sinks}
    betweenness, betweenness_method, betweenness_samples = _brandes_betweenness(nodes, valid_edges)
    algebraic = _algebraic_connectivity(nodes, valid_edges)
    k_connectivity = min([*edge_disjoint.values(), *node_disjoint.values()], default=0)
    redundancy = min(path_diversity.values(), default=0)
    # Transparent heuristic for quick operator comparison; raw constituent
    # metrics remain available for scientific analysis.
    resilience_score = max(0.0, min(100.0, 100.0 * (
        0.35 * min(1.0, k_connectivity / 2.0)
        + 0.25 * min(1.0, redundancy / 2.0)
        + 0.20 * (1.0 if not articulation else 1.0 / (1.0 + len(articulation)))
        + 0.20 * (1.0 if not bridges else 1.0 / (1.0 + len(bridges)))
    )))
    return {
        "node_count": len(nodes),
        "edge_count": len(valid_edges),
        "connected_components": len(components),
        "component_sizes": sorted((len(c) for c in components), reverse=True),
        "average_degree": (sum(degrees.values()) / len(nodes)) if nodes else 0.0,
        "max_degree": max(degrees.values(), default=0),
        "network_diameter_hops": _all_pairs_diameter(nodes, valid_edges),
        "average_source_sink_hops": (sum(path_lengths) / len(path_lengths)) if path_lengths else None,
        "source_sink_paths": paths,
        "articulation_points": articulation,
        "bridge_edges": bridges,
        "edge_density": len(valid_edges) / max(1, len(nodes) * max(1, len(nodes) - 1)),
        "node_betweenness": betweenness,
        "node_betweenness_method": betweenness_method,
        "node_betweenness_source_samples": betweenness_samples,
        "algebraic_connectivity": algebraic,
        "algebraic_connectivity_method": "sparse_eigsh" if len(nodes) >= 64 and algebraic is not None else ("dense_eigvalsh" if algebraic is not None else "unavailable"),
        "edge_disjoint_paths": edge_disjoint,
        "node_disjoint_paths": node_disjoint,
        "path_diversity": path_diversity,
        "k_connectivity_estimate": k_connectivity,
        "redundancy_level": redundancy,
        "resilience_score": resilience_score,
        "resilience_score_definition": "Transparent heuristic; use raw graph metrics for publication-grade analysis.",
    }


def validate_topology(
    *,
    mode: str,
    relay_count: int,
    branches: Any,
    manual_edges: Any = None,
    positions: Optional[Mapping[str, Sequence[float]]] = None,
    source: str = "station",
    sinks: Optional[Sequence[str]] = None,
    failed_nodes: Optional[Iterable[str]] = None,
    minimum_separation_m: float = 0.0,
    altitude_bounds_m: Optional[Tuple[float, float]] = None,
    link_feasibility: Optional[Mapping[Tuple[str, str], bool]] = None,
) -> TopologyValidation:
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    relay_count = max(0, int(relay_count))
    normalized_mode = str(mode).lower()
    if normalized_mode not in {m.value for m in TopologyMode}:
        errors.append({"code": "INVALID_MODE", "message": f"Unsupported topology mode {mode}."})
        normalized_mode = TopologyMode.MANUAL.value

    normalized_branches = sanitize_branches(branches, relay_count, allow_shared=True)
    if not normalized_branches and normalized_mode != TopologyMode.MANUAL.value:
        errors.append({"code": "NO_BRANCHES", "message": "At least one non-empty branch is required."})

    expected_relays = set(range(1, relay_count + 1))
    observed_relays = {idx for branch in normalized_branches for idx in branch}
    missing = expected_relays - observed_relays
    if missing:
        warnings.append({"code": "UNASSIGNED_RELAYS", "message": f"Relays not assigned to a path: {sorted(missing)}."})

    for bi, branch in enumerate(normalized_branches):
        if len(branch) != len(set(branch)):
            errors.append({"code": "DUPLICATE_NODE_IN_BRANCH", "branch": bi})
    shared_counts = Counter(idx for branch in normalized_branches for idx in branch)
    shared = sorted(idx for idx, count in shared_counts.items() if count > 1)
    if shared and normalized_mode == TopologyMode.PARALLEL.value:
        warnings.append({"code": "SHARED_PARALLEL_RELAYS", "message": f"Parallel branches share relays {shared}; failure independence is reduced."})

    nodes = [source] + [f"drone_{i}" for i in range(1, relay_count + 1)]
    if normalized_mode == TopologyMode.MANUAL.value and manual_edges:
        edges = normalize_manual_edges(manual_edges)
    else:
        edges = branches_to_edges(normalized_branches, source)
    sinks = list(sinks or ([f"drone_{normalized_branches[0][-1]}"] if normalized_branches else []))

    edge_counts = Counter(edges)
    duplicates = [edge for edge, count in edge_counts.items() if count > 1]
    if duplicates:
        errors.append({"code": "DUPLICATE_EDGES", "edges": [list(e) for e in duplicates]})
    for src, dst in edges:
        if src not in nodes or dst not in nodes:
            errors.append({"code": "MISSING_ENDPOINT", "edge": [src, dst]})
        if src == dst:
            errors.append({"code": "SELF_LOOP", "edge": [src, dst]})

    graph = adjacency(nodes, edges, directed=True)
    if normalized_mode in {TopologyMode.CHAIN.value, TopologyMode.PARALLEL.value, TopologyMode.FOREST.value} and has_cycle(graph):
        errors.append({"code": "CYCLE_NOT_ALLOWED", "message": f"Cycles are not allowed in {normalized_mode} mode."})
    reachable_nodes = reachable(graph, source)
    for sink in sinks:
        if sink not in reachable_nodes:
            errors.append({"code": "UNREACHABLE_SINK", "sink": sink})

    failed_set = set(failed_nodes or [])
    for src, dst in edges:
        if src in failed_set or dst in failed_set:
            errors.append({"code": "FAILED_NODE_IN_ACTIVE_ROUTE", "edge": [src, dst]})

    physically_valid = True
    if positions:
        for node, value in positions.items():
            try:
                x, y, z = (float(v) for v in value)
                if not all(math.isfinite(v) for v in (x, y, z)):
                    raise ValueError
            except Exception:
                errors.append({"code": "INVALID_COORDINATE", "node": node})
                physically_valid = False
                continue
            # Flight-altitude bounds apply to airborne UAVs, not to ground stations
            # or user terminals that legitimately reside below the service corridor.
            if str(node).startswith("drone_") and altitude_bounds_m and not altitude_bounds_m[0] <= z <= altitude_bounds_m[1]:
                errors.append({"code": "ALTITUDE_VIOLATION", "node": node, "z_m": z, "bounds_m": list(altitude_bounds_m)})
                physically_valid = False
        items = list(positions.items())
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                try:
                    distance = math.dist([float(v) for v in items[i][1]], [float(v) for v in items[j][1]])
                except Exception:
                    continue
                # Minimum airframe separation is a UAV-to-UAV constraint.
                if str(items[i][0]).startswith("drone_") and str(items[j][0]).startswith("drone_") and distance < minimum_separation_m:
                    errors.append({"code": "MINIMUM_SEPARATION_VIOLATION", "nodes": [items[i][0], items[j][0]], "distance_m": distance, "threshold_m": minimum_separation_m})
                    physically_valid = False

    communication_feasible: Optional[bool] = None
    if link_feasibility is not None:
        blocked = [edge for edge in edges if not bool(link_feasibility.get(edge, False))]
        communication_feasible = not blocked
        if blocked:
            warnings.append({"code": "INFEASIBLE_EDGES", "edges": [list(e) for e in blocked]})

    structural_errors = [e for e in errors if e.get("code") not in {"INVALID_COORDINATE", "ALTITUDE_VIOLATION", "MINIMUM_SEPARATION_VIOLATION"}]
    structurally_valid = not structural_errors
    operational = structurally_valid and physically_valid and communication_feasible is not False
    metrics = topology_metrics(nodes, edges, source, sinks)
    metrics.update({"mode": normalized_mode, "branches": normalized_branches, "edges": [list(e) for e in edges]})
    return TopologyValidation(structurally_valid, physically_valid, communication_feasible, operational, errors, warnings, metrics)


def remove_failed_from_branches(branches: Sequence[Sequence[int]], failed_indices: Iterable[int]) -> List[List[int]]:
    failed = {int(x) for x in failed_indices}
    return [[idx for idx in branch if int(idx) not in failed] for branch in branches if any(int(idx) not in failed for idx in branch)]


def candidate_standby_promotions(
    branches: Sequence[Sequence[int]],
    failed_index: int,
    standby_indices: Sequence[int],
    positions: Mapping[int, Sequence[float]],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for branch_id, branch in enumerate(branches):
        if failed_index not in branch:
            continue
        position = branch.index(failed_index)
        prev_idx = branch[position - 1] if position > 0 else None
        next_idx = branch[position + 1] if position + 1 < len(branch) else None
        for standby in standby_indices:
            score = 0.0
            if prev_idx is not None and prev_idx in positions and standby in positions:
                score += math.dist(list(positions[prev_idx]), list(positions[standby]))
            if next_idx is not None and next_idx in positions and standby in positions:
                score += math.dist(list(positions[next_idx]), list(positions[standby]))
            candidates.append({"branch_id": branch_id, "replace_index": position, "failed_index": failed_index, "standby_index": standby, "geometric_cost_m": score})
    return sorted(candidates, key=lambda x: (x["geometric_cost_m"], x["standby_index"]))


def validate_config_topology(config: Mapping[str, Any], *, link_feasibility: Optional[Mapping[Tuple[str, str], bool]] = None) -> Dict[str, Any]:
    """Validate the topology embedded in a versioned experiment configuration."""
    swarm = config.get("swarm", {}) if isinstance(config.get("swarm"), Mapping) else {}
    topology = config.get("topology", {}) if isinstance(config.get("topology"), Mapping) else {}
    region = config.get("service_region", {}) if isinstance(config.get("service_region"), Mapping) else {}
    station = config.get("station", {}) if isinstance(config.get("station"), Mapping) else {}
    positions: Dict[str, Sequence[float]] = {}
    if isinstance(station.get("position"), Sequence):
        positions[str(station.get("id", "station"))] = station.get("position")  # type: ignore[assignment]
    for item in swarm.get("drones", []) if isinstance(swarm.get("drones"), list) else []:
        if isinstance(item, Mapping) and isinstance(item.get("position"), Sequence):
            positions[str(item.get("id", f"drone_{item.get('index', '')}"))] = item.get("position")  # type: ignore[assignment]
    failed_nodes = [str(item.get("id")) for item in swarm.get("drones", []) if isinstance(item, Mapping) and item.get("failed")]
    result = validate_topology(
        mode=str(topology.get("mode", "chain")),
        relay_count=int(swarm.get("relay_count", swarm.get("drone_count", 0))),
        branches=topology.get("branches", []),
        manual_edges=topology.get("manual_edges", []),
        positions=positions,
        source=str(topology.get("source", station.get("id", "station"))),
        sinks=[str(value) for value in topology.get("sinks", [])] if isinstance(topology.get("sinks"), list) else [],
        failed_nodes=failed_nodes,
        minimum_separation_m=float(swarm.get("minimum_separation_m", 0.0)),
        altitude_bounds_m=(float(region.get("min_altitude_m", -1e9)), float(region.get("max_altitude_m", 1e9))),
        link_feasibility=link_feasibility,
    )
    payload = result.as_dict()
    payload["nodes"] = list(positions)
    payload["edges"] = result.metrics.get("edges", [])

    # Deterministic analytical preview.  This is explicitly labeled PREVIEW;
    # it helps researchers validate a draft but can never be promoted to LIVE
    # or OPERATIONAL without current runtime metrics and acknowledgements.
    preview: list[dict[str, Any]] = []
    try:
        from .link import LinkRequest, compute_analytical_link, evaluate_feasibility

        communication = config.get("communication", {}) if isinstance(config.get("communication"), Mapping) else {}
        antennas = config.get("antennas", {}) if isinstance(config.get("antennas"), Mapping) else {}
        definitions = {
            str(item.get("id")): item
            for item in antennas.get("definitions", [])
            if isinstance(item, Mapping)
        }
        assignments = antennas.get("assignments", {}) if isinstance(antennas.get("assignments"), Mapping) else {}
        active = {str(station.get("id", "station")): bool(station.get("active", True))}
        failed = {str(station.get("id", "station")): False}
        for item in swarm.get("drones", []) if isinstance(swarm.get("drones"), list) else []:
            if isinstance(item, Mapping):
                identifier = str(item.get("id", f"drone_{item.get('index', '')}"))
                active[identifier] = bool(item.get("active", True))
                failed[identifier] = bool(item.get("failed", False))
        for source_id, destination_id in payload["edges"]:
            if source_id not in positions or destination_id not in positions:
                continue
            source_antenna = definitions.get(str(assignments.get(source_id, "")), {})
            destination_antenna = definitions.get(str(assignments.get(destination_id, "")), {})
            request = LinkRequest.from_mapping({
                "src": source_id,
                "dst": destination_id,
                "tx_position": positions[source_id],
                "rx_position": positions[destination_id],
                "frequency_hz": communication.get("carrier_frequency_hz", 3.5e9),
                "bandwidth_hz": communication.get("bandwidth_hz", 20e6),
                "tx_power_dbm": communication.get("tx_power_dbm", 23.0),
                "receiver_noise_figure_db": communication.get("receiver_noise_figure_db", 7.0),
                "implementation_loss_db": communication.get("implementation_loss_db", 2.0),
                "tx_gain_dbi": source_antenna.get("gain_dbi", 0.0),
                "rx_gain_dbi": destination_antenna.get("gain_dbi", 0.0),
                "tx_cable_loss_db": source_antenna.get("cable_loss_db", 0.0),
                "rx_cable_loss_db": destination_antenna.get("cable_loss_db", 0.0),
                "path_loss_exponent": communication.get("path_loss_exponent", 2.0),
                "shadowing_sigma_db": communication.get("shadowing_sigma_db", 0.0),
                "interference_margin_db": communication.get("interference_margin_db", 0.0),
                "spectral_efficiency_factor": communication.get("spectral_efficiency_factor", 0.75),
                "model": communication.get("fallback_model", "free_space"),
                "seed": (config.get("experiment", {}) or {}).get("seed", 0),
            })
            metrics = compute_analytical_link(request)
            decision = evaluate_feasibility(
                metrics,
                source_active=active.get(source_id, False),
                destination_active=active.get(destination_id, False),
                source_failed=failed.get(source_id, False),
                destination_failed=failed.get(destination_id, False),
                operational_range_m=float(communication.get("operational_range_m", 90.0)),
                hard_outage_distance_m=float(communication.get("hard_outage_distance_m", 220.0)),
                min_snr_db=float(communication.get("min_snr_db", 3.0)),
                min_sinr_db=float(communication.get("min_sinr_db", communication.get("min_snr_db", 3.0))),
                min_capacity_mbps=float(communication.get("min_capacity_mbps", 1.0)),
                metric_ttl_s=float(communication.get("metric_ttl_s", 2.0)),
            )
            preview.append({
                "source": "PREVIEW",
                "fidelity": "F1_ANALYTICAL",
                "src": source_id,
                "dst": destination_id,
                "metrics": metrics.as_dict(),
                "decision": decision.as_dict(),
            })
    except Exception as exc:
        payload.setdefault("warnings", []).append({
            "code": "LINK_PREVIEW_UNAVAILABLE",
            "message": str(exc),
        })
    payload["link_preview"] = preview
    if preview:
        payload["communication_feasible"] = all(item["decision"]["feasible"] for item in preview)
        payload["operational"] = bool(payload["structurally_valid"] and payload["physically_valid"] and payload["communication_feasible"])
    return payload


def normalize_branches(value: Any, relay_count: int = 100000) -> List[List[int]]:
    """Compatibility helper for Mission Control payload normalization."""
    return sanitize_branches(value, relay_count, allow_shared=True)


def build_edges(branches: Sequence[Sequence[int]], source: str = "station") -> List[List[str]]:
    return [list(edge) for edge in branches_to_edges(branches, source)]


def graph_metrics(nodes: Sequence[str], edges: Sequence[Sequence[str]], source: str = "station", sinks: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    normalized = [(str(edge[0]), str(edge[1])) for edge in edges if len(edge) == 2]
    if sinks is None:
        sinks = [node for node in nodes if node != source and not any(src == node for src, _ in normalized)]
    return topology_metrics(list(nodes), normalized, source, list(sinks))
