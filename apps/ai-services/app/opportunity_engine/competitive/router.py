from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from .engine import CompetitiveIntelligenceEngine
from .models import (
    CompetitiveIntelligenceProfile,
    CompetitorCohortBreakdown,
    CompetitorSummary,
    EvaluateCompetitiveRequest,
    HeadToHeadComparison,
    WhiteSpaceOpportunityRecord,
)

router = APIRouter(prefix="/api/v1/competitive", tags=["Competitive Intelligence Engine"])

_engine = CompetitiveIntelligenceEngine()


def get_competitive_engine() -> CompetitiveIntelligenceEngine:
    return _engine


@router.get("/benchmarks", response_model=List[CompetitiveIntelligenceProfile])
def list_benchmark_competitive_landscapes() -> List[CompetitiveIntelligenceProfile]:
    """
    Returns verified competitive intelligence profiles across canonical oncology benchmark assets
    (Zongertinib, Tucatinib, Neratinib, Poziotinib, and OX-HER2-01).
    """
    engine = get_competitive_engine()
    return engine.list_benchmark_profiles()


@router.get("/competitors", response_model=List[CompetitorSummary])
def list_all_competitor_entities() -> List[CompetitorSummary]:
    """
    Returns the comprehensive catalog of known competitor assets, including approved standards
    of care, clinical-stage competitors, and emerging academic programs.
    """
    engine = get_competitive_engine()
    return engine.list_all_competitors()


@router.get("/asset/{asset_id}", response_model=CompetitiveIntelligenceProfile)
def get_asset_competitive_profile(asset_id: str) -> CompetitiveIntelligenceProfile:
    """
    Returns the complete competitive intelligence profile for an asset, containing:
    - Competitor cohorts across 10 dimensions
    - Head-to-head comparisons across 11 dimensions
    - Competitive Density, Differentiation Score, Competitive Risk, and White-Space Opportunities.
    """
    engine = get_competitive_engine()
    profile = engine.get_competitive_profile(asset_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competitive profile for asset '{asset_id}' not found. Use POST /evaluate for dynamic assessment.",
        )
    return profile


@router.get("/asset/{asset_id}/cohorts", response_model=CompetitorCohortBreakdown)
def get_asset_competitor_cohorts(asset_id: str) -> CompetitorCohortBreakdown:
    """
    Identifies competitors across all 10 required cohorts:
    direct competitors, same target, same mechanism, same biomarker, same indication,
    same patient population, same modality, clinical-stage competitors,
    approved standards of care, and emerging academic programs.
    """
    engine = get_competitive_engine()
    return engine.identify_competitors_for_asset(asset_id)


@router.get("/asset/{asset_id}/head-to-head/{competitor_id}", response_model=HeadToHeadComparison)
def get_head_to_head_comparison(asset_id: str, competitor_id: str) -> HeadToHeadComparison:
    """
    Evaluates head-to-head comparison across all 11 required dimensions:
    potency, selectivity, CNS, clinical stage, efficacy, safety,
    biomarker, resistance, combination, ownership, and commercial opportunity.
    """
    engine = get_competitive_engine()
    profile = engine.get_competitive_profile(asset_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_id}' not found.",
        )
    for comp in profile.head_to_head_comparisons:
        if comp.competitor_id.lower() == competitor_id.lower():
            return comp
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Head-to-head comparison between '{asset_id}' and '{competitor_id}' not found in profile.",
    )


@router.get("/asset/{asset_id}/white-space", response_model=List[WhiteSpaceOpportunityRecord])
def get_asset_white_space_opportunities(asset_id: str) -> List[WhiteSpaceOpportunityRecord]:
    """
    Identifies unaddressed white-space opportunities and underserved patient segments for an asset.
    """
    engine = get_competitive_engine()
    profile = engine.get_competitive_profile(asset_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_id}' not found.",
        )
    return profile.white_space_opportunities


@router.post("/evaluate", response_model=CompetitiveIntelligenceProfile)
def evaluate_custom_asset_landscape(req: EvaluateCompetitiveRequest) -> CompetitiveIntelligenceProfile:
    """
    Dynamically generates or retrieves the competitive intelligence landscape for any asset.
    """
    engine = get_competitive_engine()
    return engine.evaluate_competitive_landscape(
        asset_id=req.asset_id,
        asset_name=req.asset_name,
        target=req.target,
        indication=req.indication,
        patient_population=req.patient_population,
        modality=req.modality,
        stage=req.stage,
    )
