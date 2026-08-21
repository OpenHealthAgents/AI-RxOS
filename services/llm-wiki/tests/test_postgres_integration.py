"""Real-Postgres integration tests -- create/get/update/version/tenant
isolation/persistence exercised against the actual llm_wiki schema
(migrations/001_wiki_schema.sql), not the InMemoryWikiRepository double the
fast unit suite uses.

Skipped automatically when no Postgres is reachable. Point TEST_DATABASE_URL
elsewhere, or run `docker compose up -d postgres` for the default
localhost:15432 target (matches docker-compose.yml's host port mapping).
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import asyncpg
import pytest

from app.db.pool import MIGRATIONS_DIR
from app.repository import PostgresWikiRepository, TenantScope

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://ai_rxos:changeme@localhost:15432/ai_rxos"
)


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog", format="text"
    )


def _postgres_available() -> bool:
    async def _check() -> bool:
        try:
            conn = await asyncpg.connect(TEST_DATABASE_URL, timeout=2)
            await conn.close()
            return True
        except Exception:
            return False

    return asyncio.run(_check())


pytestmark = pytest.mark.skipif(
    not _postgres_available(),
    reason=f"Postgres not reachable at {TEST_DATABASE_URL} -- run `docker compose up -d postgres`",
)


@pytest.fixture()
async def pg_repo():
    pool = await asyncpg.create_pool(TEST_DATABASE_URL, min_size=1, max_size=5, init=_init_connection)
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        async with pool.acquire() as conn:
            await conn.execute(path.read_text(encoding="utf-8"))
    repo = PostgresWikiRepository(pool)
    marker = f"pytest-{uuid.uuid4()}"
    yield repo, marker
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM llm_wiki.wiki_pages WHERE organization_id LIKE 'pytest-%'")
    await pool.close()


async def test_real_create_and_retrieve_round_trip(pg_repo):
    repo, marker = pg_repo
    tenant = TenantScope(organization_id=marker)

    pages = await repo.compile_pages(
        tenant=tenant,
        document={"source": "pubmed", "source_id": "PMID1", "title": "T", "doi": "10.1/x"},
        entities=[{"text": "trastuzumab", "category": "drugs"}],
        summary={"concise_summary": "s1"},
        relationships=[],
        evidence=[{"entity": "trastuzumab", "category": "efficacy", "score": 0.7}],
        chunks=[],
    )
    assert len(pages) == 1
    page_id = pages[0]["id"]

    fetched = await repo.get_page(tenant, page_id)
    assert fetched is not None
    assert fetched["page"]["category"] == "drugs"
    assert fetched["version"]["summary"]["concise_summary"] == "s1"
    assert fetched["version"]["evidence"][0]["score"] == 0.7
    assert fetched["version"]["provenance"]["doi"] == "10.1/x"


async def test_real_version_increment_and_history(pg_repo):
    repo, marker = pg_repo
    tenant = TenantScope(organization_id=marker)
    doc = {"source": "s", "source_id": "d1", "title": "T"}

    p1 = await repo.compile_pages(
        tenant=tenant,
        document=doc,
        entities=[{"text": "her2", "category": "genes"}],
        summary={"concise_summary": "v1"},
        relationships=[],
        evidence=[],
        chunks=[],
    )
    page_id = p1[0]["id"]
    assert p1[0]["version"] == 1

    p2 = await repo.compile_pages(
        tenant=tenant,
        document=doc,
        entities=[{"text": "her2", "category": "genes"}],
        summary={"concise_summary": "v2"},
        relationships=[],
        evidence=[],
        chunks=[],
    )
    assert p2[0]["id"] == page_id
    assert p2[0]["version"] == 2

    versions = await repo.list_versions(tenant, page_id)
    assert [v["version"] for v in versions] == [2, 1]

    v1 = await repo.get_version(tenant, page_id, 1)
    assert v1["summary"]["concise_summary"] == "v1"


async def test_real_tenant_a_cannot_read_tenant_b(pg_repo):
    repo, marker = pg_repo
    org_a = TenantScope(organization_id=f"{marker}-a")
    org_b = TenantScope(organization_id=f"{marker}-b")
    doc = {"source": "s", "source_id": "d1", "title": "T"}

    pages = await repo.compile_pages(
        tenant=org_a,
        document=doc,
        entities=[{"text": "shared-slug", "category": "drugs"}],
        summary={"concise_summary": "org-a data"},
        relationships=[],
        evidence=[],
        chunks=[],
    )
    page_id = pages[0]["id"]

    assert await repo.get_page(org_b, page_id) is None
    assert await repo.get_page(org_a, page_id) is not None


async def test_persistence_survives_a_fresh_connection_pool(pg_repo):
    """Simulates a service restart: a brand-new pool (not the fixture's)
    must still see data written earlier, proving persistence isn't an
    artifact of connection-local state or in-process caching."""
    repo, marker = pg_repo
    tenant = TenantScope(organization_id=marker)
    pages = await repo.compile_pages(
        tenant=tenant,
        document={"source": "s", "source_id": "d1", "title": "T"},
        entities=[{"text": "restart-check", "category": "drugs"}],
        summary={"concise_summary": "still here"},
        relationships=[],
        evidence=[],
        chunks=[],
    )
    page_id = pages[0]["id"]

    fresh_pool = await asyncpg.create_pool(
        TEST_DATABASE_URL, min_size=1, max_size=2, init=_init_connection
    )
    try:
        fresh_repo = PostgresWikiRepository(fresh_pool)
        fetched = await fresh_repo.get_page(tenant, page_id)
        assert fetched is not None
        assert fetched["version"]["summary"]["concise_summary"] == "still here"
    finally:
        await fresh_pool.close()
