from __future__ import annotations

from datetime import date
from typing import List

from fastapi import APIRouter, Depends, Query

from app.opportunity_engine.biology.router import get_biology_engine
from app.opportunity_engine.clinical.router import get_clinical_engine
from app.opportunity_engine.intelligence_47_49 import PatientMatchIntelligence
from app.opportunity_engine.request_context import _trusted_tenant_id
from app.opportunity_engine.kg.engine import OncologyKnowledgeGraphEngine

from .engine import PatientMatchEngine
from .models import (
    AssetPatientMatchProfile,
    PatientCohortQuery,
    PatientMatchScenarioResponse,
)

router = APIRouter(prefix="/api/v1/patient-match", tags=["PatientMatch Population Intelligence Engine"])

_engine = PatientMatchEngine()
_knowledge_graph = OncologyKnowledgeGraphEngine()


def get_patient_match_engine() -> PatientMatchEngine:
    return _engine


@router.get("/intelligence/{asset_id}", response_model=PatientMatchIntelligence)
def get_asset_patient_match_intelligence(
    asset_id: str,
    prediction_cutoff: date | None = Query(default=None),
    tenant_id: str | None = Depends(_trusted_tenant_id),
) -> PatientMatchIntelligence:
    from app.ml.router import get_shared_ml_services

    cutoff = prediction_cutoff or date.today()
    feature_store, model_registry = get_shared_ml_services()
    biology = get_biology_engine().evaluate_intelligence(
        asset_id,
        cutoff,
        tenant_id=tenant_id,
        knowledge_graph=_knowledge_graph,
        feature_store=feature_store,
        model_registry=model_registry,
    )
    clinical = get_clinical_engine().evaluate_intelligence(
        asset_id,
        cutoff,
        tenant_id=tenant_id,
        feature_store=feature_store,
        model_registry=model_registry,
    )
    return get_patient_match_engine().evaluate_intelligence(
        asset_id,
        cutoff,
        tenant_id=tenant_id,
        feature_store=feature_store,
        model_registry=model_registry,
        biology_intelligence=biology,
        clinical_intelligence=clinical,
    )


@router.get("/benchmarks", response_model=List[AssetPatientMatchProfile])
def list_benchmark_patient_match_profiles() -> List[AssetPatientMatchProfile]:
    """
    Returns population matching intelligence profiles for all canonical benchmark assets
    (Zongertinib, Tucatinib, Poziotinib, Neratinib, and OX-HER2-01).
    """
    engine = get_patient_match_engine()
    return engine.list_benchmark_profiles()


@router.get("/asset/{asset_id}", response_model=AssetPatientMatchProfile)
def get_asset_patient_match(asset_id: str) -> AssetPatientMatchProfile:
    """
    Answers: 'Which patients are most likely to benefit from this asset?'
    Evaluates:
    - mutation, expression, amplification, protein expression, biomarker,
      disease subtype, prior therapy, resistance state, line of therapy,
      CNS status, clinical evidence, mechanism.
    Produces:
    - Best Patient Population
    - Secondary Patient Population
    - Excluded/Low-Likelihood Population
    - Biomarker Strategy
    - Patient Match Score
    - Confidence
    Provides evidence for each population recommendation.
    Regulatory disclaimer included.
    """
    engine = get_patient_match_engine()
    profile = engine.get_asset_patient_match(asset_id)
    return profile


@router.post("/scenario", response_model=PatientMatchScenarioResponse)
def match_cohort_scenario(query: PatientCohortQuery) -> PatientMatchScenarioResponse:
    """
    Evaluates an oncology patient cohort scenario across drug assets.
    Example scenario: 'ER+/HER2-mutant breast cancer after CDK4/6 progression'.
    Identifies best matching asset, ranked alternatives, combination partners, and evidence.
    """
    engine = get_patient_match_engine()
    return engine.match_cohort_scenario(query)
