from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.errors import AIPlatformError
from app.model_registry.schemas import ModelConfig, ModelRequest, ModelResponse


class ModelProviderError(AIPlatformError):
    """A provider failure eligible for registry fallback."""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        provider: str | None = None,
        details: dict[str, Any] | None = None,
        retriable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        safe_details = {"model": model, "provider": provider, **(details or {})}
        if retry_after_seconds is not None:
            safe_details["retry_after_seconds"] = retry_after_seconds
        super().__init__(
            message,
            code="MODEL_PROVIDER_ERROR",
            operation="model_call",
            retriable=retriable,
            details=safe_details,
        )


def retryable_provider_error(error: Exception) -> bool:
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is not None:
        return status_code in {408, 409, 425, 429} or status_code >= 500
    return isinstance(error, (httpx.TimeoutException, httpx.NetworkError))


def retry_after_seconds(error: Exception) -> float | None:
    response = getattr(error, "response", None)
    value = response.headers.get("retry-after") if response is not None else None
    if value is None:
        return None
    try:
        return max(float(value), 0.0)
    except (TypeError, ValueError):
        return None


def provider_error(
    config: ModelConfig, error: Exception, *, operation: str
) -> ModelProviderError:
    return ModelProviderError(
        f"{config.provider}/{config.name} {operation} failed",
        model=config.name,
        provider=config.provider,
        retriable=retryable_provider_error(error),
        retry_after_seconds=retry_after_seconds(error),
    )


class ProviderAdapter:
    def __init__(
        self, config: ModelConfig, client: httpx.AsyncClient | None = None
    ) -> None:
        self.config = config
        self.client = client

    async def complete(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError

    def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        raise NotImplementedError

    def _client(self) -> tuple[httpx.AsyncClient, bool]:
        return (
            self.client or httpx.AsyncClient(timeout=self.config.timeout_seconds),
            self.client is None,
        )

    def _require_api_key(self) -> None:
        if not self.config.api_key:
            raise ModelProviderError(
                f"{self.config.provider}/{self.config.name} credential is not configured",
                model=self.config.name,
                provider=self.config.provider,
                retriable=False,
            )


class OpenAICompatibleAdapter(ProviderAdapter):
    """Adapter for OpenAI and OpenAI-compatible open-source endpoints."""

    def _url(self) -> str:
        base_url = self.config.base_url or "https://api.openai.com/v1"
        return f"{base_url.rstrip('/')}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _payload(self, request: ModelRequest, stream: bool = False) -> dict[str, Any]:
        return {
            "model": self.config.name,
            "messages": request.messages,
            "temperature": request.temperature
            if request.temperature is not None
            else self.config.temperature,
            "max_tokens": request.max_tokens or self.config.max_tokens,
            "stream": stream,
        }

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if self.config.base_url is None:
            self._require_api_key()
        client, close_client = self._client()
        try:
            response = await client.post(
                self._url(), headers=self._headers(), json=self._payload(request)
            )
            response.raise_for_status()
            raw = response.json()
            content = raw["choices"][0]["message"]["content"]
            return ModelResponse(
                model=self.config.name,
                provider=self.config.provider,
                content=content,
                raw=raw,
            )
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise provider_error(self.config, exc, operation="completion") from exc
        finally:
            if close_client:
                await client.aclose()

    async def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        if self.config.base_url is None:
            self._require_api_key()
        client, close_client = self._client()
        try:
            async with client.stream(
                "POST",
                self._url(),
                headers=self._headers(),
                json=self._payload(request, True),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        raw = json.loads(data)
                        content = (
                            raw.get("choices", [{}])[0].get("delta", {}).get("content")
                        )
                    except (json.JSONDecodeError, IndexError, AttributeError) as exc:
                        raise ModelProviderError(
                            f"invalid stream event from {self.config.name}"
                        ) from exc
                    if content:
                        yield content
        except (httpx.HTTPError, ValueError) as exc:
            raise provider_error(self.config, exc, operation="stream") from exc
        finally:
            if close_client:
                await client.aclose()


class AnthropicAdapter(ProviderAdapter):
    def _url(self) -> str:
        return f"{(self.config.base_url or 'https://api.anthropic.com').rstrip('/')}/v1/messages"

    def _payload(self, request: ModelRequest, stream: bool = False) -> dict[str, Any]:
        system_prompts = [
            msg["content"] for msg in request.messages if msg["role"] == "system"
        ]
        non_system_messages = [
            msg for msg in request.messages if msg["role"] != "system"
        ]
        payload: dict[str, Any] = {
            "model": self.config.name,
            "messages": non_system_messages,
            "max_tokens": request.max_tokens or self.config.max_tokens,
            "temperature": request.temperature
            if request.temperature is not None
            else self.config.temperature,
        }
        if system_prompts:
            payload["system"] = "\n\n".join(system_prompts)
        if stream:
            payload["stream"] = True
        return payload

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self._require_api_key()
        client, close_client = self._client()
        try:
            response = await client.post(
                self._url(),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.config.api_key or "",
                    "anthropic-version": "2023-06-01",
                },
                json=self._payload(request),
            )
            response.raise_for_status()
            raw = response.json()
            content = raw["content"][0]["text"]
            return ModelResponse(
                model=self.config.name,
                provider=self.config.provider,
                content=content,
                raw=raw,
            )
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise provider_error(self.config, exc, operation="completion") from exc
        finally:
            if close_client:
                await client.aclose()

    async def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        self._require_api_key()
        client, close_client = self._client()
        try:
            async with client.stream(
                "POST",
                self._url(),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.config.api_key or "",
                    "anthropic-version": "2023-06-01",
                },
                json=self._payload(request, stream=True),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:].strip())
                    except json.JSONDecodeError as exc:
                        raise ModelProviderError(
                            f"invalid stream event from {self.config.name}"
                        ) from exc
                    text = event.get("delta", {}).get("text")
                    if text:
                        yield text
        except (httpx.HTTPError, ValueError) as exc:
            raise provider_error(self.config, exc, operation="stream") from exc
        finally:
            if close_client:
                await client.aclose()


class GoogleAdapter(ProviderAdapter):
    """Adapter for Google's Generative Language API."""

    def _url(self, streaming: bool = False) -> str:
        base_url = (
            self.config.base_url
            or "https://generativelanguage.googleapis.com/v1beta/models"
        )
        operation = "streamGenerateContent?alt=sse" if streaming else "generateContent"
        return f"{base_url.rstrip('/')}/{self.config.name}:{operation}"

    def _headers(self) -> dict[str, str]:
        self._require_api_key()
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self.config.api_key or "",
        }

    def _payload(self, request: ModelRequest) -> dict[str, Any]:
        contents = []
        system_instruction_parts = []
        for message in request.messages:
            if message["role"] == "system":
                system_instruction_parts.append({"text": str(message["content"])})
            else:
                role = "model" if message["role"] == "assistant" else message["role"]
                contents.append(
                    {"role": role, "parts": [{"text": str(message["content"])}]}
                )
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature
                if request.temperature is not None
                else self.config.temperature,
                "maxOutputTokens": request.max_tokens or self.config.max_tokens,
            },
        }
        if system_instruction_parts:
            payload["systemInstruction"] = {"parts": system_instruction_parts}
        return payload

    @staticmethod
    def _content(raw: dict[str, Any]) -> str:
        return raw["candidates"][0]["content"]["parts"][0]["text"]

    async def complete(self, request: ModelRequest) -> ModelResponse:
        client, close_client = self._client()
        try:
            response = await client.post(
                self._url(),
                headers=self._headers(),
                json=self._payload(request),
            )
            response.raise_for_status()
            raw = response.json()
            return ModelResponse(
                model=self.config.name,
                provider=self.config.provider,
                content=self._content(raw),
                raw=raw,
            )
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise provider_error(self.config, exc, operation="completion") from exc
        finally:
            if close_client:
                await client.aclose()

    async def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        client, close_client = self._client()
        try:
            async with client.stream(
                "POST",
                self._url(True),
                headers=self._headers(),
                json=self._payload(request),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        text = self._content(json.loads(line[5:].strip()))
                    except (
                        json.JSONDecodeError,
                        KeyError,
                        IndexError,
                        TypeError,
                    ) as exc:
                        raise ModelProviderError(
                            f"invalid stream event from {self.config.name}"
                        ) from exc
                    if text:
                        yield text
        except (httpx.HTTPError, ValueError) as exc:
            raise provider_error(self.config, exc, operation="stream") from exc
        finally:
            if close_client:
                await client.aclose()


class OpenSourceAdapter(ProviderAdapter):
    """Adapter for self-hosted Hugging Face TGI-compatible endpoints."""

    def _url(self) -> str:
        return (
            f"{(self.config.base_url or 'http://localhost:8080').rstrip('/')}/generate"
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _prompt(self, request: ModelRequest) -> str:
        return "\n".join(
            f"{message['role']}: {message['content']}" for message in request.messages
        )

    def _payload(self, request: ModelRequest, stream: bool = False) -> dict[str, Any]:
        return {
            "inputs": self._prompt(request),
            "parameters": {
                "temperature": request.temperature
                if request.temperature is not None
                else self.config.temperature,
                "max_new_tokens": request.max_tokens or self.config.max_tokens,
            },
            "stream": stream,
        }

    async def complete(self, request: ModelRequest) -> ModelResponse:
        client, close_client = self._client()
        try:
            response = await client.post(
                self._url(),
                headers=self._headers(),
                json=self._payload(request),
            )
            response.raise_for_status()
            raw = response.json()
            content = raw["generated_text"]
            return ModelResponse(
                model=self.config.name,
                provider=self.config.provider,
                content=content,
                raw=raw,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise provider_error(self.config, exc, operation="completion") from exc
        finally:
            if close_client:
                await client.aclose()

    async def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        client, close_client = self._client()
        try:
            async with client.stream(
                "POST",
                self._url(),
                headers=self._headers(),
                json=self._payload(request, True),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        event = json.loads(line.removeprefix("data:").strip())
                    except json.JSONDecodeError as exc:
                        raise ModelProviderError(
                            f"invalid stream event from {self.config.name}"
                        ) from exc
                    text = event.get("token", {}).get("text") or event.get(
                        "generated_text"
                    )
                    if text:
                        yield text
        except (httpx.HTTPError, ValueError) as exc:
            raise provider_error(self.config, exc, operation="stream") from exc
        finally:
            if close_client:
                await client.aclose()


def adapter_for(
    config: ModelConfig, client: httpx.AsyncClient | None = None
) -> ProviderAdapter:
    if config.provider == "anthropic":
        return AnthropicAdapter(config, client)
    if config.provider == "google":
        return GoogleAdapter(config, client)
    if config.provider == "open_source":
        return OpenSourceAdapter(config, client)
    return OpenAICompatibleAdapter(config, client)
