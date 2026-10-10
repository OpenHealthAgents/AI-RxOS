from __future__ import annotations

from datetime import date
from typing import List

from fastapi import APIRouter, HTTPException, Query, status

from .engine import CNSIntelligenceEngine
from .models import (
    CNSIntelligence,
    CNSIntelligenceProfile,
    EvaluateAssetCNSRequest,
    EvaluateAssetCNSResponse,
    RawCNSObservation,
)

router = APIRouter(prefix="/api/v1/cns", tags=["CNS Intelligence Engine"])

_engine = CNSIntelligenceEngine()


def get_cns_engine() -> CNSIntelligenceEngine:
    return _engine


@router.get("/benchmarks", response_model=List[CNSIntelligenceProfile])
def list_benchmark_cns_profiles() -> List[CNSIntelligenceProfile]:
    """
    Returns evaluated CNS intelligence profiles for all canonical benchmark assets
    (Tucatinib, Zongertinib, OX-HER2-01, Neratinib, and Poziotinib).
    """
    engine = get_cns_engine()
    return engine.list_benchmark_profiles()


@router.get("/profile/{asset_id}", response_model=CNSIntelligenceProfile)
def get_asset_cns_profile(asset_id: str) -> CNSIntelligenceProfile:
    """
    Retrieves the CNS intelligence profile for a specific asset,
    evaluating Kp, Kp,uu, CSF exposure, Cu,brain, BBB penetration, brain tumor exposure,
    intracranial response, CNS progression, and brain metastasis response.
    """
    engine = get_cns_engine()
    profile = engine.get_benchmark_profile(asset_id)
    if not profile.raw_observations and asset_id not in ("tucatinib", "zongertinib", "ox-her2-01", "neratinib", "poziotinib"):
        raise HTTPException(status_code=404, detail=f"No CNS observations found for asset '{asset_id}'")
    return profile


@router.get("/intelligence/{asset_id}", response_model=CNSIntelligence)
def get_asset_cns_intelligence(
    asset_id: str,
    prediction_cutoff: date | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
) -> CNSIntelligence:
    cutoff = prediction_cutoff or date.today()
    from app.ml.router import get_shared_ml_services

    feature_store, model_registry = get_shared_ml_services()
    return get_cns_engine().evaluate_intelligence(
        asset_id,
        cutoff,
        tenant_id=tenant_id,
        feature_store=feature_store,
        model_registry=model_registry,
    )


@router.post("/evaluate", response_model=EvaluateAssetCNSResponse)
def evaluate_asset_cns(req: EvaluateAssetCNSRequest) -> EvaluateAssetCNSResponse:
    """
    Evaluates an asset's CNS profile from provided or stored raw observations.
    Normalizes values across species and conditions.
    Calculates:
    - CNS Exposure Score
    - CNS Activity Score
    - CNS Translational Confidence
    Enforces invariant: never infer clinical CNS efficacy solely from physicochemical properties.
    """
    engine = get_cns_engine()
    profile = engine.evaluate_asset(
        asset_id=req.asset_id,
        asset_name=req.asset_name,
        custom_observations=req.custom_observations,
    )
    return EvaluateAssetCNSResponse(profile=profile)


@router.get("/observations/{asset_id}", response_model=List[RawCNSObservation])
def get_raw_cns_observations(asset_id: str) -> List[RawCNSObservation]:
    """
    Retrieves the raw empirical CNS observations stored for an asset.
    """
    engine = get_cns_engine()
    return engine.get_raw_observations_for_asset(asset_id)
