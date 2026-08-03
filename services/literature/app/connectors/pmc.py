from __future__ import annotations

from datetime import datetime
from typing import Any

from app.connectors.base import PageResult, SourceConnector, SourceRecord
from app.connectors.http_client import HealthClient, HTTPClient
from app.core.config import get_settings

settings = get_settings()


class PubMedCentralConnector(SourceConnector):
    def __init__(self) -> None:
        super().__init__("pmc")
        self.client = HTTPClient(
            base_url=settings.pmc_base_url,
            headers={"Accept": "application/json"},
        )
        self.health_client = HealthClient(base_url="https://api.ncbi.nlm.nih.gov")

    async def health_check(self) -> bool:
        return await self.health_client.health_check(path="/health/ready")

    async def fetch_records(
        self,
        query: str | None = None,
        page_token: str | None = None,
        since: datetime | None = None,
        page_size: int = 50,
    ) -> PageResult:
        params: dict[str, object] = {
            "format": "json",
            "pageSize": page_size,
        }
        if query:
            params["query"] = query
        if page_token:
            params["pageToken"] = page_token
        if since:
            params["lastUpdate"] = since.isoformat()

        response = await self.client.get("/search", params=params)
        payload = response.json()
        return PageResult(
            items=[self._normalize(item) for item in payload.get("items", [])],
            next_page_token=payload.get("nextPageToken"),
        )

    def _normalize(self, raw: dict[str, Any]) -> SourceRecord:
        return SourceRecord(
            source=self.source_name,
            source_id=str(raw.get("uid", "")),
            title=raw.get("title", ""),
            abstract=raw.get("abstractText"),
            authors=[
                author.get("name")
                for author in raw.get("authors", [])
                if author.get("name")
            ],
            published_date=self._parse_date(raw.get("pubDate")),
            doi=raw.get("doi"),
            url=raw.get("url"),
            source_updated_at=self._parse_date(raw.get("lastUpdate")),
            extra={"raw": raw},
        )

    def _parse_date(self, value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
