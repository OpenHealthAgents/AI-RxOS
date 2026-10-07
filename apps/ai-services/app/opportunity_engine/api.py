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


@router.get("/assets/{asset_id}/provenance/graph")
def get_asset_provenance_graph_route(asset_id: str) -> dict:
    """Returns complete immutable provenance DAG with cryptographic Merkle root hash."""
    from uuid import UUID
    from app.opportunity_engine.evidence.service import EvidenceService

    service = EvidenceService()
    rec_uuid = UUID("77777777-7777-7777-7777-777777777777")
    graph = service.get_provenance_graph(rec_uuid)
    return graph.model_dump(mode="json")


@router.get("/assets/{asset_id}/provenance/traceback")
def traceback_recommendation_provenance_route(asset_id: str) -> dict:
    """
    Given a final recommendation, traces strictly backward through all 7 stages
    (decision_input -> model_output -> model_input -> feature_derivation ->
     normalization -> extraction -> source) to root evidence sources.
    """
    from uuid import UUID
    from app.opportunity_engine.evidence.service import EvidenceService

    service = EvidenceService()
    rec_uuid = UUID("77777777-7777-7777-7777-777777777777")
    result = service.trace_recommendation_provenance(rec_uuid)
    return result.model_dump(mode="json")


@router.get("/assets/{asset_id}/evidence/quality")
def get_asset_evidence_quality_route(asset_id: str) -> dict:
    """
    Returns 10-dimension evidence quality appraisals across all sources for an asset,
    exposing quality, calibrated confidence, transparent limitations, and epistemic warnings.
    """
    from uuid import UUID
    from app.opportunity_engine.evidence.service import EvidenceService

    service = EvidenceService()
    uuid_map = {
        "zongertinib": UUID("33333333-3333-3333-3333-333333333333"),
        "tucatinib": UUID("44444444-4444-4444-4444-444444444444"),
        "neratinib": UUID("55555555-5555-5555-5555-555555555555"),
        "poziotinib": UUID("66666666-6666-6666-6666-666666666666"),
    }
    target_uuid = uuid_map.get(asset_id.lower(), UUID("33333333-3333-3333-3333-333333333333"))
    evidence_items = service.get_asset_evidence(target_uuid)

    appraisals = []
    for ev in evidence_items:
        appraisal = service.get_source_appraisal(ev.id)
        if not appraisal:
            # Generate appraisal using source attributes
            appraisal = service.calculate_quality(
                peer_reviewed=ev.peer_reviewed,
                study_type=ev.study_type,
                sample_size=ev.sample_size,
                prospective=ev.prospective_or_retrospective,
                model=ev.model,
                species=ev.species,
                source_type=ev.source_type,
                publication_date=ev.publication_date,
            )
        appraisals.append({
            "source_id": ev.source_id,
            "title": ev.title,
            "overall_quality_score": appraisal.overall_quality_score,
            "quality_grade": appraisal.quality_grade.value,
            "calibrated_confidence": appraisal.calibrated_confidence,
            "confidence_level": appraisal.confidence_level.value,
            "dimension_scores": {k: v.model_dump(mode="json") for k, v in appraisal.dimension_scores.items()},
            "quality": appraisal.quality.model_dump(mode="json"),
            "confidence": appraisal.confidence.model_dump(mode="json"),
            "limitations": appraisal.limitations,
            "is_high_confidence_claim_allowed": appraisal.is_high_confidence_claim_allowed,
            "epistemic_warning": appraisal.epistemic_warning,
        })

    return {
        "asset_id": asset_id,
        "count": len(appraisals),
        "appraisals": appraisals,
    }


@router.get("/assets/{asset_id}/evidence/contradictions")
def get_asset_evidence_contradictions_route(asset_id: str) -> dict:
    """
    Returns explicit contradictory evidence pairs for an asset.
    Preserves both Claim A and Claim B with source provenance, study designs,
    quality scores, confidence levels, and mechanistic explanations.
    """
    from uuid import UUID
    from app.opportunity_engine.evidence.service import EvidenceService

    service = EvidenceService()
    uuid_map = {
        "zongertinib": UUID("33333333-3333-3333-3333-333333333333"),
        "tucatinib": UUID("44444444-4444-4444-4444-444444444444"),
        "neratinib": UUID("55555555-5555-5555-5555-555555555555"),
        "poziotinib": UUID("66666666-6666-6666-6666-666666666666"),
    }
    target_uuid = uuid_map.get(asset_id.lower(), UUID("33333333-3333-3333-3333-333333333333"))
    contradictions = service.get_asset_contradictions(target_uuid)

    return {
        "asset_id": asset_id,
        "total_contradictions": len(contradictions),
        "silent_selection_prevented": True,
        "contradictions": [c.model_dump(mode="json") for c in contradictions],
    }


@router.get("/assets/{asset_id}/evidence/contradiction-report")
def get_asset_evidence_contradiction_report_route(asset_id: str) -> dict:
    """
    Returns high-level contradiction dossier with epistemic disclaimers
    and unresolved dispute flags.
    """
    from uuid import UUID
    from app.opportunity_engine.evidence.service import EvidenceService

    service = EvidenceService()
    uuid_map = {
        "zongertinib": UUID("33333333-3333-3333-3333-333333333333"),
        "tucatinib": UUID("44444444-4444-4444-4444-444444444444"),
        "neratinib": UUID("55555555-5555-5555-5555-555555555555"),
        "poziotinib": UUID("66666666-6666-6666-6666-666666666666"),
    }
    target_uuid = uuid_map.get(asset_id.lower(), UUID("33333333-3333-3333-3333-333333333333"))
    report = service.get_asset_contradiction_report(target_uuid, asset_name=asset_id.title())
    return report.model_dump(mode="json")


@router.get("/assets/{asset_id}/evidence/temporal-query")
def query_asset_evidence_by_time_route(
    asset_id: str,
    as_of_date: Optional[str] = Query(None, description="ISO as-of / historical cutoff date (YYYY-MM-DD)"),
    start_date: Optional[str] = Query(None, description="ISO range start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="ISO range end date (YYYY-MM-DD)"),
    date_field: str = Query("any_date", description="Target temporal coordinate: publication_date, observation_date, trial_date, outcome_date, regulatory_date, licensing_date, prediction_cutoff, public_availability_date, any_date"),
    prediction_cutoff: Optional[str] = Query(None, description="Explicit prediction cutoff boundary"),
) -> dict:
    """
    Queries all evidence for an asset across the 8 scientific temporal coordinates:
    publication date, observation date, trial date, outcome date, regulatory date,
    licensing date, prediction cutoff, public availability date.
    Strictly preserves anti-leakage invariants.
    """
    from datetime import date
    from uuid import UUID
    from app.opportunity_engine.evidence.service import EvidenceService
    from app.opportunity_engine.temporal.models import TemporalDateField, TemporalQueryFilter

    service = EvidenceService()
    uuid_map = {
        "zongertinib": UUID("33333333-3333-3333-3333-333333333333"),
        "tucatinib": UUID("44444444-4444-4444-4444-444444444444"),
        "neratinib": UUID("55555555-5555-5555-5555-555555555555"),
        "poziotinib": UUID("66666666-6666-6666-6666-666666666666"),
    }
    target_uuid = uuid_map.get(asset_id.lower(), UUID("33333333-3333-3333-3333-333333333333"))

    parsed_as_of = date.fromisoformat(as_of_date) if as_of_date else None
    parsed_start = date.fromisoformat(start_date) if start_date else None
    parsed_end = date.fromisoformat(end_date) if end_date else None
    parsed_cutoff = date.fromisoformat(prediction_cutoff) if prediction_cutoff else None

    temporal_filter = TemporalQueryFilter(
        as_of_date=parsed_as_of,
        start_date=parsed_start,
        end_date=parsed_end,
        date_field=TemporalDateField(date_field),
        prediction_cutoff=parsed_cutoff,
    )

    matching_evidence = service.query_evidence_by_time(
        asset_id=target_uuid,
        filter=temporal_filter,
    )

    return {
        "asset_id": asset_id,
        "count": len(matching_evidence),
        "filter": temporal_filter.model_dump(mode="json"),
        "evidence": [ev.model_dump(mode="json") for ev in matching_evidence],
    }


@router.get("/snapshots/{asset_id}")
def get_historical_snapshot_route(
    asset_id: str,
    cutoff_date: Optional[str] = Query(None, description="ISO prediction cutoff date (YYYY-MM-DD)"),
    prediction_cutoff: Optional[str] = Query(None, description="ISO prediction cutoff date (YYYY-MM-DD)"),
    evidence_cutoff: Optional[str] = Query(None, description="ISO evidence cutoff date (YYYY-MM-DD)"),
    strict_audit: bool = Query(True, description="Enforce strict anti-leakage audit"),
) -> dict:
    """Legacy alias for historical snapshot evaluation."""
    return get_historical_snapshot_by_cutoffs_route(
        asset_id=asset_id,
        prediction_cutoff=prediction_cutoff,
        evidence_cutoff=evidence_cutoff,
        cutoff_date=cutoff_date,
        strict_audit=strict_audit,
    )


@router.post("/historical/evaluate")
def evaluate_historical_snapshot_post_route(req: dict) -> dict:
    """
    Evaluates a historical snapshot representing exactly what was knowable at cutoff.
    Enforces prediction_cutoff, evidence_cutoff, and evaluates outcome_known_at_cutoff.
    Strictly prevents future information leakage.
    """
    from datetime import date
    from app.opportunity_engine.temporal import (
        InformationLeakageError,
        TemporalIntelligenceEngine,
    )

    asset_id = req.get("asset_id")
    if not asset_id:
        raise HTTPException(status_code=400, detail="asset_id is required.")

    pred_cutoff_str = req.get("prediction_cutoff") or req.get("cutoff_date")
    if not pred_cutoff_str:
        raise HTTPException(status_code=400, detail="prediction_cutoff is required.")

    ev_cutoff_str = req.get("evidence_cutoff")
    strict_audit = req.get("strict_audit", True)

    engine = TemporalIntelligenceEngine()
    try:
        parsed_pred = date.fromisoformat(pred_cutoff_str)
        parsed_ev = date.fromisoformat(ev_cutoff_str) if ev_cutoff_str else parsed_pred
        snapshot = engine.evaluate_historical_prediction(
            asset_id=asset_id,
            prediction_cutoff=parsed_pred,
            evidence_cutoff=parsed_ev,
            strict_audit=strict_audit,
        )
        return snapshot.model_dump(mode="json")
    except InformationLeakageError as e:
        raise HTTPException(status_code=400, detail=f"Temporal Leakage Violation: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/historical/snapshots/{asset_id}")
def get_historical_snapshot_by_cutoffs_route(
    asset_id: str,
    prediction_cutoff: Optional[str] = Query(None, description="ISO prediction cutoff date (YYYY-MM-DD)"),
    evidence_cutoff: Optional[str] = Query(None, description="ISO evidence cutoff date (YYYY-MM-DD)"),
    cutoff_date: Optional[str] = Query(None, description="ISO cutoff date (YYYY-MM-DD)"),
    strict_audit: bool = Query(True, description="Enforce strict anti-leakage audit"),
) -> dict:
    """
    Retrieves historical snapshot representing exactly what was knowable at the cutoff.
    Calculates prediction_cutoff, evidence_cutoff, and outcome_known_at_cutoff.
    """
    from datetime import date
    from app.opportunity_engine.temporal import (
        InformationLeakageError,
        TemporalIntelligenceEngine,
    )

    effective_pred_str = prediction_cutoff or cutoff_date
    if not effective_pred_str:
        raise HTTPException(status_code=400, detail="prediction_cutoff or cutoff_date is required.")

    engine = TemporalIntelligenceEngine()
    try:
        parsed_pred = date.fromisoformat(effective_pred_str)
        parsed_ev = date.fromisoformat(evidence_cutoff) if evidence_cutoff else parsed_pred
        snapshot = engine.evaluate_historical_prediction(
            asset_id=asset_id,
            prediction_cutoff=parsed_pred,
            evidence_cutoff=parsed_ev,
            strict_audit=strict_audit,
        )
        return snapshot.model_dump(mode="json")
    except InformationLeakageError as e:
        raise HTTPException(status_code=400, detail=f"Temporal Leakage Violation: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/historical/batch-evaluate")
def batch_evaluate_historical_route(req: dict) -> dict:
    """
    Batch evaluates a cohort of assets at an exact historical cutoff.
    """
    from datetime import date
    from app.opportunity_engine.temporal import (
        InformationLeakageError,
        TemporalIntelligenceEngine,
    )

    asset_ids = req.get("asset_ids", [])
    if not asset_ids:
        raise HTTPException(status_code=400, detail="asset_ids list is required.")

    pred_cutoff_str = req.get("prediction_cutoff") or req.get("cutoff_date")
    if not pred_cutoff_str:
        raise HTTPException(status_code=400, detail="prediction_cutoff is required.")

    ev_cutoff_str = req.get("evidence_cutoff")
    strict_audit = req.get("strict_audit", True)

    engine = TemporalIntelligenceEngine()
    try:
        parsed_pred = date.fromisoformat(pred_cutoff_str)
        parsed_ev = date.fromisoformat(ev_cutoff_str) if ev_cutoff_str else parsed_pred
        snapshots = engine.batch_evaluate_historical(
            asset_ids=asset_ids,
            prediction_cutoff=parsed_pred,
            evidence_cutoff=parsed_ev,
            strict_audit=strict_audit,
        )
        return {
            "prediction_cutoff": parsed_pred.isoformat(),
            "evidence_cutoff": parsed_ev.isoformat(),
            "total_evaluated": len(snapshots),
            "snapshots": [s.model_dump(mode="json") for s in snapshots],
        }
    except InformationLeakageError as e:
        raise HTTPException(status_code=400, detail=f"Temporal Leakage Violation: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/historical/timeline/{asset_id}")
def get_historical_timeline_route(asset_id: str) -> dict:
    """
    Returns progressive historical evaluation timeline across key milestones for an asset.
    """
    from app.opportunity_engine.temporal import TemporalIntelligenceEngine

    engine = TemporalIntelligenceEngine()
    try:
        timeline = engine.get_historical_timeline(asset_id)
        return timeline.model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==============================================================================
# Evidence Ranking Endpoints
# ==============================================================================

@router.get("/evidence/ranked/{asset_id}")
def get_ranked_asset_evidence(
    asset_id: str,
    as_of: Optional[str] = Query(None, description="As-of evaluation date YYYY-MM-DD"),
    cutoff: Optional[str] = Query(None, description="Prediction cutoff date YYYY-MM-DD"),
) -> dict:
    """
    Ranks all evidence for an asset across the 9 canonical dimensions:
    source quality, directness, recency, human relevance, study design,
    sample size, peer review, confidence, temporal validity.
    Returns ranked evidence with ranking rationale and transparent strengths/limitations.
    """
    from datetime import date
    from uuid import UUID
    from app.opportunity_engine.evidence import EvidenceService

    parsed_as_of = date.fromisoformat(as_of) if as_of else None
    parsed_cutoff = date.fromisoformat(cutoff) if cutoff else None

    service = EvidenceService()
    try:
        uid = UUID(asset_id) if len(asset_id) == 36 else UUID("33333333-3333-3333-3333-333333333333")
    except ValueError:
        uid = UUID("33333333-3333-3333-3333-333333333333")

    result = service.rank_asset_evidence(
        asset_id=uid,
        as_of_date=parsed_as_of,
        prediction_cutoff=parsed_cutoff,
    )
    return result.model_dump(mode="json")


@router.post("/evidence/rank")
def rank_custom_evidence_list(
    payload: dict,
) -> dict:
    """
    Ranks arbitrary evidence items using the 9-dimensional ranking engine.
    """
    from datetime import date
    from app.opportunity_engine.evidence import EvidenceRankingEngine

    items = payload.get("evidence_items", [])
    as_of_str = payload.get("as_of_date")
    cutoff_str = payload.get("prediction_cutoff")
    context = payload.get("query_context")

    as_of = date.fromisoformat(as_of_str) if as_of_str else None
    cutoff = date.fromisoformat(cutoff_str) if cutoff_str else None

    # Parse publication_date if string
    for it in items:
        if isinstance(it.get("publication_date"), str):
            it["publication_date"] = date.fromisoformat(it["publication_date"])

    result = EvidenceRankingEngine.rank_evidence_list(
        evidence_items=items,
        as_of_date=as_of,
        prediction_cutoff=cutoff,
        query_context=context,
    )
    return result.model_dump(mode="json")




