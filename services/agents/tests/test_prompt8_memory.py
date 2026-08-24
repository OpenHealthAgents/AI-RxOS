"""Tests for Prompt 8 agent memory + conversation memory: unit tests
against a fake in-memory Redis (no real Redis required), plus API-level
tests through FastAPI's TestClient proving cross-organization and
cross-workspace isolation and basic request validation.
"""

from __future__ import annotations

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import TenantContext
from app.memory.llm_wiki import AgentMemory
from app.memory.conversation import ConversationMemoryStore


class FakeRedis:
    """Minimal in-memory stand-in for redis.asyncio.Redis, covering only
    the operations AgentMemory/ConversationMemoryStore use."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._sets: dict[str, set[str]] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._values[key] = value

    async def get(self, key: str) -> str | None:
        return self._values.get(key)

    async def sadd(self, key: str, value: str) -> None:
        self._sets.setdefault(key, set()).add(value)

    async def expire(self, key: str, ttl: int) -> None:
        pass

    async def smembers(self, key: str) -> set[str]:
        return self._sets.get(key, set())


ORG_A = TenantContext(organization_id="org-a", workspace_id="ws-1", user_id="user-1")
ORG_A_WS2 = TenantContext(organization_id="org-a", workspace_id="ws-2", user_id="user-2")
ORG_B = TenantContext(organization_id="org-b", workspace_id="ws-1", user_id="user-3")


# ---------------------------------------------------------------------------
# AgentMemory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_memory_and_retrieve_roundtrip():
    store = AgentMemory(FakeRedis())
    await store.store(tenant=ORG_A, agent_id="literature-agent", key="last_query", value={"q": "HER2"})

    record = await store.retrieve(tenant=ORG_A, agent_id="literature-agent", key="last_query")
    assert record is not None
    assert record["value"] == {"q": "HER2"}
    assert record["organization_id"] == "org-a"
    assert record["workspace_id"] == "ws-1"


@pytest.mark.asyncio
async def test_agent_memory_search_filters_by_query_substring():
    store = AgentMemory(FakeRedis())
    await store.store(tenant=ORG_A, agent_id="a1", key="k1", value="HER2 targeted therapy")
    await store.store(tenant=ORG_A, agent_id="a1", key="k2", value="unrelated content")

    results = await store.search(tenant=ORG_A, agent_id="a1", query="her2")
    assert len(results) == 1
    assert results[0]["key"] == "k1"


@pytest.mark.asyncio
async def test_agent_memory_is_isolated_across_organizations():
    store = AgentMemory(FakeRedis())
    await store.store(tenant=ORG_A, agent_id="a1", key="secret", value="org-a-data")

    # Same agent_id/key, different organization -> nothing visible.
    record = await store.retrieve(tenant=ORG_B, agent_id="a1", key="secret")
    assert record is None

    results = await store.search(tenant=ORG_B, agent_id="a1")
    assert results == []


@pytest.mark.asyncio
async def test_agent_memory_is_isolated_across_workspaces_in_same_org():
    store = AgentMemory(FakeRedis())
    await store.store(tenant=ORG_A, agent_id="a1", key="secret", value="ws-1-data")

    record = await store.retrieve(tenant=ORG_A_WS2, agent_id="a1", key="secret")
    assert record is None


@pytest.mark.asyncio
async def test_agent_memory_long_term_persist_is_skipped_without_llm_wiki_url():
    store = AgentMemory(FakeRedis())
    record = await store.store(
        tenant=ORG_A, agent_id="a1", key="k1", value="v1", persist_long_term=True
    )
    assert record["long_term"]["status"] == "skipped"
    assert record["long_term"]["success"] is True


# ---------------------------------------------------------------------------
# ConversationMemoryStore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conversation_memory_add_and_get_messages():
    store = ConversationMemoryStore(FakeRedis())
    await store.add_message(tenant=ORG_A, conversation_id="conv-1", role="user", content="hello")
    await store.add_message(tenant=ORG_A, conversation_id="conv-1", role="assistant", content="hi there")

    messages = await store.get_messages(tenant=ORG_A, conversation_id="conv-1")
    assert messages is not None
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "hello"


@pytest.mark.asyncio
async def test_conversation_memory_trims_to_max_messages():
    store = ConversationMemoryStore(FakeRedis(), max_messages=3)
    for i in range(5):
        await store.add_message(tenant=ORG_A, conversation_id="conv-1", role="user", content=f"msg-{i}")

    messages = await store.get_messages(tenant=ORG_A, conversation_id="conv-1")
    assert len(messages) == 3
    assert [m["content"] for m in messages] == ["msg-2", "msg-3", "msg-4"]


@pytest.mark.asyncio
async def test_conversation_memory_is_isolated_across_organizations():
    store = ConversationMemoryStore(FakeRedis())
    await store.add_message(tenant=ORG_A, conversation_id="conv-1", role="user", content="org-a-secret")

    # A different org writing to the same conversation id is rejected...
    result = await store.add_message(tenant=ORG_B, conversation_id="conv-1", role="user", content="hijack")
    assert result is None

    # ...and cannot read it either.
    messages = await store.get_messages(tenant=ORG_B, conversation_id="conv-1")
    assert messages is None

    # The original organization's data is untouched.
    owner_messages = await store.get_messages(tenant=ORG_A, conversation_id="conv-1")
    assert len(owner_messages) == 1
    assert owner_messages[0]["content"] == "org-a-secret"


# ---------------------------------------------------------------------------
# API-level: auth, validation, and cross-tenant isolation through the routes
# ---------------------------------------------------------------------------


def _make_token(organization_id: str, workspace_id: str, user_id: str) -> str:
    settings = get_settings()
    return jwt.encode(
        {"sub": user_id, "organization_id": organization_id, "workspace_id": workspace_id},
        settings.jwt_secret,
        algorithm="HS256",
    )


@pytest.fixture
def api_client(monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main_module

    fake_redis = FakeRedis()
    monkeypatch.setattr(main_module, "_redis", fake_redis)
    monkeypatch.setattr(main_module, "conversation_memory_store", ConversationMemoryStore(fake_redis))
    return TestClient(main_module.app)


def _auth_headers(organization_id: str, workspace_id: str = "ws-1", user_id: str = "user-1") -> dict[str, str]:
    return {"Authorization": f"Bearer {_make_token(organization_id, workspace_id, user_id)}"}


def test_memory_api_requires_authentication(api_client):
    res = api_client.post("/api/v1/agents/memory", json={"agent_id": "a1", "key": "k1", "value": "v1"})
    assert res.status_code == 401


def test_memory_api_store_and_retrieve(api_client):
    headers = _auth_headers("org-a")
    res = api_client.post(
        "/api/v1/agents/memory",
        json={"agent_id": "a1", "key": "k1", "value": {"score": 0.9}},
        headers=headers,
    )
    assert res.status_code == 201

    res = api_client.get("/api/v1/agents/memory/a1/k1", headers=headers)
    assert res.status_code == 200
    assert res.json()["value"] == {"score": 0.9}


def test_memory_api_cross_organization_read_returns_404(api_client):
    api_client.post(
        "/api/v1/agents/memory",
        json={"agent_id": "a1", "key": "k1", "value": "org-a-only"},
        headers=_auth_headers("org-a"),
    )

    res = api_client.get("/api/v1/agents/memory/a1/k1", headers=_auth_headers("org-b"))
    assert res.status_code == 404


def test_conversation_api_cross_organization_hijack_returns_404(api_client):
    headers_a = _auth_headers("org-a")
    headers_b = _auth_headers("org-b")

    res = api_client.post(
        "/api/v1/agents/conversations/conv-1/messages",
        json={"role": "user", "content": "org-a-secret"},
        headers=headers_a,
    )
    assert res.status_code == 201

    res = api_client.post(
        "/api/v1/agents/conversations/conv-1/messages",
        json={"role": "user", "content": "hijack-attempt"},
        headers=headers_b,
    )
    assert res.status_code == 404

    res = api_client.get("/api/v1/agents/conversations/conv-1/messages", headers=headers_b)
    assert res.status_code == 404

    res = api_client.get("/api/v1/agents/conversations/conv-1/messages", headers=headers_a)
    assert res.status_code == 200
    assert res.json()["total"] == 1


def test_memory_api_rejects_malformed_body(api_client):
    res = api_client.post(
        "/api/v1/agents/memory",
        json={"agent_id": "a1"},  # missing required "key"/"value"
        headers=_auth_headers("org-a"),
    )
    assert res.status_code == 422
