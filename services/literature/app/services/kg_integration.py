from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any

import httpx

from app.core.config import get_settings
from app.observability.metrics import (
    KG_HANDOFF_DURATION_SECONDS,
    KG_HANDOFF_ERRORS_TOTAL,
    KG_HANDOFF_RETRIES_TOTAL,
    KG_HANDOFF_TOTAL,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


class KGIntegrationService:
    """Thin client for publishing literature-derived graph events to the KG service.

    The service translates literature entities and relationships into KG node and
    relationship payloads, then hands them off to the existing KG service. It does
    not implement graph storage, traversal, CRUD, or schema management itself.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = base_url or settings.kg_service_url
        self.timeout_seconds = timeout_seconds or settings.kg_service_timeout_seconds
        self.max_retries = max_retries or settings.kg_service_max_retries
        self.client = client or httpx.Client(timeout=self.timeout_seconds)

    def build_graph_payload(
        self, payload: dict[str, Any], tenant: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dictionary")
        self._validate_payload(payload)

        document_id = str(payload.get("document_id") or "")
        document_title = str(payload.get("document_title") or document_id)
        event_id = str(payload.get("event_id") or self._build_event_id(payload))
        source = str(payload.get("source") or "literature-service")

        nodes: list[dict[str, Any]] = []
        document_node = {
            "id": self._build_uuid(f"document:{document_id}"),
            "label": "Publication",
            "name": document_title,
            "description": f"Literature document {document_id}",
            "source": source,
            "metadata": {
                "document_id": document_id,
                "document_title": document_title,
                "tenant": tenant or {},
            },
        }
        nodes.append(document_node)

        for entity in payload.get("entities", []):
            text = str(entity.get("text") or entity.get("name") or "unknown")
            node_id = self._build_uuid(f"entity:{document_id}:{text}")
            nodes.append(
                {
                    "id": node_id,
                    "label": self._infer_label(entity),
                    "name": text,
                    "description": entity.get("normalized_identifier")
                    or entity.get("ontology_source")
                    or text,
                    "source": source,
                    "metadata": {
                        "document_id": document_id,
                        "entity_text": text,
                        "normalized_identifier": entity.get("normalized_identifier"),
                        "ontology_source": entity.get("ontology_source"),
                        "confidence_score": entity.get("confidence_score"),
                    },
                }
            )

        relationships: list[dict[str, Any]] = []
        entities_payload = payload.get("entities")
        for relationship in payload.get("relationships", []):
            predicate = str(relationship.get("predicate") or "generate")
            source_entity = (
                relationship.get("source_entity")
                or relationship.get("source")
                or relationship.get("subject")
                or None
            )
            target_entity = (
                relationship.get("target_entity")
                or relationship.get("target")
                or relationship.get("object")
                or None
            )
            if (
                source_entity is None
                and isinstance(entities_payload, list)
                and entities_payload
            ):
                first_entity = entities_payload[0]
                if isinstance(first_entity, dict):
                    source_entity = first_entity.get("text")
            if (
                target_entity is None
                and isinstance(entities_payload, list)
                and entities_payload
            ):
                last_entity = entities_payload[-1]
                if isinstance(last_entity, dict):
                    target_entity = last_entity.get("text")
            relationships.append(
                {
                    "id": self._build_uuid(
                        f"relationship:{document_id}:{predicate}:{source_entity or 'unknown'}:{target_entity or 'unknown'}"
                    ),
                    "from_node_id": self._build_uuid(
                        f"entity:{document_id}:{source_entity or text}"
                    ),
                    "to_node_id": self._build_uuid(
                        f"entity:{document_id}:{target_entity or text}"
                    ),
                    "type": self._normalize_relationship_type(predicate),
                    "evidence": relationship.get("evidence") or predicate,
                    "confidence": relationship.get("confidence")
                    or relationship.get("confidence_score"),
                    "source": source,
                    "created_at": None,
                }
            )

        return {
            "event_id": event_id,
            "document_id": document_id,
            "document_title": document_title,
            "nodes": nodes,
            "relationships": relationships,
            "source": source,
        }

    def publish_graph_payload(
        self, payload: dict[str, Any], tenant: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dictionary")
        graph_payload = self.build_graph_payload(payload, tenant=tenant)
        event_id = graph_payload["event_id"]

        start_time = time.perf_counter()
        last_error: Exception | None = None
        attempt = 0
        while attempt < self.max_retries:
            try:
                for node in graph_payload.get("nodes", []):
                    response = self.client.post(
                        f"{self.base_url}/api/v1/graph/nodes", json=node
                    )
                    if self._is_duplicate_error(response):
                        continue
                    response.raise_for_status()
                for relationship in graph_payload.get("relationships", []):
                    response = self.client.post(
                        f"{self.base_url}/api/v1/graph/relationships", json=relationship
                    )
                    if self._is_duplicate_error(response):
                        continue
                    response.raise_for_status()
                KG_HANDOFF_TOTAL.labels(status="success").inc()
                KG_HANDOFF_DURATION_SECONDS.observe(time.perf_counter() - start_time)
                return {
                    "event_id": event_id,
                    "published": True,
                    "status": "published",
                    "metrics": {"retries": attempt, "failures": 0},
                }
            except httpx.HTTPError as exc:
                last_error = exc
                attempt += 1
                if attempt >= self.max_retries:
                    KG_HANDOFF_ERRORS_TOTAL.inc()
                    KG_HANDOFF_TOTAL.labels(status="error").inc()
                    KG_HANDOFF_DURATION_SECONDS.observe(
                        time.perf_counter() - start_time
                    )
                    break
                KG_HANDOFF_RETRIES_TOTAL.inc()
                time.sleep(0.2 * attempt)

        raise (
            RuntimeError(f"Failed to publish graph payload: {last_error}")
            if last_error
            else RuntimeError("Failed to publish graph payload")
        )

    def _validate_payload(self, payload: dict[str, Any]) -> None:
        if not payload.get("document_id"):
            raise ValueError("payload.document_id is required")
        if not isinstance(payload.get("entities", []), list):
            raise ValueError("payload.entities must be a list")  # noqa: TRY004
        if not isinstance(payload.get("relationships", []), list):
            raise ValueError("payload.relationships must be a list")  # noqa: TRY004
        for entity in payload.get("entities", []):
            if not isinstance(entity, dict):
                raise TypeError("each entity entry must be a dictionary")
            if not entity.get("text"):
                raise ValueError("each entity requires text")
        for relationship in payload.get("relationships", []):
            if not isinstance(relationship, dict):
                raise TypeError("each relationship entry must be a dictionary")
            if not relationship.get("predicate"):
                raise ValueError("each relationship requires a predicate")

    def _build_event_id(self, payload: dict[str, Any]) -> str:
        source = f"{payload.get('document_id')}:{payload.get('document_title', '')}"
        return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]

    def _build_uuid(self, value: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, value))

    def _normalize_relationship_type(self, predicate: str) -> str:
        normalized = predicate.strip().upper()
        mapping = {
            "TREATS": "TREATS",
            "TARGETS": "TARGETS",
            "INTERACTS": "INTERACTS",
            "INTERACTS_WITH": "INTERACTS",
            "ASSOCIATED_WITH": "GENERATE",
            "ASSOCIATES_WITH": "GENERATE",
            "RELATES_TO": "GENERATE",
        }
        return mapping.get(normalized, "GENERATE")

    def _infer_label(self, entity: dict[str, Any]) -> str:
        text = str(entity.get("text") or "").lower()
        if "disease" in text or "syndrome" in text:
            return "Disease"
        if "protein" in text or "enzyme" in text:
            return "Protein"
        if "gene" in text:
            return "Gene"
        if "drug" in text or "compound" in text or "molecule" in text:
            return "Drug"
        return "Target"

    def _is_duplicate_error(self, response: httpx.Response) -> bool:
        if response is None:
            return False
        try:
            if response.status_code == 409:
                return True
        except AttributeError:
            return False
        return False
