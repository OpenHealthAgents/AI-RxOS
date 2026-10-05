from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.version_service import VersionNotFoundError, VersionService
from app.core.canonical_security import CanonicalPrincipal
from uuid import UUID

client = TestClient(app)
PRINCIPAL = CanonicalPrincipal(None, UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"), frozenset(), frozenset())


# ---------------------------------------------------------------------------
# Router contract: VersionNotFoundError -> 404
# ---------------------------------------------------------------------------

def test_rollback_to_nonexistent_version_returns_404():
    with patch("app.services.version_service.VersionService.rollback_to_version") as mock_rollback:
        mock_rollback.side_effect = VersionNotFoundError("Graph version 999 does not exist")
        res = client.post("/api/v1/graph/versions/rollback/999")
        assert res.status_code == 404


def test_rollback_to_existing_version_returns_200():
    with patch("app.services.version_service.VersionService.rollback_to_version") as mock_rollback:
        mock_rollback.return_value = 2
        res = client.post("/api/v1/graph/versions/rollback/1")
        assert res.status_code == 200
        assert res.json()["rolled_back_versions_count"] == 2


# ---------------------------------------------------------------------------
# Service layer: rollback validates existence and reactivates the target
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session():
    async def fake_execute_read(func, **kwargs):
        name = getattr(func, "__name__", "")
        if name == "get_version_by_number":
            if kwargs.get("version_number") == 404:
                return None
            return {"version_number": kwargs.get("version_number"), "status": "rolled_back"}
        return None

    async def fake_execute_write(func, **kwargs):
        name = getattr(func, "__name__", "")
        if name == "rollback_to_version":
            return 3
        return None

    with patch("app.database.neo4j.neo4j_manager.get_session") as mock_get:
        mock_sess = AsyncMock()
        mock_sess.execute_read = AsyncMock(side_effect=fake_execute_read)
        mock_sess.execute_write = AsyncMock(side_effect=fake_execute_write)
        mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_get.return_value.__aexit__ = AsyncMock(return_value=None)
        yield mock_sess


@pytest.mark.asyncio
async def test_service_rollback_raises_for_missing_version(mock_session):
    with pytest.raises(VersionNotFoundError):
        await VersionService.rollback_to_version(404, PRINCIPAL)


@pytest.mark.asyncio
async def test_service_rollback_succeeds_for_existing_version(mock_session):
    count = await VersionService.rollback_to_version(2, PRINCIPAL)
    assert count == 3
