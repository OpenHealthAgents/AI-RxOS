from __future__ import annotations

from datetime import date

import pytest

from app.opportunity_engine.decision.engine import MasterDecisionEngine
from app.opportunity_engine.decision.models import DecisionAction, DecisionPolicy


@pytest.fixture
def engine() -> MasterDecisionEngine:
    return MasterDecisionEngine()


def _signal(value: float, *, confidence: float = 0.8, status: str = "AVAILABLE", reason: str | None = None, **extra):
    payload = {"value": value, "confidence": confidence, "status": status, "reason": reason or "Test signal"}
    payload.update(extra)
    return payload


def test_master_decision_can_pursue(engine: MasterDecisionEngine) -> None:
    result = engine.evaluate(
        asset_id="zongertinib",
        tenant_id="tenant-1",
        evaluation_cutoff=date(2024, 1, 1),
        biology=_signal(85.0),
        clinical=_signal(82.0),
        cns=_signal(75.0),
        patient=_signal(80.0),
        safety=_signal(78.0),
        resistance=_signal(74.0),
        combination=_signal(72.0),
        competition=_signal(69.0),
        licensing=_signal(60.0),
        commercial=_signal(76.0),
        evidence_quality=_signal(0.8, status="AVAILABLE"),
        ml_predictions=_signal(82.0),
    )
    assert result.decision == DecisionAction.PURSUE
    assert result.score >= 60
    assert result.confidence > 0.0
    assert result.positive_drivers
    assert result.recommended_action == "PURSUE"


def test_master_decision_can_partner(engine: MasterDecisionEngine) -> None:
    result = engine.evaluate(
        asset_id="asset-b",
        tenant_id="tenant-1",
        evaluation_cutoff=date(2024, 1, 1),
        biology=_signal(70.0),
        clinical=_signal(66.0),
        cns=_signal(58.0),
        patient=_signal(60.0),
        safety=_signal(70.0),
        resistance=_signal(58.0),
        combination=_signal(57.0),
        competition=_signal(52.0),
        licensing=_signal(63.0),
        commercial=_signal(75.0),
        evidence_quality=_signal(0.7, status="AVAILABLE"),
        ml_predictions=_signal(64.0),
    )
    assert result.decision == DecisionAction.PARTNER


def test_master_decision_can_license(engine: MasterDecisionEngine) -> None:
    result = engine.evaluate(
        asset_id="asset-c",
        tenant_id="tenant-1",
        evaluation_cutoff=date(2024, 1, 1),
        biology=_signal(68.0),
        clinical=_signal(65.0),
        cns=_signal(52.0),
        patient=_signal(42.0),
        safety=_signal(60.0),
        resistance=_signal(66.0),
        combination=_signal(48.0),
        competition=_signal(58.0),
        licensing=_signal(88.0),
        commercial=_signal(63.0),
        evidence_quality=_signal(0.78, status="AVAILABLE"),
        ml_predictions=_signal(60.0),
    )
    assert result.decision == DecisionAction.LICENSE


def test_master_decision_can_monitor(engine: MasterDecisionEngine) -> None:
    result = engine.evaluate(
        asset_id="asset-d",
        tenant_id="tenant-1",
        evaluation_cutoff=date(2024, 1, 1),
        biology=_signal(52.0),
        clinical=_signal(58.0),
        cns=_signal(49.0),
        patient=_signal(50.0),
        safety=_signal(55.0),
        resistance=_signal(53.0),
        combination=_signal(44.0),
        competition=_signal(62.0),
        licensing=_signal(50.0),
        commercial=_signal(60.0),
        evidence_quality=_signal(0.5, status="AVAILABLE"),
        ml_predictions=_signal(54.0),
    )
    assert result.decision == DecisionAction.MONITOR


def test_master_decision_can_avoid(engine: MasterDecisionEngine) -> None:
    result = engine.evaluate(
        asset_id="asset-e",
        tenant_id="tenant-1",
        evaluation_cutoff=date(2024, 1, 1),
        biology=_signal(20.0),
        clinical=_signal(22.0),
        cns=_signal(30.0),
        patient=_signal(18.0),
        safety=_signal(15.0),
        resistance=_signal(25.0),
        combination=_signal(15.0),
        competition=_signal(10.0),
        licensing=_signal(28.0),
        commercial=_signal(22.0),
        evidence_quality=_signal(0.3, status="AVAILABLE"),
        ml_predictions=_signal(19.0),
    )
    assert result.decision == DecisionAction.AVOID


def test_master_decision_rejects_insufficient_critical_evidence(engine: MasterDecisionEngine) -> None:
    result = engine.evaluate(
        asset_id="asset-f",
        tenant_id="tenant-1",
        evaluation_cutoff=date(2024, 1, 1),
        biology=_signal(65.0),
        clinical=_signal(70.0),
        cns=None,
        patient=_signal(62.0),
        safety=None,
        resistance=_signal(50.0),
        combination=_signal(55.0),
        competition=_signal(60.0),
        licensing=None,
        commercial=None,
        evidence_quality=_signal(0.4, status="AVAILABLE"),
        ml_predictions=_signal(55.0),
    )
    assert result.decision == DecisionAction.INSUFFICIENT_EVIDENCE
    assert any("Critical missing signal" in item for item in result.unknowns)


def test_master_decision_avoids_score_averaging(engine: MasterDecisionEngine) -> None:
    result = engine.evaluate(
        asset_id="zongertinib",
        tenant_id="tenant-1",
        evaluation_cutoff=date(2024, 1, 1),
        biology=_signal(90.0),
        clinical=_signal(90.0),
        cns=_signal(90.0),
        patient=_signal(90.0),
        safety=_signal(10.0),
        resistance=_signal(10.0),
        combination=_signal(90.0),
        competition=_signal(90.0),
        licensing=_signal(90.0),
        commercial=_signal(90.0),
        evidence_quality=_signal(0.9, status="AVAILABLE"),
        ml_predictions=_signal(90.0),
    )
    assert result.decision == DecisionAction.AVOID or result.decision == DecisionAction.MONITOR
    assert result.score < 100.0
    assert result.score != 90.0


def test_master_decision_respects_tenant_and_cutoff(engine: MasterDecisionEngine) -> None:
    result = engine.evaluate(
        asset_id="asset-g",
        tenant_id="tenant-alpha",
        evaluation_cutoff=date(2024, 1, 1),
        biology=_signal(73.0),
        clinical=_signal(68.0),
        cns=_signal(66.0),
        patient=_signal(71.0),
        safety=_signal(75.0),
        resistance=_signal(69.0),
        combination=_signal(70.0),
        competition=_signal(65.0),
        licensing=_signal(72.0),
        commercial=_signal(76.0),
        evidence_quality=_signal(0.8, status="AVAILABLE"),
        ml_predictions=_signal(74.0),
    )
    assert result.tenant_id == "tenant-alpha"
    assert result.evaluation_cutoff == date(2024, 1, 1)


def test_master_decision_tracks_supporting_and_contradicting_evidence(engine: MasterDecisionEngine) -> None:
    result = engine.evaluate(
        asset_id="asset-h",
        tenant_id="tenant-1",
        evaluation_cutoff=date(2024, 1, 1),
        biology=_signal(70.0, supporting_evidence=["PMID:99999"], contradictory_evidence=["NCT:12345"]),
        clinical=_signal(65.0, supporting_evidence=["NCT:0123"], contradictory_evidence=[]),
        cns=_signal(55.0),
        patient=_signal(66.0),
        safety=_signal(78.0),
        resistance=_signal(59.0),
        combination=_signal(60.0),
        competition=_signal(48.0),
        licensing=_signal(50.0),
        commercial=_signal(70.0),
        evidence_quality=_signal(0.75, status="AVAILABLE"),
        ml_predictions=_signal(68.0),
    )
    assert "PMID:99999" in result.supporting_evidence
    assert "NCT:12345" in result.contradictory_evidence


def test_master_decision_handles_unknown_inputs_without_fabrication(engine: MasterDecisionEngine) -> None:
    result = engine.evaluate(
        asset_id="asset-i",
        tenant_id="tenant-1",
        evaluation_cutoff=date(2024, 1, 1),
        biology=_signal(70.0),
        clinical={"status": "UNKNOWN", "value": None, "reason": "No measured trial success"},
        cns={"status": "UNAVAILABLE", "reason": "No CNS ML"},
        patient={"status": "UNKNOWN", "value": None},
        safety=_signal(74.0),
        resistance={"status": "UNKNOWN", "value": None},
        combination=_signal(65.0),
        competition=_signal(63.0),
        licensing={"status": "UNKNOWN", "value": None},
        commercial=_signal(58.0),
        evidence_quality={"value": 0.6, "status": "AVAILABLE"},
        ml_predictions=_signal(60.0),
    )
    assert result.decision in {DecisionAction.MONITOR, DecisionAction.INSUFFICIENT_EVIDENCE, DecisionAction.PARTNER}
    assert any("clinical" in item.lower() or "cns" in item.lower() for item in result.unknowns)


def test_master_decision_policy_is_customizable(engine: MasterDecisionEngine) -> None:
    policy = DecisionPolicy(pursue_score_floor=60.0, min_confidence=0.2)
    result = engine.evaluate(
        asset_id="asset-j",
        tenant_id="tenant-1",
        evaluation_cutoff=date(2024, 1, 1),
        biology=_signal(62.0),
        clinical=_signal(58.0),
        cns=_signal(53.0),
        patient=_signal(60.0),
        safety=_signal(57.0),
        resistance=_signal(58.0),
        combination=_signal(60.0),
        competition=_signal(50.0),
        licensing=_signal(62.0),
        commercial=_signal(59.0),
        evidence_quality=_signal(0.5, status="AVAILABLE"),
        ml_predictions=_signal(61.0),
        policy=policy,
    )
    assert result.policy_name == "phase_11_master_decision_policy"
    assert result.score >= 0.0


def test_master_decision_reproducibility(engine: MasterDecisionEngine) -> None:
    payload = {
        "biology": _signal(80.0),
        "clinical": _signal(75.0),
        "cns": _signal(70.0),
        "patient": _signal(72.0),
        "safety": _signal(79.0),
        "resistance": _signal(68.0),
        "combination": _signal(64.0),
        "competition": _signal(66.0),
        "licensing": _signal(60.0),
        "commercial": _signal(72.0),
        "evidence_quality": _signal(0.8, status="AVAILABLE"),
        "ml_predictions": _signal(74.0),
    }
    result_1 = engine.evaluate(asset_id="asset-k", tenant_id="tenant-1", evaluation_cutoff=date(2024, 1, 1), **payload)
    result_2 = engine.evaluate(asset_id="asset-k", tenant_id="tenant-1", evaluation_cutoff=date(2024, 1, 1), **payload)
    assert result_1.score == result_2.score
    assert result_1.decision == result_2.decision
    assert result_1.model_versions == result_2.model_versions
