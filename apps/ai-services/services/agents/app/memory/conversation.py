from __future__ import annotations

import json
import logging
import time
from typing import Any

import redis.asyncio as redis

from app.core.errors import ServiceDegradedError
from app.core.security import TenantContext
from app.security.redaction import sanitize_exception

logger = logging.getLogger(__name__)

CONVERSATION_KEY = "agent:context:{organization_id}:{workspace_id}:{conversation_id}"


class ConversationMemoryStore:
    """Redis-backed tenant-isolated conversation history."""

    def __init__(
        self,
        redis_client: redis.Redis,
        ttl_seconds: int = 60 * 60 * 24,
        max_messages: int = 100,
    ):
        self.redis = redis_client
        self.ttl_seconds = ttl_seconds
        self.max_messages = max_messages

    @staticmethod
    def _key(tenant: TenantContext, conversation_id: str) -> str:
        return CONVERSATION_KEY.format(
            organization_id=tenant.organization_id or "_none",
            workspace_id=tenant.workspace_id or "_shared",
            conversation_id=conversation_id,
        )

    async def _load(
        self, tenant: TenantContext, conversation_id: str
    ) -> dict[str, Any] | None:
        try:
            raw = await self.redis.get(self._key(tenant, conversation_id))
            return json.loads(raw) if raw else None
        except (redis.RedisError, ConnectionError, OSError) as exc:
            logger.warning(
                "conversation_memory_redis_unavailable",
                extra={
                    "event": "conversation_memory_redis_unavailable",
                    "conversation_id": conversation_id,
                    **sanitize_exception(exc),
                },
            )
            raise ServiceDegradedError(
                f"Conversation memory backend unavailable: {exc}", service="redis"
            ) from exc

    @staticmethod
    def _owns(record: dict[str, Any], tenant: TenantContext) -> bool:
        owner = record.get("tenant") or {}
        return (
            owner.get("organization_id") == tenant.organization_id
            and owner.get("workspace_id") == tenant.workspace_id
        )

    async def add_message(
        self,
        *,
        tenant: TenantContext,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        record = await self._load(tenant, conversation_id)
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
        record["messages"] = record["messages"][-self.max_messages :]
        try:
            await self.redis.set(
                self._key(tenant, conversation_id),
                json.dumps(record),
                ex=self.ttl_seconds,
            )
        except (redis.RedisError, ConnectionError, OSError) as exc:
            logger.warning(
                "conversation_memory_redis_unavailable",
                extra={
                    "event": "conversation_memory_redis_unavailable",
                    "conversation_id": conversation_id,
                    **sanitize_exception(exc),
                },
            )
            raise ServiceDegradedError(
                f"Conversation memory backend unavailable: {exc}", service="redis"
            ) from exc
        return record

    async def get_messages(
        self, *, tenant: TenantContext, conversation_id: str, limit: int | None = None
    ) -> list[dict[str, Any]] | None:
        record = await self._load(tenant, conversation_id)
        if record is None or not self._owns(record, tenant):
            return None
        messages = record.get("messages", [])
        return messages[-limit:] if limit else messages
