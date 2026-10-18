"""Tests for conflict detection — the demo highlight."""

from swarm_graph import (
    claim_task,
    complete_task,
    create_task,
    detect_conflicts,
    register_agent,
    start_task,
)


def _agents(sg):
    register_agent(sg, "a1", "Alice", "builder")
    register_agent(sg, "a2", "Bob", "builder")


def test_no_conflicts_clean_graph(sg):
    _agents(sg)
    create_task(sg, "t1", "Task one")
    claim_task(sg, "t1", "a1")
    assert detect_conflicts(sg)["total"] == 0


def test_double_claim_detected(sg):
    _agents(sg)
    create_task(sg, "t1", "Task one")
    # plant a double claim directly (bypasses the atomic guard)
    sg.query(
        """
        MERGE (a1:Agent {id:'a1'}) MERGE (a2:Agent {id:'a2'})
        MERGE (t:Task {id:'t1'})
        CREATE (a1)-[:CLAIMS]->(t), (a2)-[:CLAIMS]->(t)
        """
    )
    found = detect_conflicts(sg)["double_claim"]
    assert len(found) == 1
    assert found[0]["task"] == "t1"
    assert set(found[0]["agents"]) == {"a1", "a2"}


def test_dependency_cycle_detected(sg):
    create_task(sg, "x", "X")
    create_task(sg, "y", "Y", depends_on=["x"])
    sg.query(
        "MATCH (t:Task {id:'x'}), (d:Task {id:'y'}) CREATE (t)-[:DEPENDS_ON]->(d)"
    )
    found = detect_conflicts(sg)["dependency_cycle"]
    assert len(found) == 1
    assert set(found[0]["cycle"]) >= {"x", "y"}


def test_artifact_collision_detected(sg):
    _agents(sg)
    create_task(sg, "t1", "Write index.html")
    create_task(sg, "t2", "Also write index.html")
    claim_task(sg, "t1", "a1")
    claim_task(sg, "t2", "a2")
    # both tasks declare the same output artifact while unfinished
    sg.query(
        """
        MATCH (t:Task) WHERE t.id IN ['t1','t2']
        MERGE (ar:Artifact {id:'index.html'})
        CREATE (t)-[:PRODUCES]->(ar)
        """
    )
    found = detect_conflicts(sg)["artifact_collision"]
    assert len(found) == 1
    assert found[0]["artifact"] == "index.html"


def test_no_collision_after_done(sg):
    _agents(sg)
    create_task(sg, "t1", "Task one")
    create_task(sg, "t2", "Task two")
    claim_task(sg, "t1", "a1")
    complete_task(sg, "t1", "a1", artifacts=["out.txt"])
    sg.query(
        "MATCH (t:Task {id:'t2'}) MERGE (ar:Artifact {id:'out.txt'}) "
        "CREATE (t)-[:PRODUCES]->(ar)"
    )
    # t1 is done -> no collision
    assert detect_conflicts(sg)["artifact_collision"] == []


def test_blocked_claim_detected(sg):
    _agents(sg)
    create_task(sg, "base", "Base work")
    create_task(sg, "top", "Depends on base", depends_on=["base"])
    claim_task(sg, "top", "a1")  # claimed before base is done
    found = detect_conflicts(sg)["blocked_claim"]
    assert len(found) == 1
    assert found[0]["task"] == "top"
    assert found[0]["unmet_deps"] == ["base"]
    # working in dependency order is fine
    start_task(sg, "top", "a1")
    assert detect_conflicts(sg)["blocked_claim"]  # still blocked while base undone
