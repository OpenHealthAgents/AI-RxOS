from __future__ import annotations

from typing import List
from fastapi import APIRouter, HTTPException, Query, status

from .engine import ResistanceIntelligenceEngine
from .models import (
    EscapeMechanism,
    EvaluateResistanceRequest,
    PotentialIntervention,
    ResistanceRiskProfile,
)

router = APIRouter(prefix="/api/v1/resistance", tags=["Resistance Intelligence Engine"])

_engine = ResistanceIntelligenceEngine()


def get_resistance_engine() -> ResistanceIntelligenceEngine:
    return _engine


@router.get("/benchmarks", response_model=List[ResistanceRiskProfile])
def list_benchmark_resistance_profiles() -> List[ResistanceRiskProfile]:
    """
    Returns resistance risk profiles for all canonical benchmark assets
    (Zongertinib, Tucatinib, Neratinib, Poziotinib, and OX-HER2-01).
    """
    engine = get_resistance_engine()
    return engine.list_benchmark_profiles()


@router.get("/asset/{asset_id}", response_model=ResistanceRiskProfile)
def get_asset_resistance_profile(asset_id: str) -> ResistanceRiskProfile:
    """
    Produces:
    - Resistance Risk Profile (risk score 0-100, risk tier, primary vulnerability)
    - Top Escape Mechanisms across categories:
      target mutation, target amplification, bypass signaling, downstream activation,
      pathway adaptation, phenotypic escape, tumor microenvironment mechanisms, metabolic adaptation
    - Classification:
      Observed, Clinically observed, Preclinical, Mechanistically inferred, AI-predicted
    - Evidence citations & confidence
    - Potential Interventions to preempt or overcome resistance
    - Epistemic validation audit (strict invariant enforcement)
    """
    engine = get_resistance_engine()
    return engine.get_asset_resistance_profile(asset_id)


@router.get("/asset/{asset_id}/top-escapes", response_model=List[EscapeMechanism])
def get_top_escape_mechanisms(
    asset_id: str,
    limit: int = Query(default=5, ge=1, le=20, description="Maximum number of escape mechanisms to return"),
) -> List[EscapeMechanism]:
    """
    Returns top escape mechanisms ranked by clinical impact and frequency.
    """
    engine = get_resistance_engine()
    return engine.get_top_escape_mechanisms(asset_id, limit=limit)


@router.get("/asset/{asset_id}/interventions", response_model=List[PotentialIntervention])
def get_potential_interventions(asset_id: str) -> List[PotentialIntervention]:
    """
    Returns actionable combination strategies, next-generation inhibitor switches,
    or prophylactic regimens to preempt or overcome resistance for this asset.
    """
    engine = get_resistance_engine()
    return engine.get_potential_interventions(asset_id)


@router.post("/evaluate", response_model=ResistanceRiskProfile)
def evaluate_resistance(request: EvaluateResistanceRequest) -> ResistanceRiskProfile:
    """
    Evaluates asset resistance with custom filters (e.g., minimum confidence,
    inclusion/exclusion of AI-predicted mechanisms).
    """
    engine = get_resistance_engine()
    return engine.evaluate_resistance(request)
