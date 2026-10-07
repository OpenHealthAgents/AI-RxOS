from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .models import (
    ClinicalTrialRecord,
    TrialResolutionSummary,
    TrialStatusHistory,
)
from .service import ClinicalTrialsIngestionService

router = APIRouter(prefix="/api/v1/ingest/clinicaltrials", tags=["ClinicalTrials Ingestion Engine"])
_service = ClinicalTrialsIngestionService()


class BatchTrialIngestRequest(BaseModel):
    trials: List[ClinicalTrialRecord]
    as_of_date: Optional[date] = None


class BatchTrialIngestResponse(BaseModel):
    total_submitted: int
    total_ingested: int
    trials: List[ClinicalTrialRecord]


@router.post("/trial", response_model=ClinicalTrialRecord)
def ingest_trial_route(
    trial: ClinicalTrialRecord,
    as_of_date: Optional[date] = Query(None, description="Temporal observation date of the trial snapshot"),
) -> ClinicalTrialRecord:
    """
    Ingests or updates a ClinicalTrials.gov record. Captures NCT, title, sponsor,
    collaborators, phase, status, enrollment, intervention, condition, population,
    biomarker, arms, endpoints, results, adverse events, termination; tracks
    historical changes over time; and resolves trials to canonical assets, indications,
    biomarkers, and sponsor companies.
    """
    return _service.ingest_trial(trial=trial, as_of_date=as_of_date)


@router.post("/batch", response_model=BatchTrialIngestResponse)
def batch_ingest_trials_route(
    req: BatchTrialIngestRequest,
) -> BatchTrialIngestResponse:
    """
    Batch ingests multiple ClinicalTrials.gov records with stage normalization,
    historical transition tracking, and canonical asset resolution.
    """
    ingested = _service.batch_ingest_trials(req.trials, as_of_date=req.as_of_date)
    return BatchTrialIngestResponse(
        total_submitted=len(req.trials),
        total_ingested=len(ingested),
        trials=ingested,
    )


@router.get("/{nct_id}", response_model=ClinicalTrialRecord)
def get_trial_route(nct_id: str) -> ClinicalTrialRecord:
    """Retrieves full trial record by NCT identifier."""
    trial = _service.get_trial(nct_id)
    if not trial:
        raise HTTPException(status_code=404, detail=f"Clinical trial '{nct_id}' not found.")
    return trial


@router.get("/{nct_id}/history", response_model=List[TrialStatusHistory])
def get_trial_history_route(
    nct_id: str,
    cutoff_date: Optional[date] = Query(None, description="Optional temporal cutoff date for historical zero-leakage evaluation"),
) -> List[TrialStatusHistory]:
    """
    Retrieves chronological status and protocol transition history for a trial,
    or historical status as of a cutoff date.
    """
    trial = _service.get_trial(nct_id)
    if not trial:
        raise HTTPException(status_code=404, detail=f"Clinical trial '{nct_id}' not found.")

    if cutoff_date:
        historical_status = _service.get_trial_status_at_cutoff(nct_id, cutoff_date)
        return [historical_status] if historical_status else []

    return _service.get_status_history(nct_id)


@router.get("/{nct_id}/resolutions", response_model=TrialResolutionSummary)
def get_trial_resolutions_route(nct_id: str) -> TrialResolutionSummary:
    """Retrieves resolved canonical assets, indications, biomarkers, and companies."""
    res = _service.get_resolutions(nct_id)
    if not res:
        raise HTTPException(status_code=404, detail=f"Resolutions for clinical trial '{nct_id}' not found.")
    return res


@router.get("/{nct_id}/results", response_model=Dict[str, Any])
def get_trial_results_route(nct_id: str) -> Dict[str, Any]:
    """Retrieves clinical outcomes, adverse events, endpoints, and results summary."""
    trial = _service.get_trial(nct_id)
    if not trial:
        raise HTTPException(status_code=404, detail=f"Clinical trial '{nct_id}' not found.")
    return _service.get_trial_results(nct_id)
