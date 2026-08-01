import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.database.postgres import postgres_manager
from app.orchestrator.manager import IngestionJob as OrchestrationJob
from app.orchestrator.manager import JobStatus, orchestrator
from app.schemas import IngestionJob as IngestionJobSchema
from app.schemas import IngestionRequest

router = APIRouter(prefix="/ingestion", tags=["Ingestion"])

auth_dependency = Depends(get_current_user)


@router.post("", response_model=IngestionJobSchema, status_code=202)
async def start_ingestion(
    req: IngestionRequest,
    auth_payload: dict[str, str] = auth_dependency,
) -> IngestionJobSchema:
    job_id = uuid4()
    created_at = datetime.now(timezone.utc)
    async with postgres_manager.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO literature_ingestion_jobs (
                id,
                source,
                query,
                status,
                created_at,
                schedule,
                next_run_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            job_id,
            req.source,
            req.query,
            JobStatus.SCHEDULED.value if req.schedule else JobStatus.QUEUED.value,
            created_at,
            req.schedule,
            None,
        )

    job = OrchestrationJob(
        job_id=str(job_id),
        source=req.source,
        query=req.query,
        status=JobStatus.SCHEDULED if req.schedule else JobStatus.QUEUED,
        created_at=created_at,
        schedule=req.schedule,
    )

    if req.schedule:
        await orchestrator.schedule(job, req.schedule)
    else:
        orchestrator.enqueue(job)
        await orchestrator.start()

    async with postgres_manager.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT id::text, source, query, status, created_at,
                started_at, completed_at, schedule, next_run_at,
                documents_total, documents_processed,
                documents_failed, retry_count, backoff_until,
                error_message, dead_letter_count, dead_letter_items
            FROM literature_ingestion_jobs
            WHERE id = $1
            """,
            job_id,
        )

    job_response = _row_to_job_schema(row)
    if job_response is None:
        raise HTTPException(
            status_code=500, detail="failed to load created ingestion job"
        )
    return job_response


def _row_to_job_schema(row: Any) -> IngestionJobSchema | None:
    if row is None:
        return None

    record = dict(row)
    dead_letter_items = record.get("dead_letter_items")
    if isinstance(dead_letter_items, str):
        record["dead_letter_items"] = json.loads(dead_letter_items)
    elif dead_letter_items is None:
        record["dead_letter_items"] = []
    return IngestionJobSchema(**record)


@router.get("/{job_id}", response_model=IngestionJobSchema)
async def get_ingestion_job(
    job_id: UUID,
    auth_payload: dict[str, str] = auth_dependency,
) -> IngestionJobSchema:
    async with postgres_manager.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT id::text, source, query, status, created_at,
                started_at, completed_at, schedule, next_run_at,
                documents_total, documents_processed,
                documents_failed, retry_count, backoff_until,
                error_message, dead_letter_count, dead_letter_items
            FROM literature_ingestion_jobs
            WHERE id = $1
            """,
            job_id,
        )

    job = _row_to_job_schema(row)
    if job is None:
        raise HTTPException(status_code=404, detail="ingestion job not found")
    return job


@router.post("/{job_id}/trigger", response_model=IngestionJobSchema)
async def trigger_ingestion_job(
    job_id: UUID,
    auth_payload: dict[str, str] = auth_dependency,
) -> IngestionJobSchema:
    job = await orchestrator._load_job_from_db(str(job_id))
    if job is None:
        raise HTTPException(status_code=404, detail="ingestion job not found")

    job.status = JobStatus.QUEUED
    orchestrator.enqueue(job)
    await orchestrator.start()

    async with postgres_manager.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT id::text, source, query, status, created_at,
                started_at, completed_at, schedule, next_run_at,
                documents_total, documents_processed,
                documents_failed, retry_count, backoff_until,
                error_message, dead_letter_count, dead_letter_items
            FROM literature_ingestion_jobs
            WHERE id = $1
            """,
            job_id,
        )

    if row is None:
        raise HTTPException(
            status_code=500, detail="failed to load ingestion job after trigger"
        )

    job_response = _row_to_job_schema(row)
    assert job_response is not None
    return job_response


@router.post("/{job_id}/retry", response_model=IngestionJobSchema)
async def retry_ingestion_job(
    job_id: UUID,
    auth_payload: dict[str, str] = auth_dependency,
) -> IngestionJobSchema:
    try:
        await orchestrator.trigger_retry(str(job_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    async with postgres_manager.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT id::text, source, query, status, created_at,
                started_at, completed_at, schedule, next_run_at,
                documents_total, documents_processed,
                documents_failed, retry_count, backoff_until,
                error_message, dead_letter_count, dead_letter_items
            FROM literature_ingestion_jobs
            WHERE id = $1
            """,
            job_id,
        )

    job = _row_to_job_schema(row)
    if job is None:
        raise HTTPException(status_code=404, detail="ingestion job not found")
    return job


@router.post("/{job_id}/cancel", response_model=IngestionJobSchema)
async def cancel_ingestion_job(
    job_id: UUID,
    auth_payload: dict[str, str] = auth_dependency,
) -> IngestionJobSchema:
    try:
        await orchestrator.cancel(str(job_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    async with postgres_manager.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT id::text, source, query, status, created_at,
                started_at, completed_at, documents_total,
                documents_processed, documents_failed, retry_count,
                backoff_until, error_message, schedule, next_run_at,
                dead_letter_count, dead_letter_items
            FROM literature_ingestion_jobs
            WHERE id = $1
            """,
            job_id,
        )

    job = _row_to_job_schema(row)
    if job is None:
        raise HTTPException(status_code=404, detail="ingestion job not found")
    return job


@router.get("/{job_id}/dead-letter")
async def get_dead_letter_items(
    job_id: UUID,
    auth_payload: dict[str, str] = auth_dependency,
) -> dict[str, object]:
    async with postgres_manager.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT id::text, dead_letter_items
            FROM literature_ingestion_jobs
            WHERE id = $1
            """,
            job_id,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="ingestion job not found")

    record = dict(row)
    dead_letter_items = record.get("dead_letter_items")
    if isinstance(dead_letter_items, str):
        dead_letter_items = json.loads(dead_letter_items)
    elif dead_letter_items is None:
        dead_letter_items = []

    return {
        "items": dead_letter_items,
        "total": len(dead_letter_items),
    }
