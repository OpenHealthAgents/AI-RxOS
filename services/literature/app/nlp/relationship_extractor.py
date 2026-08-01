from __future__ import annotations

import time
from typing import Any, ClassVar

from app.observability.metrics import (
    RELATIONSHIP_EXTRACTION_DURATION_SECONDS,
    RELATIONSHIP_EXTRACTION_ERRORS_TOTAL,
    RELATIONSHIP_EXTRACTION_TOTAL,
)


class RelationshipExtractor:
    """Rule-based relationship extraction for Phase 6.

    This phase discovers relationships between entities already extracted in Phase 5.
    It does not generate embeddings or write to Neo4j.
    """

    _predicate_map: ClassVar[dict[tuple[str, str], str]] = {
        ("drug", "disease"): "treats",
        ("gene", "disease"): "associated_with",
        ("protein", "protein"): "interacts_with",
        ("compound", "protein"): "targets",
    }

    def extract(
        self, entities: list[dict[str, Any]], sentence: str
    ) -> list[dict[str, Any]]:
        start_time = time.perf_counter()
        try:
            if not isinstance(entities, list):
                raise TypeError("entities must be a list")
            if not sentence or not isinstance(sentence, str):
                RELATIONSHIP_EXTRACTION_TOTAL.inc()
                return []

            relationships: list[dict[str, Any]] = []
            entity_types = {
                entity.get("type") for entity in entities if isinstance(entity, dict)
            }

            if not entity_types:
                RELATIONSHIP_EXTRACTION_TOTAL.inc()
                return []

            for left_entity in entities:
                if not isinstance(left_entity, dict):
                    continue
                left_type = str(left_entity.get("type", "")).lower()
                left_text = str(left_entity.get("text", ""))
                for right_entity in entities:
                    if not isinstance(right_entity, dict):
                        continue
                    right_type = str(right_entity.get("type", "")).lower()
                    right_text = str(right_entity.get("text", ""))
                    if left_entity is right_entity:
                        continue
                    if (left_type, right_type) not in self._predicate_map:
                        continue
                    predicate = self._predicate_map[(left_type, right_type)]
                    confidence = self._score(
                        left_type, right_type, left_text, right_text
                    )
                    relationships.append(
                        {
                            "source_entity": left_text,
                            "target_entity": right_text,
                            "source_type": left_type,
                            "target_type": right_type,
                            "predicate": predicate,
                            "confidence": round(confidence, 2),
                            "provenance": {
                                "source_sentence": sentence.strip(),
                                "source": "rule-based",
                            },
                        }
                    )

            RELATIONSHIP_EXTRACTION_TOTAL.inc()
            return relationships
        except Exception:
            RELATIONSHIP_EXTRACTION_ERRORS_TOTAL.inc()
            raise
        finally:
            RELATIONSHIP_EXTRACTION_DURATION_SECONDS.observe(
                time.perf_counter() - start_time
            )

    def _score(
        self, left_type: str, right_type: str, left_text: str, right_text: str
    ) -> float:
        base = 0.6
        if left_text and right_text:
            base += 0.1
        if left_type == "drug" and right_type == "disease":
            base += 0.2
        if left_type == "gene" and right_type == "disease":
            base += 0.15
        if left_type == "protein" and right_type == "protein":
            base += 0.15
        if left_type == "compound" and right_type == "protein":
            base += 0.15
        return min(0.99, round(base, 2))
