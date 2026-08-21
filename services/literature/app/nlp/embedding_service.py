from __future__ import annotations

import hashlib
import math
import time
from typing import Any

from app.observability.metrics import (
    EMBEDDING_GENERATION_DURATION_SECONDS,
    EMBEDDING_GENERATION_ERRORS_TOTAL,
    EMBEDDING_GENERATION_TOTAL,
)


class EmbeddingService:
    """Generate deterministic vector embeddings for normalized document content.

    This phase only produces vectors and packaging metadata. It does not write to
    PostgreSQL, call the search service, or update Neo4j.
    """

    def __init__(self, batch_size: int = 8) -> None:
        self.batch_size = max(1, batch_size)

    def generate_embeddings(self, nlp_result: dict[str, Any]) -> dict[str, Any]:
        start_time = time.perf_counter()
        try:
            if not isinstance(nlp_result, dict):
                raise TypeError("nlp_result must be a dictionary")

            document_id = nlp_result.get("document_id") or "unknown"
            text_items: list[str] = []

            if nlp_result.get("sentences"):
                text_items.extend(
                    [
                        str(sentence)
                        for sentence in nlp_result.get("sentences", [])
                        if str(sentence).strip()
                    ]
                )
            if nlp_result.get("detected_entities"):
                text_items.extend(
                    [
                        f"{entity.get('text')}:{entity.get('type')}"
                        for entity in nlp_result.get("detected_entities", [])
                        if isinstance(entity, dict)
                    ]
                )
            if nlp_result.get("relationships"):
                text_items.extend(
                    [
                        f"{relationship.get('source_entity')}:{relationship.get('predicate')}:{relationship.get('target_entity')}"
                        for relationship in nlp_result.get("relationships", [])
                        if isinstance(relationship, dict)
                    ]
                )

            batches = self._create_batches(text_items)
            generated_vectors = []
            for batch in batches:
                generated_vectors.extend([self._vectorize_text(item) for item in batch])

            elapsed = time.perf_counter() - start_time
            elapsed_ms = round(elapsed * 1000, 2)
            EMBEDDING_GENERATION_TOTAL.inc()
            EMBEDDING_GENERATION_DURATION_SECONDS.observe(elapsed)
            return {
                "document_id": document_id,
                "embedding_batches": batches,
                "embeddings": generated_vectors,
                "embedding_count": len(generated_vectors),
                "metadata": {
                    "source": "EmbeddingService",
                    "embedding_dimensions": len(generated_vectors[0])
                    if generated_vectors
                    else 16,
                    "batch_size": self.batch_size,
                    "text_source_count": len(text_items),
                },
                "processing_metrics": {
                    "total_processing_time_ms": elapsed_ms,
                    "batch_count": len(batches),
                    "failed_batches": 0,
                    "retries": 0,
                },
            }
        except Exception:
            EMBEDDING_GENERATION_ERRORS_TOTAL.inc()
            raise

    def embed_text(self, text: str) -> list[float]:
        """Public entry point for embedding a single arbitrary string (e.g. a chunk)."""
        return self._vectorize_text(text)

    def _create_batches(self, items: list[str]) -> list[list[str]]:
        batches: list[list[str]] = []
        for index in range(0, len(items), self.batch_size):
            batches.append(items[index : index + self.batch_size])
        return batches

    def _vectorize_text(self, text: str) -> list[float]:
        normalized = (text or "").strip().lower()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        seed = int(digest[:8], 16)
        vector: list[float] = []
        for index in range(16):
            value = math.sin((index + 1) * (seed % 97 + 1)) + math.cos(
                (index + 1) * 0.25
            )
            vector.append(round(value, 6))
        return vector
