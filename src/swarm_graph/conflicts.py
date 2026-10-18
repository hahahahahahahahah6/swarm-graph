"""Conflict detection — the demo highlight.

Scans the shared graph for the coordination failures that message queues
and shared docs handle badly:

1. ``double_claim``      — two agents holding CLAIMS on the same task
2. ``dependency_cycle``   — a DEPENDS_ON cycle that deadlocks progress
3. ``artifact_collision`` — two unfinished tasks producing the same artifact
4. ``blocked_claim``      — a claimed/in-progress task whose dependencies
                           are not done yet (working out of order)
"""

from __future__ import annotations

from .graph import SwarmGraph
from .plan import _fetch_edges, _find_cycle


def detect_conflicts(sg: SwarmGraph) -> dict:
    conflicts: dict[str, list] = {
        "double_claim": [],
        "dependency_cycle": [],
        "artifact_collision": [],
        "blocked_claim": [],
    }

    # 1. two agents, one task
    res = sg.query(
        """
        MATCH (t:Task)<-[c1:CLAIMS]-(a1:Agent),
              (t)<-[c2:CLAIMS]-(a2:Agent)
        WHERE a1.id < a2.id
        RETURN t.id AS task, a1.id AS agent1, a2.id AS agent2
        """
    )
    for row in res.result_set:
        conflicts["double_claim"].append(
            {"task": row[0], "agents": [row[1], row[2]]}
        )

    # 2. cycles in DEPENDS_ON (ignore done tasks)
    info, edges = _fetch_edges(sg)
    active = {tid for tid, m in info.items() if m["status"] != "done"}
    cyc = _find_cycle(active, edges)
    if cyc:
        conflicts["dependency_cycle"].append({"cycle": cyc})

    # 3. two unfinished tasks -> same artifact
    res = sg.query(
        """
        MATCH (t1:Task)-[:PRODUCES]->(ar:Artifact)<-[:PRODUCES]-(t2:Task)
        WHERE t1.id < t2.id
          AND t1.status IN ['pending','claimed','in_progress']
          AND t2.status IN ['pending','claimed','in_progress']
        RETURN ar.id AS artifact, t1.id AS task1, t2.id AS task2
        """
    )
    for row in res.result_set:
        conflicts["artifact_collision"].append(
            {"artifact": row[0], "tasks": [row[1], row[2]]}
        )

    # 4. claimed but dependencies unmet
    res = sg.query(
        """
        MATCH (t:Task)-[:DEPENDS_ON]->(d:Task)
        WHERE t.status IN ['claimed','in_progress'] AND d.status <> 'done'
        RETURN DISTINCT t.id AS task, collect(d.id) AS unmet
        """
    )
    for row in res.result_set:
        conflicts["blocked_claim"].append({"task": row[0], "unmet_deps": row[1]})

    conflicts["total"] = sum(len(v) for k, v in conflicts.items() if k != "total")
    return conflicts
