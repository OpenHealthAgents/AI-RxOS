"""Integration tests against a real Neo4j instance, exercising the actual
Cypher in app/cypher/queries.py end-to-end (the mocked tests elsewhere in
this suite only verify router/service wiring, not that the Cypher itself is
correct). Points at NEO4J_TEST_URI (default bolt://localhost:7687) using
NEO4J_TEST_USER/NEO4J_TEST_PASSWORD (defaults matching docker-compose.yml's
neo4j service). The whole module is skipped if no Neo4j is reachable, so it
degrades gracefully in environments without Docker running.

Run with a live Neo4j via: docker compose up -d neo4j
"""
import os
import uuid

import pytest
import pytest_asyncio
from neo4j import AsyncGraphDatabase

from app.cypher import queries
from app.core.neo4j_security import Neo4jScope

NEO4J_TEST_URI = os.environ.get("NEO4J_TEST_URI", "bolt://localhost:7687")
NEO4J_TEST_USER = os.environ.get("NEO4J_TEST_USER", "neo4j")
NEO4J_TEST_PASSWORD = os.environ.get("NEO4J_TEST_PASSWORD", "changeme_neo4j")


def _neo4j_reachable() -> bool:
    import socket
    from urllib.parse import urlparse

    host = urlparse(NEO4J_TEST_URI).hostname or "localhost"
    port = urlparse(NEO4J_TEST_URI).port or 7687
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _neo4j_reachable(),
    reason=f"No Neo4j reachable at {NEO4J_TEST_URI} (start it with: docker compose up -d neo4j)",
)


@pytest_asyncio.fixture
async def driver():
    drv = AsyncGraphDatabase.driver(NEO4J_TEST_URI, auth=(NEO4J_TEST_USER, NEO4J_TEST_PASSWORD))
    yield drv
    await drv.close()


@pytest_asyncio.fixture
async def session(driver):
    async with driver.session(database="neo4j") as sess:
        await sess.run("MATCH (n) DETACH DELETE n")
        await sess.execute_write(queries.create_constraints_and_indexes)
        class ScopedSession:
            def __init__(self, value):
                self.value = value

            async def execute_read(self, callback, *args, **kwargs):
                kwargs.setdefault("scope", Neo4jScope(None, system=True))
                return await self.value.execute_read(callback, *args, **kwargs)

            async def execute_write(self, callback, *args, **kwargs):
                kwargs.setdefault("scope", Neo4jScope(None, system=True))
                return await self.value.execute_write(callback, *args, **kwargs)

            async def run(self, *args, **kwargs):
                return await self.value.run(*args, **kwargs)

        try:
            yield ScopedSession(sess)
        finally:
            await sess.run("MATCH (n) DETACH DELETE n")


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.mark.asyncio
async def test_node_crud_round_trip(session):
    node_id = _uid()
    created = await session.execute_write(
        queries.create_node,
        label="Gene",
        node_id=node_id,
        name="BRCA1",
        description="Breast cancer susceptibility gene",
        source="NCBI",
        metadata_json="{}",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        version=0,
    )
    assert created["id"] == node_id
    assert created["label"] == "Gene"

    fetched = await session.execute_read(queries.get_node, node_id=node_id, max_version=0)
    assert fetched is not None
    assert fetched["name"] == "BRCA1"

    updated = await session.execute_write(
        queries.update_node,
        node_id=node_id,
        name="BRCA1-Updated",
        description=None,
        source=None,
        metadata_json=None,
        updated_at="2026-01-02T00:00:00",
        max_version=0,
    )
    assert updated["name"] == "BRCA1-Updated"

    deleted_count = await session.execute_write(queries.delete_node, node_id=node_id, max_version=0)
    assert deleted_count == 1

    gone = await session.execute_read(queries.get_node, node_id=node_id, max_version=0)
    assert gone is None


@pytest.mark.asyncio
async def test_relationship_and_neighbors_and_path(session):
    gene_id, protein_id = _uid(), _uid()
    for node_id, label, name in [(gene_id, "Gene", "GeneX"), (protein_id, "Protein", "ProteinX")]:
        await session.execute_write(
            queries.create_node,
            label=label,
            node_id=node_id,
            name=name,
            description=None,
            source=None,
            metadata_json="{}",
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
            version=0,
        )

    rel_id = _uid()
    rel = await session.execute_write(
        queries.create_relationship,
        from_node_id=gene_id,
        to_node_id=protein_id,
        relationship_type="TARGETS",
        rel_id=rel_id,
        evidence="unit test",
        confidence=0.9,
        source="test-suite",
        created_at="2026-01-01T00:00:00",
        version=0,
        max_version=0,
    )
    assert rel["type"] == "TARGETS"

    neighbors = await session.execute_read(queries.get_neighbors, node_id=gene_id, max_version=0)
    assert neighbors is not None
    assert len(neighbors["neighbors"]) == 1
    assert neighbors["neighbors"][0]["node"]["id"] == protein_id

    path = await session.execute_read(
        queries.get_path, start_node_id=gene_id, end_node_id=protein_id, max_depth=3, max_version=0
    )
    assert path is not None
    assert len(path["nodes"]) == 2

    count = await session.execute_read(
        queries.count_relationships_between,
        from_node_id=gene_id,
        to_node_id=protein_id,
        relationship_type="TARGETS",
        max_version=0,
    )
    assert count == 1

    await session.execute_write(queries.delete_relationship, rel_id=rel_id, max_version=0)
    for node_id in (gene_id, protein_id):
        await session.execute_write(queries.delete_node, node_id=node_id, max_version=0)


@pytest.mark.asyncio
async def test_search_nodes_by_name(session):
    node_id = _uid()
    unique_name = f"SearchableGene-{node_id[:8]}"
    await session.execute_write(
        queries.create_node,
        label="Gene",
        node_id=node_id,
        name=unique_name,
        description=None,
        source=None,
        metadata_json="{}",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        version=0,
    )
    results = await session.execute_read(queries.search_nodes, q=unique_name[:12], label="Gene", max_version=0, limit=10)
    assert any(r["id"] == node_id for r in results)
    await session.execute_write(queries.delete_node, node_id=node_id, max_version=0)


@pytest.mark.asyncio
async def test_bulk_import_batches_and_version_rollback(session):
    node_ids = [_uid(), _uid()]
    rows = [
        {
            "id": nid,
            "name": f"BatchNode-{i}",
            "description": None,
            "source": "test-suite",
            "metadata": "{}",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "version": 0,
        }
        for i, nid in enumerate(node_ids)
    ]
    await session.execute_write(queries.merge_import_nodes_batch, label="Gene", rows=rows)
    for nid in node_ids:
        fetched = await session.execute_read(queries.get_node, node_id=nid, max_version=0)
        assert fetched is not None

    version_number = await session.execute_write(queries.get_next_version_number)
    await session.execute_write(
        queries.create_version,
        version_id=_uid(),
        version_number=version_number,
        description="integration test version",
        created_at="2026-01-01T00:00:00",
    )
    existing = await session.execute_read(queries.get_version_by_number, version_number=version_number)
    assert existing is not None

    missing = await session.execute_read(queries.get_version_by_number, version_number=-1)
    assert missing is None

    rolled_back_count = await session.execute_write(queries.rollback_to_version, target_version=version_number)
    assert rolled_back_count == 0
    reactivated = await session.execute_read(queries.get_version_by_number, version_number=version_number)
    assert reactivated["status"] == "active"

    for nid in node_ids:
        await session.execute_write(queries.delete_node, node_id=nid, max_version=0)


@pytest.mark.asyncio
async def test_list_nodes_excludes_graphversion_and_malformed_legacy_nodes(session):
    """Regression test for a real production bug: list_nodes' unrestricted
    MATCH (n) was returning internal :GraphVersion bookkeeping nodes and any
    node created outside the validated NodeCreate write path (e.g. seeded
    directly via Cypher with a non-UUID id and no created_at/updated_at),
    both of which crash NodeListResponse validation with a 500."""
    good_id = _uid()
    await session.execute_write(
        queries.create_node,
        label="Gene",
        node_id=good_id,
        name="RegressionGene",
        description=None,
        source=None,
        metadata_json="{}",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        version=0,
    )

    # A GraphVersion bookkeeping node, and a legacy-style node seeded
    # directly via Cypher (non-UUID id, no created_at/updated_at) - exactly
    # the shape that broke GET /nodes.
    legacy_id = f"gene:REGRESSION_TEST_{uuid.uuid4()}"
    await session.run(
        "CREATE (:GraphVersion {id: $id, version_number: 999999, "
        "description: 'regression test version', status: 'active', "
        "created_at: '2026-01-01T00:00:00'})",
        id=_uid(),
    )
    await session.run(
        "CREATE (:Gene {id: $legacy_id, name: 'BadLegacyGene', organism: 'human'})",
        legacy_id=legacy_id,
    )

    nodes, total = await session.execute_read(queries.list_nodes, max_version=0, label=None, page=1, size=100)
    ids = [n["id"] for n in nodes]
    labels = [n["label"] for n in nodes]

    assert good_id in ids
    assert legacy_id not in ids
    assert "GraphVersion" not in labels
    for n in nodes:
        assert "name" in n and n["name"]
        assert "created_at" in n and n["created_at"]
        assert "updated_at" in n and n["updated_at"]
    assert total == len(nodes)

    await session.execute_write(queries.delete_node, node_id=good_id, max_version=0)
    await session.run("MATCH (n:GraphVersion {version_number: 999999}) DETACH DELETE n")
    await session.run("MATCH (n) WHERE n.id = $legacy_id DETACH DELETE n", legacy_id=legacy_id)
