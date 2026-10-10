from __future__ import annotations

from datetime import date
from typing import List

from fastapi import APIRouter, Query

from app.opportunity_engine.intelligence_47_49 import CombinationIntelligence
from app.opportunity_engine.kg.engine import OncologyKnowledgeGraphEngine
from app.opportunity_engine.resistance.router import get_resistance_engine

from .engine import CombinationIntelligenceEngine
from .models import (
    CombinationIntelligenceProfile,
    EvaluateCombinationQuery,
    RecommendedCombinationStrategy,
)

router = APIRouter(prefix="/api/v1/combination", tags=["Combination Intelligence Engine"])

_engine = CombinationIntelligenceEngine()
_knowledge_graph = OncologyKnowledgeGraphEngine()


def get_combination_engine() -> CombinationIntelligenceEngine:
    return _engine


@router.get("/intelligence/{asset_id}", response_model=CombinationIntelligence)
def get_asset_combination_intelligence(
    asset_id: str,
    prediction_cutoff: date | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
) -> CombinationIntelligence:
    from app.ml.router import get_shared_ml_services

    cutoff = prediction_cutoff or date.today()
    feature_store, model_registry = get_shared_ml_services()
    resistance = get_resistance_engine().evaluate_intelligence(
        asset_id,
        cutoff,
        tenant_id=tenant_id,
        knowledge_graph=_knowledge_graph,
        feature_store=feature_store,
        model_registry=model_registry,
    )
    return get_combination_engine().evaluate_intelligence(
        asset_id,
        cutoff,
        tenant_id=tenant_id,
        resistance_intelligence=resistance,
        knowledge_graph=_knowledge_graph,
    )


@router.get("/benchmarks", response_model=List[CombinationIntelligenceProfile])
def list_benchmark_combination_profiles() -> List[CombinationIntelligenceProfile]:
    """
    Returns combination intelligence profiles across canonical benchmark assets
    (Zongertinib, Tucatinib, Neratinib, Poziotinib, and OX-HER2-01).
    """
    engine = get_combination_engine()
    return engine.list_benchmark_combination_profiles()


@router.get("/asset/{asset_id}", response_model=CombinationIntelligenceProfile)
def get_asset_combination_profile(asset_id: str) -> CombinationIntelligenceProfile:
    """
    Produces:
    - Recommended combinations for an asset addressing its resistance liabilities
    - Evaluations across all 8 core dimensions:
      mechanistic complementarity, preclinical evidence, clinical evidence,
      toxicity overlap, pharmacological feasibility, development feasibility,
      existing combinations, and competitive combinations
    - Epistemic audit distinguishing:
      clinically validated, preclinical supported, mechanistically plausible, AI-generated
    - Confidence, development risk score, and development risk tier
    """
    engine = get_combination_engine()
    return engine.get_asset_combination_profile(asset_id)


@router.get("/mechanism", response_model=List[RecommendedCombinationStrategy])
def find_combinations_for_mechanism(
    name: str = Query(..., description="Resistance mechanism name to search, e.g. 'Estrogen Receptor', 'T798M', 'PIK3CA'"),
) -> List[RecommendedCombinationStrategy]:
    """
    Finds prioritized combination strategies that address a specific resistance mechanism.
    """
    engine = get_combination_engine()
    return engine.find_combinations_for_resistance_mechanism(name)


@router.post("/evaluate", response_model=List[RecommendedCombinationStrategy])
def evaluate_combinations(query: EvaluateCombinationQuery) -> List[RecommendedCombinationStrategy]:
    """
    Evaluates and filters combinations based on criteria such as minimum confidence,
    maximum development risk tier, or inclusion of AI-generated hypotheses.
    """
    engine = get_combination_engine()
    return engine.evaluate_combinations(query)
