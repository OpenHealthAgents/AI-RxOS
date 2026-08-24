from __future__ import annotations

import json
from typing import Protocol

import redis.asyncio as redis

from app.agent_harness.schemas import AgentState


class CheckpointStore(Protocol):
    async def save(self, state: AgentState) -> None: ...

    async def load(self, run_id: str) -> AgentState | None: ...


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self._states: dict[str, AgentState] = {}

    async def save(self, state: AgentState) -> None:
        self._states[state.run_id] = state.model_copy(deep=True)

    async def load(self, run_id: str) -> AgentState | None:
        state = self._states.get(run_id)
        return state.model_copy(deep=True) if state else None


class RedisCheckpointStore:
    def __init__(self, client: redis.Redis, prefix: str = "agents:checkpoints") -> None:
        self.client = client
        self.prefix = prefix.rstrip(":")

    def _key(self, run_id: str) -> str:
        return f"{self.prefix}:{run_id}"

    async def save(self, state: AgentState) -> None:
        await self.client.set(self._key(state.run_id), state.model_dump_json())

    async def load(self, run_id: str) -> AgentState | None:
        raw = await self.client.get(self._key(run_id))
        return AgentState.model_validate(json.loads(raw)) if raw else None