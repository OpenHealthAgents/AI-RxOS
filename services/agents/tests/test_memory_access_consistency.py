from __future__ import annotations

import asyncio
import json

import jwt
import pytest
from fastapi.testclient import TestClient

from app.agent_harness import AgentRuntime, AgentState, InMemoryCheckpointStore, StateGraph
from app.core.config import get_settings
from app.core.security import TenantContext
from app.main import app
from app.memory.llm_wiki import LLMWikiMemoryAdapter
from app.model_registry.schemas import ModelResponse


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.sets = {}

    async def set(self, key, value, ex=None):
        self.values[key] = value

    async def get(self, key):
        return self.values.get(key)

    async def sadd(self, key, value):
        self.sets.setdefault(key, set()).add(value)

    async def expire(self, key, ttl):
        return None


class SharedWikiAdapter(LLMWikiMemoryAdapter):
    records: dict[tuple[str | None, str | None, str, str], object] = {}

    async def store(self, *, tenant, agent_id, key, value, provenance=None):
        self.records[(tenant.organization_id, tenant.workspace_id, agent_id, key)] = value
        return {"status": "completed"}

    async def retrieve(self, *, tenant, agent_id, key):
        value = self.records.get((tenant.organization_id, tenant.workspace_id, agent_id, key))
        if value is None:
            return None
        return {
            "agent_id": agent_id,
            "key": key,
            "value": value,
            "organization_id": tenant.organization_id,
            "workspace_id": tenant.workspace_id,
        }


def auth_headers(organization_id: str, workspace_id: str) -> dict[str, str]:
    settings = get_settings()
    token = jwt.encode(
        {"sub": "consistency-user", "organization_id": organization_id, "workspace_id": workspace_id},
        settings.jwt_secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


class EmptyModels:
    async def complete(self, _request):
        return ModelResponse(model="unused", provider="openai", content="unused")


@pytest.mark.asyncio
async def test_api_write_is_visible_to_graph_run_through_same_wiki_path(monkeypatch):
    import app.main as main_module
    import app.memory.llm_wiki as memory_module

    fake_redis = FakeRedis()
    monkeypatch.setattr(main_module, "_redis", fake_redis)
    monkeypatch.setattr(get_settings(), "llm_wiki_url", "https://wiki.test")
    monkeypatch.setattr(memory_module, "LLMWikiMemoryAdapter", SharedWikiAdapter)
    SharedWikiAdapter.records.clear()
    headers = auth_headers("org-consistency", "workspace-1")

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agents/memory",
            json={
                "agent_id": "researcher",
                "key": "finding",
                "value": {"drug": "trastuzumab"},
                "persist_long_term": True,
            },
            headers=headers,
        )

    assert response.status_code == 201

    runtime = AgentRuntime(
        models=EmptyModels(),
        prompts=object(),
        tools=object(),
        tenant=TenantContext(organization_id="org-consistency", workspace_id="workspace-1"),
    )
    observed = {}

    async def graph_node(state, dependencies):
        observed["memory"] = await dependencies.memory.retrieve_long_term("researcher", "finding")
        return {}

    graph = StateGraph().add_node("read", graph_node).set_entry_point("read").compile(InMemoryCheckpointStore())
    await graph.run(runtime, state=AgentState(run_id="graph-consistency-run"))

    assert observed["memory"]["value"] == {"drug": "trastuzumab"}
    assert observed["memory"]["organization_id"] == "org-consistency"
    assert observed["memory"]["workspace_id"] == "workspace-1"


@pytest.mark.asyncio
async def test_graph_persist_is_visible_to_api_read_through_same_wiki_path(monkeypatch):
    import app.main as main_module
    import app.memory.llm_wiki as memory_module

    fake_redis = FakeRedis()
    monkeypatch.setattr(main_module, "_redis", fake_redis)
    monkeypatch.setattr(get_settings(), "llm_wiki_url", "https://wiki.test")
    monkeypatch.setattr(memory_module, "LLMWikiMemoryAdapter", SharedWikiAdapter)
    SharedWikiAdapter.records.clear()
    tenant = TenantContext(organization_id="org-graph", workspace_id="workspace-graph")
    runtime = AgentRuntime(models=EmptyModels(), prompts=object(), tools=object(), tenant=tenant)

    async def graph_node(state, dependencies):
        await dependencies.memory.persist(
            "researcher",
            "finding",
            {"drug": "trastuzumab"},
            {"source": "graph-run"},
        )
        return {}

    graph = StateGraph().add_node("write", graph_node).set_entry_point("write").compile(InMemoryCheckpointStore())
    await graph.run(runtime, state=AgentState(run_id="graph-write-run"))

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/agents/memory/researcher/finding",
            headers=auth_headers("org-graph", "workspace-graph"),
        )

    assert response.status_code == 200
    assert response.json()["value"] == {"drug": "trastuzumab"}
    assert response.json()["organization_id"] == "org-graph"
    assert response.json()["workspace_id"] == "workspace-graph"
