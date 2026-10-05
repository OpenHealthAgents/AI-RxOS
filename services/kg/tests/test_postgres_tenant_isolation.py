from __future__ import annotations

import os
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio

from app.core.canonical_security import CanonicalPrincipal
from app.database.canonical_store import CanonicalStore
from app.schemas.canonical import (
    CanonicalEntityCreate,
    CanonicalRelationshipCreate,
    EntityType,
    IdentifierInput,
    LicensingEventType,
    Modality,
    ObservationCreate,
    ObservationKind,
    SourceRecordInput,
    Visibility,
)
from app.services.canonical_repository import CanonicalRepository

TEST_DATABASE_URL = os.getenv("KG_TEST_DATABASE_URL")
ORG_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ORG_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_A = UUID("aaaaaaaa-0000-0000-0000-000000000001")
USER_B = UUID("bbbbbbbb-0000-0000-0000-000000000001")
TENANT_A = CanonicalPrincipal(USER_A, ORG_A, frozenset(), frozenset())
TENANT_B = CanonicalPrincipal(USER_B, ORG_B, frozenset(), frozenset())
OPERATOR = CanonicalPrincipal(UUID("11111111-1111-1111-1111-111111111111"), None, frozenset({"operator"}), frozenset())


def _admin_url(database_url: str) -> str:
    parts = urlsplit(database_url)
    return urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment))


def _source(namespace: str, external_id: str) -> SourceRecordInput:
    return SourceRecordInput(
        namespace=namespace,
        external_id=external_id,
        source_type="database",
        provenance={"b05_fixture": True},
    )


@pytest_asyncio.fixture
async def tenant_store():
    if not TEST_DATABASE_URL:
        pytest.skip("set KG_TEST_DATABASE_URL for PostgreSQL tenant isolation tests")
    database_name = f"ai_rxos_b05_{uuid4().hex}"
    role_name = f"b05_app_{uuid4().hex[:16]}"
    role_password = uuid4().hex
    admin = await asyncpg.connect(_admin_url(TEST_DATABASE_URL), statement_cache_size=0)
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        await admin.execute(
            f"CREATE ROLE \"{role_name}\" LOGIN PASSWORD '{role_password}' NOSUPERUSER NOCREATEDB NOCREATEROLE"
        )
        await admin.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{database_name}" TO "{role_name}"')
    finally:
        await admin.close()
    parts = urlsplit(TEST_DATABASE_URL)
    app_netloc = f"{quote(role_name)}:{quote(role_password)}@{parts.hostname}:{parts.port}"
    database_url = urlunsplit((parts.scheme, app_netloc, f"/{database_name}", parts.query, parts.fragment))
    store = CanonicalStore()
    try:
        await store.initialize(database_url)
        yield store
    finally:
        await store.close()
        admin = await asyncpg.connect(_admin_url(TEST_DATABASE_URL), statement_cache_size=0)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
            await admin.execute(f'DROP ROLE IF EXISTS "{role_name}"')
        finally:
            await admin.close()


async def _seed(store: CanonicalStore) -> dict[str, object]:
    repository = CanonicalRepository(store)
    suffix = uuid4().hex
    public = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.TARGET,
            preferred_name=f"B05 public {suffix}",
            source_record=_source("b05", f"public:{suffix}"),
        ),
        OPERATOR,
    )
    public_id = UUID(str(public["id"]))
    tenant_entities: dict[str, dict[EntityType, UUID]] = {"a": {}, "b": {}}
    entity_types = list(EntityType)
    for key, principal, organization in (("a", TENANT_A, ORG_A), ("b", TENANT_B, ORG_B)):
        for entity_type in entity_types:
            payload = CanonicalEntityCreate(
                entity_type=entity_type,
                preferred_name=f"B05 {key} {entity_type.value} {suffix}",
                modality=Modality.OTHER if entity_type == EntityType.THERAPEUTIC_ASSET else None,
                attributes=(
                    {"event_type": LicensingEventType.OTHER}
                    if entity_type == EntityType.LICENSING_EVENT
                    else {}
                ),
                visibility=Visibility.TENANT,
                source_record=_source("b05", f"{key}:{entity_type.value}:{suffix}"),
            )
            entity = await repository.create_entity(payload, principal)
            tenant_entities[key][entity_type] = UUID(str(entity["id"]))

    target_a = tenant_entities["a"][EntityType.TARGET]
    target_b = tenant_entities["b"][EntityType.TARGET]
    for entity_id, principal, key in ((target_a, TENANT_A, "a"), (target_b, TENANT_B, "b")):
        source = _source("b05", f"identifier:{key}:{suffix}")
        await repository.ensure_identifier(entity_id, "b05", "private", f"{key}-{suffix}", source, Visibility.TENANT, principal)
        await repository.create_observation(
            ObservationCreate(
                entity_id=entity_id,
                visibility=Visibility.TENANT,
                property_name="private_fact",
                observation_kind=ObservationKind.SOURCE_FACT,
                value={"tenant": key},
                source_record=_source("b05", f"observation:{key}:{suffix}"),
            ),
            principal,
        )
        await repository.create_relationship(
            CanonicalRelationshipCreate(
                subject_entity_id=entity_id,
                object_entity_id=public_id,
                visibility=Visibility.TENANT,
                predicate="ANNOTATES",
                observation_value={"tenant": key},
                source_record=_source("b05", f"relationship:{key}:{suffix}"),
            ),
            principal,
        )
        await repository.reconcile_legacy_record(
            {
                "source_type": "b05",
                "source_record_id": f"reconciliation:{key}:{suffix}",
                "entity_type": EntityType.TARGET.value,
                "tenant_id": str(principal.organization_id),
                "names": [f"B05 {key} target {suffix}"],
                "source_record": _source("b05", f"reconciliation:{key}:{suffix}").model_dump(mode="json"),
            },
            principal,
        )

    await repository.create_observation(
        ObservationCreate(
            entity_id=public_id,
            property_name="public_fact",
            observation_kind=ObservationKind.SOURCE_FACT,
            value={"public": True},
            source_record=_source("b05", f"public-observation:{suffix}"),
        ),
        OPERATOR,
    )
    return {"public": public_id, "a": tenant_entities["a"], "b": tenant_entities["b"]}


@pytest.mark.asyncio
async def test_direct_rls_attack_matrix_and_public_visibility(tenant_store):
    store = tenant_store
    ids = await _seed(store)
    target_a = ids["a"][EntityType.TARGET]
    target_b = ids["b"][EntityType.TARGET]

    async with store.connection(ORG_A) as connection:
        visible = await connection.fetch("SELECT id, organization_id FROM canonical.entities")
        visible_ids = {row["id"] for row in visible}
        assert ids["public"] in visible_ids, "public entity is not visible to tenant A"
        assert target_a in visible_ids, "tenant A entity is not visible to tenant A"
        current_org = await connection.fetchval("SELECT current_setting('app.canonical_organization_id', true)")
        assert target_b not in visible_ids, (
            "tenant B entity leaked to tenant A: "
            f"row={next(row for row in visible if row['id'] == target_b)}, "
            f"current_org={current_org}"
        )
        assert await connection.fetchval("SELECT count(*) FROM canonical.identifiers WHERE organization_id = $1", ORG_B) == 0
        assert await connection.fetchval("SELECT count(*) FROM canonical.observations WHERE organization_id = $1", ORG_B) == 0
        assert await connection.fetchval("SELECT count(*) FROM canonical.relationships WHERE organization_id = $1", ORG_B) == 0
        assert await connection.fetchval("SELECT count(*) FROM canonical.reconciliation_results WHERE tenant_id = $1", ORG_B) == 0
        assert await connection.fetchval("SELECT count(*) FROM canonical.source_records WHERE organization_id = $1", ORG_B) == 0

        assert await connection.execute("UPDATE canonical.entities SET preferred_name = 'ATTACKED' WHERE id = $1", target_b) == "UPDATE 0"
        assert await connection.execute("DELETE FROM canonical.entities WHERE id = $1", target_b) == "DELETE 0"
        assert await connection.execute("UPDATE canonical.identifiers SET value = 'ATTACKED' WHERE organization_id = $1", ORG_B) == "UPDATE 0"
        assert await connection.execute("DELETE FROM canonical.observations WHERE organization_id = $1", ORG_B) == "DELETE 0"
        assert await connection.execute("UPDATE canonical.relationships SET predicate = 'ATTACKED' WHERE organization_id = $1", ORG_B) == "UPDATE 0"
        assert await connection.execute("DELETE FROM canonical.reconciliation_results WHERE tenant_id = $1", ORG_B) == "DELETE 0"
        assert await connection.execute("DELETE FROM canonical.source_records WHERE organization_id = $1", ORG_B) == "DELETE 0"
        with pytest.raises(asyncpg.PostgresError):
            await connection.execute(
                """INSERT INTO canonical.entities
                (id, entity_type, preferred_name, normalized_name, visibility, organization_id)
                VALUES ($1, 'target', 'forged', 'forged', 'tenant', $2)""",
                uuid4(), ORG_B,
            )

    async with store.connection(ORG_B) as connection:
        visible_ids = {row["id"] for row in await connection.fetch("SELECT id FROM canonical.entities")}
        assert ids["public"] in visible_ids and target_b in visible_ids and target_a not in visible_ids

    async with store.connection(None) as connection:
        private_count = await connection.fetchval(
            "SELECT count(*) FROM canonical.entities WHERE organization_id IS NOT NULL"
        )
        assert private_count == 0
        assert await connection.fetchval("SELECT count(*) FROM canonical.reconciliation_results WHERE tenant_id IS NOT NULL") == 0


@pytest.mark.asyncio
async def test_connection_context_is_transaction_local_and_pool_safe(tenant_store):
    store = tenant_store
    pool = store.pool
    assert pool is not None
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SELECT set_config('app.canonical_organization_id', $1, true)", str(ORG_A))
            assert await connection.fetchval("SELECT canonical.current_organization_id()") == ORG_A
        async with connection.transaction():
            assert await connection.fetchval("SELECT current_setting('app.canonical_organization_id', true)") in ("", None)
            await connection.execute("SELECT set_config('app.canonical_organization_id', $1, true)", str(ORG_B))
            assert await connection.fetchval("SELECT canonical.current_organization_id()") == ORG_B
        async with connection.transaction():
            assert await connection.fetchval("SELECT current_setting('app.canonical_organization_id', true)") in ("", None)

    async with store.connection(ORG_A) as connection:
        assert await connection.fetchval("SELECT canonical.current_organization_id()") == ORG_A
    async with store.connection(ORG_B) as connection:
        assert await connection.fetchval("SELECT canonical.current_organization_id()") == ORG_B
    async with store.connection(None) as connection:
        assert await connection.fetchval("SELECT current_setting('app.canonical_organization_id', true)") == ""
