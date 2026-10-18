"""Audit trail: every agent action as a causal graph.

This is the second leg of the project (track 1: agents acting on connected
data). Inspired by agent-guard's cheat detection: instead of only blocking
bad actions, the graph *remembers* them, so you can later ask "which chain
of actions corrupted this artifact?" and walk the CAUSED_BY edges backwards.

Schema:
    (:Agent)-[:DID]->(:Action {id, type, detail, at})
    (:Action)-[:TARGETS]->(:Task | :Artifact)
    (:Action)-[:CAUSED_BY]->(:Action)      (causal chain)
    (:Action)-[:VIOLATES]->(:Rule {id, name, description})
"""

from __future__ import annotations

import uuid

from .graph import SwarmGraph


def define_rule(sg: SwarmGraph, rule_id: str, name: str, description: str) -> dict:
    res = sg.query(
        """
        MERGE (r:Rule {id: $rule_id})
        SET r.name = $name, r.description = $description
        RETURN r.id AS id, r.name AS name
        """,
        {"rule_id": rule_id, "name": name, "description": description},
    )
    row = res.result_set[0]
    return {"id": row[0], "name": row[1]}


def log_action(
    sg: SwarmGraph,
    agent_id: str,
    action_type: str,
    detail: str = "",
    targets: list[str] | None = None,
    caused_by: str | None = None,
    violates: str | None = None,
) -> str:
    """Log one agent action. Returns the action id.

    ``targets`` are task or artifact ids the action touched.
    ``caused_by`` links to a previous action id (causal chain).
    ``violates`` is a rule id when the action trips a guard rule.
    """
    action_id = f"act-{uuid.uuid4().hex[:12]}"
    sg.query(
        """
        MATCH (a:Agent {id: $agent_id})
        CREATE (act:Action {id: $action_id, type: $type, detail: $detail, at: $now})
        CREATE (a)-[:DID]->(act)
        """,
        {
            "agent_id": agent_id,
            "action_id": action_id,
            "type": action_type,
            "detail": detail,
            "now": sg.now_ms(),
        },
    )
    for target in targets or []:
        sg.query(
            """
            MATCH (act:Action {id: $action_id})
            OPTIONAL MATCH (t:Task {id: $target})
            OPTIONAL MATCH (ar:Artifact {id: $target})
            FOREACH (_ IN CASE WHEN t IS NOT NULL THEN [1] ELSE [] END |
                CREATE (act)-[:TARGETS]->(t))
            FOREACH (_ IN CASE WHEN ar IS NOT NULL THEN [1] ELSE [] END |
                CREATE (act)-[:TARGETS]->(ar))
            """,
            {"action_id": action_id, "target": target},
        )
    if caused_by:
        sg.query(
            """
            MATCH (act:Action {id: $action_id}), (prev:Action {id: $prev})
            CREATE (act)-[:CAUSED_BY]->(prev)
            """,
            {"action_id": action_id, "prev": caused_by},
        )
    if violates:
        sg.query(
            """
            MATCH (act:Action {id: $action_id}), (r:Rule {id: $rule})
            CREATE (act)-[:VIOLATES]->(r)
            """,
            {"action_id": action_id, "rule": violates},
        )
    return action_id


def audit_trail(sg: SwarmGraph, node_id: str, depth: int = 5) -> dict:
    """Walk backwards from a task/artifact through the actions that touched it.

    Returns the causal chain: every action TARGETS-ing the node, plus what
    each action was CAUSED_BY, and any VIOLATES edges (guard hits).
    """
    res = sg.query(
        f"""
        MATCH (n)
        WHERE n.id = $node_id AND (n:Task OR n:Artifact)
        OPTIONAL MATCH chain = (act:Action)-[:TARGETS]->(n)
        OPTIONAL MATCH (act)-[cb:CAUSED_BY*1..{depth}]->(prev:Action)
        OPTIONAL MATCH (act)-[:VIOLATES]->(r:Rule)
        OPTIONAL MATCH (ag:Agent)-[:DID]->(act)
        RETURN act.id AS action, act.type AS type, act.detail AS detail,
               ag.id AS agent,
               [x IN nodes(chain) | x.id] AS caused_by_chain,
               collect(DISTINCT r.id) AS violations
        """,
        {"node_id": node_id},
    )
    trail = []
    for row in res.result_set:
        if row[0] is None:
            continue
        trail.append(
            {
                "action": row[0],
                "type": row[1],
                "detail": row[2],
                "agent": row[3],
                "caused_by_chain": [x for x in (row[4] or []) if x],
                "violations": [v for v in row[5] if v],
            }
        )
    return {"node": node_id, "trail": trail}


def violations(sg: SwarmGraph, agent_id: str | None = None) -> list[dict]:
    """All guard-rule violations, optionally filtered to one agent."""
    cypher = """
        MATCH (ag:Agent)-[:DID]->(act:Action)-[:VIOLATES]->(r:Rule)
        """
    params: dict = {}
    if agent_id:
        cypher += " WHERE ag.id = $agent_id"
        params["agent_id"] = agent_id
    cypher += " RETURN ag.id, act.id, act.type, act.detail, r.id, r.name ORDER BY act.at"
    res = sg.query(cypher, params)
    return [
        {
            "agent": row[0],
            "action": row[1],
            "type": row[2],
            "detail": row[3],
            "rule": row[4],
            "rule_name": row[5],
        }
        for row in res.result_set
    ]
