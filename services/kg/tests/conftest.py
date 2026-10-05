import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.core.canonical_security import CanonicalPrincipal, get_canonical_principal
from app.database.canonical_store import CanonicalStore
from app.main import app
from app.services.canonical_repository import CanonicalRepository

TEST_DATABASE_URL = os.getenv("KG_TEST_DATABASE_URL")


def _admin_url(database_url: str) -> str:
    parts = urlsplit(database_url)
    return urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment))


@pytest_asyncio.fixture
async def canonical_repo():
    if not TEST_DATABASE_URL:
        pytest.skip("set KG_TEST_DATABASE_URL to run canonical PostgreSQL integration tests")
    database_name = f"ai_rxos_canonical_{uuid4().hex}"
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
        yield store, CanonicalRepository(store)
    finally:
        await store.close()
        admin = await asyncpg.connect(_admin_url(TEST_DATABASE_URL), statement_cache_size=0)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
        finally:
            await admin.close()


@pytest.fixture(autouse=True)
def scoped_graph_principal():
    app.dependency_overrides[get_canonical_principal] = lambda: CanonicalPrincipal(
        None,
        UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        frozenset(),
        frozenset(),
    )
    yield
    app.dependency_overrides.pop(get_canonical_principal, None)
