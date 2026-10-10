"""B07 live Neo4j tenant-isolation checks for the scoped query boundary."""
import os
import socket
import uuid
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from neo4j import AsyncGraphDatabase

from app.core.neo4j_security import Neo4jAuthorizationError, Neo4jScope
from app.cypher import queries

URI = os.getenv("NEO4J_TEST_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_TEST_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_TEST_PASSWORD", "changeme_neo4j")
A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
A_SCOPE = Neo4jScope(A)
B_SCOPE = Neo4jScope(B)
SYSTEM_SCOPE = Neo4jScope(None, system=True)


def _reachable() -> bool:
    parsed = urlparse(URI)
    try:
        with socket.create_connection((parsed.hostname or "localhost", parsed.port or 7687), timeout=1.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _reachable(), reason="Neo4j is not reachable")


@pytest_asyncio.fixture
async def session():
    driver = AsyncGraphDatabase.driver(URI, auth=(USER, PASSWORD))
    async with driver.session(database="neo4j") as value:
        yield value
    await driver.close()


@pytest.mark.asyncio
async def test_b07_nodes_relationships_traversal_and_mutations(session):
    public_id = str(uuid.uuid4())
    a_id, a2_id = str(uuid.uuid4()), str(uuid.uuid4())
    b_id, b2_id = str(uuid.uuid4()), str(uuid.uuid4())
    rel_ids = []
    try:
        for node_id, label, name, scope in [
            (public_id, "Target", "B07 Public", SYSTEM_SCOPE),
            (a_id, "Drug", "B07 A1", A_SCOPE),
            (a2_id, "Target", "B07 A2", A_SCOPE),
            (b_id, "Drug", "B07 B1", B_SCOPE),
            (b2_id, "Target", "B07 B2", B_SCOPE),
        ]:
            await session.execute_write(
                queries.create_node,
                label=label,
                node_id=node_id,
                name=name,
                description=None,
                source="b07-test",
                metadata_json="{}",
                created_at="2026-01-01T00:00:00",
                updated_at="2026-01-01T00:00:00",
                version=0,
                scope=scope,
            )

        for source, target, rel_type, scope in [
            (a_id, a2_id, "TARGETS", A_SCOPE),
            (a_id, public_id, "TARGETS", A_SCOPE),
            (b_id, b2_id, "TARGETS", B_SCOPE),
            (b_id, public_id, "TARGETS", B_SCOPE),
        ]:
            rel = await session.execute_write(
                queries.create_relationship,
                from_node_id=source,
                to_node_id=target,
                relationship_type=rel_type,
                rel_id=str(uuid.uuid4()),
                evidence="b07",
                confidence=1.0,
                source="b07-test",
                created_at="2026-01-01T00:00:00",
                version=0,
                max_version=0,
                scope=scope,
            )
            assert rel is not None
            rel_ids.append(rel["id"])

        assert (await session.execute_read(queries.get_node, node_id=b_id, max_version=0, scope=A_SCOPE)) is None
        assert (await session.execute_read(queries.get_node, node_id=public_id, max_version=0, scope=A_SCOPE))["id"] == public_id
        assert (await session.execute_read(queries.search_nodes, q="B07 B1", label="Drug", max_version=0, limit=10, scope=A_SCOPE)) == []

        neighbors = await session.execute_read(queries.get_neighbors, node_id=a_id, max_version=0, scope=A_SCOPE)
        assert {item["node"]["id"] for item in neighbors["neighbors"]} == {a2_id, public_id}
        assert await session.execute_read(queries.get_path, start_node_id=a_id, end_node_id=b2_id, max_depth=5, max_version=0, scope=A_SCOPE) is None
        assert await session.execute_read(queries.count_relationships_between, from_node_id=b_id, to_node_id=b2_id, relationship_type="TARGETS", max_version=0, scope=A_SCOPE) == 0

        assert await session.execute_write(queries.update_node, node_id=b_id, name="ATTACKED", description=None, source=None, metadata_json=None, updated_at="2026-01-02T00:00:00", max_version=0, scope=A_SCOPE) is None
        assert await session.execute_write(queries.delete_node, node_id=b_id, max_version=0, scope=A_SCOPE) == 0
        assert await session.execute_write(queries.delete_relationship, rel_id=rel_ids[2], max_version=0, scope=A_SCOPE) == 0
        assert await session.execute_write(queries.create_relationship, from_node_id=a_id, to_node_id=b_id, relationship_type="TARGETS", rel_id=str(uuid.uuid4()), evidence="spoof", confidence=1.0, source="b07-test", created_at="2026-01-01T00:00:00", version=0, max_version=0, scope=A_SCOPE) is None
    finally:
        for rel_id in rel_ids:
            await session.execute_write(queries.delete_relationship, rel_id=rel_id, max_version=0, scope=SYSTEM_SCOPE)
        for node_id in (public_id, a_id, a2_id, b_id, b2_id):
            await session.execute_write(queries.delete_node, node_id=node_id, max_version=0, scope=SYSTEM_SCOPE)


@pytest.mark.asyncio
async def test_b07_missing_scope_fails_closed():
    class Transaction:
        async def run(self, *_args, **_kwargs):
            raise AssertionError("unscoped query reached Neo4j")

    with pytest.raises(Neo4jAuthorizationError):
        await queries.get_node(Transaction(), "missing", 0, None)
