from __future__ import annotations

import logging
import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from app.model_registry.adapters import ModelProviderError, ProviderAdapter, adapter_for
from app.model_registry.schemas import ModelRegistryConfig, ModelRequest, ModelResponse
from app.core.errors import TimeoutError as PlatformTimeoutError

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
            name: adapter_factory(model_config) for name, model_config in config.models.items()
        }

    def _model_order(self) -> list[str]:
        return [self.config.primary_model, *self.config.fallback_models]

    async def complete(self, request: ModelRequest) -> ModelResponse:
        failures: list[str] = []
        for model_name in self._model_order():
            try:
                return await asyncio.wait_for(
                    self.adapters[model_name].complete(request),
                    timeout=self.config.models[model_name].timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                exc = PlatformTimeoutError("model_call", details={"model": model_name})
                failures.append(f"{model_name}: {exc}")
                logger.warning("model_call_failed", extra={"event": "model_call_failed", "model": model_name, "error_code": exc.code})
            except (ModelProviderError, TimeoutError) as exc:
                failures.append(f"{model_name}: {exc}")
                logger.warning("Model %s failed; trying next configured model", model_name)
        raise ModelProviderError("all configured models failed: " + "; ".join(failures), details={"attempts": failures})

    async def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        failures: list[str] = []
        for model_name in self._model_order():
            try:
                async with asyncio.timeout(self.config.models[model_name].timeout_seconds):
                    yielded = False
                    async for chunk in self.adapters[model_name].stream(request):
                        yielded = True
                        yield chunk
                return
            except asyncio.TimeoutError as exc:
                exc = PlatformTimeoutError("model_stream", details={"model": model_name})
                if yielded:
                    raise exc
                failures.append(f"{model_name}: {exc}")
                logger.warning("model_stream_failed", extra={"event": "model_stream_failed", "model": model_name, "error_code": exc.code})
                continue
            except (ModelProviderError, TimeoutError) as exc:
                if yielded:
                    raise
                failures.append(f"{model_name}: {exc}")
                logger.warning("Streaming model %s failed; trying next configured model", model_name)
        raise ModelProviderError("all configured streaming models failed: " + "; ".join(failures), details={"attempts": failures})