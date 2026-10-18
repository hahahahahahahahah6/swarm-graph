"""60-second demo: three agents build a landing page on one shared graph.

Run:  python demo/demo_scenario.py   (needs FalkorDB on localhost:6379)

Narrative:
  1. Three agents, five tasks, real dependencies.
  2. Naive coordination fails: two agents grab the same task.
  3. swarm-graph: atomic claim (one winner), plan() orders the work,
     detect_conflicts() catches a planted artifact collision, and the
     audit trail records a guard-rule violation with its causal chain.
"""

from __future__ import annotations

import sys
import threading

sys.path.insert(0, "src")

from swarm_graph import (  # noqa: E402
    SwarmGraph,
    audit_trail,
    claim_task,
    complete_task,
    connect,
    create_task,
    define_rule,
    detect_conflicts,
    log_action,
    plan_tasks,
    register_agent,
    start_task,
    violations,
)


def banner(text: str) -> None:
    print(f"\n{'=' * 60}\n{text}\n{'=' * 60}")


def main() -> None:
    sg = connect(graph="swarm_demo")
    sg.wipe()

    banner("SETUP: 3 agents, 1 shared graph, 5 tasks")
    for aid, name, role in [
        ("designer", "Dana", "design"),
        ("writer", "Walt", "copy"),
        ("coder", "Cleo", "frontend"),
    ]:
        register_agent(sg, aid, name, role)
        print(f"  agent: {name} ({role})")

    create_task(sg, "design", "Design mockup", priority=3)
    create_task(sg, "copy", "Write landing copy", priority=2, depends_on=["design"])
    create_task(sg, "build", "Build page", priority=3, depends_on=["design", "copy"])
    create_task(sg, "test", "Test page", priority=1, depends_on=["build"])
    create_task(sg, "deploy", "Deploy", priority=1, depends_on=["test"])

    banner("ACT 1: naive coordination — two agents grab the same task")
    # Simulate the naive world: no atomic guard, both agents "take" it.
    sg.query(
        "MATCH (a:Agent {id:'coder'}), (t:Task {id:'build'}) "
        "CREATE (a)-[:CLAIMS]->(t)"
    )
    sg.query(
        "MATCH (a:Agent {id:'writer'}), (t:Task {id:'build'}) "
        "CREATE (a)-[:CLAIMS]->(t)"
    )
    dc = detect_conflicts(sg)["double_claim"]
    print(f"  detect_conflicts() -> double_claim: {dc}")
    print("  Without the graph guard, both agents happily do duplicate work.")
    # clean up the planted mess
    sg.query("MATCH ()-[c:CLAIMS]->(:Task {id:'build'}) DELETE c")

    banner("ACT 2: atomic claim — 6 agents race, exactly one wins")
    for i in range(6):
        register_agent(sg, f"racer{i}", f"Racer{i}", "builder")
    winners = []
    lock = threading.Lock()

    def race(i: int) -> None:
        got = claim_task(sg, "design", f"racer{i}")
        if got:
            with lock:
                winners.append(got["agent_id"])

    threads = [threading.Thread(target=race, args=(i,)) for i in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    print(f"  winners: {winners}  (exactly one)")
    # hand the task to the real designer for the rest of the demo
    sg.query("MATCH ()-[c:CLAIMS]->(:Task {id:'design'}) DELETE c")
    sg.query("MATCH (t:Task {id:'design'}) SET t.status='pending'")
    claim_task(sg, "design", "designer")

    banner("ACT 3: plan() — dependency order, no central scheduler")
    plan = plan_tasks(sg)
    print(f"  order: {plan['order']}")
    print(f"  claimable right now: {plan['ready']}")
    print(f"  cycles: {plan['cycles'] or 'none'}")

    banner("ACT 4: the work happens — in dependency order")
    claim_task(sg, "design", "designer")
    start_task(sg, "design", "designer")
    log_action(sg, "designer", "write_file", "mockup v1", targets=["design"])
    complete_task(sg, "design", "designer", artifacts=["mockup.fig"])
    print("  designer: design done -> mockup.fig")

    claim_task(sg, "copy", "writer")
    complete_task(sg, "copy", "writer", artifacts=["copy.md"])
    print("  writer: copy done -> copy.md")

    claim_task(sg, "build", "coder")
    # coder gets sloppy: also declares mockup.fig as its output -> collision
    sg.query(
        "MATCH (t:Task {id:'build'}) "
        "MERGE (ar:Artifact {id:'mockup.fig'}) CREATE (t)-[:PRODUCES]->(ar)"
    )
    col = detect_conflicts(sg)["artifact_collision"]
    print(f"  detect_conflicts() -> artifact_collision: {col}")
    print("  Two unfinished tasks writing the same artifact — caught before merge.")
    sg.query(
        "MATCH (:Task {id:'build'})-[p:PRODUCES]->(:Artifact {id:'mockup.fig'}) "
        "DELETE p"
    )
    complete_task(sg, "build", "coder", artifacts=["index.html"])
    print("  coder: build done -> index.html (collision resolved)")

    banner("ACT 5: audit trail — the guard remembers")
    define_rule(
        sg, "no-test-tamper", "No test tampering",
        "Agents must not weaken test assertions to make them pass.",
    )
    claim_task(sg, "test", "coder")
    a1 = log_action(sg, "coder", "run_tests", "3 failures", targets=["test"])
    a2 = log_action(
        sg, "coder", "edit_file", "changed toBe(10) to toBe(9)",
        targets=["test"], caused_by=a1, violates="no-test-tamper",
    )
    print(f"  violations: {violations(sg)}")
    trail = audit_trail(sg, "test")
    for e in trail["trail"]:
        print(f"  - {e['agent']}: {e['type']} ({e['detail']}) "
              f"violations={e['violations']} caused_by={e['caused_by_chain']}")
    assert a2  # silence linters

    banner("DEMO COMPLETE")
    print("  claim: atomic   plan: topological   conflicts: detected   audit: causal")
    print("  Track 2 (coordination) + Track 1 (agents acting on connected data).")


if __name__ == "__main__":
    main()
