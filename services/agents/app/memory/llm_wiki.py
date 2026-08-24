from __future__ import annotations

import json
import time
import inspect
import logging
from typing import Any

import httpx
import redis.asyncio as redis

from app.core.config import get_settings
from app.core.security import TenantContext

logger = logging.getLogger(__name__)


class LLMWikiMemoryError(RuntimeError):
    pass


class LLMWikiMemoryAdapter:
    """Agent memory adapter using the existing LLM Wiki compile/page APIs."""

    def __init__(self, base_url: str, *, api_key: str | None = None, timeout_seconds: float = 5.0, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.client = client

    @staticmethod
    def _slug(agent_id: str, key: str) -> str:
        return f"{agent_id}:{key}".replace(" ", "_")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        client = self.client or httpx.AsyncClient(timeout=self.timeout_seconds)
        close_client = self.client is None
        try:
            response = await client.request(method, f"{self.base_url}{path}", headers=self._headers(), **kwargs)
            return response
        except httpx.HTTPError as exc:
            raise LLMWikiMemoryError(f"LLM Wiki request failed: {exc}") from exc
        finally:
            if close_client:
                await client.aclose()

    async def store(
        self,
        *,
        tenant: TenantContext,
        agent_id: str,
        key: str,
        value: Any,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/api/v1/wiki/compile",
            json={
                "document": {
                    "source": "agent_memory",
                    "source_id": f"{agent_id}:{key}",
                    "title": key,
                    "content": json.dumps(value),
                },
                "entities": [{"text": self._slug(agent_id, key), "category": "agent_memory"}],
                "summary": {"concise_summary": json.dumps(value), "provenance": provenance or {}},
                "tenant": tenant.as_dict(),
            },
        )
        if response.status_code not in (200, 201):
            raise LLMWikiMemoryError(f"LLM Wiki rejected memory write: {response.status_code}")
        return {"status": "completed", "agent_id": agent_id, "key": key}

    async def retrieve(
        self, *, tenant: TenantContext, agent_id: str, key: str
    ) -> dict[str, Any] | None:
        response = await self._request(
            "GET",
            "/api/v1/wiki/pages",
            params={
                "category": "agent_memory",
                "slug": self._slug(agent_id, key),
                "organization_id": tenant.organization_id,
                "workspace_id": tenant.workspace_id,
            },
        )
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise LLMWikiMemoryError(f"LLM Wiki rejected memory read: {response.status_code}")
        page = response.json()
        latest = page.get("latest_version") or {}
        summary = latest.get("summary") or {}
        raw_value = summary.get("concise_summary")
        try:
            value = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
        except json.JSONDecodeError:
            value = raw_value
        return {
            "agent_id": agent_id,
            "key": key,
            "value": value,
            "organization_id": tenant.organization_id,
            "workspace_id": tenant.workspace_id,
            "version": page.get("current_version"),
            "provenance": summary.get("provenance", {}),
        }


class AgentMemory:
    """Run-local memory with explicit opt-in persistence to LLM Wiki."""

    def __init__(
        self,
        run_id: str | redis.Redis,
        tenant: TenantContext | None = None,
        long_term: LLMWikiMemoryAdapter | None = None,
        ttl_seconds: int = 60 * 60 * 24 * 30,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self.redis = redis_client or (run_id if not isinstance(run_id, str) else None)
        self.run_id = run_id if isinstance(run_id, str) else None
        self.tenant = tenant
        if long_term is None:
            settings = get_settings()
            if settings.llm_wiki_url:
                long_term = LLMWikiMemoryAdapter(settings.llm_wiki_url)
            else:
                logger.warning(
                    "agent_long_term_memory_disabled",
                    extra={"event": "agent_long_term_memory_disabled", "run_id": self.run_id},
                )
        self.long_term = long_term
        self.ttl_seconds = ttl_seconds
        self._short_term: dict[str, Any] = {}

    def remember(self, key: str, value: Any) -> None:
        self._short_term[key] = value

    def recall(self, key: str, default: Any = None) -> Any:
        return self._short_term.get(key, default)

    @staticmethod
    def _scope(tenant: TenantContext) -> tuple[str, str]:
        return (tenant.organization_id or "_none", tenant.workspace_id or "_shared")

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
        self.remember(key, value)
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
        if self.redis is not None:
            org, workspace = self._scope(tenant)
            scoped_key = f"agent:memory:{org}:{workspace}:{agent_id}:{key}"
            index_key = f"agent:memory:index:{org}:{workspace}:{agent_id}"
            await self.redis.set(scoped_key, json.dumps(record), ex=self.ttl_seconds)
            await self.redis.sadd(index_key, key)
            await self.redis.expire(index_key, self.ttl_seconds)
        if persist_long_term:
            record["long_term"] = await self.persist(agent_id, key, value, provenance)
        return record

    async def retrieve(self, *, tenant: TenantContext, agent_id: str, key: str) -> dict[str, Any] | None:
        if self.redis is not None:
            org, workspace = self._scope(tenant)
            raw = await self.redis.get(f"agent:memory:{org}:{workspace}:{agent_id}:{key}")
            if raw:
                return json.loads(raw)
        return await self.retrieve_long_term(agent_id, key) if self.long_term else None

    async def search(self, *, tenant: TenantContext, agent_id: str, query: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        if self.redis is None:
            return []
        org, workspace = self._scope(tenant)
        keys = await self.redis.smembers(f"agent:memory:index:{org}:{workspace}:{agent_id}")
        records = []
        for key in keys:
            record = await self.retrieve(tenant=tenant, agent_id=agent_id, key=key)
            if record and (not query or query.lower() in json.dumps(record.get("value", "")).lower()):
                records.append(record)
        records.sort(key=lambda record: record.get("stored_at", 0), reverse=True)
        return records[:limit]

    async def persist(self, agent_id: str, key: str, value: Any, provenance: dict[str, Any] | None = None) -> dict[str, Any]:
        self.remember(key, value)
        if self.long_term is None:
            return {"success": True, "status": "skipped", "reason": "LLM_WIKI_URL not configured"}
        if self.tenant is None:
            return {"status": "short_term_only"}
        return await self.long_term.store(tenant=self.tenant, agent_id=agent_id, key=key, value=value, provenance=provenance)

    async def retrieve_long_term(self, agent_id: str, key: str) -> dict[str, Any] | None:
        if self.long_term is None:
            return None
        if self.tenant is None:
            return None
        return await self.long_term.retrieve(tenant=self.tenant, agent_id=agent_id, key=key)


def create_agent_memory(
    run_id: str,
    tenant: TenantContext,
    *,
    redis_client: redis.Redis | None = None,
) -> AgentMemory:
    """Create the single request/run-scoped memory access path."""
    return AgentMemory(run_id, tenant, redis_client=redis_client)