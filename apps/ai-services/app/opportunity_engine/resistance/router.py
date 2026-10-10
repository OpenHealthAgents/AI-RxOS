from __future__ import annotations

from datetime import date
from typing import List

from fastapi import APIRouter, Query

from app.opportunity_engine.intelligence_47_49 import ResistanceIntelligence
from app.opportunity_engine.kg.engine import OncologyKnowledgeGraphEngine

from .engine import ResistanceIntelligenceEngine
from .models import (
    EscapeMechanism,
    EvaluateResistanceRequest,
    PotentialIntervention,
    ResistanceRiskProfile,
)

router = APIRouter(prefix="/api/v1/resistance", tags=["Resistance Intelligence Engine"])

_engine = ResistanceIntelligenceEngine()
_knowledge_graph = OncologyKnowledgeGraphEngine()


def get_resistance_engine() -> ResistanceIntelligenceEngine:
    return _engine


@router.get("/intelligence/{asset_id}", response_model=ResistanceIntelligence)
def get_asset_resistance_intelligence(
    asset_id: str,
    prediction_cutoff: date | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
) -> ResistanceIntelligence:
    from app.ml.router import get_shared_ml_services

    feature_store, model_registry = get_shared_ml_services()
    return get_resistance_engine().evaluate_intelligence(
        asset_id,
        prediction_cutoff or date.today(),
        tenant_id=tenant_id,
        knowledge_graph=_knowledge_graph,
        feature_store=feature_store,
        model_registry=model_registry,
    )


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
