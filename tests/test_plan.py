"""Tests for dependency planning."""

from swarm_graph import claim_task, complete_task, create_task, plan_tasks, register_agent


def _linear(sg):
    # design -> copy -> frontend -> test
    create_task(sg, "design", "Design mockup", priority=1)
    create_task(sg, "copy", "Write copy", priority=2, depends_on=["design"])
    create_task(sg, "frontend", "Build frontend", priority=3, depends_on=["copy"])
    create_task(sg, "test", "Test page", priority=1, depends_on=["frontend"])


def test_topological_order(sg):
    _linear(sg)
    plan = plan_tasks(sg)
    assert plan["order"] == ["design", "copy", "frontend", "test"]
    assert plan["cycles"] == []
    assert plan["ready"] == ["design"]  # only the root is claimable


def test_done_tasks_satisfy_deps(sg):
    _linear(sg)
    register_agent(sg, "a1", "A", "builder")
    claim_task(sg, "design", "a1")
    complete_task(sg, "design", "a1")
    plan = plan_tasks(sg)
    assert "design" not in plan["order"]
    assert plan["ready"] == ["copy"]


def test_cycle_detected(sg):
    create_task(sg, "x", "X")
    create_task(sg, "y", "Y", depends_on=["x"])
    # plant a cycle: x depends on y
    sg.query(
        "MATCH (t:Task {id:'x'}), (d:Task {id:'y'}) CREATE (t)-[:DEPENDS_ON]->(d)"
    )
    plan = plan_tasks(sg)
    assert plan["cycles"], "expected a cycle to be reported"
    cyc = plan["cycles"][0]
    assert set(cyc) >= {"x", "y"}
    assert plan["blocked"]  # cyclic tasks are not in order


def test_diamond_dependencies(sg):
    # a -> b, a -> c, b+c -> d
    create_task(sg, "a", "A")
    create_task(sg, "b", "B", depends_on=["a"])
    create_task(sg, "c", "C", depends_on=["a"])
    create_task(sg, "d", "D", depends_on=["b", "c"])
    plan = plan_tasks(sg)
    order = plan["order"]
    assert order.index("a") < order.index("b") < order.index("d")
    assert order.index("a") < order.index("c") < order.index("d")


def test_priority_breaks_ties(sg):
    create_task(sg, "low", "Low", priority=0)
    create_task(sg, "high", "High", priority=10)
    plan = plan_tasks(sg)
    assert plan["order"][0] == "high"
