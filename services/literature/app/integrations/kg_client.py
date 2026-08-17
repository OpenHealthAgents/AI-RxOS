from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.knowledge.models import (
    deterministic_entity_id,
    normalize_entity_label,
    normalize_relationship_type,
)
from app.observability.metrics import metrics

logger = logging.getLogger(__name__)


class KGClient:
    """Integration boundary with the AI-RxOS Knowledge Graph service (`services/kg`)."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.base_url = self.config.get("kg_service_url", "http://kg:8083").rstrip("/")
        self.timeout = float(self.config.get("kg_timeout", 5.0))
        self.max_retries = int(self.config.get("kg_max_retries", 1))
        self.backoff_seconds = float(self.config.get("kg_backoff_seconds", 0.25))

    def update_knowledge_graph(self, entities: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> dict[str, Any]:
        """Convert extracted entities and relationships into a KG import request.

        Payload shape matches services/kg/app/schemas/imports.py::ImportJSONRequest
        exactly (flat NodeCreate/RelationshipCreate, not a nested "properties"
        envelope). Entity/relationship ids are derived deterministically (see
        app.knowledge.models.deterministic_entity_id) so the same node id can
        be referenced later from LLM Wiki chunk metadata without a round trip
        to this service. Entities/relationships whose type isn't recognized by
        the KG's label/relationship-type vocabulary are skipped rather than
        sent and rejected as a batch (the KG's schema validation is atomic
        across the whole request body).
        """
        entity_id_by_text: dict[str, str] = {}
        nodes_payload: list[dict[str, Any]] = []
        for e in entities:
            text = e.get("text")
            category = e.get("type") or e.get("category")
            if not text or not category:
                continue
            label = normalize_entity_label(category)
            if not label:
                continue
            entity_id = deterministic_entity_id(category, text)
            entity_id_by_text[text.strip().lower()] = entity_id
            nodes_payload.append(
                {
                    "id": entity_id,
                    "label": label,
                    "name": text,
                    "source": "literature_service",
                    "metadata": {"category": e.get("category")},
                }
            )

        edges_payload: list[dict[str, Any]] = []
        for r in relationships:
            source_text = r.get("source_entity") or r.get("subject")
            target_text = r.get("target_entity") or r.get("object")
            predicate = r.get("predicate")
            if not source_text or not target_text or not predicate:
                continue
            rel_type = normalize_relationship_type(predicate)
            from_id = entity_id_by_text.get(str(source_text).strip().lower())
            to_id = entity_id_by_text.get(str(target_text).strip().lower())
            if not rel_type or not from_id or not to_id:
                continue
            edges_payload.append(
                {
                    "from_node_id": from_id,
                    "to_node_id": to_id,
                    "type": rel_type,
                    "confidence": r.get("confidence"),
                    "source": "literature_service",
                    "evidence": (r.get("provenance") or {}).get("source_sentence"),
                }
            )

        if not nodes_payload and not edges_payload:
            return {
                "success": True,
                "updated_nodes": 0,
                "updated_edges": 0,
                "status": "no_op",
                "entity_id_map": entity_id_by_text,
            }

        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    res = client.post(
                        f"{self.base_url}/api/v1/graph/import/json",
                        json={"nodes": nodes_payload, "relationships": edges_payload},
                    )
                if res.status_code in (200, 201, 202):
                    metrics.increment("literature.kg_update.success")
                    return {
                        "success": True,
                        "updated_nodes": len(nodes_payload),
                        "updated_edges": len(edges_payload),
                        "status": "completed",
                        "entity_id_map": entity_id_by_text,
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
