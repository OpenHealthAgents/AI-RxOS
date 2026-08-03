from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

import httpx

from app.connectors.base import PageResult, SourceConnector, SourceRecord
from app.connectors.http_client import HealthClient, HTTPClient
from app.parsing import parse_document
from app.utils.logging import get_logger

logger = get_logger(__name__)

URL_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)


class CompanyWebsiteConnector(SourceConnector):
    def __init__(self) -> None:
        super().__init__("company_website")
        self.client = HTTPClient(base_url="", headers={"Accept": "text/html"})
        self.health_client = HealthClient(base_url="https://example.com")

    async def health_check(self) -> bool:
        try:
            response = await self.health_client.get("/")
            return response.status_code == 200
        except (httpx.HTTPError, RuntimeError):
            return False

    async def fetch_records(
        self,
        query: str | None = None,
        page_token: str | None = None,
        since: datetime | None = None,
        page_size: int = 50,
    ) -> PageResult:
        if not query or not isinstance(query, str):
            raise ValueError("query must be a valid company website URL")

        url = self._normalize_url(query)
        response = await self.client.get(url, params=None)
        html_text = response.text
        metadata = self._extract_metadata(html_text)
        parsed = self._parse_html_document(html_text)

        record = SourceRecord(
            source=self.source_name,
            source_id=url,
            title=parsed.get("title") or metadata.get("title") or url,
            abstract=parsed.get("abstract")
            or metadata.get("description")
            or self._extract_first_paragraph(html_text),
            authors=parsed.get("authors") or metadata.get("authors") or [],
            published_date=self._parse_date(metadata.get("published_date")),
            doi=None,
            url=url,
            source_updated_at=None,
            extra={"metadata": metadata, "parsed_metadata": parsed},
        )

        return PageResult(items=[record], next_page_token=None)

    def _normalize_url(self, query: str) -> str:
        url = query.strip()
        if not URL_SCHEME_RE.match(url):
            url = "https://" + url.lstrip("/")
        return url

    def _extract_metadata(self, html_text: str) -> dict[str, Any]:
        parser = _HTMLMetadataParser()
        parser.feed(html_text)
        return parser.metadata

    def _parse_html_document(self, html_text: str) -> dict[str, Any]:
        try:
            return parse_document("html", io.BytesIO(html_text.encode("utf-8")))
        except Exception as exc:
            logger.warning(
                "HTML parsing failed for company website connector", exc_info=exc
            )
            return {
                "title": "",
                "authors": [],
                "abstract": "",
                "keywords": [],
                "sections": [],
                "references": [],
                "tables": [],
                "figures": [],
                "supplementary": [],
            }

    def _extract_first_paragraph(self, html_text: str) -> str:
        match = re.search(r"<p[^>]*>(.*?)</p>", html_text, re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        return text

    def _parse_date(self, value: Any) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%d %B %Y", "%B %d, %Y"]:
            try:
                return datetime.strptime(value.strip(), fmt).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue
        return None


class _HTMLMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.metadata: dict[str, Any] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        attrs_dict = {name.lower(): value for name, value in attrs if value is not None}
        name = attrs_dict.get("name") or attrs_dict.get("property")
        content = attrs_dict.get("content") or attrs_dict.get("value")
        if not name or not content:
            return
        key = name.lower().replace("meta:", "")
        if key in {"description", "og:description", "twitter:description"}:
            self.metadata.setdefault("description", content)
        elif key in {"author", "article:author", "og:article:author"}:
            self.metadata.setdefault("authors", []).append(content)
        elif key in {"og:title", "twitter:title", "title"}:
            self.metadata.setdefault("title", content)
        elif key in {
            "article:published_time",
            "publication_date",
            "date",
            "publish_date",
        }:
            self.metadata.setdefault("published_date", content)
        elif key.startswith("citation_"):
            self.metadata[key] = content
