from __future__ import annotations

from typing import List
from fastapi import APIRouter, HTTPException, Query, status

from .engine import SafetyIntelligenceEngine
from .models import (
    EvaluateSafetyRequest,
    MajorRiskSignal,
    SafetyIntelligenceProfile,
)

router = APIRouter(prefix="/api/v1/safety", tags=["Safety Intelligence Engine"])

_engine = SafetyIntelligenceEngine()


def get_safety_engine() -> SafetyIntelligenceEngine:
    return _engine


@router.get("/benchmarks", response_model=List[SafetyIntelligenceProfile])
def list_benchmark_safety_profiles() -> List[SafetyIntelligenceProfile]:
    """
    Returns safety intelligence profiles across all canonical benchmark assets
    (Zongertinib, Tucatinib, Neratinib, Poziotinib, and OX-HER2-01).
    """
    engine = get_safety_engine()
    return engine.list_benchmark_safety_profiles()


@router.get("/asset/{asset_id}", response_model=SafetyIntelligenceProfile)
def get_asset_safety_profile(asset_id: str) -> SafetyIntelligenceProfile:
    """
    Evaluates 10 core safety and toxicity dimensions:
    common adverse events, Grade >=3 adverse events, dose-limiting toxicity,
    discontinuation, organ toxicity, target-related toxicity, off-target toxicity,
    animal toxicity, therapeutic window, and dose exposure relationship.

    Produces:
    - Safety Score (0 - 100)
    - Therapeutic Index Score (0 - 100)
    - Safety Confidence (0.0 - 1.0)
    - Major Risk Signals
    Ratings: GOOD, MODERATE, HIGH RISK, INSUFFICIENT EVIDENCE.
    Strict Invariant: Do not convert missing safety evidence into a positive score.
    """
    engine = get_safety_engine()
    return engine.get_asset_safety_profile(asset_id)


@router.get("/asset/{asset_id}/risk-signals", response_model=List[MajorRiskSignal])
def get_asset_risk_signals(asset_id: str) -> List[MajorRiskSignal]:
    """
    Returns major clinical risk signals, black-box warnings, and organ alerts for an asset.
    """
    engine = get_safety_engine()
    return engine.get_major_risk_signals(asset_id)


@router.post("/evaluate", response_model=SafetyIntelligenceProfile)
def evaluate_asset_safety(request: EvaluateSafetyRequest) -> SafetyIntelligenceProfile:
    """
    Evaluates safety intelligence for a requested asset.
    """
    engine = get_safety_engine()
    return engine.evaluate_asset_safety(request)
