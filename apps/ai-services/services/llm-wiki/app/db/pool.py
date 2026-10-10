from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import asyncpg

from app.core.config import get_settings

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    # Let callers pass/receive Python dict/list values directly for jsonb
    # columns instead of hand-rolling json.dumps + ::jsonb casts on every
    # query.
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
        format="text",
    )


async def init_pool() -> asyncpg.Pool:
    global _pool
    settings = get_settings()
    _pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=1,
        max_size=10,
        init=_init_connection,
    )
    await _run_migrations(_pool)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool_dependency() -> asyncpg.Pool:
    """FastAPI dependency returning the live pool.

    Kept as a plain callable (not a bare module import inside handlers) so
    tests can swap it via `app.dependency_overrides` for a fake repository
    without needing a real Postgres instance.
    """
    if _pool is None:
        raise RuntimeError("database pool is not initialized")
    return _pool


async def _run_migrations(pool: asyncpg.Pool) -> None:
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        async with pool.acquire() as conn:
            await conn.execute(sql)
        logger.info("applied migration %s", path.name)


@asynccontextmanager
async def tenant_connection(
    pool: asyncpg.Pool, organization_id: str | None
) -> AsyncIterator[asyncpg.Connection]:
    """Acquire a connection with the caller's tenant scope set for the
    duration of one transaction.

    `set_config(..., true)` makes the GUC transaction-local, so it never
    leaks onto the next request when the pooled connection is reused for a
    different tenant. This is the second (database-layer) half of tenant
    isolation -- see llm_wiki.wiki_pages_isolation in migrations/001; the
    first half is the explicit WHERE clause every repository query also
    applies.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.wiki_organization_id', $1, true)",
                organization_id or "",
            )
            yield conn
