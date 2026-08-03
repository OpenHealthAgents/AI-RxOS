from __future__ import annotations

import asyncio

import httpx

from app.core.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class HTTPClient:
    def __init__(
        self, base_url: str, timeout: int = 30, headers: dict[str, str] | None = None
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = headers or {}
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout, headers=self.headers
        )

    async def get(
        self,
        path: str,
        params: dict[str, object] | list[tuple[str, object]] | None = None,
    ) -> httpx.Response:
        return await self._request("GET", path, params=params)

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, object] | list[tuple[str, object]] | None = None,
    ) -> httpx.Response:
        request_params: (
            dict[str, str | int | float | bool | None]
            | list[tuple[str, str | int | float | bool | None]]
            | None
        ) = None
        if params is not None:
            if isinstance(params, dict):
                request_params = {}
                for key, value in params.items():
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        request_params[key] = value
                    else:
                        request_params[key] = str(value)
            else:
                request_params = [
                    (
                        key,
                        value
                        if isinstance(value, (str, int, float, bool)) or value is None
                        else str(value),
                    )
                    for key, value in params
                ]

        attempt = 0
        backoff = 0.5
        while True:
            attempt += 1
            try:
                response = await self._client.request(
                    method, path, params=request_params
                )
                response.raise_for_status()
                return response
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                if attempt >= 3 or not self._retryable(exc):
                    logger.error(
                        "HTTP request failed",
                        exc_info=exc,
                        extra={"method": method, "path": path, "params": params},
                    )
                    raise
                await asyncio.sleep(backoff)
                backoff *= 2

    def _retryable(self, exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            return status in {429, 500, 502, 503, 504}
        return True

    async def close(self) -> None:
        await self._client.aclose()


class HealthClient(HTTPClient):
    async def health_check(self, path: str = "/") -> bool:
        try:
            response = await self.get(path)
            return response.status_code == 200
        except httpx.HTTPError:
            return False
