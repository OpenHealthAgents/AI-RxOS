from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
import jwt

from app.core.config import Settings
from app.core.canonical_security import CanonicalPrincipal
from app.database.canonical_store import CanonicalStore
from app.database.neo4j import Neo4jManager
from app.schemas.canonical import (
    CanonicalEntityCreate,
    CanonicalRelationshipCreate,
    EntityType,
    IdentifierInput,
    Modality,
    ObservationCreate,
    ObservationKind,
    SourceRecordInput,
    Visibility,
)
from app.services.canonical_projection import CanonicalProjectionWorker
from app.services.canonical_repository import CanonicalAuthorizationError, CanonicalRepository

TEST_DATABASE_URL = os.getenv("KG_TEST_DATABASE_URL")
TEST_NEO4J_URI = os.getenv("KG_TEST_NEO4J_URI")
TEST_SEARCH_URL = os.getenv("KG_TEST_SEARCH_URL")
TEST_KG_URL = os.getenv("KG_TEST_KG_URL", "http://kg:8083")
TEST_SEARCH_TOKEN = os.getenv("KG_TEST_SEARCH_INTERNAL_TOKEN", "")
TEST_JWT_SECRET = os.getenv("KG_TEST_JWT_SECRET", "change_this_dev_secret_before_deploying")


def source(external_id: str, observed_at: datetime | None = None) -> SourceRecordInput:
    return SourceRecordInput(
        namespace="b10-live",
        external_id=external_id,
        source_type="publication",
        published_at=observed_at,
        observed_at=observed_at,
        provenance={"synthetic": True, "scenario": "B10", "scientific_claim": False},
    )


def principal(organization_id: UUID | None = None) -> CanonicalPrincipal:
    if organization_id is None:
        return CanonicalPrincipal(None, None, frozenset({"operator"}), frozenset())
    return CanonicalPrincipal(uuid4(), organization_id, frozenset(), frozenset())


@pytest.mark.asyncio
async def test_b10_source_to_search_and_graph_flow():
    if not TEST_DATABASE_URL or not TEST_NEO4J_URI or not TEST_SEARCH_URL or not TEST_SEARCH_TOKEN:
        pytest.skip("set B10 live PostgreSQL, Neo4j, Search, and internal-token settings")

    store = CanonicalStore()
    neo4j = Neo4jManager()
    settings = Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        neo4j_uri=TEST_NEO4J_URI,
        neo4j_user=os.getenv("KG_TEST_NEO4J_USER", "neo4j"),
        neo4j_password=os.getenv("KG_TEST_NEO4J_PASSWORD", "changeme_neo4j"),
        search_service_url=TEST_SEARCH_URL,
        search_internal_token=TEST_SEARCH_TOKEN,
    )
    await store.initialize(TEST_DATABASE_URL)
    neo4j.init_driver(settings)
    repository = CanonicalRepository(store)
    worker = CanonicalProjectionWorker(store, neo4j, settings)
    timestamp = datetime.now(timezone.utc)
    suffix = str(uuid4())
    tenant_a = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    tenant_b = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    try:
        target = await repository.create_entity(
            CanonicalEntityCreate(
                entity_type=EntityType.TARGET,
                preferred_name=f"B10 target {suffix}",
                visibility=Visibility.GLOBAL,
                source_record=source(f"target:{suffix}", timestamp),
                identifiers=[IdentifierInput(
                    namespace="pubmed",
                    identifier_type="pmid",
                    value=f"B10-{suffix}",
                    source_record=source(f"target-id:{suffix}", timestamp),
                )],
            ),
            principal(),
        )
        asset = await repository.create_entity(
            CanonicalEntityCreate(
                entity_type=EntityType.THERAPEUTIC_ASSET,
                preferred_name=f"B10 asset {suffix}",
                modality=Modality.SMALL_MOLECULE,
                visibility=Visibility.TENANT,
                attributes={"development_names": [f"B10 compound {suffix}"]},
                source_record=source(f"asset:{suffix}", timestamp),
                identifiers=[IdentifierInput(
                    namespace="internal",
                    identifier_type="asset",
                    value=f"B10-ASSET-{suffix}",
                    source_record=source(f"asset-id:{suffix}", timestamp),
                )],
            ),
            principal(tenant_a),
        )
        asset_id = UUID(str(asset["id"]))
        target_id = UUID(str(target["id"]))
        assert asset["organization_id"] == tenant_a
        assert asset["created_source_record_id"]

        resolved = await repository.reconcile_legacy_record(
            {
                "source_type": "publication",
                "source_record_id": f"asset:{suffix}",
                "entity_type": "therapeutic_asset",
                "source_record": source(f"reconcile:{suffix}").model_dump(mode="json"),
                "identifiers": [{"namespace": "internal", "identifier_type": "asset", "value": f"B10-ASSET-{suffix}"}],
                "names": [f"B10 asset {suffix}"],
                "tenant_id": str(tenant_a),
            },
            principal(tenant_a),
        )
        assert resolved["status"] == "EXACT_MATCH"
        assert resolved["canonical_entity_id"] == str(asset_id)

        observation = await repository.create_observation(
            ObservationCreate(
                entity_id=asset_id,
                property_name="source_fact",
                observation_kind=ObservationKind.SOURCE_FACT,
                value={"source_fact": "synthetic B10 observation"},
                visibility=Visibility.TENANT,
                source_record=source(f"observation:{suffix}", timestamp),
            ),
            principal(tenant_a),
        )
        assert observation["entity_id"] == asset_id
        assert observation["observed_at"] == timestamp

        relationship = await repository.create_relationship(
            CanonicalRelationshipCreate(
                subject_entity_id=asset_id,
                predicate="TARGETS",
                object_entity_id=target_id,
                visibility=Visibility.TENANT,
                source_record=source(f"relationship:{suffix}", timestamp),
                observation_value={"synthetic": True},
                observation_kind=ObservationKind.SOURCE_FACT,
            ),
            principal(tenant_a),
        )
        relationship_id = UUID(str(relationship["id"]))

        async with store.connection(tenant_a) as connection:
            outbox = await connection.fetch(
                """SELECT event_type, aggregate_id, visibility, organization_id, payload
                FROM canonical.projection_outbox
                WHERE aggregate_id = ANY($1::uuid[]) ORDER BY id""",
                [asset_id, relationship_id],
            )
        assert {row["event_type"] for row in outbox} == {"entity.upserted", "relationship.upserted"}
        assert all(row["organization_id"] == tenant_a for row in outbox)

        await worker.run_once(limit=100, organization_id=tenant_a)
        await worker.run_once(limit=100, organization_id=tenant_a)

        async with neo4j.get_session() as session:
            graph_result = await session.run(
                """MATCH (a:CanonicalEntity {id: $asset_id})-[r:CANONICAL_RELATIONSHIP {id: $relationship_id}]->
                    (t:CanonicalEntity {id: $target_id})
                RETURN a.id AS asset_id, t.id AS target_id, r.predicate AS predicate""",
                asset_id=str(asset_id), target_id=str(target_id), relationship_id=str(relationship_id),
            )
            graph_record = await graph_result.single()
        assert graph_record is not None
        assert graph_record["predicate"] == "TARGETS"

        async with httpx.AsyncClient(timeout=10.0) as client:
            headers_a = {"X-Authenticated-Organization-ID": str(tenant_a)}
            headers_b = {"X-Authenticated-Organization-ID": str(tenant_b)}
            search_a = await client.get(TEST_SEARCH_URL + "/api/v1/search", params={"q": f"B10 asset {suffix}"}, headers=headers_a)
            search_b = await client.get(TEST_SEARCH_URL + "/api/v1/search", params={"q": f"B10 asset {suffix}"}, headers=headers_b)
            missing = await client.get(TEST_SEARCH_URL + "/api/v1/search", params={"q": f"B10 asset {suffix}"})
            graph_token = jwt.encode(
                {
                    "sub": str(uuid4()),
                    "organization_id": str(tenant_a),
                    "exp": int(timestamp.timestamp()) + 3600,
                },
                TEST_JWT_SECRET,
                algorithm="HS256",
            )
            graph_response = await client.get(
                f"{TEST_KG_URL}/api/v1/graph/neighbors/{asset_id}",
                headers={"Authorization": f"Bearer {graph_token}"},
            )
        assert search_a.status_code == 200
        assert any(item["id"] == str(asset_id) for item in search_a.json()["items"])
        assert search_b.status_code == 200
        assert not any(item["id"] == str(asset_id) for item in search_b.json()["items"])
        assert missing.status_code == 401
        assert graph_response.status_code == 200
        assert any(item["relationship"]["type"] == "CANONICAL_RELATIONSHIP" for item in graph_response.json()["neighbors"])

        async with store.connection(tenant_a) as connection:
            before_relationship_events = await connection.fetchval(
                "SELECT count(*) FROM canonical.projection_outbox WHERE organization_id = $1 AND event_type = 'relationship.upserted'",
                tenant_a,
            )
        with pytest.raises((CanonicalAuthorizationError, LookupError)):
            await repository.create_relationship(
                CanonicalRelationshipCreate(
                    subject_entity_id=asset_id,
                    predicate="TARGETS",
                    object_entity_id=UUID(str((await repository.create_entity(
                        CanonicalEntityCreate(
                            entity_type=EntityType.TARGET,
                            preferred_name=f"B10 private target {suffix}",
                            visibility=Visibility.TENANT,
                            source_record=source(f"private-target:{suffix}"),
                        ),
                        principal(tenant_b),
                    ))["id"])),
                    visibility=Visibility.TENANT,
                    source_record=source(f"cross-tenant-relationship:{suffix}"),
                    observation_value={"synthetic": True},
                ),
                principal(tenant_a),
            )
        async with store.connection(tenant_a) as connection:
            after_relationship_events = await connection.fetchval(
                "SELECT count(*) FROM canonical.projection_outbox WHERE organization_id = $1 AND event_type = 'relationship.upserted'",
                tenant_a,
            )
        assert after_relationship_events == before_relationship_events
    finally:
        await neo4j.close()
        await store.close()
