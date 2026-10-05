from __future__ import annotations

import os
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from app.core.config import Settings
from app.core.canonical_security import CanonicalPrincipal
from app.database.canonical_store import CanonicalStore
from app.database.neo4j import Neo4jManager
from app.schemas.canonical import (
    CanonicalEntityCreate,
    CanonicalRelationshipCreate,
    EntityType,
    SourceRecordInput,
    Visibility,
)
from app.services.canonical_projection import CanonicalProjectionWorker
from app.services.canonical_repository import CanonicalRepository

TEST_DATABASE_URL = os.getenv("KG_TEST_DATABASE_URL")
TEST_NEO4J_URI = os.getenv("KG_TEST_NEO4J_URI")
TEST_SEARCH_URL = os.getenv("KG_TEST_SEARCH_URL")


@pytest.mark.asyncio
async def test_global_canonical_entity_projects_to_neo4j():
    if not TEST_DATABASE_URL or not TEST_NEO4J_URI or not TEST_SEARCH_URL:
        pytest.skip("set KG_TEST_DATABASE_URL, KG_TEST_NEO4J_URI, and KG_TEST_SEARCH_URL for projection integration")

    store = CanonicalStore()
    neo4j = Neo4jManager()
    settings = Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        neo4j_uri=TEST_NEO4J_URI,
        neo4j_user=os.getenv("KG_TEST_NEO4J_USER", "neo4j"),
        neo4j_password=os.getenv("KG_TEST_NEO4J_PASSWORD", "changeme_neo4j"),
        search_service_url=TEST_SEARCH_URL,
        search_internal_token=os.getenv("KG_TEST_SEARCH_INTERNAL_TOKEN", ""),
    )
    try:
        await store.initialize(TEST_DATABASE_URL)
        neo4j.init_driver(settings)
        repository = CanonicalRepository(store)
        suffix = str(uuid4())
        entity = await repository.create_entity(
            CanonicalEntityCreate(
                entity_type=EntityType.TARGET,
            preferred_name=f"Synthetic graph projection {suffix}",
                visibility=Visibility.GLOBAL,
                source_record=SourceRecordInput(
                    namespace="ai-rxos-test",
                    external_id=f"neo4j-projection:{suffix}",
                    source_type="demo",
                    provenance={"synthetic": True, "scientific_claim": False},
                ),
            ),
            CanonicalPrincipal(None, None, frozenset({"operator"}), frozenset()),
        )
        entity_id = entity["id"]
        worker = CanonicalProjectionWorker(store, neo4j, settings)
        delivered = await worker.run_once(limit=100)
        async with neo4j.get_session() as session:
            result = await session.run(
                "MATCH (n:CanonicalEntity {id: $id}) RETURN n.entity_type AS entity_type, n.name AS name",
                id=str(entity_id),
            )
            record = await result.single()
        assert record is not None
        assert record["entity_type"] == "target"
        assert record["name"] == f"Synthetic graph projection {suffix}"
        await worker._project_graph(
            "entity.upserted",
            {"id": str(entity_id), "entity_type": "target", "preferred_name": "stale", "organization_id": None},
            1,
        )
        async with neo4j.get_session() as session:
            versioned = await session.run(
                "MATCH (n:CanonicalEntity {id: $id}) RETURN n.name AS name, n.projection_version AS version",
                id=str(entity_id),
            )
            versioned_record = await versioned.single()
        assert versioned_record["name"] == f"Synthetic graph projection {suffix}"
        assert versioned_record["version"] is not None
        async with httpx.AsyncClient(timeout=8.0) as client:
            search_response = await client.get(
                f"{TEST_SEARCH_URL.rstrip('/')}/api/v1/search",
                params={"q": f"Synthetic graph projection {suffix}"},
                headers={"X-Authenticated-Organization-ID": str(uuid4())},
            )
        assert search_response.status_code == 200
        assert any(item["id"] == str(entity_id) for item in search_response.json()["items"])
        second = await repository.create_entity(
            CanonicalEntityCreate(
                entity_type=EntityType.DISEASE,
                preferred_name=f"Synthetic disease projection {suffix}",
                visibility=Visibility.GLOBAL,
                source_record=SourceRecordInput(
                    namespace="ai-rxos-test",
                    external_id=f"neo4j-projection-disease:{suffix}",
                    source_type="demo",
                    provenance={"synthetic": True, "scientific_claim": False},
                ),
            ),
            CanonicalPrincipal(None, None, frozenset({"operator"}), frozenset()),
        )
        relationship = await repository.create_relationship(
            CanonicalRelationshipCreate(
                subject_entity_id=entity_id,
                predicate="ASSOCIATED_WITH",
                object_entity_id=second["id"],
                visibility=Visibility.GLOBAL,
                source_record=SourceRecordInput(
                    namespace="ai-rxos-test",
                    external_id=f"neo4j-projection-relationship:{suffix}",
                    source_type="demo",
                    provenance={"synthetic": True, "scientific_claim": False},
                ),
                observation_value={"synthetic": True},
            ),
            CanonicalPrincipal(None, None, frozenset({"operator"}), frozenset()),
        )
        await worker.run_once(limit=100)
        async with neo4j.get_session() as session:
            relationship_result = await session.run(
                """MATCH (:CanonicalEntity {id: $subject_id})-[r:CANONICAL_RELATIONSHIP {id: $relationship_id}]->
                    (:CanonicalEntity {id: $object_id})
                    RETURN r.predicate AS predicate""",
                subject_id=str(entity_id),
                relationship_id=str(relationship["id"]),
                object_id=str(second["id"]),
            )
            relationship_record = await relationship_result.single()
        assert relationship_record is not None
        assert relationship_record["predicate"] == "ASSOCIATED_WITH"
        async with store.connection(None) as connection:
            search_event = await connection.fetchrow(
                """SELECT delivered_at, last_error FROM canonical.projection_outbox
                WHERE aggregate_id = $1 AND event_type = 'entity.upserted'""",
                entity_id,
            )
        assert delivered >= 1
        assert search_event["delivered_at"] is not None
        assert search_event["last_error"] is None
    finally:
        await neo4j.close()
        await store.close()
