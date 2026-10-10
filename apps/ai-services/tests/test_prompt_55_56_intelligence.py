from __future__ import annotations

from datetime import date

from app.opportunity_engine.decision.action import ActionCategory, ActionIntelligence
from app.opportunity_engine.decision.engine import MasterDecisionEngine
from app.opportunity_engine.decision.models import DecisionAction
from app.opportunity_engine.decision.why import WhyEngine


def _signal(value: float, *, confidence: float = 0.8, status: str = "AVAILABLE", reason: str | None = None, **extra):
    payload = {"value": value, "confidence": confidence, "status": status, "reason": reason or "Test signal"}
    payload.update(extra)
    return payload


def test_why_explains_pursue_decision() -> None:
    engine = MasterDecisionEngine()
    result = engine.evaluate(
        asset_id="asset-why-pursue",
        tenant_id="tenant-1",
        evaluation_cutoff=date(2024, 1, 1),
        biology=_signal(85.0),
        clinical=_signal(80.0),
        cns=_signal(75.0),
        patient=_signal(82.0),
        safety=_signal(80.0),
        resistance=_signal(76.0),
        combination=_signal(78.0),
        competition=_signal(72.0),
        licensing=_signal(74.0),
        commercial=_signal(77.0),
        evidence_quality=_signal(0.85),
        ml_predictions=_signal(81.0, model_version="ml-v3", feature_version="feat-2"),
    )

    why = WhyEngine().explain(result, inputs={
        "biology": _signal(85.0, supporting_evidence=["PMID:1111"], contradictory_evidence=[]),
        "clinical": _signal(80.0, supporting_evidence=["NCT:2222"], contradictory_evidence=[]),
        "cns": _signal(75.0),
        "patient": _signal(82.0),
        "safety": _signal(80.0),
        "resistance": _signal(76.0),
        "combination": _signal(78.0),
        "competition": _signal(72.0),
        "licensing": _signal(74.0),
        "commercial": _signal(77.0),
        "ml_predictions": _signal(81.0, model_version="ml-v3", feature_version="feat-2"),
    })

    assert why.decision == DecisionAction.PURSUE
    assert why.supporting_evidence
    assert why.unknowns == [] or isinstance(why.unknowns, list)
    assert why.ml_contributors or why.trace
    assert "PURSUE" in why.explanation


def test_why_explains_insufficient_evidence() -> None:
    engine = MasterDecisionEngine()
    result = engine.evaluate(
        asset_id="asset-why-insufficient",
        tenant_id="tenant-1",
        evaluation_cutoff=date(2024, 1, 1),
        biology=_signal(60.0),
        clinical=_signal(65.0),
        cns=None,
        patient=_signal(55.0),
        safety=None,
        resistance=_signal(58.0),
        combination=_signal(50.0),
        competition=_signal(60.0),
        licensing=None,
        commercial=None,
        evidence_quality=_signal(0.45),
        ml_predictions=_signal(55.0),
    )
    why = WhyEngine().explain(result, inputs={
        "biology": _signal(60.0),
        "clinical": _signal(65.0),
        "cns": None,
        "patient": _signal(55.0),
        "safety": None,
        "resistance": _signal(58.0),
        "combination": _signal(50.0),
        "competition": _signal(60.0),
        "licensing": None,
        "commercial": None,
        "ml_predictions": _signal(55.0, model_version="ml-v2"),
    })
    assert result.decision == DecisionAction.INSUFFICIENT_EVIDENCE
    assert why.decision == DecisionAction.INSUFFICIENT_EVIDENCE
    assert why.evidence_gaps
    assert any("Critical evidence" in item or "insufficient" in item.lower() for item in why.evidence_gaps)


def test_why_tracks_contradictory_and_unknown_evidence() -> None:
    decision = MasterDecisionEngine().evaluate(
        asset_id="asset-why-contradict",
        tenant_id="tenant-1",
        evaluation_cutoff=date(2024, 1, 1),
        biology=_signal(70.0, supporting_evidence=["PMID:77"], contradictory_evidence=["NCT:99"]),
        clinical={"status": "UNKNOWN", "reason": "No trial readout"},
        cns={"status": "UNAVAILABLE", "reason": "No CNS ML"},
        patient=_signal(65.0),
        safety=_signal(74.0),
        resistance=_signal(60.0),
        combination=_signal(58.0),
        competition=_signal(55.0),
        licensing=_signal(72.0),
        commercial=_signal(68.0),
        evidence_quality=_signal(0.72),
        ml_predictions=_signal(64.0),
    )
    why = WhyEngine().explain(decision, inputs={
        "biology": _signal(70.0, supporting_evidence=["PMID:77"], contradictory_evidence=["NCT:99"]),
        "clinical": {"status": "UNKNOWN", "reason": "No trial readout"},
        "cns": {"status": "UNAVAILABLE", "reason": "No CNS ML"},
        "patient": _signal(65.0),
        "safety": _signal(74.0),
        "resistance": _signal(60.0),
        "combination": _signal(58.0),
        "competition": _signal(55.0),
        "licensing": _signal(72.0),
        "commercial": _signal(68.0),
    })
    assert "NCT:99" in why.contradictory_evidence
    assert any("clinical" in item.lower() or "cns" in item.lower() for item in why.unknowns)


def test_action_intelligence_ranks_actions_for_pursue() -> None:
    engine = MasterDecisionEngine()
    decision = engine.evaluate(
        asset_id="asset-action-pursue",
        tenant_id="tenant-1",
        evaluation_cutoff=date(2024, 1, 1),
        biology=_signal(86.0),
        clinical=_signal(82.0),
        cns=_signal(76.0),
        patient=_signal(81.0),
        safety=_signal(78.0),
        resistance=_signal(74.0),
        combination=_signal(77.0),
        competition=_signal(70.0),
        licensing=_signal(75.0),
        commercial=_signal(79.0),
        evidence_quality=_signal(0.8),
        ml_predictions=_signal(82.0, model_version="ml-v4", feature_version="feat-9"),
    )
    why = WhyEngine().explain(decision, inputs={
        "biology": _signal(86.0),
        "clinical": _signal(82.0),
        "cns": _signal(76.0),
        "patient": _signal(81.0),
        "safety": _signal(78.0),
        "resistance": _signal(74.0),
        "combination": _signal(77.0),
        "competition": _signal(70.0),
        "licensing": _signal(75.0),
        "commercial": _signal(79.0),
        "ml_predictions": _signal(82.0, model_version="ml-v4", feature_version="feat-9"),
    })
    actions = ActionIntelligence().rank_actions(decision, why)
    assert actions.decision == DecisionAction.PURSUE
    assert actions.recommended_actions
    assert any(item.action == ActionCategory.RUN_EXPERIMENT for item in actions.recommended_actions)
    assert actions.recommended_actions[0].priority in {"P0", "P1"}


def test_action_intelligence_maintains_tenant_and_cutoff_semantics() -> None:
    decision = MasterDecisionEngine().evaluate(
        asset_id="asset-action-monitor",
        tenant_id="tenant-beta",
        evaluation_cutoff=date(2024, 2, 1),
        biology=_signal(58.0),
        clinical=_signal(56.0),
        cns=_signal(50.0),
        patient=_signal(52.0),
        safety=_signal(57.0),
        resistance=_signal(55.0),
        combination=_signal(49.0),
        competition=_signal(62.0),
        licensing=_signal(52.0),
        commercial=_signal(61.0),
        evidence_quality=_signal(0.6),
        ml_predictions=_signal(56.0),
    )
    why = WhyEngine().explain(decision, inputs={
        "biology": _signal(58.0),
        "clinical": _signal(56.0),
        "cns": _signal(50.0),
        "patient": _signal(52.0),
        "safety": _signal(57.0),
        "resistance": _signal(55.0),
        "combination": _signal(49.0),
        "competition": _signal(62.0),
        "licensing": _signal(52.0),
        "commercial": _signal(61.0),
    })
    actions = ActionIntelligence().rank_actions(decision, why)
    assert actions.tenant_id == "tenant-beta"
    assert actions.evaluation_cutoff == date(2024, 2, 1)
    assert actions.recommended_actions


def test_action_intelligence_rejects_unsupported_actions() -> None:
    decision = MasterDecisionEngine().evaluate(
        asset_id="asset-action-unsupported",
        tenant_id="tenant-1",
        evaluation_cutoff=date(2024, 1, 1),
        biology=_signal(40.0),
        clinical=_signal(45.0),
        cns=None,
        patient={"status": "UNKNOWN", "reason": "No patient evidence"},
        safety=None,
        resistance=_signal(42.0),
        combination=_signal(38.0),
        competition=_signal(40.0),
        licensing=None,
        commercial=None,
        evidence_quality=_signal(0.3),
        ml_predictions=_signal(41.0),
    )
    why = WhyEngine().explain(decision, inputs={
        "biology": _signal(40.0),
        "clinical": _signal(45.0),
        "cns": None,
        "patient": {"status": "UNKNOWN", "reason": "No patient evidence"},
        "safety": None,
        "resistance": _signal(42.0),
        "combination": _signal(38.0),
        "competition": _signal(40.0),
        "licensing": None,
        "commercial": None,
    })
    actions = ActionIntelligence().rank_actions(decision, why)
    assert any(item.action in {ActionCategory.COLLECT_EVIDENCE, ActionCategory.ESCALATE_EXPERT_REVIEW} for item in actions.recommended_actions)
    assert ActionCategory.INITIATE_LICENSING not in {item.action for item in actions.recommended_actions}
