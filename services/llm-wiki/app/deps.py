from __future__ import annotations

from fastapi import Depends

from app.db.pool import get_pool_dependency
from app.repository import PostgresWikiRepository, WikiRepository


def get_repository(pool=Depends(get_pool_dependency)) -> WikiRepository:
    """Overridden in tests via `app.dependency_overrides[get_repository]`
    to swap in `InMemoryWikiRepository` -- since that override replaces
    this callable outright, `get_pool_dependency` (and therefore the real
    database) is never touched by the unit test suite."""
    return PostgresWikiRepository(pool)
