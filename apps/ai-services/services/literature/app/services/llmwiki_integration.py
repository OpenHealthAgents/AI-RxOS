from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.observability.metrics import (
    LLMWIKI_UPDATE_DURATION_SECONDS,
    LLMWIKI_UPDATE_ERRORS_TOTAL,
    LLMWIKI_UPDATE_RETRIES_TOTAL,
    LLMWIKI_UPDATE_TOTAL,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class LLMWikiIntegrationService:
    """Thin client for sending structured literature knowledge to LLM Wiki."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url or settings.llmwiki_service_url
        self.timeout_seconds = (
            timeout_seconds or settings.llmwiki_service_timeout_seconds
        )
        self.max_retries = max_retries or settings.llmwiki_service_max_retries
        self.client = client or httpx.Client(timeout=self.timeout_seconds)

    def update_knowledge(
        self, payload: dict[str, Any], tenant: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dictionary")
        if (
            not payload.get("entities")
            and not payload.get("relationships")
            and not payload.get("summary")
        ):
            raise ValueError(
                "payload must include at least entities, relationships, or summary"
            )

        request_payload = {
            "document_id": str(
                payload.get("document_id") or payload.get("id") or "unknown"
            ),
            "title": payload.get("title") or payload.get("document_title") or None,
            "entities": payload.get("entities") or [],
            "relationships": payload.get("relationships") or [],
            "summary": payload.get("summary") or {},
            "evidence": payload.get("evidence") or [],
            "tenant": tenant or {},
            "source": payload.get("source") or "literature_service",
        }

        start_time = time.perf_counter()
        last_error: Exception | None = None
        attempt = 0
        while attempt < self.max_retries:
            try:
                response = self.client.post(
                    f"{self.base_url}/llmwiki/update", json=request_payload
                )
                response.raise_for_status()
                result = response.json()
                LLMWIKI_UPDATE_TOTAL.labels(status="success").inc()
                LLMWIKI_UPDATE_DURATION_SECONDS.observe(
                    time.perf_counter() - start_time
                )
                return {
                    "document_id": request_payload["document_id"],
                    "status": result.get("status", "ok"),
                    "updated": True,
                    "metrics": {"retries": attempt, "failures": 0},
                }
            except httpx.HTTPError as exc:
                last_error = exc
                attempt += 1
                if attempt >= self.max_retries:
                    LLMWIKI_UPDATE_ERRORS_TOTAL.inc()
                    LLMWIKI_UPDATE_TOTAL.labels(status="error").inc()
                    LLMWIKI_UPDATE_DURATION_SECONDS.observe(
                        time.perf_counter() - start_time
                    )
                    break
                LLMWIKI_UPDATE_RETRIES_TOTAL.inc()
                time.sleep(0.2 * attempt)

        logger.error("LLM Wiki update failed", exc_info=last_error)
        raise RuntimeError(f"Failed to update LLM Wiki: {last_error}") from last_error
