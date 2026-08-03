import pytest

from app.connectors.company_website import CompanyWebsiteConnector


class _DummyResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


@pytest.mark.asyncio
async def test_company_website_health_check_returns_true_when_endpoint_is_reachable(monkeypatch):
    connector = CompanyWebsiteConnector()

    async def fake_get(path: str, params=None):
        assert path == "/"
        return _DummyResponse(200)

    monkeypatch.setattr(connector.health_client, "get", fake_get)

    assert await connector.health_check() is True


@pytest.mark.asyncio
async def test_company_website_health_check_returns_false_when_endpoint_is_unreachable(monkeypatch):
    connector = CompanyWebsiteConnector()

    async def fake_get(path: str, params=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(connector.health_client, "get", fake_get)

    assert await connector.health_check() is False
