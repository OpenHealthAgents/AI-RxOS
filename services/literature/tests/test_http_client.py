import httpx
import pytest

from app.connectors.http_client import HTTPClient


class DummyTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    async def handle_async_request(self, request):
        resp = self.responses[self.calls]
        self.calls += 1
        return resp


@pytest.mark.asyncio
async def test_http_client_retries_on_429_and_succeeds():
    responses = [
        httpx.Response(429, json={"error": "rate limit"}),
        httpx.Response(200, json={"ok": True}),
    ]
    client = HTTPClient(base_url="https://example.com")
    client._client._transport = DummyTransport(responses)

    response = await client.get("/test")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_http_client_fails_after_max_retries():
    responses = [
        httpx.Response(503, json={"error": "service unavailable"}),
        httpx.Response(503, json={"error": "service unavailable"}),
        httpx.Response(503, json={"error": "service unavailable"}),
    ]
    client = HTTPClient(base_url="https://example.com")
    client._client._transport = DummyTransport(responses)

    with pytest.raises(httpx.HTTPStatusError):
        await client.get("/test")
