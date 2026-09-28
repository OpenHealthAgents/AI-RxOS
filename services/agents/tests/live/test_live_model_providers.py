from __future__ import annotations

import os

import pytest

from app.model_registry.registry import ModelRegistry
from app.model_registry.schemas import ModelConfig, ModelRegistryConfig, ModelRequest

LIVE = os.getenv("AI_RXOS_LIVE_MODEL_TESTS") == "1"


_PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "open_source": "OPEN_SOURCE_API_KEY",
}


def _configured_provider(provider: str) -> ModelRegistry | None:
    key = os.getenv(_PROVIDER_ENV[provider])
    model = os.getenv(f"AI_RXOS_{provider.upper()}_MODEL")
    if provider == "open_source":
        model = model or os.getenv("OPEN_SOURCE_MODEL")
    if not key and provider != "open_source":
        return None
    if not model:
        return None
    config = ModelConfig(
        name=model,
        provider=provider,  # type: ignore[arg-type]
        api_key=key,
        base_url=os.getenv(f"AI_RXOS_{provider.upper()}_BASE_URL"),
        timeout_seconds=float(os.getenv("AI_RXOS_LIVE_TIMEOUT_SECONDS", "30")),
        max_retries=1,
    )
    return ModelRegistry(
        ModelRegistryConfig(primary_model="live", models={"live": config})
    )


@pytest.mark.parametrize("provider", ["openai", "anthropic", "google", "open_source"])
@pytest.mark.skipif(not LIVE, reason="set AI_RXOS_LIVE_MODEL_TESTS=1 to enable")
@pytest.mark.asyncio
async def test_model_registry_live_provider_completion_and_stream(provider: str):
    registry = _configured_provider(provider)
    if registry is None:
        pytest.skip(f"{provider} live credentials and model are not configured")

    request = ModelRequest(messages=[{"role": "user", "content": "Reply with OK."}], max_tokens=8)
    response = await registry.complete(request)
    assert response.provider == provider
    assert response.content

    chunks = [chunk async for chunk in registry.stream(request)]
    assert "".join(chunks)
