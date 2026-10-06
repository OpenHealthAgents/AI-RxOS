from __future__ import annotations

from typing import List
from fastapi import APIRouter, HTTPException, status

from .engine import ClinicalDevelopmentIntelligenceEngine
from .models import (
    ClinicalDevelopmentProfile,
    EvaluateAssetClinicalRequest,
    EvaluateAssetClinicalResponse,
    ObservedClinicalOutcome,
)

router = APIRouter(prefix="/api/v1/clinical", tags=["Clinical Development Intelligence Engine"])

_engine = ClinicalDevelopmentIntelligenceEngine()


def get_clinical_engine() -> ClinicalDevelopmentIntelligenceEngine:
    return _engine


@router.get("/benchmarks", response_model=List[ClinicalDevelopmentProfile])
def list_benchmark_clinical_profiles() -> List[ClinicalDevelopmentProfile]:
    """
    Returns clinical development profiles for all canonical benchmark assets
    (Tucatinib, Zongertinib, Poziotinib, Neratinib, and OX-HER2-01).
    """
    engine = get_clinical_engine()
    return engine.list_benchmark_profiles()


@router.get("/profile/{asset_id}", response_model=ClinicalDevelopmentProfile)
def get_asset_clinical_profile(asset_id: str) -> ClinicalDevelopmentProfile:
    """
    Retrieves the clinical development profile for a specific asset.
    Evaluates stage, trial design, enrollment, population, biomarker enrichment,
    endpoints (ORR, CR, DOR, PFS, OS), toxicity, discontinuation, and dose optimization.
    Produces:
    - Clinical Success Probability
    - Clinical Readiness Score
    - Development Risk Score
    - Evidence Confidence
    """
    engine = get_clinical_engine()
    profile = engine.get_benchmark_profile(asset_id)
    if not profile.observed_clinical_outcomes and asset_id not in ("tucatinib", "zongertinib", "poziotinib", "neratinib", "ox-her2-01"):
        raise HTTPException(status_code=404, detail=f"No clinical development data found for asset '{asset_id}'")
    return profile


@router.post("/evaluate", response_model=EvaluateAssetClinicalResponse)
def evaluate_asset_clinical(req: EvaluateAssetClinicalRequest) -> EvaluateAssetClinicalResponse:
    """
    Evaluates an asset's clinical profile from custom or preloaded outcomes.
    Strictly separates:
    - observed clinical outcome
    - model prediction
    - expert interpretation
    - unknown
    """
    engine = get_clinical_engine()
    profile = engine.evaluate_asset(
        asset_id=req.asset_id,
        asset_name=req.asset_name,
        custom_outcomes=req.custom_outcomes,
    )
    return EvaluateAssetClinicalResponse(profile=profile)


@router.get("/outcomes/{asset_id}", response_model=List[ObservedClinicalOutcome])
def get_observed_outcomes(asset_id: str) -> List[ObservedClinicalOutcome]:
    """
    Retrieves the observed clinical outcomes (empirical facts) for an asset.
    """
    engine = get_clinical_engine()
    profile = engine.get_benchmark_profile(asset_id)
    return profile.observed_clinical_outcomes
