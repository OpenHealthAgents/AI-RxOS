from __future__ import annotations

import json
import time
from typing import Any

import redis.asyncio as redis

from app.core.security import TenantContext

CONVERSATION_KEY = "agent:context:{conversation_id}"


class ConversationMemoryStore:
    """Redis-backed tenant-isolated conversation history."""

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
        return owner.get("organization_id") == tenant.organization_id and owner.get("workspace_id") == tenant.workspace_id

    async def add_message(self, *, tenant: TenantContext, conversation_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
        record = await self._load(conversation_id)
        if record is None:
            record = {"tenant": tenant.as_dict(), "messages": []}
        elif not self._owns(record, tenant):
            return None
        record["messages"].append({"role": role, "content": content, "metadata": metadata or {}, "created_at": time.time(), "user_id": tenant.user_id})
        record["messages"] = record["messages"][-self.max_messages :]
        await self.redis.set(self._key(conversation_id), json.dumps(record), ex=self.ttl_seconds)
        return record

    async def get_messages(self, *, tenant: TenantContext, conversation_id: str, limit: int | None = None) -> list[dict[str, Any]] | None:
        record = await self._load(conversation_id)
        if record is None or not self._owns(record, tenant):
            return None
        messages = record.get("messages", [])
        return messages[-limit:] if limit else messages
