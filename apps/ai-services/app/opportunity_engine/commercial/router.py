from __future__ import annotations

from typing import List
from fastapi import APIRouter, HTTPException, Query, status

from .engine import CommercialOpportunityEngine
from .models import (
    CommercialAssumptionRecord,
    CommercialOpportunityProfile,
    EvaluateCommercialRequest,
    ModeledRevenueProjections,
)

router = APIRouter(prefix="/api/v1/commercial", tags=["Commercial Opportunity Intelligence Engine"])

_engine = CommercialOpportunityEngine()


def get_commercial_engine() -> CommercialOpportunityEngine:
    return _engine


@router.get("/benchmarks", response_model=List[CommercialOpportunityProfile])
def list_benchmark_commercial_profiles() -> List[CommercialOpportunityProfile]:
    """
    Returns commercial opportunity intelligence profiles across canonical oncology benchmark assets
    (Zongertinib, Tucatinib, Neratinib, Poziotinib, and OX-HER2-01).
    """
    engine = get_commercial_engine()
    return engine.list_benchmark_profiles()


@router.get("/asset/{asset_id}", response_model=CommercialOpportunityProfile)
def get_asset_commercial_profile(asset_id: str) -> CommercialOpportunityProfile:
    """
    Evaluates 11 dimensions:
    addressable population, biomarker-defined population, treatment duration,
    standard of care, unmet need, competitive density, clinical differentiation,
    potential line of therapy, pricing analogs, pipeline crowding, and market expansion.

    Produces:
    - Commercial Opportunity Score (0 - 100)
    - Market Attractiveness
    - Competitive Pressure
    - Unmet Need
    - Commercial Confidence (0.0 - 1.0)

    Enforces epistemic invariant: Every assumption identifies provenance (Observed, Externally sourced,
    Modeled, Assumed, or Unknown). If key assumptions are Unknown, confidence is strictly capped at <=0.40.
    """
    engine = get_commercial_engine()
    profile = engine.get_commercial_profile(asset_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Commercial profile for asset '{asset_id}' not found. Use POST /evaluate for dynamic modeling.",
        )
    return profile


@router.get("/asset/{asset_id}/assumptions", response_model=List[CommercialAssumptionRecord])
def get_asset_commercial_assumptions(asset_id: str) -> List[CommercialAssumptionRecord]:
    """
    Returns the audited assumptions list for an asset with explicit epistemic provenance
    (Observed, Externally sourced, Modeled, Assumed, or Unknown).
    """
    engine = get_commercial_engine()
    profile = engine.get_commercial_profile(asset_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_id}' not found.",
        )
    return profile.assumptions_audit


@router.get("/asset/{asset_id}/projections", response_model=ModeledRevenueProjections)
def get_asset_revenue_projections(asset_id: str) -> ModeledRevenueProjections:
    """
    Returns deterministic modeled revenue projections (Base, Bull, Bear) with explicit formula lineage.
    """
    engine = get_commercial_engine()
    profile = engine.get_commercial_profile(asset_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_id}' not found.",
        )
    return profile.modeled_revenue_projections


@router.post("/evaluate", response_model=CommercialOpportunityProfile)
def evaluate_asset_commercial_opportunity(req: EvaluateCommercialRequest) -> CommercialOpportunityProfile:
    """
    Dynamically models commercial opportunity intelligence for any biopharmaceutical asset.
    """
    engine = get_commercial_engine()
    return engine.evaluate_commercial_opportunity(
        asset_id=req.asset_id,
        asset_name=req.asset_name,
        target=req.target,
        indication=req.indication,
        potential_line_of_therapy=req.potential_line_of_therapy,
    )
