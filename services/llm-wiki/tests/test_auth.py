import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.deps import get_repository
from app.main import app
from app.repository import InMemoryWikiRepository

_COMPILE_BODY = {"document": {"title": "T"}, "entities": [], "summary": {}}


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    monkeypatch.delenv("LLM_WIKI_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def unauthed_client():
    """A client with data access faked out but auth NOT bypassed -- unlike
    the `client` fixture in conftest.py, this exercises the real
    require_api_key dependency."""
    app.dependency_overrides[get_repository] = lambda: InMemoryWikiRepository()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_no_api_key_configured_allows_unauthenticated_requests(unauthed_client):
    # Dev-mode posture: LLM_WIKI_API_KEY unset means no auth is enforced,
    # matching services/literature's LLMWikiClient (which only ever sends
    # a bearer token when it has one configured).
    res = unauthed_client.post("/api/v1/wiki/compile", json=_COMPILE_BODY)
    assert res.status_code == 201


def test_missing_bearer_token_rejected_when_api_key_configured(unauthed_client, monkeypatch):
    monkeypatch.setenv("LLM_WIKI_API_KEY", "secret-key")
    get_settings.cache_clear()
    res = unauthed_client.post("/api/v1/wiki/compile", json=_COMPILE_BODY)
    assert res.status_code == 401


def test_wrong_api_key_rejected(unauthed_client, monkeypatch):
    monkeypatch.setenv("LLM_WIKI_API_KEY", "secret-key")
    get_settings.cache_clear()
    res = unauthed_client.post(
        "/api/v1/wiki/compile", json=_COMPILE_BODY, headers={"Authorization": "Bearer wrong"}
    )
    assert res.status_code == 401


def test_correct_api_key_accepted(unauthed_client, monkeypatch):
    monkeypatch.setenv("LLM_WIKI_API_KEY", "secret-key")
    get_settings.cache_clear()
    res = unauthed_client.post(
        "/api/v1/wiki/compile", json=_COMPILE_BODY, headers={"Authorization": "Bearer secret-key"}
    )
    assert res.status_code == 201
