"""Dependency planning: topological order + cycle detection.

``plan_tasks`` reads the DEPENDS_ON DAG out of the graph and returns an
execution order with Kahn's algorithm. Done tasks are treated as satisfied
and skipped; anything left over after the sort is part of (or downstream
of) a dependency cycle and is reported explicitly instead of silently
dropped.
"""

from __future__ import annotations

from .graph import SwarmGraph


def _fetch_edges(sg: SwarmGraph) -> tuple[dict[str, dict], dict[str, set[str]]]:
    """Return ({task_id: {title, status, priority}}, {task_id: {dep_ids}})."""
    res = sg.query(
        """
        MATCH (t:Task)
        OPTIONAL MATCH (t)-[:DEPENDS_ON]->(d:Task)
        RETURN t.id AS id, t.title AS title, t.status AS status,
               t.priority AS priority, collect(d.id) AS deps
        """
    )
    info: dict[str, dict] = {}
    edges: dict[str, set[str]] = {}
    for row in res.result_set:
        tid, title, status, priority, deps = row
        info[tid] = {"title": title, "status": status, "priority": priority or 0}
        edges[tid] = {d for d in deps if d}
    return info, edges


def _find_all_cycles(nodes: set[str], edges: dict[str, set[str]]) -> list[list[str]]:
    """Return all disjoint dependency cycles via repeated DFS."""
    cycles = []
    remaining = set(nodes)
    while remaining:
        cyc = _find_cycle(remaining, edges)
        if not cyc:
            break
        cycles.append(cyc)
        remaining -= set(cyc)
    return cycles


def _find_cycle(nodes: set[str], edges: dict[str, set[str]]) -> list[str]:
    """Return one dependency cycle (list of task ids) via DFS, or []."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}
    stack: list[str] = []

    def dfs(u: str) -> list[str] | None:
        color[u] = GRAY
        stack.append(u)
        for v in sorted(edges.get(u, ())):
            if v not in nodes:
                continue
            if color[v] == GRAY:
                return stack[stack.index(v):] + [v]
            if color[v] == WHITE:
                hit = dfs(v)
                if hit:
                    return hit
        stack.pop()
        color[u] = BLACK
        return None

    for n in sorted(nodes):
        if color[n] == WHITE:
            hit = dfs(n)
            if hit:
                return hit
    return []


def plan_tasks(sg: SwarmGraph) -> dict:
    """Compute an execution order for all non-done tasks.

    Returns ``{"order": [...], "cycles": [...], "ready": [...]}`` where
    ``order`` is a topologically sorted list of task ids (dependencies
    first), ``cycles`` lists dependency cycles that block progress, and
    ``ready`` is the subset of ``order`` whose dependencies are all done
    (i.e. claimable right now).
    """
    info, edges = _fetch_edges(sg)
    done = {tid for tid, m in info.items() if m["status"] == "done"}
    active = {tid for tid in info if tid not in done}

    # indegree counts only unsatisfied (non-done) dependencies
    indegree = {tid: 0 for tid in active}
    dependents: dict[str, set[str]] = {tid: set() for tid in active}
    for tid in active:
        for dep in edges[tid]:
            if dep in active:
                indegree[tid] += 1
                dependents[dep].add(tid)

    # Kahn's, priority-aware: higher priority first among available tasks
    order: list[str] = []
    available = sorted(
        [tid for tid in active if indegree[tid] == 0],
        key=lambda t: (-info[t]["priority"], t),
    )
    while available:
        tid = available.pop(0)
        order.append(tid)
        for nxt in sorted(dependents[tid], key=lambda t: (-info[t]["priority"], t)):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                available.append(nxt)
        available.sort(key=lambda t: (-info[t]["priority"], t))

    blocked = sorted(active - set(order))
    cycles = _find_all_cycles(set(blocked), edges)

    ready = [
        tid
        for tid in order
        if all(dep in done for dep in edges[tid])
        and info[tid]["status"] == "pending"
    ]
    return {
        "order": order,
        "cycles": cycles,
        "blocked": blocked,
        "ready": ready,
        "tasks": {tid: info[tid] for tid in order},
    }
