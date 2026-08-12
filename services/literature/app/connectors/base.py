from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ConnectorError(Exception):
    pass


class SourceRecord(BaseModel):
    source: str
    source_id: str
    title: str
    abstract: str | None = None
    authors: list[str] = []
    published_date: datetime | None = None
    doi: str | None = None
    url: str | None = None
    source_updated_at: datetime | None = None
    extra: dict[str, object] = {}


class PageResult(BaseModel):
    items: list[SourceRecord]
    next_page_token: str | None = None


class SourceConnector(ABC):
    source_name: str

    def __init__(self, source_name: str):
        self.source_name = source_name

    @abstractmethod
    async def health_check(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def fetch_records(
        self,
        query: str | None = None,
        page_token: str | None = None,
        since: datetime | None = None,
        page_size: int = 50,
    ) -> PageResult:
        raise NotImplementedError


class BaseConnector:
    """Base class for Prompt 6 source connectors in sources.py."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.name = "base"
        self.timeout = float(self.config.get("timeout", 5.0))
        self.max_retries = int(self.config.get("max_retries", 3))
        self.backoff_seconds = float(self.config.get("backoff_seconds", 0.5))
        self.user_agent = self.config.get("user_agent", "AI-RxOS-Literature-Agent/1.0")

    def connect(self) -> dict[str, Any]:
        return {"connected": True}

    def get_limitation(self) -> str | None:
        return None

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = kwargs.setdefault("headers", {})
        headers.setdefault("User-Agent", self.user_agent)

        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp
            except (httpx.HTTPError, httpx.RequestError) as exc:
                if attempt >= self.max_retries:
                    logger.warning("HTTP request failed after %d retries: %s", attempt, exc)
                    raise
                delay = self.backoff_seconds * (2**attempt)
                logger.info("Request failed, retrying in %.2fs: %s", delay, exc)
                time.sleep(delay)
        raise RuntimeError("Request failed")

    def _request_json(self, url: str, **kwargs: Any) -> dict[str, Any] | None:
        try:
            resp = self._request("GET", url, **kwargs)
            return resp.json()
        except Exception as exc:
            logger.warning("Failed to fetch JSON from %s: %s", url, exc)
            return None

    def _request_text(self, url: str, **kwargs: Any) -> str | None:
        try:
            resp = self._request("GET", url, **kwargs)
            return resp.text
        except Exception as exc:
            logger.warning("Failed to fetch text from %s: %s", url, exc)
            return None

    def normalize_document(self, doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": doc.get("title") or "Untitled Document",
            "abstract": doc.get("abstract") or "",
            "content": doc.get("content") or doc.get("abstract") or "",
            "authors": doc.get("authors") or [],
            "published_date": doc.get("published_date"),
            "source": doc.get("source"),
            "source_id": doc.get("source_id"),
            "doi": doc.get("doi"),
            "url": doc.get("url"),
            "journal": doc.get("journal"),
            "metadata": doc.get("metadata") or {},
        }

    def _extract_html_title(self, html_content: str) -> str | None:
        if not html_content:
            return None
        m = re.search(r"<title>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
        if m:
            import html
            return html.unescape(m.group(1)).strip()
        return None

    def _html_to_text(self, html_content: str) -> str:
        if not html_content:
            return ""
        text = re.sub(r"<(script|style).*?>.*?</\1>", "", html_content, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        import html
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

