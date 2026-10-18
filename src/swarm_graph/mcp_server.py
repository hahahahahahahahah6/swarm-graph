"""MCP server: many agents share one swarm graph through tools.

Run:  swarm-graph-mcp
(or:  python -m swarm_graph.mcp_server)

Configure in Claude Code (.mcp.json):
    {
      "mcpServers": {
        "swarm-graph": {
          "command": "swarm-graph-mcp",
          "env": { "SWARM_HOST": "localhost", "SWARM_PORT": "6379" }
        }
      }
    }
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import graph as _graph_mod
from . import tasks as _tasks
from . import plan as _plan
from . import conflicts as _conflicts
from . import audit as _audit

mcp = FastMCP("swarm-graph")

_sg = None


def sg():
    global _sg
    if _sg is None:
        _sg = _graph_mod.connect()
    return _sg


@mcp.tool()
def register_agent(agent_id: str, name: str, role: str) -> dict:
    """Register an agent (id, name, role) on the shared graph."""
    return _tasks.register_agent(sg(), agent_id, name, role)


@mcp.tool()
def create_task(task_id: str, title: str, priority: int = 0, depends_on: list[str] | None = None) -> dict:
    """Create a pending task, optionally with dependency ids."""
    return _tasks.create_task(sg(), task_id, title, priority, depends_on or [])


@mcp.tool()
def claim_task(task_id: str, agent_id: str) -> dict:
    """Atomically claim a pending task. Fails (claimed: false) if taken."""
    got = _tasks.claim_task(sg(), task_id, agent_id)
    if got is None:
        return {"claimed": False, "task_id": task_id, "agent_id": agent_id}
    return {"claimed": True, **got}


@mcp.tool()
def start_task(task_id: str, agent_id: str) -> dict:
    """Mark your claimed task as in_progress."""
    return {"ok": _tasks.start_task(sg(), task_id, agent_id)}


@mcp.tool()
def complete_task(task_id: str, agent_id: str, artifacts: list[str] | None = None) -> dict:
    """Mark your claimed task done, optionally linking produced artifacts."""
    return {"ok": _tasks.complete_task(sg(), task_id, agent_id, artifacts or [])}


@mcp.tool()
def release_task(task_id: str, agent_id: str) -> dict:
    """Give your claimed task back to the pool."""
    return {"ok": _tasks.release_task(sg(), task_id, agent_id)}


@mcp.tool()
def fail_task(task_id: str, agent_id: str) -> dict:
    """Mark your claimed task as failed."""
    return {"ok": _tasks.fail_task(sg(), task_id, agent_id)}


@mcp.tool()
def get_plan() -> dict:
    """Topological execution order, dependency cycles, and claimable tasks."""
    return _plan.plan_tasks(sg())


@mcp.tool()
def detect_conflicts() -> dict:
    """Scan for double-claims, dependency cycles, artifact collisions, blocked claims."""
    return _conflicts.detect_conflicts(sg())


@mcp.tool()
def task_info(task_id: str) -> dict:
    """Status, claimers, and dependencies of one task."""
    info = _tasks.task_info(sg(), task_id)
    return info or {"error": "task not found"}


@mcp.tool()
def log_action(agent_id: str, action_type: str, detail: str = "",
               targets: list[str] | None = None, caused_by: str | None = None,
               violates: str | None = None) -> dict:
    """Log an agent action to the audit trail (causal graph)."""
    action_id = _audit.log_action(sg(), agent_id, action_type, detail,
                                  targets or [], caused_by, violates)
    return {"action_id": action_id}


@mcp.tool()
def define_rule(rule_id: str, name: str, description: str) -> dict:
    """Define a guard rule that actions can violate."""
    return _audit.define_rule(sg(), rule_id, name, description)


@mcp.tool()
def audit_trail(node_id: str, depth: int = 5) -> dict:
    """Causal chain of actions that touched a task or artifact."""
    depth = max(1, min(int(depth), 10))
    return _audit.audit_trail(sg(), node_id, depth)


@mcp.tool()
def violations(agent_id: str | None = None) -> list:
    """All guard-rule violations, optionally for one agent."""
    return _audit.violations(sg(), agent_id)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
