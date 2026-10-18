"""swarm-graph: multi-agent shared state graph on FalkorDB.

Agents coordinate through one shared property graph instead of a central
scheduler or message queue:

- :Agent -[:CLAIMS]-> :Task        (atomic, first-writer-wins)
- :Task  -[:DEPENDS_ON]-> :Task    (planned with topological sort)
- :Task  -[:PRODUCES]-> :Artifact
- :Agent -[:DID]-> :Action -[:TARGETS]-> (:Task|:Artifact)   (audit trail)
- :Action -[:CAUSED_BY]-> :Action  (causal chain)
- :Action -[:VIOLATES]-> :Rule     (guard-rule violations)
"""

from .graph import SwarmGraph, connect
from .tasks import (
    register_agent,
    create_task,
    claim_task,
    claim_failure_reason,
    release_task,
    complete_task,
    fail_task,
    start_task,
    task_info,
)
from .plan import plan_tasks
from .conflicts import detect_conflicts
from .audit import log_action, audit_trail, define_rule, violations

__all__ = [
    "SwarmGraph",
    "connect",
    "register_agent",
    "create_task",
    "claim_task",
    "claim_failure_reason",
    "release_task",
    "complete_task",
    "fail_task",
    "start_task",
    "task_info",
    "plan_tasks",
    "detect_conflicts",
    "log_action",
    "audit_trail",
    "define_rule",
    "violations",
]

__version__ = "0.1.0"
