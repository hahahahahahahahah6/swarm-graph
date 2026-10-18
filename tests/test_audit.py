"""Tests for the audit trail (track 1: agents acting on connected data)."""

from swarm_graph import (
    audit_trail,
    claim_task,
    complete_task,
    create_task,
    define_rule,
    log_action,
    register_agent,
    violations,
)


def _agents(sg):
    register_agent(sg, "a1", "Alice", "builder")
    register_agent(sg, "a2", "Bob", "builder")


def test_log_and_audit_trail(sg):
    _agents(sg)
    create_task(sg, "t1", "Write tests")
    claim_task(sg, "t1", "a1")
    act = log_action(sg, "a1", "edit_file", "changed toBe(10) to toBe(9)",
                     targets=["t1"])
    trail = audit_trail(sg, "t1")
    assert len(trail["trail"]) == 1
    entry = trail["trail"][0]
    assert entry["action"] == act
    assert entry["agent"] == "a1"
    assert entry["type"] == "edit_file"


def test_causal_chain(sg):
    _agents(sg)
    create_task(sg, "t1", "Write tests")
    first = log_action(sg, "a1", "read_file", "read test file", targets=["t1"])
    second = log_action(sg, "a1", "edit_file", "weakened assertion",
                        targets=["t1"], caused_by=first)
    trail = audit_trail(sg, "t1")
    by_id = {e["action"]: e for e in trail["trail"]}
    assert by_id[second]["caused_by_chain"] == [first]


def test_violation_flagging(sg):
    _agents(sg)
    define_rule(sg, "no-test-tamper", "No test tampering",
                "Agents must not weaken test assertions to pass.")
    create_task(sg, "t1", "Write tests")
    log_action(sg, "a1", "edit_file", "toBe(10) -> toBe(9)",
               targets=["t1"], violates="no-test-tamper")
    found = violations(sg)
    assert len(found) == 1
    assert found[0]["agent"] == "a1"
    assert found[0]["rule"] == "no-test-tamper"

    trail = audit_trail(sg, "t1")
    assert trail["trail"][0]["violations"] == ["no-test-tamper"]

    # per-agent filter
    assert violations(sg, agent_id="a2") == []
    assert len(violations(sg, agent_id="a1")) == 1


def test_audit_survives_task_completion(sg):
    _agents(sg)
    create_task(sg, "t1", "Write tests")
    claim_task(sg, "t1", "a1")
    log_action(sg, "a1", "write_file", "wrote tests", targets=["t1"])
    complete_task(sg, "t1", "a1", artifacts=["test_x.py"])
    # artifact inherits the causal history through the task
    trail = audit_trail(sg, "test_x.py")
    assert trail["trail"] == []  # artifact itself has no direct actions...
    # ...but the task's trail is intact
    assert len(audit_trail(sg, "t1")["trail"]) == 1
