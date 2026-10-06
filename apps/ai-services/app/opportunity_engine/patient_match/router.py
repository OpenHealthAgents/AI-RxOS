from __future__ import annotations

from typing import List
from fastapi import APIRouter, HTTPException, status

from .engine import PatientMatchEngine
from .models import (
    AssetPatientMatchProfile,
    PatientCohortQuery,
    PatientMatchScenarioResponse,
)

router = APIRouter(prefix="/api/v1/patient-match", tags=["PatientMatch Population Intelligence Engine"])

_engine = PatientMatchEngine()


def get_patient_match_engine() -> PatientMatchEngine:
    return _engine


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
