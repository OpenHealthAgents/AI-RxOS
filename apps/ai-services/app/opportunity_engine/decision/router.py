from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .action import ActionIntelligence, ActionResult
from .engine import MasterDecisionEngine
from .models import DecisionAction, DecisionPolicy, DecisionRequest, DecisionResult
from .why import WhyEngine, WhyResult

router = APIRouter(prefix="/api/v1/decision", tags=["Master Decision Engine"])
_engine = MasterDecisionEngine()
_why_engine = WhyEngine()
_action_engine = ActionIntelligence()


@router.post("/master", response_model=DecisionResult)
def evaluate_master_decision(req: DecisionRequest) -> DecisionResult:
    try:
        return _engine.evaluate_request(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/why", response_model=WhyResult)
def explain_master_decision(req: DecisionRequest) -> WhyResult:
    try:
        decision = _engine.evaluate_request(req)
        return _why_engine.explain(decision, inputs={
            "biology": req.biology,
            "clinical": req.clinical,
            "cns": req.cns,
            "patient": req.patient,
            "safety": req.safety,
            "resistance": req.resistance,
            "combination": req.combination,
            "competition": req.competition,
            "licensing": req.licensing,
            "commercial": req.commercial,
            "evidence_quality": req.evidence_quality,
            "ml_predictions": req.ml_predictions,
        })
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/actions", response_model=ActionResult)
def rank_actions_for_decision(req: DecisionRequest) -> ActionResult:
    try:
        decision = _engine.evaluate_request(req)
        why = _why_engine.explain(decision, inputs={
            "biology": req.biology,
            "clinical": req.clinical,
            "cns": req.cns,
            "patient": req.patient,
            "safety": req.safety,
            "resistance": req.resistance,
            "combination": req.combination,
            "competition": req.competition,
            "licensing": req.licensing,
            "commercial": req.commercial,
            "evidence_quality": req.evidence_quality,
            "ml_predictions": req.ml_predictions,
        })
        return _action_engine.rank_actions(decision, why)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/master", response_model=DecisionResult)
def get_master_decision(
    asset_id: str,
    tenant_id: str | None = Query(default=None),
    cutoff: str | None = Query(default=None, alias="cutoff"),
    policy_name: str | None = Query(default=None),
) -> DecisionResult:
    payload: dict[str, Any] = {
        "asset_id": asset_id,
        "tenant_id": tenant_id,
        "evaluation_cutoff": cutoff or date.today().isoformat(),
        "policy": DecisionPolicy(name=policy_name or "phase_11_master_decision_policy"),
    }
    # The master decision engine is intentionally deterministic and uses explicit policy-driven scoring.
    return _engine.evaluate(**payload)
