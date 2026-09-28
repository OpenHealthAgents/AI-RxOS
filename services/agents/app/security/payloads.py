from __future__ import annotations

import base64
import json
from typing import Any, Protocol

import redis.asyncio as redis
from cryptography.fernet import Fernet, InvalidToken

from app.core.security import TenantContext


class ExecutionPayloadStore(Protocol):
    async def put(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        payload_id: str,
        payload: dict[str, Any],
    ) -> None: ...

    async def get(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        payload_id: str,
    ) -> dict[str, Any] | None: ...

    async def delete(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        payload_id: str,
    ) -> None: ...


class RedisExecutionPayloadStore:
    """Encrypted durable execution payloads separate from operational Redis metadata."""

    def __init__(
        self,
        client: redis.Redis,
        *,
        key: str,
        prefix: str = "agents:execution-payloads",
        ttl_seconds: int = 86400,
    ) -> None:
        self.client = client
        self.fernet = Fernet(_fernet_key(key))
        self.prefix = prefix.rstrip(":")
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def scope(tenant_id: str, workspace_id: str) -> str:
        return f"{tenant_id or '_none'}:{workspace_id or '_shared'}"

    def _key(self, tenant_id: str, workspace_id: str, payload_id: str) -> str:
        return f"{self.prefix}:{self.scope(tenant_id, workspace_id)}:{payload_id}"

    async def put(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        payload_id: str,
        payload: dict[str, Any],
    ) -> None:
        token = self.fernet.encrypt(
            json.dumps(payload, separators=(",", ":")).encode()
        )
        await self.client.set(
            self._key(tenant_id, workspace_id, payload_id),
            token,
            ex=self.ttl_seconds,
        )

    async def get(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        payload_id: str,
    ) -> dict[str, Any] | None:
        raw = await self.client.get(self._key(tenant_id, workspace_id, payload_id))
        if raw is None:
            return None
        try:
            decoded = self.fernet.decrypt(raw)
            payload = json.loads(decoded)
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("execution payload is unavailable") from exc
        if not isinstance(payload, dict):
            raise TypeError("execution payload is invalid")
        return payload

    async def delete(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        payload_id: str,
    ) -> None:
        await self.client.delete(self._key(tenant_id, workspace_id, payload_id))


def _fernet_key(configured_key: str) -> bytes:
    try:
        decoded = base64.urlsafe_b64decode(configured_key.encode())
    except (ValueError, TypeError) as exc:
        raise ValueError("execution payload key must be a valid Fernet key") from exc
    if len(decoded) != 32 or len(configured_key) != 44:
        raise ValueError("execution payload key must be a valid Fernet key")
    return configured_key.encode()


def tenant_scope(tenant: dict[str, str]) -> tuple[str, str]:
    return tenant.get("organization_id", "_none"), tenant.get("workspace_id", "_shared")


def context_scope(tenant: TenantContext) -> tuple[str, str]:
    return tenant.organization_id or "_none", tenant.workspace_id or "_shared"
