from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from .dlq import DeadLetterQueueService
from .engine import AsyncIngestionOrchestrator
from .models import (
    DeadLetterRecord,
    DeadLetterStatus,
    IngestionItem,
    IngestionPipeline,
    IngestionRunRecord,
    PipelineSchedule,
)

router = APIRouter(prefix="/api/v1/orchestration", tags=["Asynchronous Ingestion Orchestration"])

_dlq_service = DeadLetterQueueService()
_orchestrator = AsyncIngestionOrchestrator(dlq_service=_dlq_service)


def get_orchestrator() -> AsyncIngestionOrchestrator:
    return _orchestrator


class TriggerRunRequest(BaseModel):
    incremental: bool = True
    items: Optional[List[IngestionItem]] = None


class ResolveDeadLetterRequest(BaseModel):
    resolution_note: str


# ==============================================================================
# Pipeline Endpoints
# ==============================================================================

@router.get("/pipelines", response_model=List[IngestionPipeline])
def list_pipelines() -> List[IngestionPipeline]:
    """Lists all configured ingestion pipelines."""
    return get_orchestrator().list_pipelines()


@router.get("/pipelines/{pipeline_id}", response_model=IngestionPipeline)
def get_pipeline(pipeline_id: str) -> IngestionPipeline:
    """Retrieves live state and configuration for a pipeline."""
    pipe = get_orchestrator().get_pipeline(pipeline_id)
    if not pipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline '{pipeline_id}' not found.",
        )
    return pipe


@router.post("/pipelines", response_model=IngestionPipeline, status_code=status.HTTP_201_CREATED)
def register_pipeline(pipeline: IngestionPipeline) -> IngestionPipeline:
    """Registers or updates an ingestion pipeline."""
    return get_orchestrator().register_pipeline(pipeline)


@router.post("/pipelines/{pipeline_id}/trigger", response_model=IngestionRunRecord)
async def trigger_pipeline(
    pipeline_id: str,
    req: Optional[TriggerRunRequest] = None,
) -> IngestionRunRecord:
    """
    Manually triggers an ingestion run.
    Supports incremental or full historical replay and optional inline item submission.
    """
    orch = get_orchestrator()
    incremental = req.incremental if req else True
    items = req.items if req else None

    try:
        return await orch.trigger_pipeline_run(
            pipeline_id=pipeline_id,
            incremental=incremental,
            triggered_by="MANUAL",
            items_override=items,
        )
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/pipelines/{pipeline_id}/schedule", response_model=IngestionPipeline)
def update_schedule(
    pipeline_id: str,
    schedule: PipelineSchedule,
) -> IngestionPipeline:
    """Updates the cron / interval schedule for an ingestion pipeline."""
    orch = get_orchestrator()
    try:
        return orch.update_pipeline_schedule(pipeline_id, schedule)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ==============================================================================
# Ingestion Run Audit Endpoints
# ==============================================================================

@router.get("/runs", response_model=List[IngestionRunRecord])
def list_runs(
    pipeline_id: Optional[str] = Query(None, description="Optional filter by pipeline ID"),
    limit: int = Query(50, ge=1, le=200),
) -> List[IngestionRunRecord]:
    """Lists recent execution runs and telemetry."""
    return get_orchestrator().list_runs(pipeline_id=pipeline_id, limit=limit)


@router.get("/runs/{run_id}", response_model=IngestionRunRecord)
def get_run(run_id: UUID) -> IngestionRunRecord:
    """Retrieves full execution audit trail for a specific run."""
    run = get_orchestrator().get_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found.",
        )
    return run


# ==============================================================================
# Dead-Letter Queue (DLQ) Endpoints
# ==============================================================================

@router.get("/dlq", response_model=List[DeadLetterRecord])
def list_dead_letters(
    pipeline_id: Optional[str] = Query(None, description="Filter by pipeline"),
    status_filter: Optional[DeadLetterStatus] = Query(None, alias="status"),
    category: Optional[str] = Query(None, description="Filter by failure category"),
    limit: int = Query(100, ge=1, le=500),
) -> List[DeadLetterRecord]:
    """Queries dead-letter records."""
    return get_orchestrator().dlq.list_records(
        pipeline_id=pipeline_id,
        status=status_filter,
        failure_category=category,
        limit=limit,
    )


@router.get("/dlq/{dlq_id}", response_model=DeadLetterRecord)
def get_dead_letter(dlq_id: UUID) -> DeadLetterRecord:
    """Retrieves a single dead-letter record with error context."""
    record = get_orchestrator().dlq.get(dlq_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dead-letter record '{dlq_id}' not found.",
        )
    return record


@router.post("/dlq/{dlq_id}/replay", response_model=IngestionRunRecord)
async def replay_dead_letter(dlq_id: UUID) -> IngestionRunRecord:
    """
    Replays a dead-letter item through its designated pipeline.
    Marks record as REPLAYED if processing succeeds.
    """
    orch = get_orchestrator()
    try:
        return await orch.replay_dead_letter(dlq_id)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/dlq/{dlq_id}/resolve", response_model=DeadLetterRecord)
def resolve_dead_letter(
    dlq_id: UUID,
    req: ResolveDeadLetterRequest,
) -> DeadLetterRecord:
    """Marks a dead-letter item as resolved with an audit note."""
    record = get_orchestrator().dlq.resolve(dlq_id, req.resolution_note)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dead-letter record '{dlq_id}' not found.",
        )
    return record


# ==============================================================================
# Observability & Health Endpoints
# ==============================================================================

@router.get("/observability/metrics")
def get_metrics() -> Dict[str, Any]:
    """Returns observability metrics: item counts, error summaries, throughput."""
    return get_orchestrator().get_observability_metrics()


@router.get("/observability/health")
def get_health() -> Dict[str, Any]:
    """Returns health status across all active ingestion pipelines."""
    return get_orchestrator().get_health_status()
