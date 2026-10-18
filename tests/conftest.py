"""Shared test fixture: fresh graph per test."""

import os

import pytest

from swarm_graph import SwarmGraph

HOST = os.environ.get("SWARM_HOST", "localhost")
PORT = int(os.environ.get("SWARM_PORT", "6379"))
USERNAME = os.environ.get("SWARM_USER")
PASSWORD = os.environ.get("SWARM_PASSWORD")


@pytest.fixture()
def sg():
    g = SwarmGraph(host=HOST, port=PORT, graph="swarm_test", username=USERNAME, password=PASSWORD)
    g.wipe()
    yield g
    g.wipe()
