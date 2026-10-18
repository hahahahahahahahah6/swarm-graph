"""Task lifecycle on the shared graph.

The critical primitive is :func:`claim_task`: a single Cypher query that
checks "still pending and unclaimed" and creates the CLAIMS edge in one
atomic step. FalkorDB executes each query as one transaction, so two agents
racing for the same task cannot both win — the loser gets ``None`` back.
"""

from __future__ import annotations

from .graph import SwarmGraph


def register_agent(sg: SwarmGraph, agent_id: str, name: str, role: str) -> dict:
    res = sg.query(
        """
        MERGE (a:Agent {id: $agent_id})
        SET a.name = $name, a.role = $role
        RETURN a.id AS id, a.name AS name, a.role AS role
        """,
        {"agent_id": agent_id, "name": name, "role": role},
    )
    row = res.result_set[0]
    return {"id": row[0], "name": row[1], "role": row[2]}


def create_task(
    sg: SwarmGraph,
    task_id: str,
    title: str,
    priority: int = 0,
    depends_on: list[str] | None = None,
) -> dict:
    """Create a pending task, optionally wiring DEPENDS_ON edges."""
    res = sg.query(
        """
        MERGE (t:Task {id: $task_id})
        ON CREATE SET t.title = $title, t.priority = $priority,
                      t.status = 'pending', t.created_at = $now
        RETURN t.id AS id, t.title AS title, t.status AS status
        """,
        {"task_id": task_id, "title": title, "priority": priority, "now": sg.now_ms()},
    )
    for dep in depends_on or []:
        sg.query(
            """
            MATCH (t:Task {id: $task_id}), (d:Task {id: $dep})
            MERGE (t)-[:DEPENDS_ON]->(d)
            """,
            {"task_id": task_id, "dep": dep},
        )
    row = res.result_set[0]
    return {"id": row[0], "title": row[1], "status": row[2]}


def claim_task(sg: SwarmGraph, task_id: str, agent_id: str) -> dict | None:
    """Atomically claim a pending task.

    Returns ``{"task_id", "agent_id"}`` on success, ``None`` when the task
    is already claimed / in progress / done, or either node is missing.
    """
    res = sg.query(
        """
        MATCH (t:Task {id: $task_id})
        WHERE t.status = 'pending' AND NOT (t)<-[:CLAIMS]-(:Agent)
        MATCH (a:Agent {id: $agent_id})
        CREATE (a)-[c:CLAIMS {at: $now}]->(t)
        SET t.status = 'claimed'
        RETURN t.id AS task_id, a.id AS agent_id
        """,
        {"task_id": task_id, "agent_id": agent_id, "now": sg.now_ms()},
    )
    if not res.result_set:
        return None
    row = res.result_set[0]
    return {"task_id": row[0], "agent_id": row[1]}


def release_task(sg: SwarmGraph, task_id: str, agent_id: str) -> bool:
    """Give a claimed task back to the pool. Only the claimer can release."""
    res = sg.query(
        """
        MATCH (a:Agent {id: $agent_id})-[c:CLAIMS]->(t:Task {id: $task_id})
        WHERE t.status IN ['claimed', 'in_progress']
        DELETE c
        SET t.status = 'pending'
        REMOVE t.started_at
        RETURN t.id AS task_id
        """,
        {"task_id": task_id, "agent_id": agent_id},
    )
    return bool(res.result_set)


def _set_status(
    sg: SwarmGraph, task_id: str, agent_id: str, status: str, artifacts: list[str] | None = None
) -> bool:
    res = sg.query(
        """
        MATCH (a:Agent {id: $agent_id})-[c:CLAIMS]->(t:Task {id: $task_id})
        WHERE t.status IN ['claimed', 'in_progress']
        DELETE c
        SET t.status = $status, t.finished_at = $now
        REMOVE t.started_at
        RETURN t.id AS task_id
        """,
        {"task_id": task_id, "agent_id": agent_id, "status": status, "now": sg.now_ms()},
    )
    if not res.result_set:
        return False
    for path in artifacts or []:
        sg.query(
            """
            MATCH (t:Task {id: $task_id})
            MERGE (ar:Artifact {id: $path})
            ON CREATE SET ar.path = $path
            MERGE (t)-[:PRODUCES]->(ar)
            """,
            {"task_id": task_id, "path": path},
        )
    return True


def complete_task(
    sg: SwarmGraph, task_id: str, agent_id: str, artifacts: list[str] | None = None
) -> bool:
    """Mark a claimed task done, optionally linking produced artifacts."""
    return _set_status(sg, task_id, agent_id, "done", artifacts)


def fail_task(sg: SwarmGraph, task_id: str, agent_id: str) -> bool:
    """Mark a task failed and return it to the pool for retry.

    The failure itself should be recorded with log_action(); the task
    goes back to 'pending' so another agent can pick it up.
    """
    return _set_status(sg, task_id, agent_id, "pending")


def start_task(sg: SwarmGraph, task_id: str, agent_id: str) -> bool:
    """claimed -> in_progress. Only the claimer can start."""
    res = sg.query(
        """
        MATCH (a:Agent {id: $agent_id})-[:CLAIMS]->(t:Task {id: $task_id})
        WHERE t.status = 'claimed'
        SET t.status = 'in_progress', t.started_at = $now
        RETURN t.id AS task_id
        """,
        {"task_id": task_id, "agent_id": agent_id, "now": sg.now_ms()},
    )
    return bool(res.result_set)


def task_info(sg: SwarmGraph, task_id: str) -> dict | None:
    res = sg.query(
        """
        MATCH (t:Task {id: $task_id})
        OPTIONAL MATCH (a:Agent)-[:CLAIMS]->(t)
        OPTIONAL MATCH (t)-[:DEPENDS_ON]->(d:Task)
        RETURN t.id, t.title, t.status, t.priority,
               collect(DISTINCT a.id) AS claimers,
               collect(DISTINCT d.id) AS depends_on
        """,
        {"task_id": task_id},
    )
    if not res.result_set:
        return None
    row = res.result_set[0]
    return {
        "id": row[0],
        "title": row[1],
        "status": row[2],
        "priority": row[3],
        "claimers": [c for c in row[4] if c],
        "depends_on": [d for d in row[5] if d],
    }
