from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx


_RATE_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0
_PATENT_ID = re.compile(r"^[A-Z]{2}\d[A-Z0-9]+$", re.IGNORECASE)
_PATENT_PATH = re.compile(r"/patent/([A-Z]{2}\d[A-Z0-9]+)(?:/|$)", re.IGNORECASE)


class GooglePatentsConnector:
    """Rate-limited public Google Patents search adapter; it does not infer legal status."""

    source_name = "Google Patents"
    parser_version = "google-patents-xhr-v1"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.base_url = str(config.get("base_url", "https://patents.google.com")).rstrip("/")
        self.timeout = float(config.get("timeout", 15.0))
        self.max_retries = int(config.get("max_retries", 3))
        self.backoff_seconds = float(config.get("backoff_seconds", 0.5))
        self.requests_per_second = float(config.get("requests_per_second", 0.5))
        self.user_agent = str(config.get(
            "user_agent", "AI-RxOS Patent Intelligence/1.0 (+https://ai-rxos.org)"
        ))
        if self.max_retries < 0 or self.requests_per_second <= 0:
            raise ValueError("Google Patents retry and rate settings must be positive")
        self.last_malformed_records: list[dict[str, Any]] = []
        self.last_total_count: int | None = None

    def _pace(self) -> None:
        global _LAST_REQUEST_AT
        interval = 1.0 / self.requests_per_second
        with _RATE_LOCK:
            delay = interval - (time.monotonic() - _LAST_REQUEST_AT)
            if delay > 0:
                time.sleep(delay)
            _LAST_REQUEST_AT = time.monotonic()

    def _get(self, url: str) -> str:
        for attempt in range(self.max_retries + 1):
            self._pace()
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                    response = client.get(url, headers={"User-Agent": self.user_agent})
                response.raise_for_status()
                return response.text
            except httpx.HTTPStatusError as exc:
                retryable = exc.response.status_code == 429 or exc.response.status_code >= 500
                if not retryable or attempt >= self.max_retries:
                    raise
            except httpx.TransportError:
                if attempt >= self.max_retries:
                    raise
            time.sleep(self.backoff_seconds * (2**attempt))
        raise RuntimeError("Google Patents request exhausted retries")

    def _search_url(self, query: str, page: int, page_size: int) -> str:
        search_expression = f"q=({query})&page={page}&num={page_size}"
        return f"{self.base_url}/xhr/query?{urlencode({'url': search_expression, 'exp': ''})}"

    def _fetch_payload(self, query: str, page: int, page_size: int) -> dict[str, Any]:
        body = self._get(self._search_url(query, page, page_size))
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError("Google Patents returned malformed JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), dict):
            raise ValueError("Google Patents response has no results object")
        return payload

    @staticmethod
    def _flatten_results(results: dict[str, Any]) -> list[dict[str, Any]]:
        flattened = []
        for cluster in results.get("cluster", []):
            if not isinstance(cluster, dict):
                continue
            for item in cluster.get("result", []):
                if isinstance(item, dict):
                    flattened.append(item)
        return flattened

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    def _normalize_result(
        self, result: dict[str, Any], query: str
    ) -> dict[str, Any]:
        patent = result.get("patent")
        if not isinstance(patent, dict):
            raise ValueError("Google Patents result has no patent metadata")
        publication_number = str(patent.get("publication_number") or "").strip().upper()
        result_id = str(result.get("id") or "")
        match = _PATENT_PATH.search(result_id)
        source_id = publication_number or (match.group(1).upper() if match else "")
        if not source_id or not _PATENT_ID.fullmatch(source_id):
            raise ValueError("Google Patents result has no valid publication number")
        title = str(patent.get("title") or "").strip()
        if not title:
            raise ValueError("Google Patents result has no title")

        now = datetime.now(timezone.utc)
        url = f"{self.base_url}/patent/{source_id}/en"
        family_metadata = patent.get("family_metadata")
        family_identifier = None
        if isinstance(family_metadata, dict):
            family_identifier = (
                family_metadata.get("family_id")
                or family_metadata.get("family_identifier")
            )
        snippet = patent.get("snippet")
        source_snapshot = dict(result)
        return {
            "source": "patent",
            "source_id": source_id,
            "title": title,
            "abstract": None,
            "content": snippet,
            "authors": self._string_list(patent.get("inventor")),
            "published_date": patent.get("publication_date"),
            "url": url,
            "journal": self.source_name,
            "content_hash": hashlib.sha256(
                json.dumps(
                    source_snapshot, sort_keys=True, ensure_ascii=True, default=str
                ).encode("utf-8")
            ).hexdigest(),
            "retrieved_at": now,
            "raw_payload": source_snapshot,
            "metadata": {
                "source_name": self.source_name,
                "query": query,
                "parser_version": self.parser_version,
                "retrieved_at": now.isoformat(),
                "jurisdiction": source_id[:2],
                "publication_number": source_id,
                "application_number": patent.get("application_number"),
                "grant_number": patent.get("grant_number"),
                "family_identifier": family_identifier,
                "filing_date_source": patent.get("filing_date"),
                "publication_date_source": patent.get("publication_date"),
                "grant_date_source": patent.get("grant_date"),
                "priority_numbers": self._string_list(patent.get("priority_number")),
                "inventors": self._string_list(patent.get("inventor")),
                "assignees": self._string_list(patent.get("assignee")),
                "applicants": self._string_list(patent.get("applicant")),
                "language": patent.get("language"),
                "search_snippet": snippet,
                "search_snippet_is_excerpt": bool(snippet),
                "family_metadata": family_metadata,
                "source_url": url,
            },
        }

    def fetch_page(
        self, query: str, *, page_token: str | None = None, page_size: int = 50
    ) -> tuple[list[dict[str, Any]], str | None]:
        query = query.strip()
        if not query:
            raise ValueError("patent ingestion requires a patent identifier or explicit search query")
        if not 1 <= page_size <= 100:
            raise ValueError("Google Patents page_size must be within 1..100")
        try:
            page = int(page_token or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid persisted Google Patents page checkpoint") from exc
        if page < 0:
            raise ValueError("Google Patents page checkpoint cannot be negative")

        self.last_malformed_records = []
        payload = self._fetch_payload(query, page, page_size)
        results = payload["results"]
        self.last_total_count = results.get("total_num_results")
        total_pages = results.get("total_num_pages")
        if not isinstance(total_pages, int) or total_pages < 1:
            total_pages = 1
        items = self._flatten_results(results)
        records = []
        for index, item in enumerate(items):
            try:
                records.append(self._normalize_result(item, query))
            except (TypeError, ValueError) as exc:
                self.last_malformed_records.append({
                    "source_id": item.get("id"),
                    "error_message": str(exc),
                    "raw_payload": item,
                    "page": page,
                    "record_index": index,
                })
        next_page_token = str(page + 1) if page + 1 < total_pages else None
        return records, next_page_token
