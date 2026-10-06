from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from .engine import BiologyIntelligenceEngine
from .models import (
    BiologyIntelligenceProfile,
    EvaluateAssetBiologyRequest,
    EvaluateAssetBiologyResponse,
    RawBiologicalObservation,
)

router = APIRouter(prefix="/api/v1/biology", tags=["Biology Intelligence Engine"])

_engine = BiologyIntelligenceEngine()


def get_biology_engine() -> BiologyIntelligenceEngine:
    return _engine


@router.get("/benchmarks", response_model=List[BiologyIntelligenceProfile])
def list_benchmark_biology_profiles() -> List[BiologyIntelligenceProfile]:
    """
    Returns evaluated biology intelligence profiles for all canonical benchmark assets
    (Zongertinib, Tucatinib, Poziotinib, Neratinib, and OX-HER2-01).
    """
    engine = get_biology_engine()
    return engine.list_benchmark_profiles()


@router.get("/profile/{asset_id}", response_model=BiologyIntelligenceProfile)
def get_asset_biology_profile(asset_id: str) -> BiologyIntelligenceProfile:
    """
    Retrieves the biology intelligence profile for a specific asset,
    evaluating the 12 biological dimensions and 6 canonical scores strictly from empirical evidence.
    """
    engine = get_biology_engine()
    profile = engine.get_benchmark_profile(asset_id)
    if not profile.raw_observations and asset_id not in ("zongertinib", "tucatinib", "poziotinib", "neratinib", "ox-her2-01"):
        raise HTTPException(status_code=404, detail=f"No biological observations found for asset '{asset_id}'")
    return profile


@router.post("/evaluate", response_model=EvaluateAssetBiologyResponse)
def evaluate_asset_biology(req: EvaluateAssetBiologyRequest) -> EvaluateAssetBiologyResponse:
    """
    Evaluates an asset's biological profile from provided or pre-loaded raw observations.
    Calculates:
    - Biology Validation Score
    - Potency Score
    - Selectivity Score
    - Biomarker Score
    - Mechanistic Confidence
    - Translational Readiness
    """
    engine = get_biology_engine()
    profile = engine.evaluate_asset(
        asset_id=req.asset_id,
        asset_name=req.asset_name,
        custom_observations=req.custom_observations,
    )
    return EvaluateAssetBiologyResponse(profile=profile)


@router.get("/observations/{asset_id}", response_model=List[RawBiologicalObservation])
def get_raw_observations(asset_id: str) -> List[RawBiologicalObservation]:
    """
    Retrieves the raw empirical biological observations (IC50s, selectivity ratios,
    CRISPR dependencies, animal TGI, clinical ORR) stored for an asset.
    """
    engine = get_biology_engine()
    return engine.get_raw_observations_for_asset(asset_id)
