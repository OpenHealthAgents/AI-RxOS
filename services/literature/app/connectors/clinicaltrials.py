from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.connectors.base import PageResult, SourceConnector, SourceRecord
from app.connectors.http_client import HealthClient, HTTPClient
from app.core.config import get_settings

settings = get_settings()


class ClinicalTrialsConnector(SourceConnector):
    def __init__(self) -> None:
        super().__init__("clinicaltrials")
        self.client = HTTPClient(
            base_url=settings.clinicaltrials_base_url,
            headers={"Accept": "application/json"},
        )
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
        params: dict[str, object] = {
            "fmt": "json",
            "min_rnk": 1,
            "max_rnk": page_size,
        }
        if query:
            params["expr"] = query
        if page_token:
            params["min_rnk"] = int(page_token)
            params["max_rnk"] = int(page_token) + page_size - 1
        if since:
            params["lastupdatefrom"] = since.strftime("%Y-%m-%d")

        response = await self.client.get("/study_fields", params=params)
        payload = response.json()
        fields = payload.get("StudyFieldsResponse", {}).get("StudyFields", [])
        next_token = None
        if fields and len(fields) == page_size:
            next_token = str(int(page_token or "1") + page_size)

        return PageResult(
            items=[self._normalize(item) for item in fields],
            next_page_token=next_token,
        )

    def _normalize(self, raw: dict[str, Any]) -> SourceRecord:
        return SourceRecord(
            source=self.source_name,
            source_id=str(raw.get("NCTId", [""])[0]),
            title=(raw.get("BriefTitle", [""])[0] if raw.get("BriefTitle") else ""),
            abstract=(
                raw.get("BriefSummary", [""])[0] if raw.get("BriefSummary") else None
            ),
            authors=[],
            published_date=self._parse_date(
                raw.get("StartDate", [""])[0] if raw.get("StartDate") else None
            ),
            doi=None,
            url=f"https://clinicaltrials.gov/study/{raw.get('NCTId', [''])[0]}",
            source_updated_at=self._parse_date(
                raw.get("LastUpdatePostDate", [""])[0]
                if raw.get("LastUpdatePostDate")
                else None
            ),
            extra={"raw": raw},
        )

    def _parse_date(self, value: Any) -> datetime | None:
        if not value:
            return None
        for fmt in ["%B %d, %Y", "%Y-%m-%d"]:
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
