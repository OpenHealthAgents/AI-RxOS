from __future__ import annotations

import asyncio
from datetime import datetime

from app.connectors.base import PageResult, SourceConnector, SourceRecord
from app.connectors.http_client import HealthClient
from app.connectors.sources import ClinicalTrialsConnector as ClinicalTrialsAPIConnector
from app.core.config import get_settings


class ClinicalTrialsConnector(SourceConnector):
    """Async Literature connector facade over the shared ClinicalTrials v2 adapter."""

    def __init__(self) -> None:
        super().__init__("clinicaltrials")
        settings = get_settings()
        self.client = ClinicalTrialsAPIConnector({
            "base_url": settings.clinicaltrials_base_url,
            "timeout": settings.clinicaltrials_timeout,
            "max_retries": settings.clinicaltrials_max_retries,
            "backoff_seconds": settings.clinicaltrials_backoff_seconds,
            "requests_per_second": settings.clinicaltrials_requests_per_second,
        })
        self.health_client = HealthClient(base_url="https://clinicaltrials.gov")

    async def health_check(self) -> bool:
        return await self.health_client.health_check(path="/api/info")

    async def fetch_records(
        self,
        query: str | None = None,
        page_token: str | None = None,
        since: datetime | None = None,
        page_size: int = 50,
    ) -> PageResult:
        if since is not None:
            raise ValueError("ClinicalTrials v2 ingestion does not accept a since filter")
        items, next_page_token = await asyncio.to_thread(
            self.client.fetch_page,
            query or "",
            page_token=page_token,
            page_size=page_size,
        )
        return PageResult(
            items=[
                SourceRecord(
                    source=self.source_name,
                    source_id=item["nct_id"],
                    title=item["title"],
                    abstract=item.get("abstract"),
                    authors=[],
                    published_date=None,
                    url=item["url"],
                    extra={
                        **item["metadata"],
                        "raw_payload": item["raw_payload"],
                        "content_hash": item["content_hash"],
                    },
                )
                for item in items
            ],
            next_page_token=next_page_token,
        )
