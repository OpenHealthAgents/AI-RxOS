from __future__ import annotations

import time
from typing import Any

from app.observability.metrics import (
    EVIDENCE_RANKING_DURATION_SECONDS,
    EVIDENCE_RANKING_ERRORS_TOTAL,
    EVIDENCE_RANKING_TOTAL,
)


class EvidenceRankingService:
    """Rank literature-derived evidence records from prior NLP stages.

    The service is intentionally lightweight: it accepts parser + NLP output,
    aggregates confidence, deduplicates overlapping evidence, preserves provenance,
    and returns a structured ranking payload for downstream consumers.
    """

    def __init__(self, strategy: str = "hybrid") -> None:
        self.strategy = strategy

    def rank_evidence(
        self, document: dict[str, Any], nlp_result: dict[str, Any]
    ) -> dict[str, Any]:
        start_time = time.perf_counter()
        if not isinstance(document, dict):
            EVIDENCE_RANKING_ERRORS_TOTAL.inc()
            raise ValueError("document must be a dictionary")  # noqa: TRY004
        if not isinstance(nlp_result, dict):
            EVIDENCE_RANKING_ERRORS_TOTAL.inc()
            raise ValueError("nlp_result must be a dictionary")  # noqa: TRY004

        entities = (
            nlp_result.get("entities") or nlp_result.get("detected_entities") or []
        )
        relationships = nlp_result.get("relationships") or []

        if not entities and not relationships:
            return {
                "document_id": document.get("document_id")
                or document.get("id")
                or "unknown",
                "evidence_items": [],
                "ranking_metrics": {
                    "total_evidence_items": 0,
                    "deduplicated_items": 0,
                    "strategy": self.strategy,
                },
            }

        evidence_items: list[dict[str, Any]] = []
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            evidence_items.append(
                self._build_entity_evidence(document, nlp_result, entity)
            )

        for relationship in relationships:
            if not isinstance(relationship, dict):
                continue
            evidence_items.append(
                self._build_relationship_evidence(document, nlp_result, relationship)
            )

        deduped = self._deduplicate(evidence_items)
        ranked = self._apply_ranking(deduped)

        elapsed = time.perf_counter() - start_time
        EVIDENCE_RANKING_TOTAL.inc()
        EVIDENCE_RANKING_DURATION_SECONDS.observe(elapsed)
        return {
            "document_id": document.get("document_id")
            or document.get("id")
            or "unknown",
            "evidence_items": ranked,
            "ranking_metrics": {
                "total_evidence_items": len(evidence_items),
                "deduplicated_items": len(ranked),
                "strategy": self.strategy,
            },
        }

    def _build_entity_evidence(
        self,
        document: dict[str, Any],
        nlp_result: dict[str, Any],
        entity: dict[str, Any],
    ) -> dict[str, Any]:
        confidence = float(entity.get("confidence_score") or 0.0)
        return {
            "evidence_id": self._build_id(document, entity, "entity"),
            "document_id": document.get("document_id")
            or document.get("id")
            or "unknown",
            "supporting_entities": [
                entity.get("text") or entity.get("name") or "unknown"
            ],
            "supporting_relationships": [],
            "overall_confidence": confidence,
            "ranking_score": self._score(confidence, 0.0, 0.0),
            "provenance": {
                "source_document": document.get("title")
                or document.get("document_id")
                or "unknown",
                "source_sentence": nlp_result.get("sentences", [""])[0]
                if nlp_result.get("sentences")
                else "",
                "ontology_source": entity.get("ontology_source"),
                "normalized_identifier": entity.get("normalized_identifier"),
            },
            "processing_metadata": {
                "evidence_type": "entity",
                "stage": "ranking",
            },
        }

    def _build_relationship_evidence(
        self,
        document: dict[str, Any],
        nlp_result: dict[str, Any],
        relationship: dict[str, Any],
    ) -> dict[str, Any]:
        confidence = float(relationship.get("confidence") or 0.0)
        relation_text = relationship.get("predicate") or "related"
        supporting_entities = [
            relationship.get("source_entity")
            or relationship.get("source")
            or relationship.get("subject")
            or "unknown",
            relationship.get("target_entity")
            or relationship.get("target")
            or relationship.get("object")
            or "unknown",
        ]
        return {
            "evidence_id": self._build_id(document, relationship, "relationship"),
            "document_id": document.get("document_id")
            or document.get("id")
            or "unknown",
            "supporting_entities": supporting_entities,
            "supporting_relationships": [relation_text],
            "overall_confidence": confidence,
            "ranking_score": self._score(confidence, 0.1, 0.1),
            "provenance": {
                "source_document": document.get("title")
                or document.get("document_id")
                or "unknown",
                "source_sentence": relationship.get("provenance", {}).get(
                    "source_sentence"
                )
                if isinstance(relationship.get("provenance"), dict)
                else "",
                "ontology_source": None,
                "normalized_identifier": None,
            },
            "processing_metadata": {
                "evidence_type": "relationship",
                "stage": "ranking",
            },
        }

    def _deduplicate(
        self, evidence_items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        seen = set()
        deduped: list[dict[str, Any]] = []
        for item in evidence_items:
            key = tuple(
                sorted(
                    [
                        str(item.get("evidence_id")),
                        *[str(x) for x in item.get("supporting_entities", [])],
                    ]
                )
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _apply_ranking(
        self, evidence_items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        ranked = sorted(
            evidence_items,
            key=lambda item: item.get("ranking_score", 0.0),
            reverse=True,
        )
        for index, item in enumerate(ranked, start=1):
            item["rank"] = index
        return ranked

    def _score(
        self, confidence: float, entity_boost: float, relationship_boost: float
    ) -> float:
        return round(
            min(1.0, max(0.0, confidence + entity_boost + relationship_boost)), 4
        )

    def _build_id(
        self, document: dict[str, Any], payload: dict[str, Any], evidence_type: str
    ) -> str:
        identifier = f"{document.get('document_id') or document.get('id') or 'unknown'}:{evidence_type}:{payload.get('text') or payload.get('predicate') or payload.get('name') or 'unknown'}"
        return identifier.lower().replace(" ", "-")
