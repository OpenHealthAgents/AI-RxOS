from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from .models import DeadLetterRecord, DeadLetterStatus

logger = logging.getLogger(__name__)


class DeadLetterQueueService:
    """
    Dead-Letter Queue (DLQ) service for unrecoverable or exhausted-retry ingestion failures.
    Ensures zero silent data loss: all failed items are preserved with full diagnostic
    context, error categorization, original payloads, and replay capability.
    """

    def __init__(self) -> None:
        self._records_by_id: Dict[UUID, DeadLetterRecord] = {}

    def enqueue(
        self,
        pipeline_id: str,
        item_id: str,
        source: str,
        payload: dict,
        failure_reason: str,
        failure_category: str,
        stack_trace: Optional[str] = None,
        retry_attempts: int = 0,
    ) -> DeadLetterRecord:
        """Enqueues a failed ingestion item into the Dead-Letter Queue."""
        record = DeadLetterRecord(
            pipeline_id=pipeline_id,
            item_id=str(item_id),
            source=source,
            payload=payload,
            failure_reason=failure_reason,
            failure_category=failure_category,
            stack_trace=stack_trace,
            retry_attempts=retry_attempts,
            status=DeadLetterStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        self._records_by_id[record.id] = record
        logger.error(
            "DLQ Enqueued item %s from source %s (pipeline: %s, category: %s): %s",
            item_id,
            source,
            pipeline_id,
            failure_category,
            failure_reason,
        )
        return record

    def get(self, dlq_id: UUID) -> Optional[DeadLetterRecord]:
        """Retrieves a dead-letter record by its UUID."""
        return self._records_by_id.get(dlq_id)

    def list_records(
        self,
        pipeline_id: Optional[str] = None,
        status: Optional[DeadLetterStatus] = None,
        failure_category: Optional[str] = None,
        limit: int = 100,
    ) -> List[DeadLetterRecord]:
        """Queries dead-letter records filtered by pipeline, status, or category."""
        results: List[DeadLetterRecord] = []
        for record in self._records_by_id.values():
            if pipeline_id and record.pipeline_id != pipeline_id:
                continue
            if status and record.status != status:
                continue
            if failure_category and record.failure_category != failure_category:
                continue
            results.append(record)

        # Sort descending by creation date
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results[:limit]

    def mark_replayed(self, dlq_id: UUID, resolution_note: str = "") -> Optional[DeadLetterRecord]:
        """Marks a dead-letter record as successfully replayed."""
        record = self._records_by_id.get(dlq_id)
        if record:
            record.status = DeadLetterStatus.REPLAYED
            record.resolved_at = datetime.now(timezone.utc)
            record.resolution_note = resolution_note or "Replayed successfully by orchestrator"
        return record

    def resolve(self, dlq_id: UUID, resolution_note: str) -> Optional[DeadLetterRecord]:
        """Marks a dead-letter record as manually resolved."""
        record = self._records_by_id.get(dlq_id)
        if record:
            record.status = DeadLetterStatus.RESOLVED
            record.resolved_at = datetime.now(timezone.utc)
            record.resolution_note = resolution_note
        return record

    def discard(self, dlq_id: UUID, reason: str) -> Optional[DeadLetterRecord]:
        """Discards an invalid or irrecoverable dead-letter record."""
        record = self._records_by_id.get(dlq_id)
        if record:
            record.status = DeadLetterStatus.DISCARDED
            record.resolved_at = datetime.now(timezone.utc)
            record.resolution_note = f"Discarded: {reason}"
        return record

    def count_pending(self, pipeline_id: Optional[str] = None) -> int:
        """Returns the number of pending dead-letter items."""
        return sum(
            1 for r in self._records_by_id.values()
            if r.status == DeadLetterStatus.PENDING and (pipeline_id is None or r.pipeline_id == pipeline_id)
        )

    def clear(self) -> None:
        self._records_by_id.clear()
