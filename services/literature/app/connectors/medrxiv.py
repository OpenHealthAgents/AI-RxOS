from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.connectors.base import PageResult, SourceConnector, SourceRecord
from app.connectors.http_client import HealthClient, HTTPClient
from app.core.config import get_settings

settings = get_settings()


class MedRxivConnector(SourceConnector):
    def __init__(self) -> None:
        super().__init__("medrxiv")
        self.client = HTTPClient(
            base_url=settings.medrxiv_base_url,
            headers={"Accept": "application/json"},
        )
        self.health_client = HealthClient(base_url=settings.medrxiv_base_url)

    async def health_check(self) -> bool:
        return await self.health_client.health_check(path="/details/medrxiv/0/1")

    async def fetch_records(
        self,
        query: str | None = None,
        page_token: str | None = None,
        since: datetime | None = None,
        page_size: int = 50,
    ) -> PageResult:
        params: dict[str, object] = {
            "format": "json",
            "cursor": page_token or "0",
            "count": page_size,
        }
        if query:
            params["collection"] = query
        if since:
            params["date_from"] = since.strftime("%Y-%m-%d")

        response = await self.client.get("/details/medrxiv", params=params)
        payload = response.json()
        items = payload.get("collection", [])
        next_cursor = payload.get("cursor")
        return PageResult(
            items=[self._normalize(item) for item in items],
            next_page_token=str(next_cursor) if next_cursor is not None else None,
        )

    def _normalize(self, raw: dict[str, Any]) -> SourceRecord:
        return SourceRecord(
            source=self.source_name,
            source_id=str(raw.get("relating_article_id", "")),
            title=raw.get("title", ""),
            abstract=raw.get("abstract", None),
            authors=[
                author.strip()
                for author in raw.get("authors", "").split(";")
                if author.strip()
            ],
            published_date=self._parse_date(raw.get("date")),
            doi=raw.get("doi"),
            url=raw.get("url"),
            source_updated_at=self._parse_date(raw.get("date")),
            extra={"raw": raw},
        )

    def _parse_date(self, value: Any) -> datetime | None:
        if not value:
            return None
        for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S"]:
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
