from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import UUID

from .dedup import IngestionDeduplicator
from .dlq import DeadLetterQueueService
from .models import (
    DeadLetterRecord,
    DeadLetterStatus,
    IngestionItem,
    IngestionPipeline,
    IngestionRunRecord,
    IngestionRunStatus,
    IngestionTelemetry,
    PipelineSchedule,
    PipelineStatus,
    QualityValidationStatus,
    RetryPolicy,
    Watermark,
)
from .quality import IngestionDataQualityValidator
from .retry import IngestionRetryExecutor

logger = logging.getLogger(__name__)


# Type aliases for pipeline callbacks
# Fetcher: (watermark_timestamp: Optional[datetime], limit: int) -> Awaitable[List[IngestionItem]]
FetcherCallback = Callable[[Optional[datetime], int], Awaitable[List[IngestionItem]]]
# Processor: (item: IngestionItem) -> Awaitable[Any]
ProcessorCallback = Callable[[IngestionItem], Awaitable[Any]]


class AsyncIngestionOrchestrator:
    """
    Production-grade asynchronous ingestion orchestration engine providing:
    - Scheduled ingestion & interval triggers
    - Incremental updates & high-watermark tracking
    - Exponential backoff retry with jitter
    - Dead-letter queue (DLQ) isolation with zero silent data loss
    - Content hash deduplication
    - Comprehensive observability metrics & execution audit logs
    - Ingestion data-quality validation gates
    """

    def __init__(
        self,
        dlq_service: Optional[DeadLetterQueueService] = None,
        deduplicator: Optional[IngestionDeduplicator] = None,
    ) -> None:
        self.dlq = dlq_service or DeadLetterQueueService()
        self.deduplicator = deduplicator or IngestionDeduplicator()

        self._pipelines: Dict[str, IngestionPipeline] = {}
        self._fetchers: Dict[str, FetcherCallback] = {}
        self._processors: Dict[str, ProcessorCallback] = {}
        self._runs_by_id: Dict[UUID, IngestionRunRecord] = {}
        self._runs_by_pipeline: Dict[str, List[UUID]] = {}
        self._lock = asyncio.Lock()

        # Seed reference pipelines
        self._bootstrap_default_pipelines()

    def _bootstrap_default_pipelines(self) -> None:
        """Initializes default reference pipelines for primary evidence sources."""
        now = datetime.now(timezone.utc)
        defaults = [
            ("pubmed", "PubMed Oncology Evidence Ingestion", "PubMed", 3600),
            ("clinicaltrials", "ClinicalTrials.gov Protocol & Status Ingestion", "ClinicalTrials.gov", 7200),
            ("regulatory", "FDA/EMA Regulatory Decisions & Approvals", "Regulatory", 14400),
            ("patents", "USPTO/EPO Patent Intelligence & Claims Ingestion", "Patents", 86400),
            ("company_events", "Public Company Events & Deals Ingestion", "CorporateFilings", 43200),
        ]
        for pid, name, source, interval in defaults:
            pipe = IngestionPipeline(
                id=pid,
                name=name,
                source_name=source,
                schedule=PipelineSchedule(
                    interval_seconds=interval,
                    is_enabled=True,
                    next_run_at=now + timedelta(seconds=interval),
                ),
                retry_policy=RetryPolicy(max_retries=3, initial_backoff_seconds=0.2, max_backoff_seconds=5.0),
                watermark=Watermark(pipeline_id=pid, updated_at=now),
                status=PipelineStatus.IDLE,
                created_at=now,
                updated_at=now,
            )
            self._pipelines[pid] = pipe

    # ==========================================================================
    # Pipeline Management
    # ==========================================================================

    def register_pipeline(
        self,
        pipeline: IngestionPipeline,
        fetcher: Optional[FetcherCallback] = None,
        processor: Optional[ProcessorCallback] = None,
    ) -> IngestionPipeline:
        """Registers a pipeline with optional custom fetcher and processor callbacks."""
        self._pipelines[pipeline.id] = pipeline
        if fetcher:
            self._fetchers[pipeline.id] = fetcher
        if processor:
            self._processors[pipeline.id] = processor
        return pipeline

    def get_pipeline(self, pipeline_id: str) -> Optional[IngestionPipeline]:
        return self._pipelines.get(pipeline_id)

    def list_pipelines(self) -> List[IngestionPipeline]:
        return list(self._pipelines.values())

    def update_pipeline_schedule(
        self,
        pipeline_id: str,
        schedule: PipelineSchedule,
    ) -> IngestionPipeline:
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            raise KeyError(f"Pipeline '{pipeline_id}' not found.")
        pipeline.schedule = schedule
        if schedule.interval_seconds and not schedule.next_run_at:
            pipeline.schedule.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=schedule.interval_seconds)
        pipeline.updated_at = datetime.now(timezone.utc)
        return pipeline

    # ==========================================================================
    # Scheduling & Execution Loop
    # ==========================================================================

    async def run_scheduled_due(self) -> List[IngestionRunRecord]:
        """
        Evaluates active pipeline schedules and triggers any runs that are currently due.
        """
        now = datetime.now(timezone.utc)
        due_runs: List[IngestionRunRecord] = []

        for pipe in self._pipelines.values():
            if not pipe.schedule.is_enabled:
                continue
            if pipe.status == PipelineStatus.RUNNING:
                continue

            is_due = False
            if pipe.schedule.next_run_at and pipe.schedule.next_run_at <= now:
                is_due = True
            elif pipe.schedule.interval_seconds and not pipe.schedule.next_run_at:
                is_due = True

            if is_due:
                logger.info("Triggering scheduled run for pipeline: %s", pipe.id)
                run_record = await self.trigger_pipeline_run(
                    pipeline_id=pipe.id,
                    incremental=True,
                    triggered_by="SCHEDULED",
                )
                due_runs.append(run_record)

                # Advance next run
                if pipe.schedule.interval_seconds:
                    pipe.schedule.next_run_at = now + timedelta(seconds=pipe.schedule.interval_seconds)
                else:
                    pipe.schedule.next_run_at = now + timedelta(hours=24)

        return due_runs

    # ==========================================================================
    # Core Pipeline Run Execution
    # ==========================================================================

    async def trigger_pipeline_run(
        self,
        pipeline_id: str,
        incremental: bool = True,
        triggered_by: str = "MANUAL",
        items_override: Optional[List[IngestionItem]] = None,
        fetcher_override: Optional[FetcherCallback] = None,
        processor_override: Optional[ProcessorCallback] = None,
    ) -> IngestionRunRecord:
        """
        Executes an ingestion run for a pipeline.
        Enforces strict invariant: NO INGESTION PIPELINE SHOULD SILENTLY FAIL.
        All exceptions are caught, logged, accounted for, and surfaced in the run status.
        """
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            raise KeyError(f"Pipeline '{pipeline_id}' not found.")

        # Create initial run record
        run = IngestionRunRecord(
            pipeline_id=pipeline_id,
            triggered_by=triggered_by,
            status=IngestionRunStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            watermark_start=pipeline.watermark.last_processed_timestamp,
            telemetry=IngestionTelemetry(),
        )
        self._runs_by_id[run.id] = run
        self._runs_by_pipeline.setdefault(pipeline_id, []).append(run.id)

        pipeline.status = PipelineStatus.RUNNING
        pipeline.updated_at = datetime.now(timezone.utc)

        start_time = asyncio.get_event_loop().time()

        try:
            # 1. Fetch items
            fetcher = fetcher_override or self._fetchers.get(pipeline_id)
            processor = processor_override or self._processors.get(pipeline_id)

            watermark_ts = pipeline.watermark.last_processed_timestamp if incremental else None

            if items_override is not None:
                items = items_override
            elif fetcher:
                items = await fetcher(watermark_ts, 100)
            else:
                # Default empty fetch if no callback is registered
                items = []

            run.telemetry.items_fetched = len(items)
            max_seen_timestamp: Optional[datetime] = None

            # 2. Process each item through Quality Gate, Deduplication, and Retry Processor
            for item in items:
                run.telemetry.items_processed += 1

                # A. Data-Quality Validation Gate
                quality_report = IngestionDataQualityValidator.validate_item(
                    item=item,
                    strict_mode=pipeline.quality_gate_strict,
                )
                run.quality_reports.append(quality_report.model_dump())

                if quality_report.has_errors and pipeline.quality_gate_strict:
                    # Quality gate failure -> route directly to DLQ
                    reason = "; ".join(i.message for i in quality_report.issues if i.severity == "ERROR")
                    self.dlq.enqueue(
                        pipeline_id=pipeline_id,
                        item_id=item.item_id,
                        source=item.source,
                        payload=item.payload,
                        failure_reason=f"Data Quality Validation Failed: {reason}",
                        failure_category="QUALITY_VALIDATION_ERROR",
                    )
                    run.telemetry.items_failed += 1
                    run.telemetry.items_dead_lettered += 1
                    run.telemetry.error_summary["QUALITY_VALIDATION_ERROR"] = (
                        run.telemetry.error_summary.get("QUALITY_VALIDATION_ERROR", 0) + 1
                    )
                    continue

                # B. Content Hash Deduplication Gate
                is_dup, c_hash = self.deduplicator.is_duplicate(
                    pipeline_id=pipeline_id,
                    item_id=item.item_id,
                    payload=item.payload,
                    source=item.source,
                )
                if is_dup:
                    run.telemetry.items_deduplicated += 1
                    self.deduplicator.record_duplicate(pipeline_id)
                    continue

                # C. Processing with Exponential Backoff Retry
                item_success = False
                retry_attempts_used = 0

                if processor:
                    try:
                        def on_retry(att: int, exc: Exception, delay: float) -> None:
                            nonlocal retry_attempts_used
                            retry_attempts_used = att
                            run.telemetry.items_retried += 1

                        await IngestionRetryExecutor.execute_with_retry(
                            processor,
                            item,
                            policy=pipeline.retry_policy,
                            on_retry_callback=on_retry,
                        )
                        item_success = True
                    except Exception as item_err:
                        # Processing exhausted retries or failed fatally
                        logger.error(
                            "Pipeline %s item %s processing failed after %d retries: %s",
                            pipeline_id,
                            item.item_id,
                            retry_attempts_used,
                            item_err,
                        )
                        self.dlq.enqueue(
                            pipeline_id=pipeline_id,
                            item_id=item.item_id,
                            source=item.source,
                            payload=item.payload,
                            failure_reason=str(item_err),
                            failure_category=type(item_err).__name__,
                            stack_trace=traceback.format_exc(),
                            retry_attempts=retry_attempts_used,
                        )
                        run.telemetry.items_failed += 1
                        run.telemetry.items_dead_lettered += 1
                        cat = type(item_err).__name__
                        run.telemetry.error_summary[cat] = run.telemetry.error_summary.get(cat, 0) + 1
                else:
                    # No-op processor succeeds by default
                    item_success = True

                if item_success:
                    run.telemetry.items_succeeded += 1
                    self.deduplicator.register(
                        pipeline_id=pipeline_id,
                        item_id=item.item_id,
                        payload=item.payload,
                        source=item.source,
                    )
                    # Track incremental watermark progress
                    item_dt = item.timestamp
                    if item_dt:
                        if max_seen_timestamp is None or item_dt > max_seen_timestamp:
                            max_seen_timestamp = item_dt

            # 3. Update High-Watermark (Only if items succeeded or at least progress made)
            if max_seen_timestamp:
                pipeline.watermark.last_processed_timestamp = max_seen_timestamp
                pipeline.watermark.high_watermark_value = max_seen_timestamp.isoformat()
                pipeline.watermark.updated_at = datetime.now(timezone.utc)
                run.watermark_end = max_seen_timestamp

            # 4. Resolve Overall Run Status
            if run.telemetry.items_failed == 0:
                run.status = IngestionRunStatus.COMPLETED
            elif run.telemetry.items_succeeded > 0:
                run.status = IngestionRunStatus.PARTIAL_SUCCESS
            else:
                run.status = IngestionRunStatus.FAILED

        except Exception as pipe_err:
            # Fatal unhandled pipeline crash
            logger.critical("Fatal unhandled exception in pipeline %s: %s", pipeline_id, pipe_err)
            run.status = IngestionRunStatus.FAILED
            run.error_message = f"Fatal pipeline failure: {pipe_err}"
            pipeline.status = PipelineStatus.ERROR
        finally:
            end_time = asyncio.get_event_loop().time()
            run.telemetry.duration_seconds = round(end_time - start_time, 4)
            run.completed_at = datetime.now(timezone.utc)

            if pipeline.status != PipelineStatus.ERROR:
                pipeline.status = PipelineStatus.IDLE
            pipeline.updated_at = datetime.now(timezone.utc)

        return run

    # ==========================================================================
    # Dead-Letter Replay
    # ==========================================================================

    async def replay_dead_letter(self, dlq_id: UUID) -> IngestionRunRecord:
        """
        Replays a dead-letter item through its designated pipeline.
        If processing succeeds, the DLQ record is marked as REPLAYED.
        """
        dlq_record = self.dlq.get(dlq_id)
        if not dlq_record:
            raise KeyError(f"Dead-letter record {dlq_id} not found.")

        item = IngestionItem(
            item_id=dlq_record.item_id,
            source=dlq_record.source,
            payload=dlq_record.payload,
            timestamp=datetime.now(timezone.utc),
        )

        run = await self.trigger_pipeline_run(
            pipeline_id=dlq_record.pipeline_id,
            incremental=False,
            triggered_by="REPLAY",
            items_override=[item],
        )

        if run.status == IngestionRunStatus.COMPLETED:
            self.dlq.mark_replayed(dlq_id, f"Successfully replayed in run {run.id}")
        else:
            logger.warning("DLQ replay for %s completed with status: %s", dlq_id, run.status)

        return run

    # ==========================================================================
    # Observability & Metrics
    # ==========================================================================

    def get_run(self, run_id: UUID) -> Optional[IngestionRunRecord]:
        return self._runs_by_id.get(run_id)

    def list_runs(
        self,
        pipeline_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[IngestionRunRecord]:
        if pipeline_id:
            run_ids = self._runs_by_pipeline.get(pipeline_id, [])
            records = [self._runs_by_id[rid] for rid in run_ids if rid in self._runs_by_id]
        else:
            records = list(self._runs_by_id.values())

        records.sort(key=lambda r: r.started_at, reverse=True)
        return records[:limit]

    def get_observability_metrics(self) -> Dict[str, Any]:
        """Calculates system-wide and per-pipeline telemetry metrics."""
        total_runs = len(self._runs_by_id)
        succeeded_runs = sum(1 for r in self._runs_by_id.values() if r.status == IngestionRunStatus.COMPLETED)
        failed_runs = sum(1 for r in self._runs_by_id.values() if r.status == IngestionRunStatus.FAILED)
        partial_runs = sum(1 for r in self._runs_by_id.values() if r.status == IngestionRunStatus.PARTIAL_SUCCESS)

        total_items_processed = sum(r.telemetry.items_processed for r in self._runs_by_id.values())
        total_items_succeeded = sum(r.telemetry.items_succeeded for r in self._runs_by_id.values())
        total_items_failed = sum(r.telemetry.items_failed for r in self._runs_by_id.values())
        total_items_deduped = sum(r.telemetry.items_deduplicated for r in self._runs_by_id.values())
        total_items_dead_lettered = sum(r.telemetry.items_dead_lettered for r in self._runs_by_id.values())

        pipeline_summaries = {}
        for pid, pipe in self._pipelines.items():
            pipe_runs = [self._runs_by_id[rid] for rid in self._runs_by_pipeline.get(pid, []) if rid in self._runs_by_id]
            pipeline_summaries[pid] = {
                "name": pipe.name,
                "status": pipe.status.value,
                "total_runs": len(pipe_runs),
                "items_processed": sum(r.telemetry.items_processed for r in pipe_runs),
                "items_succeeded": sum(r.telemetry.items_succeeded for r in pipe_runs),
                "items_failed": sum(r.telemetry.items_failed for r in pipe_runs),
                "pending_dead_letters": self.dlq.count_pending(pipeline_id=pid),
                "watermark": (
                    pipe.watermark.last_processed_timestamp.isoformat()
                    if pipe.watermark.last_processed_timestamp
                    else None
                ),
            }

        return {
            "orchestrator_status": "HEALTHY",
            "active_pipelines": len(self._pipelines),
            "total_runs": total_runs,
            "runs_breakdown": {
                "completed": succeeded_runs,
                "partial_success": partial_runs,
                "failed": failed_runs,
            },
            "item_metrics": {
                "processed": total_items_processed,
                "succeeded": total_items_succeeded,
                "failed": total_items_failed,
                "deduplicated": total_items_deduped,
                "dead_lettered": total_items_dead_lettered,
            },
            "dlq_pending_total": self.dlq.count_pending(),
            "pipelines": pipeline_summaries,
        }

    def get_health_status(self) -> Dict[str, Any]:
        """Provides a health evaluation flagging degraded or error states."""
        unhealthy_pipelines = [
            pid for pid, p in self._pipelines.items()
            if p.status == PipelineStatus.ERROR
        ]
        pending_dlq = self.dlq.count_pending()
        is_healthy = len(unhealthy_pipelines) == 0

        return {
            "status": "HEALTHY" if is_healthy else "DEGRADED",
            "unhealthy_pipelines": unhealthy_pipelines,
            "pending_dlq_count": pending_dlq,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
