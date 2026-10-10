from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
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
    Modality,
    ObservationCreate,
    ObservationKind,
    SourceRecordInput,
    Visibility,
)
from app.services.canonical_repository import CanonicalRepository

TEST_DATABASE_URL = os.getenv("KG_TEST_DATABASE_URL")
MIGRATION_DIR = Path(__file__).parents[1] / "migrations"
GLOBAL_OPERATOR = CanonicalPrincipal(
    UUID("11111111-1111-1111-1111-111111111111"),
    None,
    frozenset({"operator", "reviewer"}),
    frozenset(),
)


def _admin_url(database_url: str) -> str:
    parts = urlsplit(database_url)
    return urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment))


@pytest_asyncio.fixture
async def validation_store():
    if not TEST_DATABASE_URL:
        pytest.skip("set KG_TEST_DATABASE_URL for disposable PostgreSQL migration validation")
    database_name = f"ai_rxos_b04_{uuid4().hex}"
    admin = await asyncpg.connect(_admin_url(TEST_DATABASE_URL), statement_cache_size=0)
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
    finally:
        await admin.close()

    parts = urlsplit(TEST_DATABASE_URL)
    database_url = urlunsplit((parts.scheme, parts.netloc, f"/{database_name}", parts.query, parts.fragment))
    store = CanonicalStore()
    try:
        await store.initialize(database_url)
        yield store
    finally:
        await store.close()
        admin = await asyncpg.connect(_admin_url(TEST_DATABASE_URL), statement_cache_size=0)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
        finally:
            await admin.close()


def _source(namespace: str, external_id: str) -> SourceRecordInput:
    return SourceRecordInput(
        namespace=namespace,
        external_id=external_id,
        source_type="database",
        provenance={"b04_fixture": True},
    )


async def _counts(store: CanonicalStore) -> dict[str, int]:
    async with store.connection(None) as connection:
        return {
            table: await connection.fetchval(f"SELECT count(*) FROM canonical.{table}")
            for table in ("source_records", "entities", "identifiers", "observations", "relationships", "reconciliation_results")
        }


@pytest.mark.asyncio
async def test_clean_migration_schema_and_repeat_are_stable(validation_store):
    store = validation_store
    async with store.connection(None) as connection:
        tables = {
            row["table_name"]
            for row in await connection.fetch(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'canonical'"
            )
        }
        assert {"schema_migrations", "source_records", "entities", "identifiers", "aliases", "observations", "relationships", "projection_outbox", "reconciliation_results"} <= tables
        migration_rows = await connection.fetch(
            "SELECT migration_id, checksum FROM canonical.schema_migrations ORDER BY migration_id"
        )
        assert [row["migration_id"] for row in migration_rows] == [
            path.name for path in sorted(MIGRATION_DIR.glob("[0-9][0-9][0-9]_*.sql"))
        ]
        assert all(row["checksum"] for row in migration_rows)
        policies = await connection.fetch(
            "SELECT tablename, policyname FROM pg_policies WHERE schemaname = 'canonical'"
        )
        assert any(row["tablename"] == "reconciliation_results" for row in policies)
        security = await connection.fetch(
            """SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'canonical' AND c.relname IN (
                'source_records', 'entities', 'identifiers', 'aliases', 'relationships',
                'observations', 'projection_outbox', 'reconciliation_results')"""
        )
        assert all(row["relrowsecurity"] and row["relforcerowsecurity"] for row in security)

        before = await connection.fetch("SELECT * FROM canonical.schema_migrations ORDER BY migration_id")
    for _ in range(3):
        await store.apply_migrations()
    async with store.connection(None) as connection:
        after = await connection.fetch("SELECT * FROM canonical.schema_migrations ORDER BY migration_id")
    assert [dict(row) for row in before] == [dict(row) for row in after]


@pytest.mark.asyncio
async def test_existing_canonical_data_survives_repeated_migration(validation_store):
    store = validation_store
    repository = CanonicalRepository(store)
    suffix = uuid4().hex
    entity = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.THERAPEUTIC_ASSET,
            preferred_name=f"B04 asset {suffix}",
            modality=Modality.OTHER,
            source_record=_source("b04", f"asset:{suffix}"),
            visibility=Visibility.GLOBAL,
        ),
        GLOBAL_OPERATOR,
    )
    entity_id = UUID(str(entity["id"]))
    await repository.create_observation(
        ObservationCreate(
            entity_id=entity_id,
            property_name="b04_fact",
            observation_kind=ObservationKind.SOURCE_FACT,
            value={"fixture": True},
            source_record=_source("b04", f"observation:{suffix}"),
        ),
        GLOBAL_OPERATOR,
    )
    before = await _counts(store)
    await store.apply_migrations()
    after = await _counts(store)
    assert after == before
    fetched = await repository.get_entity(entity_id, GLOBAL_OPERATOR)
    assert fetched["preferred_name"] == f"B04 asset {suffix}"


@pytest.mark.asyncio
async def test_b02_b03_source_lineage_survives_migration(validation_store):
    store = validation_store
    repository = CanonicalRepository(store)
    literature = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.PUBLICATION,
            preferred_name="B02 compatibility publication",
            source_record=_source("literature", "b02-compatibility"),
        ),
        GLOBAL_OPERATOR,
    )
    neo4j = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.TARGET,
            preferred_name="B03 compatibility target",
            source_record=_source("neo4j", "b03-compatibility"),
        ),
        GLOBAL_OPERATOR,
    )
    before = await _counts(store)
    await store.apply_migrations()
    after = await _counts(store)
    assert after == before
    async with store.connection(None) as connection:
        namespaces = await connection.fetch(
            "SELECT namespace, external_id FROM canonical.source_records WHERE external_id = ANY($1::text[]) ORDER BY namespace",
            ["b02-compatibility", "b03-compatibility"],
        )
    assert [(row["namespace"], row["external_id"]) for row in namespaces] == [
        ("literature", "b02-compatibility"),
        ("neo4j", "b03-compatibility"),
    ]
    assert literature["created_source_record_id"]
    assert neo4j["created_source_record_id"]


@pytest.mark.asyncio
async def test_checksum_drift_is_detected(validation_store):
    store = validation_store
    async with store.connection(None) as connection:
        await connection.execute(
            "UPDATE canonical.schema_migrations SET checksum = 'tampered' WHERE migration_id = $1",
            "001_canonical_data_model.sql",
        )
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        await store.apply_migrations()


@pytest.mark.asyncio
async def test_failed_migration_is_transactional_and_retryable(validation_store):
    store = validation_store
    pool = store.pool
    assert pool is not None
    async with pool.acquire() as connection:
        with pytest.raises(asyncpg.DuplicateTableError):
            async with connection.transaction():
                await connection.execute("CREATE TABLE canonical.b04_recovery_probe (id integer)")
                await connection.execute("CREATE TABLE canonical.b04_recovery_probe (id integer)")
        assert await connection.fetchval(
            "SELECT to_regclass('canonical.b04_recovery_probe')"
        ) is None
        async with connection.transaction():
            await connection.execute("CREATE TABLE canonical.b04_recovery_probe (id integer)")
        assert await connection.fetchval(
            "SELECT to_regclass('canonical.b04_recovery_probe')"
        ) == "canonical.b04_recovery_probe"
        await connection.execute("DROP TABLE canonical.b04_recovery_probe")


@pytest.mark.asyncio
async def test_canonical_constraints_and_append_only_integrity(validation_store):
    store = validation_store
    repository = CanonicalRepository(store)
    suffix = uuid4().hex
    entity = await repository.create_entity(
        CanonicalEntityCreate(
            entity_type=EntityType.TARGET,
            preferred_name=f"B04 target {suffix}",
            source_record=_source("b04", f"target:{suffix}"),
        ),
        GLOBAL_OPERATOR,
    )
    entity_id = UUID(str(entity["id"]))
    async with store.pool.acquire() as connection:
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await connection.execute(
                """INSERT INTO canonical.identifiers
                (id, entity_id, visibility, namespace, identifier_type, value, normalized_value, source_record_id)
                VALUES ($1, $2, 'global', 'b04', 'orphan', 'x', 'x', $3)""",
                uuid4(), uuid4(), uuid4(),
            )
        await connection.execute(
            """INSERT INTO canonical.identifiers
            (id, entity_id, visibility, namespace, identifier_type, value, normalized_value, source_record_id)
            VALUES ($1, $2, 'global', 'b04', 'stable', 'x', 'x', $3)""",
            uuid4(), entity_id, entity["created_source_record_id"],
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await connection.execute(
                """INSERT INTO canonical.identifiers
                (id, entity_id, visibility, namespace, identifier_type, value, normalized_value, source_record_id)
                VALUES ($1, $2, 'global', 'b04', 'stable', 'x', 'x', $3)""",
                uuid4(), entity_id, entity["created_source_record_id"],
            )
        observation = await repository.create_observation(
            ObservationCreate(
                entity_id=entity_id,
                property_name="append_only_fixture",
                observation_kind=ObservationKind.SOURCE_FACT,
                value={"fixture": True},
                source_record=_source("b04", f"append-only:{suffix}"),
            ),
            GLOBAL_OPERATOR,
        )
        with pytest.raises(asyncpg.PostgresError, match="append-only"):
            await connection.execute(
                "UPDATE canonical.observations SET property_name = 'tampered' WHERE id = $1",
                observation["id"],
            )
