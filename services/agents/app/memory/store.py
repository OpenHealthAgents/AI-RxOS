"""Agent memory and conversation memory backends.

No memory or conversation implementation existed anywhere in the repo
before this (services/agents was a ~65-line stub that only enqueued
AgentTask records to Redis — see app/main.py's TASK_KEY convention, which
this module follows). This deliberately does not implement the full
Postgres agents/conversations/messages schema sketched in
architecture/04-database-schemas.md — only the reusable Redis-backed
memory infrastructure future agents need, matching the existing
TASK_KEY = "agents:task:{id}" pattern and the architecture doc's own
`agent:context:{conversation_id}` Redis hash convention for conversation
state.

Working/short-term memory lives in Redis with a TTL. "Long-term" durability
is delegated to LLM Wiki (see LLMWikiMemoryClient) exactly as literature's
wiki_client.py does: if LLM_WIKI_URL isn't configured, writes are recorded
as skipped rather than pretending a production LLM Wiki service exists.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import redis.asyncio as redis

from app.core.config import get_settings
from app.core.security import TenantContext

AGENT_MEMORY_KEY = "agent:memory:{org}:{workspace}:{agent_id}:{key}"
AGENT_MEMORY_INDEX_KEY = "agent:memory:index:{org}:{workspace}:{agent_id}"
CONVERSATION_KEY = "agent:context:{conversation_id}"

_NO_ORG = "_none"
_NO_WORKSPACE = "_shared"


def _scope(tenant: TenantContext) -> tuple[str, str]:
    return (tenant.organization_id or _NO_ORG, tenant.workspace_id or _NO_WORKSPACE)


class LLMWikiMemoryClient:
    """Optional long-term persistence of memory entries through LLM Wiki.

    Mirrors services/literature/app/integrations/wiki_client.py's HTTP
    contract (POST {url}/api/v1/wiki/compile) rather than inventing a new
    one. When LLM_WIKI_URL is not configured — the default, since no real
    LLM Wiki service is deployed anywhere in this repo — writes are
    recorded as skipped instead of silently pretending to succeed.
    """

    def __init__(self, base_url: str | None = None, timeout_seconds: float = 5.0):
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def persist(
        self,
        *,
        source_type: str,
        source_id: str,
        title: str,
        text: str,
        tenant: TenantContext,
    ) -> dict[str, Any]:
        if not self.base_url:
            return {"success": True, "status": "skipped", "reason": "LLM_WIKI_URL not configured"}
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                res = client.post(
                    f"{self.base_url.rstrip('/')}/api/v1/wiki/compile",
                    json={
                        "document": {"source": source_type, "source_id": source_id, "title": title},
                        "entities": [{"text": title, "category": source_type}],
                        "summary": {"concise_summary": text},
                        "tenant": tenant.as_dict(),
                    },
                )
            if res.status_code in (200, 201):
                return {"success": True, "status": "completed"}
            return {"success": False, "status": "failed", "error": res.text}
        except httpx.HTTPError as exc:
            return {"success": False, "status": "failed", "error": str(exc)}


class AgentMemoryStore:
    """Redis-backed agent memory scoped by organization/workspace/agent.

    Scoping comes exclusively from the caller-supplied TenantContext
    (derived from the verified JWT — see app.core.security.get_tenant_context),
    never from client-suppliable request fields, so one organization can
    never read another's agent memory by guessing keys.
    """

    def __init__(self, redis_client: redis.Redis, ttl_seconds: int = 60 * 60 * 24 * 30):
        self.redis = redis_client
        self.ttl_seconds = ttl_seconds
        settings = get_settings()
        self.long_term = LLMWikiMemoryClient(getattr(settings, "llm_wiki_url", None))

    async def store(
        self,
        *,
        tenant: TenantContext,
        agent_id: str,
        key: str,
        value: Any,
        provenance: dict[str, Any] | None = None,
        persist_long_term: bool = False,
    ) -> dict[str, Any]:
        org, workspace = _scope(tenant)
        record = {
            "organization_id": tenant.organization_id,
            "workspace_id": tenant.workspace_id,
            "project_id": tenant.project_id,
            "agent_id": agent_id,
            "key": key,
            "value": value,
            "provenance": provenance or {},
            "stored_at": time.time(),
        }
        scoped_key = AGENT_MEMORY_KEY.format(org=org, workspace=workspace, agent_id=agent_id, key=key)
        await self.redis.set(scoped_key, json.dumps(record), ex=self.ttl_seconds)

        index_key = AGENT_MEMORY_INDEX_KEY.format(org=org, workspace=workspace, agent_id=agent_id)
        await self.redis.sadd(index_key, key)
        await self.redis.expire(index_key, self.ttl_seconds)

        if persist_long_term:
            record["long_term"] = self.long_term.persist(
                source_type="agent_memory",
                source_id=f"{agent_id}:{key}",
                title=key,
                text=json.dumps(value) if not isinstance(value, str) else value,
                tenant=tenant,
            )
        return record

    async def retrieve(self, *, tenant: TenantContext, agent_id: str, key: str) -> dict[str, Any] | None:
        org, workspace = _scope(tenant)
        scoped_key = AGENT_MEMORY_KEY.format(org=org, workspace=workspace, agent_id=agent_id, key=key)
        raw = await self.redis.get(scoped_key)
        return json.loads(raw) if raw else None

    async def search(
        self, *, tenant: TenantContext, agent_id: str, query: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        org, workspace = _scope(tenant)
        index_key = AGENT_MEMORY_INDEX_KEY.format(org=org, workspace=workspace, agent_id=agent_id)
        keys = await self.redis.smembers(index_key)
        records: list[dict[str, Any]] = []
        for raw_key in keys:
            scoped_key = AGENT_MEMORY_KEY.format(org=org, workspace=workspace, agent_id=agent_id, key=raw_key)
            raw = await self.redis.get(scoped_key)
            if not raw:
                continue
            record = json.loads(raw)
            if query and query.lower() not in json.dumps(record.get("value", "")).lower():
                continue
            records.append(record)
        records.sort(key=lambda r: r.get("stored_at", 0), reverse=True)
        return records[:limit]


class ConversationMemoryStore:
    """Redis-backed conversation memory, keyed agent:context:{conversation_id}
    per architecture/04-database-schemas.md's Redis convention.

    The tenant that first creates a conversation "owns" it; every
    subsequent read/write must present a matching TenantContext or the
    operation is treated as not-found (never as "forbidden", so a caller
    probing conversation ids can't distinguish "wrong tenant" from
    "doesn't exist").
    """

    def __init__(self, redis_client: redis.Redis, ttl_seconds: int = 60 * 60 * 24, max_messages: int = 100):
        self.redis = redis_client
        self.ttl_seconds = ttl_seconds
        self.max_messages = max_messages

    @staticmethod
    def _key(conversation_id: str) -> str:
        return CONVERSATION_KEY.format(conversation_id=conversation_id)

    async def _load(self, conversation_id: str) -> dict[str, Any] | None:
        raw = await self.redis.get(self._key(conversation_id))
        return json.loads(raw) if raw else None

    @staticmethod
    def _owns(record: dict[str, Any], tenant: TenantContext) -> bool:
        owner = record.get("tenant") or {}
        return owner.get("organization_id") == tenant.organization_id and owner.get(
            "workspace_id"
        ) == tenant.workspace_id

    async def add_message(
        self,
        *,
        tenant: TenantContext,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        record = await self._load(conversation_id)
        if record is None:
            record = {"tenant": tenant.as_dict(), "messages": []}
        elif not self._owns(record, tenant):
            return None

        record["messages"].append(
            {
                "role": role,
                "content": content,
                "metadata": metadata or {},
                "created_at": time.time(),
                "user_id": tenant.user_id,
            }
        )
        if len(record["messages"]) > self.max_messages:
            record["messages"] = record["messages"][-self.max_messages :]

        await self.redis.set(self._key(conversation_id), json.dumps(record), ex=self.ttl_seconds)
        return record

    async def get_messages(
        self, *, tenant: TenantContext, conversation_id: str, limit: int | None = None
    ) -> list[dict[str, Any]] | None:
        record = await self._load(conversation_id)
        if record is None or not self._owns(record, tenant):
            return None
        messages = record.get("messages", [])
        return messages[-limit:] if limit else messages
