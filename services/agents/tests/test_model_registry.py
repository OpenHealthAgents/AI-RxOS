from __future__ import annotations

import httpx
import pytest

from app.core.observability import metrics
from app.model_registry.adapters import (
    ModelProviderError,
    OpenSourceAdapter,
    adapter_for,
    retryable_provider_error,
)
from app.model_registry.registry import ModelRegistry
from app.model_registry.schemas import (
    ModelConfig,
    ModelRegistryConfig,
    ModelRequest,
    ModelResponse,
)


def registry_config() -> ModelRegistryConfig:
    return ModelRegistryConfig(
        primary_model="primary",
        fallback_models=["backup"],
        models={
            "primary": ModelConfig(
                name="gpt-test", provider="openai", temperature=0.7, max_tokens=111
            ),
            "backup": ModelConfig(
                name="claude-test",
                provider="anthropic",
                temperature=0.1,
                max_tokens=222,
            ),
        },
    )


class FakeAdapter:
    def __init__(
        self, response: ModelResponse | None = None, error: Exception | None = None
    ) -> None:
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
async def test_transient_provider_failure_retries_with_bounded_policy():
    config = ModelRegistryConfig(
        primary_model="primary",
        models={
            "primary": ModelConfig(name="gpt-test", provider="openai", max_retries=1)
        },
    )

    class FlakyAdapter:
        attempts = 0

        async def complete(self, request: ModelRequest) -> ModelResponse:
            self.attempts += 1
            if self.attempts == 1:
                raise ModelProviderError("rate limited", retriable=True)
            return ModelResponse(model="gpt-test", provider="openai", content="ok")

    adapter = FlakyAdapter()
    registry = ModelRegistry(config, adapters={"primary": adapter})
    response = await registry.complete(
        ModelRequest(messages=[{"role": "user", "content": "hi"}])
    )

    assert response.content == "ok"
    assert adapter.attempts == 2
    assert "agent_model_retries_total" in metrics.render()


@pytest.mark.asyncio
async def test_complete_falls_back_when_primary_fails():
    config = registry_config()
    registry = ModelRegistry(
        config,
        adapters={
            "primary": FakeAdapter(error=ModelProviderError("timeout")),
            "backup": FakeAdapter(
                response=ModelResponse(
                    model="claude-test", provider="anthropic", content="backup"
                )
            ),
        },
    )

    response = await registry.complete(
        ModelRequest(messages=[{"role": "user", "content": "hello"}])
    )

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

    chunks = [
        chunk
        async for chunk in registry.stream(
            ModelRequest(messages=[{"role": "user", "content": "hello"}])
        )
    ]

    assert chunks == ["hello", " world"]


def test_registry_config_rejects_missing_fallback_model():
    with pytest.raises(ValueError, match="not configured"):
        ModelRegistryConfig(
            primary_model="primary", fallback_models=["missing"], models={}
        )


def test_open_source_provider_uses_dedicated_adapter():
    config = ModelConfig(
        name="mistral", provider="open_source", base_url="http://model"
    )

    assert isinstance(adapter_for(config), OpenSourceAdapter)


def test_provider_retry_classifier_excludes_auth_and_invalid_request():
    request = httpx.Request("POST", "https://provider.test")
    assert retryable_provider_error(
        httpx.HTTPStatusError(
            "rate", request=request, response=httpx.Response(429, request=request)
        )
    )
    assert retryable_provider_error(
        httpx.HTTPStatusError(
            "server", request=request, response=httpx.Response(503, request=request)
        )
    )
    assert not retryable_provider_error(
        httpx.HTTPStatusError(
            "auth", request=request, response=httpx.Response(401, request=request)
        )
    )
    assert not retryable_provider_error(
        httpx.HTTPStatusError(
            "invalid", request=request, response=httpx.Response(400, request=request)
        )
    )
