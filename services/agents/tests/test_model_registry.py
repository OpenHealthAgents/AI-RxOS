from __future__ import annotations

import pytest

from app.model_registry.adapters import ModelProviderError
from app.model_registry.adapters import OpenSourceAdapter, adapter_for
from app.model_registry.registry import ModelRegistry
from app.model_registry.schemas import ModelConfig, ModelRegistryConfig, ModelRequest, ModelResponse


def registry_config() -> ModelRegistryConfig:
    return ModelRegistryConfig(
        primary_model="primary",
        fallback_models=["backup"],
        models={
            "primary": ModelConfig(name="gpt-test", provider="openai", temperature=0.7, max_tokens=111),
            "backup": ModelConfig(name="claude-test", provider="anthropic", temperature=0.1, max_tokens=222),
        },
    )


class FakeAdapter:
    def __init__(self, response: ModelResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if self.error:
            raise self.error
        assert request.messages
        return self.response

    async def stream(self, request: ModelRequest):
        if self.error:
            raise self.error
        for chunk in ("hello", " world"):
            yield chunk


@pytest.mark.asyncio
async def test_complete_falls_back_when_primary_fails():
    config = registry_config()
    registry = ModelRegistry(
        config,
        adapters={
            "primary": FakeAdapter(error=ModelProviderError("timeout")),
            "backup": FakeAdapter(response=ModelResponse(model="claude-test", provider="anthropic", content="backup")),
        },
    )

    response = await registry.complete(ModelRequest(messages=[{"role": "user", "content": "hello"}]))

    assert response.content == "backup"
    assert response.model == "claude-test"


@pytest.mark.asyncio
async def test_stream_falls_back_before_first_chunk():
    config = registry_config()
    registry = ModelRegistry(
        config,
        adapters={
            "primary": FakeAdapter(error=ModelProviderError("unavailable")),
            "backup": FakeAdapter(),
        },
    )

    chunks = [chunk async for chunk in registry.stream(ModelRequest(messages=[{"role": "user", "content": "hello"}]))]

    assert chunks == ["hello", " world"]


def test_registry_config_rejects_missing_fallback_model():
    with pytest.raises(ValueError, match="not configured"):
        ModelRegistryConfig(primary_model="primary", fallback_models=["missing"], models={})


def test_open_source_provider_uses_dedicated_adapter():
    config = ModelConfig(name="mistral", provider="open_source", base_url="http://model")

    assert isinstance(adapter_for(config), OpenSourceAdapter)