from __future__ import annotations

import json
from typing import Protocol

import redis.asyncio as redis

from app.prompt_registry.schemas import PromptTemplate


class PromptStore(Protocol):
    async def save(self, prompt: PromptTemplate) -> PromptTemplate: ...

    async def get(
        self, name: str, version: int | None = None
    ) -> PromptTemplate | None: ...

    async def list_versions(self, name: str) -> list[int]: ...


class InMemoryPromptStore:
    def __init__(self) -> None:
        self._prompts: dict[tuple[str, int], PromptTemplate] = {}

    async def save(self, prompt: PromptTemplate) -> PromptTemplate:
        key = (prompt.name, prompt.version)
        if key in self._prompts:
            raise ValueError(
                f"prompt version already exists: {prompt.name} v{prompt.version}"
            )
        self._prompts[key] = prompt
        return prompt

    async def get(self, name: str, version: int | None = None) -> PromptTemplate | None:
        if version is not None:
            return self._prompts.get((name, version))
        versions = await self.list_versions(name)
        return self._prompts.get((name, versions[-1])) if versions else None

    async def list_versions(self, name: str) -> list[int]:
        return sorted(
            version for prompt_name, version in self._prompts if prompt_name == name
        )


class RedisPromptStore:
    """Redis-backed versioned store using atomic per-prompt version counters."""

    def __init__(self, client: redis.Redis, prefix: str = "agents:prompts") -> None:
        self.client = client
        self.prefix = prefix.rstrip(":")

    def _version_key(self, name: str, version: int) -> str:
        return f"{self.prefix}:{name}:v:{version}"

    def _counter_key(self, name: str) -> str:
        return f"{self.prefix}:{name}:latest"

    async def save(self, prompt: PromptTemplate) -> PromptTemplate:
        version = await self.client.incr(self._counter_key(prompt.name))
        if version != prompt.version:
            await self.client.decr(self._counter_key(prompt.name))
            raise ValueError(
                f"prompt version must be next version {version} for {prompt.name}"
            )
        await self.client.set(
            self._version_key(prompt.name, prompt.version), prompt.model_dump_json()
        )
        return prompt

    async def get(self, name: str, version: int | None = None) -> PromptTemplate | None:
        if version is None:
            raw_version = await self.client.get(self._counter_key(name))
            if raw_version is None:
                return None
            version = int(raw_version)
        raw = await self.client.get(self._version_key(name, version))
        return PromptTemplate.model_validate(json.loads(raw)) if raw else None

    async def list_versions(self, name: str) -> list[int]:
        latest = await self.client.get(self._counter_key(name))
        return list(range(1, int(latest) + 1)) if latest else []
