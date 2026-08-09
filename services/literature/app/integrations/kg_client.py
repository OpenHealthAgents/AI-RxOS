from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.observability.metrics import metrics

logger = logging.getLogger(__name__)


class KGClient:
    """Integration boundary with the AI-RxOS Knowledge Graph service (`services/kg`)."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.base_url = self.config.get("kg_service_url", "http://localhost:8001").rstrip("/")
        self.timeout = float(self.config.get("kg_timeout", 5.0))
        self.max_retries = int(self.config.get("kg_max_retries", 1))
        self.backoff_seconds = float(self.config.get("kg_backoff_seconds", 0.25))

    def update_knowledge_graph(self, entities: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> dict[str, Any]:
        """Convert extracted entities and relationships into KG update operations."""
        nodes_payload = [
            {
                "label": e.get("label", "Entity").capitalize(),
                "properties": {
                    "name": e.get("text"),
                    "category": e.get("category"),
                    "source": "literature_service",
                },
            }
            for e in entities
            if e.get("text")
        ]

        edges_payload = [
            {
                "subject": r.get("subject"),
                "predicate": r.get("predicate", "RELATED_TO").upper(),
                "object": r.get("object"),
                "properties": {
                    "confidence": r.get("confidence", 0.8),
                    "evidence": r.get("evidence", ""),
                },
            }
            for r in relationships
            if r.get("subject") and r.get("object")
        ]

        if not nodes_payload and not edges_payload:
            return {"success": True, "updated_nodes": 0, "updated_edges": 0, "status": "no_op"}

        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    res = client.post(f"{self.base_url}/api/v1/graph/import", json={"nodes": nodes_payload, "relationships": edges_payload})
                if res.status_code in (200, 201, 202):
                    metrics.increment("literature.kg_update.success")
                    return {
                        "success": True,
                        "updated_nodes": len(nodes_payload),
                        "updated_edges": len(edges_payload),
                        "status": "completed",
                    }
                if res.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    delay = self.backoff_seconds * (2**attempt)
                    logger.warning("KG update retryable status %s on attempt %d, sleeping %.2fs", res.status_code, attempt + 1, delay)
                    time.sleep(delay)
                    continue
                msg = f"KG service returned status {res.status_code}: {res.text}"
                logger.warning("KG update rejected: %s", msg)
                metrics.increment("literature.kg_update.failure")
                return {"success": False, "error": msg, "retry_eligible": True, "status": "failed"}
            except (httpx.HTTPError, RuntimeError, KeyError, TypeError, ValueError, OSError) as exc:
                if attempt < self.max_retries:
                    delay = self.backoff_seconds * (2**attempt)
                    logger.warning("KG update HTTP failure attempt %d, retrying in %.2fs: %s", attempt + 1, delay, exc)
                    time.sleep(delay)
                    continue
                msg = f"KG service unavailable: {exc}"
                logger.warning(msg)
                metrics.increment("literature.kg_update.failure")
                return {"success": False, "error": msg, "retry_eligible": True, "status": "failed"}

        msg = "KG update did not complete after retries"
        logger.warning(msg)
        metrics.increment("literature.kg_update.failure")
        return {"success": False, "error": msg, "retry_eligible": True, "status": "failed"}
