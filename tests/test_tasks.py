"""Tests for atomic task claiming — the foundation of the whole project."""

import threading

from swarm_graph import (
    claim_task,
    complete_task,
    create_task,
    fail_task,
    register_agent,
    release_task,
    start_task,
    task_info,
)


def _seed(sg):
    register_agent(sg, "a1", "Alice", "builder")
    register_agent(sg, "a2", "Bob", "builder")
    create_task(sg, "t1", "Write docs", priority=1)


def test_claim_happy_path(sg):
    _seed(sg)
    got = claim_task(sg, "t1", "a1")
    assert got == {"task_id": "t1", "agent_id": "a1"}
    assert task_info(sg, "t1")["status"] == "claimed"
    assert task_info(sg, "t1")["claimers"] == ["a1"]


def test_second_claim_fails(sg):
    _seed(sg)
    assert claim_task(sg, "t1", "a1") is not None
    assert claim_task(sg, "t1", "a2") is None  # already taken


def test_claim_missing_task_or_agent(sg):
    _seed(sg)
    assert claim_task(sg, "nope", "a1") is None
    assert claim_task(sg, "t1", "ghost") is None


def test_claim_done_task_fails(sg):
    _seed(sg)
    claim_task(sg, "t1", "a1")
    assert complete_task(sg, "t1", "a1", artifacts=["docs.md"]) is True
    assert claim_task(sg, "t1", "a2") is None


def test_release_and_reclaim(sg):
    _seed(sg)
    claim_task(sg, "t1", "a1")
    assert release_task(sg, "t1", "a1") is True
    assert task_info(sg, "t1")["status"] == "pending"
    assert claim_task(sg, "t1", "a2") is not None  # someone else can take it


def test_only_claimer_can_release_or_complete(sg):
    _seed(sg)
    claim_task(sg, "t1", "a1")
    assert release_task(sg, "t1", "a2") is False
    assert complete_task(sg, "t1", "a2") is False
    assert task_info(sg, "t1")["status"] == "claimed"


def test_start_requires_claimed(sg):
    _seed(sg)
    assert start_task(sg, "t1", "a1") is False  # not claimed yet
    claim_task(sg, "t1", "a1")
    assert start_task(sg, "t1", "a1") is True
    assert task_info(sg, "t1")["status"] == "in_progress"


def test_concurrent_claim_single_winner(sg):
    """N agents racing for one task: exactly one wins. The money test."""
    n = 12
    for i in range(n):
        register_agent(sg, f"racer-{i}", f"Racer {i}", "builder")
    create_task(sg, "hot", "Hot task everyone wants")

    winners = []
    lock = threading.Lock()

    def race(i):
        from swarm_graph import connect

        local = connect()  # separate connection per thread
        local.g = local.db.select_graph("swarm_test")
        got = claim_task(local, "hot", f"racer-{i}")
        if got:
            with lock:
                winners.append(got["agent_id"])

    threads = [threading.Thread(target=race, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(winners) == 1, f"expected exactly 1 winner, got {winners}"
    assert task_info(sg, "hot")["claimers"] == winners


def test_claim_failure_reason(sg):
    from swarm_graph import claim_failure_reason

    assert claim_failure_reason(sg, "nope") == "task not found"
    _seed(sg)
    assert claim_failure_reason(sg, "t1") == "claimable"
    claim_task(sg, "t1", "a1")
    assert claim_failure_reason(sg, "t1") == "already claimed by ['a1']"
    complete_task(sg, "t1", "a1")
    assert claim_failure_reason(sg, "t1") == "task is done"


def test_fail_returns_to_pool(sg):
    _seed(sg)
    claim_task(sg, "t1", "a1")
    assert fail_task(sg, "t1", "a1") is True
    info = task_info(sg, "t1")
    assert info["status"] == "pending"
    assert info["claimers"] == []
    # another agent can pick it up
    assert claim_task(sg, "t1", "a2") is not None
