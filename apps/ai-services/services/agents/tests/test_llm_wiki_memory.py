from __future__ import annotations

import json

import httpx
import pytest

from app.core.security import TenantContext
from app.memory.llm_wiki import AgentMemory, LLMWikiMemoryAdapter


def test_short_term_memory_is_scoped_to_one_run():
    first = AgentMemory(
        "run-1", TenantContext(organization_id="org-a", workspace_id="ws-1")
    )
    second = AgentMemory(
        "run-2", TenantContext(organization_id="org-a", workspace_id="ws-1")
    )
    first.remember("finding", "private")

    assert first.recall("finding") == "private"
    assert second.recall("finding") is None


@pytest.mark.asyncio
async def test_llm_wiki_memory_forwards_workspace_and_isolates_retrieval():
    stored: dict[tuple[str | None, str | None, str], dict] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            payload = json.loads(request.content)
            tenant = payload["tenant"]
            entity = payload["entities"][0]["text"]
            stored[
                (tenant.get("organization_id"), tenant.get("workspace_id"), entity)
            ] = payload
            return httpx.Response(201, json={"success": True}, request=request)

        params = dict(request.url.params)
        identity = (
            params.get("organization_id"),
            params.get("workspace_id"),
            params["slug"],
        )
        payload = stored.get(identity)
        if payload is None:
            return httpx.Response(404, request=request)
        return httpx.Response(
            200,
            json={
                "current_version": 1,
                "latest_version": {
                    "summary": payload["summary"],
                },
            },
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = LLMWikiMemoryAdapter("https://wiki.test", client=client)
    tenant_a = TenantContext(organization_id="org-a", workspace_id="ws-1")
    tenant_b = TenantContext(organization_id="org-a", workspace_id="ws-2")

    await adapter.store(
        tenant=tenant_a,
        agent_id="researcher",
        key="finding",
        value={"drug": "trastuzumab"},
    )
    assert (
        await adapter.retrieve(tenant=tenant_a, agent_id="researcher", key="finding")
    )["value"] == {"drug": "trastuzumab"}
    assert (
        await adapter.retrieve(tenant=tenant_b, agent_id="researcher", key="finding")
        is None
    )
    await client.aclose()


def test_agent_memory_auto_configures_llm_wiki_from_settings(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "llm_wiki_url", "https://wiki.test")
    memory = AgentMemory("configured-run", TenantContext(organization_id="org-a"))

    assert memory.long_term is not None
    assert memory.long_term.base_url == "https://wiki.test"
