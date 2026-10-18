"""Connection handling and schema bootstrap for the swarm graph."""

from __future__ import annotations

import os
import time

from falkordb import FalkorDB

GRAPH_NAME = "swarm"


class SwarmGraph:
    """Thin wrapper around a FalkorDB graph handle with schema bootstrap."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        graph: str = GRAPH_NAME,
        username: str | None = None,
        password: str | None = None,
    ):
        self.host = host
        self.port = port
        self.graph_name = graph
        self.db = FalkorDB(host=host, port=port, username=username, password=password)
        self.g = self.db.select_graph(graph)
        self._bootstrap()

    def _bootstrap(self) -> None:
        # Indexes keep MATCH on id fast; CREATE INDEX is idempotent.
        for label, prop in [
            ("Agent", "id"),
            ("Task", "id"),
            ("Artifact", "id"),
            ("Action", "id"),
            ("Rule", "id"),
        ]:
            try:
                self.g.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
            except Exception:
                pass  # already exists

    def wipe(self) -> None:
        """Delete everything in the graph. Tests and demos only."""
        self.g.delete()

    def query(self, cypher: str, params: dict | None = None):
        return self.g.query(cypher, params or {})

    def now_ms(self) -> int:
        return int(time.time() * 1000)


def connect(
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    password: str | None = None,
) -> SwarmGraph:
    """Connect using env overrides (SWARM_HOST / SWARM_PORT / SWARM_USER / SWARM_PASSWORD) when present."""
    return SwarmGraph(
        host=host or os.environ.get("SWARM_HOST", "localhost"),
        port=port or int(os.environ.get("SWARM_PORT", "6379")),
        username=username or os.environ.get("SWARM_USER"),
        password=password or os.environ.get("SWARM_PASSWORD"),
    )
