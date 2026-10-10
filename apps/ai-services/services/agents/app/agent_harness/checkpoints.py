from __future__ import annotations

import json
from typing import Protocol

import redis.asyncio as redis

from app.agent_harness.schemas import AgentState
from app.core.config import get_settings
from app.core.security import TenantContext
from app.security.payloads import RedisExecutionPayloadStore, tenant_scope


class CheckpointStore(Protocol):
    async def save(self, state: AgentState) -> None: ...

    async def load(
        self, run_id: str, *, tenant: TenantContext | None = None
    ) -> AgentState | None: ...


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self._states: dict[str, AgentState] = {}

    async def save(self, state: AgentState) -> None:
        self._states[state.run_id] = state.model_copy(deep=True)

    async def load(
        self, run_id: str, *, tenant: TenantContext | None = None
    ) -> AgentState | None:
        state = self._states.get(run_id)
        return state.model_copy(deep=True) if state else None


class RedisCheckpointStore:
    def __init__(
        self,
        client: redis.Redis,
        prefix: str = "agents:checkpoints",
        payload_store: RedisExecutionPayloadStore | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        self.client = client
        self.prefix = prefix.rstrip(":")
        self.payloads = payload_store or RedisExecutionPayloadStore(
            client, key=get_settings().execution_payload_key
        )
        self.ttl_seconds = ttl_seconds or get_settings().checkpoint_ttl

    @staticmethod
    def _scope(state: AgentState | None = None, tenant: TenantContext | None = None) -> str:
        values = state.data.get("tenant", {}) if state is not None else {}
        if tenant is not None:
            values = tenant.as_dict()
        organization_id = values.get("organization_id", "_none")
        workspace_id = values.get("workspace_id", "_shared")
        return f"{organization_id}:{workspace_id}"

    def _key(
        self,
        run_id: str,
        *,
        state: AgentState | None = None,
        tenant: TenantContext | None = None,
    ) -> str:
        return f"{self.prefix}:{self._scope(state, tenant)}:{run_id}"

    async def save(self, state: AgentState) -> None:
        tenant_id, workspace_id = tenant_scope(state.data.get("tenant", {}))
        await self.payloads.put(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            payload_id=state.run_id,
            payload=state.model_dump(mode="json"),
        )
        metadata = {
            "run_id": state.run_id,
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "payload_reference": state.run_id,
        }
        await self.client.set(
            self._key(state.run_id, state=state),
            json.dumps(metadata, separators=(",", ":")),
            ex=self.ttl_seconds,
        )

    async def load(
        self, run_id: str, *, tenant: TenantContext | None = None
    ) -> AgentState | None:
        raw = await self.client.get(self._key(run_id, tenant=tenant))
        if not raw:
            return None
        metadata = json.loads(raw)
        payload = await self.payloads.get(
            tenant_id=metadata["tenant_id"],
            workspace_id=metadata["workspace_id"],
            payload_id=metadata["payload_reference"],
        )
        return AgentState.model_validate(payload) if payload else None
