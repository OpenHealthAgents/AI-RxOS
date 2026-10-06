from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.opportunity_engine.backtest.engine import HistoricalBacktestEngine
from app.opportunity_engine.comparison.engine import OpportunityComparisonEngine
from app.opportunity_engine.data.fixtures import (
    get_fixture_asset,
    list_fixture_assets,
)
from app.opportunity_engine.domain.schemas import (
    AssetComparisonResult,
    AssetIntelligence,
    HistoricalBacktestQuery,
    HistoricalBacktestResult,
    StrategicAction,
)
from app.opportunity_engine.patient_match.engine import (
    PatientMatchEngine,
    PatientMatchResult,
    PatientProfileQuery,
)

router = APIRouter(prefix="/api/v1/decision", tags=["Opportunity Decision Engine"])


class CompareRequest(BaseModel):
    asset_ids: List[str] = Field(default=["zongertinib", "neratinib"])
    target: str = "HER2"
    indication: str = "Breast Cancer"
    setting: str = "Metastatic"


@router.get("/assets", response_model=List[AssetIntelligence])
def list_assets(
    target: Optional[str] = Query(None, description="Target filter, e.g. HER2"),
    action: Optional[StrategicAction] = Query(None, description="Action filter, e.g. PURSUE"),
) -> List[AssetIntelligence]:
    assets = list_fixture_assets()
    if target:
        assets = [a for a in assets if a.target.lower() == target.lower()]
    if action:
        assets = [a for a in assets if a.recommendation.action == action]
    return assets


@router.get("/assets/{asset_id}", response_model=AssetIntelligence)
def get_asset(asset_id: str) -> AssetIntelligence:
    asset = get_fixture_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found.")
    return asset


@router.post("/compare", response_model=AssetComparisonResult)
def compare_assets(req: CompareRequest) -> AssetComparisonResult:
    try:
        return OpportunityComparisonEngine.compare_assets(
            asset_ids=req.asset_ids,
            target=req.target,
            indication=req.indication,
            setting=req.setting,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/patient-match", response_model=PatientMatchResult)
def match_patient(query: PatientProfileQuery) -> PatientMatchResult:
    return PatientMatchEngine.match_patient(query)


@router.post("/backtest", response_model=HistoricalBacktestResult)
def backtest(query: HistoricalBacktestQuery) -> HistoricalBacktestResult:
    try:
        return HistoricalBacktestEngine.run_backtest(query)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AssertionError as e:
        raise HTTPException(status_code=400, detail=f"Anti-leakage violation: {str(e)}")


@router.get("/opportunities")
def get_opportunity_matrix() -> dict:
    assets = list_fixture_assets()
    grouped = {
        "PURSUE": [],
        "INVESTIGATE": [],
        "PARTNER": [],
        "LICENSE": [],
        "MONITOR": [],
        "AVOID": [],
    }
    for a in assets:
        grouped[a.recommendation.action.value].append(
            {
                "id": a.id,
                "name": a.name,
                "code_name": a.code_name,
                "target": a.target,
                "stage": a.stage.value,
                "owner": a.owner,
                "development_potential_score": a.recommendation.development_potential_score,
                "badge_text": a.recommendation.badge_text,
                "rationale": a.recommendation.rationale,
            }
        )
    return {
        "categories": grouped,
        "total_assets_assessed": len(assets),
        "decision_workflow": ["DISCOVER", "EVALUATE", "UNDERSTAND", "COMPARE", "DECIDE", "VERIFY", "ACT"],
    }


@router.get("/assets/{asset_id}/evidence")
def get_asset_evidence_route(
    asset_id: str,
    cutoff_date: Optional[str] = Query(None, description="ISO date cutoff for anti-leakage evaluation"),
) -> dict:
    from datetime import date
    from uuid import UUID
    from app.opportunity_engine.evidence.service import EvidenceService

    service = EvidenceService()
    parsed_cutoff = date.fromisoformat(cutoff_date) if cutoff_date else None

    # Map slug to fixture UUID if applicable
    uuid_map = {
        "zongertinib": UUID("33333333-3333-3333-3333-333333333333"),
        "tucatinib": UUID("44444444-4444-4444-4444-444444444444"),
        "neratinib": UUID("55555555-5555-5555-5555-555555555555"),
        "poziotinib": UUID("66666666-6666-6666-6666-666666666666"),
    }
    target_uuid = uuid_map.get(asset_id.lower(), UUID("33333333-3333-3333-3333-333333333333"))
    evidence_items = service.get_asset_evidence(target_uuid, cutoff_date=parsed_cutoff)
    return {
        "asset_id": asset_id,
        "count": len(evidence_items),
        "cutoff_date": cutoff_date,
        "evidence": [ev.model_dump(mode="json") for ev in evidence_items],
    }


@router.get("/assets/{asset_id}/lineage")
def get_asset_lineage_route(asset_id: str) -> dict:
    from uuid import UUID
    from app.opportunity_engine.evidence.service import EvidenceService

    service = EvidenceService()
    zong_uuid = UUID("33333333-3333-3333-3333-333333333333")
    rec_uuid = UUID("77777777-7777-7777-7777-777777777777")
    graph = service.get_lineage_graph_for_recommendation(rec_uuid, zong_uuid)
    return graph.model_dump(mode="json")


@router.get("/assets/{asset_id}/lineage/verify")
def verify_asset_lineage_route(asset_id: str) -> dict:
    from uuid import UUID
    from app.opportunity_engine.evidence.service import EvidenceService

    service = EvidenceService()
    rec_uuid = UUID("77777777-7777-7777-7777-777777777777")
    is_complete, orphans = service.lineage_engine.verify_lineage_integrity(rec_uuid)
    return {
        "asset_id": asset_id,
        "recommendation_id": str(rec_uuid),
        "is_lineage_complete": is_complete,
        "orphaned_scores_count": len(orphans),
        "orphaned_components": orphans,
        "audit_pass": is_complete and len(orphans) == 0,
    }


@router.get("/snapshots/{asset_id}")
def get_historical_snapshot_route(
    asset_id: str,
    cutoff_date: str = Query(..., description="ISO prediction cutoff date (YYYY-MM-DD)"),
) -> dict:
    from datetime import date
    from app.opportunity_engine.temporal import (
        InformationLeakageError,
        TemporalIntelligenceEngine,
    )

    engine = TemporalIntelligenceEngine()
    try:
        parsed_cutoff = date.fromisoformat(cutoff_date)
        snapshot = engine.evaluate_historical_prediction(asset_id, parsed_cutoff)
        return snapshot.model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InformationLeakageError as e:
        raise HTTPException(status_code=400, detail=f"Temporal Leakage Violation: {str(e)}")


