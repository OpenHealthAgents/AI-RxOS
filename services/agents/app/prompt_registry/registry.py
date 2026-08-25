from __future__ import annotations

from collections.abc import Mapping
from string import Template
from typing import Any

from app.prompt_registry.schemas import PromptTemplate
from app.prompt_registry.storage import PromptStore


class PromptNotFoundError(LookupError):
    pass


class PromptRegistry:
    def __init__(self, store: PromptStore) -> None:
        self.store = store

    async def register(
        self,
        name: str,
        template: str,
        *,
        version: int | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PromptTemplate:
        if version is None:
            versions = await self.store.list_versions(name)
            version = versions[-1] + 1 if versions else 1
        prompt = PromptTemplate(
            name=name,
            version=version,
            template=template,
            description=description,
            metadata=metadata or {},
        )
        return await self.store.save(prompt)

    async def retrieve(self, name: str, version: int | None = None) -> PromptTemplate:
        prompt = await self.store.get(name, version)
        if prompt is None:
            suffix = "latest" if version is None else f"v{version}"
            raise PromptNotFoundError(f"prompt not found: {name} ({suffix})")
        return prompt

    async def render(
        self,
        name: str,
        variables: Mapping[str, Any] | None = None,
        *,
        version: int | None = None,
    ) -> str:
        prompt = await self.retrieve(name, version)
        return Template(prompt.template).substitute(dict(variables or {}))

    async def versions(self, name: str) -> list[int]:
        return await self.store.list_versions(name)
