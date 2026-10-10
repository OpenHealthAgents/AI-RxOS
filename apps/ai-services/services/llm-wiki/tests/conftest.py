import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

os.environ["ENVIRONMENT"] = "test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.auth import require_api_key  # noqa: E402
from app.deps import get_repository  # noqa: E402
from app.main import app  # noqa: E402
from app.repository import InMemoryWikiRepository  # noqa: E402


@pytest.fixture()
def repo() -> InMemoryWikiRepository:
    return InMemoryWikiRepository()


@pytest.fixture()
def client(repo):
    """Fast, DB-independent client: in-memory repository, auth bypassed.

    Deliberately does NOT use `with TestClient(app) as client:` -- entering
    the context manager would run app/main.py's lifespan, which calls
    init_pool() and requires a real Postgres connection. Every route here
    gets its data access through the overridden `get_repository`
    dependency, so the (never-initialized) real pool is never touched.
    """
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[require_api_key] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
