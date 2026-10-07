from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set, Tuple


class IngestionDeduplicator:
    """
    Idempotent deduplication engine for ingestion pipelines.
    Computes cryptographic fingerprints across payloads to prevent redundant
    expensive LLM extraction, vector embedding, and database writes.
    """

    def __init__(self) -> None:
        # Map: composite_key -> content_hash
        self._seen_items: Dict[str, str] = {}
        # Set of active content hashes
        self._hash_set: Set[str] = set()
        self._dedup_counts: Dict[str, int] = {}

    @classmethod
    def compute_content_hash(
        cls,
        source: str,
        item_id: str,
        payload: Dict[str, Any],
    ) -> str:
        """Computes a deterministic SHA-256 content hash of the payload and identity."""
        hasher = hashlib.sha256()
        hasher.update(source.strip().lower().encode("utf-8"))
        hasher.update(str(item_id).strip().upper().encode("utf-8"))

        # Serialize payload deterministically with sorted keys
        try:
            serialized = json.dumps(payload, sort_keys=True, default=str)
        except Exception:
            serialized = str(sorted(payload.items()))
        hasher.update(serialized.encode("utf-8"))
        return hasher.hexdigest()

    def is_duplicate(
        self,
        pipeline_id: str,
        item_id: str,
        payload: Dict[str, Any],
        source: str = "",
    ) -> Tuple[bool, str]:
        """
        Checks whether an item is a duplicate.
        Returns: (is_duplicate: bool, content_hash: str)
        """
        composite_key = f"{pipeline_id}:{str(item_id).strip().upper()}"
        content_hash = self.compute_content_hash(source=source or pipeline_id, item_id=item_id, payload=payload)

        existing_hash = self._seen_items.get(composite_key)
        if existing_hash is not None and existing_hash == content_hash:
            return True, content_hash

        # Also check global hash collision for exact duplicate payload across identical pipeline
        pipeline_hash_key = f"{pipeline_id}::{content_hash}"
        if pipeline_hash_key in self._hash_set:
            return True, content_hash

        return False, content_hash

    def register(
        self,
        pipeline_id: str,
        item_id: str,
        payload: Dict[str, Any],
        source: str = "",
    ) -> str:
        """Registers a processed item hash into the deduplication store."""
        composite_key = f"{pipeline_id}:{str(item_id).strip().upper()}"
        content_hash = self.compute_content_hash(source=source or pipeline_id, item_id=item_id, payload=payload)
        self._seen_items[composite_key] = content_hash
        self._hash_set.add(f"{pipeline_id}::{content_hash}")
        return content_hash

    def record_duplicate(self, pipeline_id: str) -> None:
        self._dedup_counts[pipeline_id] = self._dedup_counts.get(pipeline_id, 0) + 1

    def get_duplicate_count(self, pipeline_id: str) -> int:
        return self._dedup_counts.get(pipeline_id, 0)

    def clear(self) -> None:
        self._seen_items.clear()
        self._hash_set.clear()
        self._dedup_counts.clear()
