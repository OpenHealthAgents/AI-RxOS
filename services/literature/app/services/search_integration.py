from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.observability.metrics import (
    SEARCH_HANDOFF_DURATION_SECONDS,
    SEARCH_HANDOFF_ERRORS_TOTAL,
    SEARCH_HANDOFF_RETRIES_TOTAL,
    SEARCH_HANDOFF_TOTAL,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


class SearchIntegrationService:
    """Thin client for handing embeddings to the existing Search service.

    This service does not implement vector storage or hybrid search logic itself;
    it submits embedding payloads to the shared Search service API.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = base_url or settings.search_service_url
        self.timeout_seconds = (
            timeout_seconds or settings.search_service_timeout_seconds
        )
        self.max_retries = max_retries or settings.search_service_max_retries
        self.client = httpx.Client(timeout=self.timeout_seconds)

    def submit_embeddings(
        self,
        document_id: str,
        embeddings: list[dict[str, Any]],
        tenant: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not document_id:
            raise ValueError("document_id is required")
        if not embeddings:
            return {
                "document_id": document_id,
                "status": "skipped",
                "upserted": 0,
                "metrics": {"retries": 0, "failures": 0},
            }

        payload = {
            "document_id": document_id,
            "tenant": tenant or {},
            "documents": embeddings,
        }

        last_error: Exception | None = None
        attempt = 0
        start_time = time.perf_counter()
        while attempt < self.max_retries:
            try:
                response = self.client.post(
                    f"{self.base_url}/api/v1/search/index", json=payload
                )
                response.raise_for_status()
                result = response.json()
                SEARCH_HANDOFF_TOTAL.labels(status="success").inc()
                SEARCH_HANDOFF_DURATION_SECONDS.observe(
                    time.perf_counter() - start_time
                )
                return {
                    "document_id": document_id,
                    "status": result.get("status", "ok"),
                    "upserted": result.get("upserted", len(embeddings)),
                    "metrics": {
                        "retries": attempt,
                        "failures": 0,
                    },
                }
            except httpx.HTTPError as exc:
                last_error = exc
                attempt += 1
                if attempt >= self.max_retries:
                    SEARCH_HANDOFF_ERRORS_TOTAL.inc()
                    SEARCH_HANDOFF_TOTAL.labels(status="error").inc()
                    SEARCH_HANDOFF_DURATION_SECONDS.observe(
                        time.perf_counter() - start_time
                    )
                    break
                SEARCH_HANDOFF_RETRIES_TOTAL.inc()
                time.sleep(0.2 * attempt)

        raise (
            RuntimeError(f"Failed to submit embeddings to search service: {last_error}")
            if last_error
            else RuntimeError("Failed to submit embeddings to search service")
        )
