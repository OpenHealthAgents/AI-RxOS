from __future__ import annotations

import os
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio

from app.core.config import Settings
from app.database.postgres import PostgresManager

TEST_DATABASE_URL = os.getenv("KG_TEST_DATABASE_URL")
ORG_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ORG_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _admin_url(database_url: str) -> str:
    parts = urlsplit(database_url)
    return urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment))


@pytest_asyncio.fixture
async def legacy_store():
    if not TEST_DATABASE_URL:
        pytest.skip("set KG_TEST_DATABASE_URL for legacy PostgreSQL security tests")
    database_name = f"ai_rxos_b06_{uuid4().hex}"
    role_name = f"b06_app_{uuid4().hex[:16]}"
    role_password = uuid4().hex
    admin = await asyncpg.connect(_admin_url(TEST_DATABASE_URL))
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        await admin.execute(
            f'CREATE ROLE "{role_name}" LOGIN PASSWORD \'{role_password}\' '
            "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
        )
        await admin.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{database_name}" TO "{role_name}"')
        target = await asyncpg.connect(
            urlunsplit((urlsplit(TEST_DATABASE_URL).scheme, urlsplit(TEST_DATABASE_URL).netloc, f"/{database_name}", "", ""))
        )
        try:
            await target.execute(f'GRANT USAGE, CREATE ON SCHEMA public TO "{role_name}"')
        finally:
            await target.close()
    finally:
        await admin.close()

    parts = urlsplit(TEST_DATABASE_URL)
    app_netloc = f"{quote(role_name)}:{quote(role_password)}@{parts.hostname}:{parts.port}"
    database_url = urlunsplit((parts.scheme, app_netloc, f"/{database_name}", parts.query, parts.fragment))
    manager = PostgresManager()
    try:
        await manager.init_pool(Settings(
            LITERATURE_DATABASE_URL=database_url,
            LITERATURE_MIGRATION_DATABASE_URL=database_url,
        ))
        async with manager.acquire(system_scope=True) as connection:
            assert await connection.fetchval("SELECT current_database()") == database_name
        assert await manager.ensure_schema()
        yield manager
    finally:
        await manager.close()
        admin = await asyncpg.connect(_admin_url(TEST_DATABASE_URL))
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
            await admin.execute(f'DROP ROLE IF EXISTS "{role_name}"')
        finally:
            await admin.close()


async def _seed(manager: PostgresManager) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    public_id, paper_a, paper_b, job_a, job_b = [uuid4() for _ in range(5)]
    async with manager.acquire(system_scope=True) as connection:
        await connection.executemany(
            "INSERT INTO literature_papers (id, title, source, tenant_id) VALUES ($1, $2, 'b06', $3)",
            [(public_id, "B06 public", None), (paper_a, "B06 A", ORG_A), (paper_b, "B06 B", ORG_B)],
        )
        await connection.executemany(
            """INSERT INTO literature_ingestion_jobs
            (id, source, query, status, organization_id)
            VALUES ($1, 'b06', $2, 'queued', $3)""",
            [(job_a, "A", ORG_A), (job_b, "B", ORG_B)],
        )
    return public_id, paper_a, paper_b, job_a, job_b


@pytest.mark.asyncio
async def test_legacy_rls_attack_matrix_and_pool_reuse(legacy_store: PostgresManager):
    public_id, paper_a, paper_b, job_a, job_b = await _seed(legacy_store)

    async with legacy_store.acquire(ORG_A) as connection:
        assert await connection.fetchval("SELECT rolsuper FROM pg_roles WHERE rolname = current_user") is False
        assert await connection.fetchval("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user") is False
        for table in ("literature_papers", "literature_ingestion_jobs"):
            assert await connection.fetchval(
                f"SELECT relrowsecurity FROM pg_class WHERE oid = '{table}'::regclass"
            ) is True
            assert await connection.fetchval(
                f"SELECT relforcerowsecurity FROM pg_class WHERE oid = '{table}'::regclass"
            ) is True
        assert {row["id"] for row in await connection.fetch("SELECT id FROM literature_papers")} == {public_id, paper_a}
        assert {row["id"] for row in await connection.fetch("SELECT id FROM literature_ingestion_jobs")} == {job_a}
        assert await connection.execute("UPDATE literature_papers SET title = 'attacked' WHERE id = $1", paper_b) == "UPDATE 0"
        assert await connection.execute("DELETE FROM literature_papers WHERE id = $1", paper_b) == "DELETE 0"
        assert await connection.execute("UPDATE literature_ingestion_jobs SET status = 'failed' WHERE id = $1", job_b) == "UPDATE 0"
        assert await connection.execute("DELETE FROM literature_ingestion_jobs WHERE id = $1", job_b) == "DELETE 0"
        with pytest.raises(asyncpg.PostgresError):
            await connection.execute(
                "INSERT INTO literature_papers (id, title, source, tenant_id) VALUES ($1, 'spoof', 'b06', $2)",
                uuid4(), ORG_B,
            )
        with pytest.raises(asyncpg.PostgresError):
            await connection.execute(
                "INSERT INTO literature_ingestion_jobs (id, source, query, status, organization_id) VALUES ($1, 'b06', 'spoof', 'queued', $2)",
                uuid4(), ORG_B,
            )

    async with legacy_store.acquire(ORG_B) as connection:
        assert {row["id"] for row in await connection.fetch("SELECT id FROM literature_papers")} == {public_id, paper_b}
        assert {row["id"] for row in await connection.fetch("SELECT id FROM literature_ingestion_jobs")} == {job_b}
        assert await connection.execute("UPDATE literature_papers SET title = 'attacked' WHERE id = $1", paper_a) == "UPDATE 0"
        assert await connection.execute("DELETE FROM literature_papers WHERE id = $1", paper_a) == "DELETE 0"
        assert await connection.execute("UPDATE literature_ingestion_jobs SET status = 'failed' WHERE id = $1", job_a) == "UPDATE 0"
        assert await connection.execute("DELETE FROM literature_ingestion_jobs WHERE id = $1", job_a) == "DELETE 0"

    async with legacy_store.acquire(None) as connection:
        assert {row["id"] for row in await connection.fetch("SELECT id FROM literature_papers")} == {public_id}
        assert await connection.fetch("SELECT id FROM literature_ingestion_jobs") == []
        assert await connection.execute("UPDATE literature_papers SET title = 'attacked' WHERE id = $1", paper_a) == "UPDATE 0"
        assert await connection.execute("DELETE FROM literature_papers WHERE id = $1", paper_b) == "DELETE 0"

    async with legacy_store.acquire(ORG_A) as connection:
        assert await connection.fetchval("SELECT count(*) FROM literature_papers") == 2
    async with legacy_store.acquire(ORG_B) as connection:
        assert await connection.fetchval("SELECT count(*) FROM literature_papers") == 2
    async with legacy_store.acquire(None) as connection:
        assert await connection.fetchval("SELECT count(*) FROM literature_papers") == 1
