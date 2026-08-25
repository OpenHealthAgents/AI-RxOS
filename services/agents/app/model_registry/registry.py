from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Callable
from typing import Any

from app.core.errors import AIPlatformError
from app.core.errors import TimeoutError as PlatformTimeoutError
from app.core.observability import metrics
from app.model_registry.adapters import (
    ModelProviderError,
    ProviderAdapter,
    adapter_for,
)
from app.model_registry.schemas import ModelRegistryConfig, ModelRequest, ModelResponse
from app.security.redaction import sanitize_exception

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Provider-neutral model selection with ordered failure fallback."""

    def __init__(
        self,
        config: ModelRegistryConfig,
        adapters: dict[str, ProviderAdapter] | None = None,
        adapter_factory: Callable[[Any], ProviderAdapter] = adapter_for,
    ) -> None:
        self.config = config
        self.adapters = adapters or {
            name: adapter_factory(model_config)
            for name, model_config in config.models.items()
        }

    def _model_order(self) -> list[str]:
        return [self.config.primary_model, *self.config.fallback_models]

    async def complete(self, request: ModelRequest) -> ModelResponse:
        failures: list[str] = []
        for model_name in self._model_order():
            model_config = self.config.models[model_name]
            for attempt in range(model_config.max_retries + 1):
                try:
                    return await asyncio.wait_for(
                        self.adapters[model_name].complete(request),
                        timeout=model_config.timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    timeout_error = PlatformTimeoutError(
                        "model_call", details={"model": model_name}
                    )
                    error: AIPlatformError = timeout_error
                except (ModelProviderError, PlatformTimeoutError) as exc:
                    error = exc
                if isinstance(error, ModelProviderError) and not error.retriable:
                    attempt = model_config.max_retries
                failures.append(model_name)
                logger.warning(
                    "model_call_failed",
                    extra={
                        "event": "model_call_failed",
                        "model": model_name,
                        "error_code": error.code,
                        "attempt": attempt + 1,
                        **sanitize_exception(error),
                    },
                )
                if attempt < model_config.max_retries:
                    metrics.inc(
                        "agent_model_retries_total",
                        provider=model_config.provider,
                        model=model_config.name,
                    )
                    retry_after = error.details.get("retry_after_seconds")
                    delay = (
                        float(retry_after)
                        if isinstance(retry_after, (int, float))
                        else min(2**attempt + random.random(), 30)
                    )
                    await asyncio.sleep(max(delay, 0.0))
        raise ModelProviderError(
            "all configured models failed",
            details={"attempts": len(failures)},
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        failures: list[str] = []
        for model_name in self._model_order():
            model_config = self.config.models[model_name]
            for attempt in range(model_config.max_retries + 1):
                yielded = False
                try:
                    async with asyncio.timeout(model_config.timeout_seconds):
                        async for chunk in self.adapters[model_name].stream(request):
                            yielded = True
                            yield chunk
                    return
                except asyncio.TimeoutError:
                    error: AIPlatformError = PlatformTimeoutError(
                        "model_stream", details={"model": model_name}
                    )
                except (ModelProviderError, PlatformTimeoutError) as exc:
                    error = exc
                if yielded:
                    raise error
                failures.append(model_name)
                logger.warning(
                    "model_stream_failed",
                    extra={
                        "event": "model_stream_failed",
                        "model": model_name,
                        "attempt": attempt + 1,
                        **sanitize_exception(error),
                    },
                )
                if error.retriable and attempt < model_config.max_retries:
                    retry_after = error.details.get("retry_after_seconds")
                    delay = (
                        float(retry_after)
                        if isinstance(retry_after, (int, float))
                        else min(2**attempt + random.random(), 30)
                    )
                    await asyncio.sleep(max(delay, 0.0))
                else:
                    break
        raise ModelProviderError(
            "all configured streaming models failed",
            details={"attempts": len(failures)},
        )
