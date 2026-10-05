from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from croniter import croniter

from app.core.config import get_settings
from app.database.postgres import postgres_manager
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class JobStatus(str, Enum):
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeadLetterStatus(str, Enum):
    PENDING = "pending"
    RETRIED = "retried"


@dataclass
class JobProgress:
    total_documents: int = 0
    processed_documents: int = 0
    failed_documents: int = 0
    dead_lettered_documents: int = 0
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class IngestionJob:
    job_id: str
    source: str
    query: str
    organization_id: str | None = None
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    schedule: str | None = None
    next_run_at: datetime | None = None
    progress: JobProgress = field(default_factory=JobProgress)
    error_message: str | None = None
    retry_count: int = 0
    backoff_until: datetime | None = None
    cancel_requested: bool = False
    dead_letter_count: int = 0
    dead_letter_items: list[dict[str, Any]] = field(default_factory=list)
    checkpoint: dict[str, Any] = field(default_factory=dict)
    auth_context: dict[str, Any] = field(default_factory=dict)
    worker_task: asyncio.Task | None = None


class IngestionOrchestrator:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[IngestionJob] = asyncio.Queue()
        self._dead_letter: list[dict[str, Any]] = []
        self._running_jobs: dict[str, IngestionJob] = {}
        self._worker: asyncio.Task | None = None
        self._scheduler: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._metrics: dict[str, int] = {
            "ingestion.jobs_created": 0,
            "ingestion.jobs_started": 0,
            "ingestion.jobs_completed": 0,
            "ingestion.jobs_failed": 0,
            "ingestion.jobs_cancelled": 0,
            "ingestion.job_retries": 0,
            "ingestion.dead_letters": 0,
            "ingestion.jobs_scheduled": 0,
            "ingestion.jobs_rescheduled": 0,
        }
        self._recovered_persisted_jobs = False

    async def start(self) -> None:
        if self._worker is None or self._worker.done():
            if postgres_manager.pool is not None and not self._recovered_persisted_jobs:
                await self._recover_persisted_jobs()
            self._stop_event.clear()
            self._worker = asyncio.create_task(self._worker_loop())
            self._scheduler = asyncio.create_task(self._scheduler_loop())
            logger.info("Ingestion orchestrator worker started")

    async def _recover_persisted_jobs(self) -> None:
        async with postgres_manager.acquire(system_scope=True) as connection:
            rows = await connection.fetch(
                """SELECT id::text, source, query, status, created_at, started_at, completed_at,
                    schedule, next_run_at, documents_total, documents_processed, documents_failed,
                    retry_count, backoff_until, error_message, dead_letter_count, dead_letter_items,
                    organization_id, checkpoint, auth_context
                FROM literature_ingestion_jobs WHERE status IN ('queued', 'running')
                ORDER BY created_at"""
            )
        self._recovered_persisted_jobs = True
        for row in rows:
            job = await self._load_job_from_row(row)
            if job.status == JobStatus.RUNNING:
                job.status = JobStatus.QUEUED
                job.error_message = "worker restarted; resuming from persisted checkpoint"
            self.enqueue(job)

    async def stop(self) -> None:
        self._stop_event.set()
        if self._worker:
            await self._worker
        if self._scheduler:
            self._scheduler.cancel()
            try:
                await self._scheduler
            except asyncio.CancelledError:
                pass
        logger.info("Ingestion orchestrator stopped")

    def enqueue(self, job: IngestionJob) -> None:
        if job.status == JobStatus.SCHEDULED:
            asyncio.create_task(self._persist_job_state(job))
            return

        self._queue.put_nowait(job)
        self._running_jobs[job.job_id] = job
        self._metrics["ingestion.jobs_created"] += 1
        logger.info("Job enqueued", extra={"job_id": job.job_id, "source": job.source})
        asyncio.create_task(self._persist_job_state(job))

    async def schedule(self, job: IngestionJob, schedule: str) -> None:
        job.schedule = schedule
        job.next_run_at = self._compute_next_run(schedule)
        job.status = JobStatus.SCHEDULED
        self._metrics["ingestion.jobs_scheduled"] += 1
        await self._persist_job_state(job)
        await self.start()
        logger.info(
            "Job scheduled",
            extra={
                "job_id": job.job_id,
                "schedule": schedule,
                "next_run_at": job.next_run_at.isoformat(),
            },
        )

    def _compute_next_run(
        self, schedule: str, reference: datetime | None = None
    ) -> datetime:
        now = reference or datetime.now(timezone.utc)
        if not croniter.is_valid(schedule):
            raise ValueError("invalid schedule expression")
        next_run = croniter(schedule, now).get_next(datetime)
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=timezone.utc)
        return next_run

    async def _scheduler_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(3)
                now = datetime.now(timezone.utc)
                async with postgres_manager.acquire() as connection:
                    await connection.execute(
                        "SELECT set_config('app.literature_system_scope', 'true', true)"
                    )
                    rows = await connection.fetch(
                        """
                        SELECT id::text, source, query, status, created_at,
                            started_at, completed_at, schedule, next_run_at,
                            documents_total, documents_processed,
                            documents_failed, retry_count, backoff_until,
                            error_message, dead_letter_count, dead_letter_items,
                            organization_id, checkpoint, auth_context
                        FROM literature_ingestion_jobs
                        WHERE status = $1
                          AND next_run_at IS NOT NULL
                          AND next_run_at <= $2
                        """,
                        JobStatus.SCHEDULED.value,
                        now,
                    )

                for row in rows:
                    job = await self._load_job_from_row(row)
                    job.status = JobStatus.QUEUED
                    job.next_run_at = None
                    await self._persist_job_state(job)
                    self.enqueue(job)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Scheduler loop failed")

    async def _load_job_from_db(
        self, job_id: str, organization_id: str | None = None
    ) -> IngestionJob | None:
        acquire = (
            postgres_manager.acquire(organization_id)
            if organization_id is not None
            else postgres_manager.acquire()
        )
        async with acquire as connection:
            row = await connection.fetchrow(
                """
                SELECT id::text, source, query, status, created_at,
                    started_at, completed_at, schedule, next_run_at,
                    documents_total, documents_processed,
                    documents_failed, retry_count, backoff_until,
                    error_message, dead_letter_count, dead_letter_items,
                    organization_id, checkpoint, auth_context
                FROM literature_ingestion_jobs
                WHERE id = $1
                """,
                job_id,
            )
        if row is None:
            return None
        return await self._load_job_from_row(row)

    async def _load_job_from_row(self, row: Any) -> IngestionJob:
        dead_letter_items = row["dead_letter_items"] or []
        if isinstance(dead_letter_items, str):
            dead_letter_items = json.loads(dead_letter_items)
        checkpoint = row.get("checkpoint", {}) if hasattr(row, "get") else {}
        auth_context = row.get("auth_context", {}) if hasattr(row, "get") else {}
        if isinstance(checkpoint, str):
            checkpoint = json.loads(checkpoint)
        if isinstance(auth_context, str):
            auth_context = json.loads(auth_context)

        return IngestionJob(
            job_id=row["id"],
            source=row["source"],
            query=row["query"],
            organization_id=row.get("organization_id") if hasattr(row, "get") else None,
            status=JobStatus(row["status"]),
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            schedule=row["schedule"],
            next_run_at=row["next_run_at"],
            progress=JobProgress(
                total_documents=row["documents_total"],
                processed_documents=row["documents_processed"],
                failed_documents=row["documents_failed"],
                last_update=datetime.now(timezone.utc),
            ),
            error_message=row["error_message"],
            retry_count=row["retry_count"],
            backoff_until=row["backoff_until"],
            dead_letter_count=row["dead_letter_count"],
            dead_letter_items=dead_letter_items,
            checkpoint=checkpoint or {},
            auth_context=auth_context or {},
        )

    async def trigger_retry(self, job_id: str, organization_id: str | None = None) -> None:
        job = self._running_jobs.get(job_id)
        if job is None:
            job = await self._load_job_from_db(job_id, organization_id)
        if job is None:
            raise ValueError("job not found")
        if job.retry_count >= settings.ingestion_max_retries:
            raise ValueError("job retry limit has been reached")

        job.retry_count += 1
        job.backoff_until = datetime.now(timezone.utc) + timedelta(
            seconds=5 * job.retry_count
        )
        job.status = JobStatus.QUEUED
        job.next_run_at = None
        self._metrics["ingestion.job_retries"] += 1
        self.enqueue(job)
        await self.start()
        logger.info(
            "Retry scheduled",
            extra={"job_id": job.job_id, "retry_count": job.retry_count},
        )

    async def cancel(self, job_id: str, organization_id: str | None = None) -> None:
        job = self._running_jobs.get(job_id)
        if job is None:
            job = await self._load_job_from_db(job_id, organization_id)
        if job is None:
            raise ValueError("job not found")

        job.cancel_requested = True
        job.status = JobStatus.CANCELLED
        await self._persist_job_state(job)
        logger.info("Cancellation requested", extra={"job_id": job.job_id})

    async def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if job.backoff_until and job.backoff_until > datetime.now(timezone.utc):
                await asyncio.sleep(
                    (job.backoff_until - datetime.now(timezone.utc)).total_seconds()
                )

            if job.cancel_requested:
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now(timezone.utc)
                self._metrics["ingestion.jobs_cancelled"] += 1
                await self._persist_job_state(job)
                continue

            await self._process_job(job)

    async def _process_job(self, job: IngestionJob) -> None:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        self._metrics["ingestion.jobs_started"] += 1
        await self._persist_job_state(job)

        try:
            if job.source == "pubmed":
                from app.services.pubmed_ingestion import PubMedIngestionProcessor

                processor = PubMedIngestionProcessor()
                await processor.run(job, self._persist_job_state)
            elif job.source == "clinicaltrials":
                from app.services.clinicaltrials_ingestion import ClinicalTrialsIngestionProcessor

                processor = ClinicalTrialsIngestionProcessor()
            elif job.source == "regulatory":
                from app.services.regulatory_ingestion import RegulatoryIngestionProcessor

                processor = RegulatoryIngestionProcessor()
                await processor.run(job, self._persist_job_state)
            elif job.source == "patent":
                from app.services.patent_ingestion import PatentIngestionProcessor

                processor = PatentIngestionProcessor()
                await processor.run(job, self._persist_job_state)
            else:
                await self._simulate_ingestion(job)
            if job.cancel_requested:
                job.status = JobStatus.CANCELLED
                self._metrics["ingestion.jobs_cancelled"] += 1
            else:
                job.status = JobStatus.COMPLETED
                self._metrics["ingestion.jobs_completed"] += 1
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            self._metrics["ingestion.jobs_failed"] += 1
            dead_letter_item = {
                "job_id": job.job_id,
                "source": job.source,
                "query": job.query,
                "error_message": job.error_message,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": DeadLetterStatus.PENDING.value,
            }
            job.dead_letter_items.append(dead_letter_item)
            job.dead_letter_count += 1
            self._dead_letter.append(dead_letter_item)
            self._metrics["ingestion.dead_letters"] += 1
            logger.exception("Ingestion job failed", extra={"job_id": job.job_id})
        finally:
            job.completed_at = datetime.now(timezone.utc)
            await self._persist_job_state(job)
            if job.schedule and job.status in {JobStatus.COMPLETED, JobStatus.FAILED}:
                await self._reschedule(job)
                await self._persist_job_state(job)

    async def _reschedule(self, job: IngestionJob) -> None:
        if not job.schedule:
            return

        job.status = JobStatus.SCHEDULED
        job.next_run_at = self._compute_next_run(job.schedule, job.completed_at)
        self._metrics["ingestion.jobs_rescheduled"] += 1
        logger.info(
            "Job rescheduled",
            extra={"job_id": job.job_id, "next_run_at": job.next_run_at.isoformat()},
        )

    async def _simulate_ingestion(self, job: IngestionJob) -> None:
        total = 10
        job.progress.total_documents = total
        for index in range(total):
            if job.cancel_requested:
                break
            await asyncio.sleep(0.01)
            job.progress.processed_documents += 1
            job.progress.last_update = datetime.now(timezone.utc)
            if index == 7 and job.retry_count == 0:
                raise RuntimeError("temporary ingestion error")

    async def _persist_job_state(self, job: IngestionJob) -> None:
        acquire = (
            postgres_manager.acquire(job.organization_id)
            if job.organization_id is not None
            else postgres_manager.acquire()
        )
        async with acquire as connection:
            await connection.execute(
                """
                UPDATE literature_ingestion_jobs
                SET status = $1,
                    started_at = $2,
                    completed_at = $3,
                    schedule = $4,
                    next_run_at = $5,
                    documents_total = $6,
                    documents_processed = $7,
                    documents_failed = $8,
                    error_message = $9,
                    retry_count = $10,
                    backoff_until = $11,
                    dead_letter_count = $12,
                    dead_letter_items = $13,
                    checkpoint = $14::jsonb
                WHERE id = $15 AND (organization_id IS NULL OR organization_id = $16::uuid)
                """,
                job.status.value,
                job.started_at,
                job.completed_at,
                job.schedule,
                job.next_run_at,
                job.progress.total_documents,
                job.progress.processed_documents,
                job.progress.failed_documents,
                job.error_message,
                job.retry_count,
                job.backoff_until,
                job.dead_letter_count,
                json.dumps(job.dead_letter_items),
                json.dumps(job.checkpoint),
                job.job_id,
                job.organization_id,
            )

    def get_job(self, job_id: str) -> IngestionJob | None:
        return self._running_jobs.get(job_id)

    def get_metrics(self) -> dict[str, int]:
        return dict(self._metrics)

    def get_dead_letters(self, job_id: str | None = None) -> list[dict[str, Any]]:
        items = [
            item
            for item in self._dead_letter
            if job_id is None or item["job_id"] == job_id
        ]
        return list(items)


orchestrator = IngestionOrchestrator()
