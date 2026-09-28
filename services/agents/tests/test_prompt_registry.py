from __future__ import annotations

import pytest

from app.prompt_registry.registry import PromptNotFoundError, PromptRegistry
from app.prompt_registry.storage import InMemoryPromptStore


@pytest.mark.asyncio
async def test_register_retrieve_by_version_and_latest():
    registry = PromptRegistry(InMemoryPromptStore())
    await registry.register("research", "Find papers about ${topic}.")
    await registry.register("research", "Review evidence about ${topic}.")

    assert (
        await registry.retrieve("research", version=1)
    ).template == "Find papers about ${topic}."
    assert (await registry.retrieve("research")).version == 2


@pytest.mark.asyncio
async def test_render_interpolates_variables_and_supports_explicit_version():
    registry = PromptRegistry(InMemoryPromptStore())
    await registry.register("greeting", "Hello ${name}, use ${tone} tone.")

    rendered = await registry.render("greeting", {"name": "Ada", "tone": "concise"})

    assert rendered == "Hello Ada, use concise tone."


@pytest.mark.asyncio
async def test_render_rejects_missing_variables_and_unknown_prompts():
    registry = PromptRegistry(InMemoryPromptStore())
    await registry.register("greeting", "Hello ${name}.")

    with pytest.raises(KeyError):
        await registry.render("greeting")
    with pytest.raises(PromptNotFoundError):
        await registry.retrieve("missing")


@pytest.mark.asyncio
async def test_explicit_versions_are_immutable():
    registry = PromptRegistry(InMemoryPromptStore())
    await registry.register("research", "v1", version=1)

    with pytest.raises(ValueError, match="already exists"):
        await registry.register("research", "replacement", version=1)

    assert await registry.versions("research") == [1]
