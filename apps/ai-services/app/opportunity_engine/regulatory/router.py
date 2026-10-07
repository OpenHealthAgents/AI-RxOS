from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from pydantic import BaseModel
from .models import (
    RegulatoryEventRecord,
    RegulatoryEventType,
    UnverifiedMarketingClaimError,
)
from .service import RegulatoryIntelligenceService

router = APIRouter(prefix="/api/v1/regulatory", tags=["Regulatory Intelligence"])

# Shared singleton service instance
_regulatory_service = RegulatoryIntelligenceService()


def get_regulatory_service() -> RegulatoryIntelligenceService:
    return _regulatory_service


class BatchRegulatoryIngestRequest(BaseModel):
    events: List[RegulatoryEventRecord]
    strict: bool = False


class BatchRegulatoryIngestResponse(BaseModel):
    total_submitted: int
    total_ingested: int
    events: List[RegulatoryEventRecord]


@router.get("/assets/{asset_id}/timeline", response_model=List[RegulatoryEventRecord])
def get_asset_regulatory_timeline(
    asset_id: UUID,
    cutoff_date: Optional[date] = Query(None, description="Optional temporal cutoff date to prevent leakage"),
    include_rejected: bool = Query(False, description="Whether to include rejected unverified marketing claims"),
) -> List[RegulatoryEventRecord]:
    """
    Returns the complete, chronologically ordered regulatory events timeline for an asset.
    Strictly filters out events occurring after cutoff_date when specified.
    """
    service = get_regulatory_service()
    return service.get_asset_timeline(
        asset_id=asset_id,
        cutoff_date=cutoff_date,
        include_rejected=include_rejected,
    )


@router.get("/assets/{asset_id}/status")
def get_asset_regulatory_status(
    asset_id: UUID,
    cutoff_date: Optional[date] = Query(None, description="Temporal cutoff date (defaults to today)"),
    indication: Optional[str] = Query(None, description="Optional disease indication name filter"),
) -> Dict[str, Any]:
    """
    Synthesizes the verifiable regulatory status of an asset as of cutoff_date.
    """
    service = get_regulatory_service()
    target_cutoff = cutoff_date or date.today()
    return service.get_regulatory_status_at_cutoff(
        asset_id=asset_id,
        cutoff_date=target_cutoff,
        indication_name=indication,
    )


@router.post("/events", response_model=RegulatoryEventRecord, status_code=status.HTTP_201_CREATED)
def record_regulatory_event(
    event: RegulatoryEventRecord,
    strict: bool = Query(True, description="Strictly reject unverified marketing claims asserting approval"),
) -> RegulatoryEventRecord:
    """
    Records and verifies a regulatory event.
    Enforces invariant: Never infer regulatory approval from marketing claims without verified evidence.
    """
    service = get_regulatory_service()
    try:
        return service.record_event(event=event, strict=strict)
    except UnverifiedMarketingClaimError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.post("/events/batch", response_model=BatchRegulatoryIngestResponse)
def batch_record_regulatory_events(
    req: BatchRegulatoryIngestRequest,
) -> BatchRegulatoryIngestResponse:
    """
    Batch records and validates regulatory events.
    Enforces required provenance and dates on every event.
    """
    service = get_regulatory_service()
    try:
        ingested = service.batch_record_events(req.events, strict=req.strict)
        return BatchRegulatoryIngestResponse(
            total_submitted=len(req.events),
            total_ingested=len(ingested),
            events=ingested,
        )
    except UnverifiedMarketingClaimError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.get("/events/type/{event_type}", response_model=List[RegulatoryEventRecord])
def get_regulatory_events_by_type(
    event_type: RegulatoryEventType,
    cutoff_date: Optional[date] = Query(None, description="Optional temporal cutoff date to prevent leakage"),
) -> List[RegulatoryEventRecord]:
    """
    Retrieves all regulatory events of a specified event type (e.g. FAST_TRACK,
    BREAKTHROUGH_THERAPY, ORPHAN_DRUG, ACCELERATED_APPROVAL, FULL_APPROVAL,
    COMPLETE_RESPONSE_LETTER, WITHDRAWAL, SAFETY_WARNING, LABEL_CHANGE).
    """
    service = get_regulatory_service()
    return service.get_events_by_type(event_type=event_type, cutoff_date=cutoff_date)

