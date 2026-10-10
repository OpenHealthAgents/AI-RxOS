from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.opportunity_engine.decision.models import DecisionAction, DecisionResult
from app.opportunity_engine.decision.why import WhyResult


class ActionCategory(str, Enum):
    COLLECT_EVIDENCE = "collect evidence"
    CONTACT_OWNER = "contact owner"
    INITIATE_LICENSING = "initiate licensing"
    INITIATE_PARTNERSHIP = "initiate partnership"
    RUN_EXPERIMENT = "run experiment"
    INVESTIGATE_BIOMARKER = "investigate biomarker/CNS/resistance"
    TEST_COMBINATION = "test combination"
    MONITOR_TRIAL = "monitor trial/competitor"
    ESCALATE_EXPERT_REVIEW = "escalate expert review"
    AVOID = "avoid"


class ActionRecommendation(BaseModel):
    action: ActionCategory
    priority: str
    rationale: str
    decision_value: float
    urgency: float
    effort: float
    uncertainty_reduction: float
    supporting_evidence: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    lineage: dict[str, Any] = Field(default_factory=dict)


class ActionResult(BaseModel):
    asset_id: str
    tenant_id: str | None = None
    evaluation_cutoff: date
    decision: DecisionAction
    recommended_actions: list[ActionRecommendation] = Field(default_factory=list)


class ActionIntelligence:
    """Rank deterministic, evidence-traceable actions from a decision and WHY explanation."""

    def rank_actions(self, decision_result: DecisionResult, why_result: WhyResult) -> ActionResult:
        actions: list[ActionRecommendation] = []
        positive = decision_result.positive_drivers
        negative = decision_result.negative_drivers
        unknowns = why_result.unknowns or decision_result.unknowns
        evidence = why_result.supporting_evidence or decision_result.supporting_evidence
        contradictions = why_result.contradictory_evidence or decision_result.contradictory_evidence

        if decision_result.decision == DecisionAction.PURSUE:
            actions.append(self._build_action(
                ActionCategory.RUN_EXPERIMENT,
                priority="P1",
                decision_value=0.9,
                urgency=0.8,
                effort=0.6,
                uncertainty_reduction=0.65,
                rationale="This recommendation is favorable; run the next targeted experiment to reduce evidence gaps and validate the strongest drivers.",
                evidence=evidence,
                unknowns=unknowns,
                lineage={"decision": decision_result.decision.value, "drivers": positive[:3]},
            ))
            actions.append(self._build_action(
                ActionCategory.CONTACT_OWNER,
                priority="P2",
                decision_value=0.7,
                urgency=0.6,
                effort=0.3,
                uncertainty_reduction=0.45,
                rationale="Coordinate with the asset owner to accelerate decision-critical data collection.",
                evidence=evidence,
                unknowns=unknowns,
                lineage={"decision": decision_result.decision.value},
            ))

        elif decision_result.decision == DecisionAction.PARTNER:
            actions.append(self._build_action(
                ActionCategory.INITIATE_PARTNERSHIP,
                priority="P1",
                decision_value=0.85,
                urgency=0.7,
                effort=0.5,
                uncertainty_reduction=0.6,
                rationale="The profile supports partnership rather than full internal pursuit; align with a partner that can de-risk development.",
                evidence=evidence,
                unknowns=unknowns,
                lineage={"decision": decision_result.decision.value, "drivers": positive[:3]},
            ))
            actions.append(self._build_action(
                ActionCategory.COLLECT_EVIDENCE,
                priority="P2",
                decision_value=0.65,
                urgency=0.8,
                effort=0.4,
                uncertainty_reduction=0.72,
                rationale="Targeted evidence collection can reduce the remaining uncertainty before a partnership agreement.",
                evidence=evidence,
                unknowns=unknowns,
                lineage={"decision": decision_result.decision.value},
            ))

        elif decision_result.decision == DecisionAction.LICENSE:
            actions.append(self._build_action(
                ActionCategory.INITIATE_LICENSING,
                priority="P1",
                decision_value=0.9,
                urgency=0.8,
                effort=0.4,
                uncertainty_reduction=0.7,
                rationale="The strongest licensing evidence and strategic fit support a licensing path.",
                evidence=evidence,
                unknowns=unknowns,
                lineage={"decision": decision_result.decision.value, "drivers": positive[:3]},
            ))
            actions.append(self._build_action(
                ActionCategory.MONITOR_TRIAL,
                priority="P2",
                decision_value=0.6,
                urgency=0.5,
                effort=0.3,
                uncertainty_reduction=0.4,
                rationale="Monitor the competitive and clinical context to ensure licensing value remains credible.",
                evidence=evidence,
                unknowns=unknowns,
                lineage={"decision": decision_result.decision.value},
            ))

        elif decision_result.decision == DecisionAction.MONITOR:
            actions.append(self._build_action(
                ActionCategory.COLLECT_EVIDENCE,
                priority="P1",
                decision_value=0.7,
                urgency=0.8,
                effort=0.5,
                uncertainty_reduction=0.85,
                rationale="This recommendation is promising but uncertain; collect the missing evidence that can materially change the assessment.",
                evidence=evidence,
                unknowns=unknowns,
                lineage={"decision": decision_result.decision.value, "gaps": why_result.evidence_gaps[:3]},
            ))
            actions.append(self._build_action(
                ActionCategory.INVESTIGATE_BIOMARKER,
                priority="P2",
                decision_value=0.65,
                urgency=0.7,
                effort=0.6,
                uncertainty_reduction=0.78,
                rationale="Biomarker, CNS, or resistance questions remain the most actionable uncertainty drivers for this asset.",
                evidence=evidence,
                unknowns=unknowns,
                lineage={"decision": decision_result.decision.value},
            ))

        elif decision_result.decision == DecisionAction.AVOID:
            actions.append(self._build_action(
                ActionCategory.AVOID,
                priority="P1",
                decision_value=0.8,
                urgency=0.7,
                effort=0.2,
                uncertainty_reduction=0.4,
                rationale="The evidence and risk profile do not sustain a positive investment path.",
                evidence=evidence,
                unknowns=unknowns,
                lineage={"decision": decision_result.decision.value, "negative_drivers": negative[:3]},
            ))
            actions.append(self._build_action(
                ActionCategory.ESCALATE_EXPERT_REVIEW,
                priority="P2",
                decision_value=0.55,
                urgency=0.5,
                effort=0.3,
                uncertainty_reduction=0.38,
                rationale="Escalate only for a formal review of the key risk signals and contradictory evidence before final disinvestment decisions.",
                evidence=contradictions,
                unknowns=unknowns,
                lineage={"decision": decision_result.decision.value},
            ))

        else:
            actions.append(self._build_action(
                ActionCategory.COLLECT_EVIDENCE,
                priority="P1",
                decision_value=0.7,
                urgency=0.9,
                effort=0.5,
                uncertainty_reduction=0.9,
                rationale="Critical evidence is absent; targeted evidence collection is the primary action needed to resolve the insufficiency.",
                evidence=evidence,
                unknowns=unknowns,
                lineage={"decision": decision_result.decision.value, "gaps": why_result.evidence_gaps[:5]},
            ))
            actions.append(self._build_action(
                ActionCategory.ESCALATE_EXPERT_REVIEW,
                priority="P2",
                decision_value=0.6,
                urgency=0.8,
                effort=0.4,
                uncertainty_reduction=0.6,
                rationale="Escalate to experts to clarify the specific missing evidence required for a reliable decision.",
                evidence=evidence,
                unknowns=unknowns,
                lineage={"decision": decision_result.decision.value},
            ))

        if unknowns:
            actions.insert(
                0,
                self._build_action(
                    ActionCategory.COLLECT_EVIDENCE,
                    priority="P0",
                    decision_value=0.8,
                    urgency=0.9,
                    effort=0.45,
                    uncertainty_reduction=0.95,
                    rationale="The primary action is evidence collection because unknowns remain the main decision blocker.",
                    evidence=evidence,
                    unknowns=unknowns,
                    lineage={"unknowns": unknowns[:5]},
                ),
            )

        ordered = sorted(
            actions,
            key=lambda item: (
                -self._score_action(item),
                item.priority,
                item.action.value,
            ),
        )
        return ActionResult(
            asset_id=decision_result.asset_id,
            tenant_id=decision_result.tenant_id,
            evaluation_cutoff=decision_result.evaluation_cutoff,
            decision=decision_result.decision,
            recommended_actions=ordered,
        )

    def _build_action(
        self,
        action: ActionCategory,
        *,
        priority: str,
        decision_value: float,
        urgency: float,
        effort: float,
        uncertainty_reduction: float,
        rationale: str,
        evidence: list[str],
        unknowns: list[str],
        lineage: dict[str, Any],
    ) -> ActionRecommendation:
        return ActionRecommendation(
            action=action,
            priority=priority,
            rationale=rationale,
            decision_value=max(0.0, min(1.0, decision_value)),
            urgency=max(0.0, min(1.0, urgency)),
            effort=max(0.0, min(1.0, effort)),
            uncertainty_reduction=max(0.0, min(1.0, uncertainty_reduction)),
            supporting_evidence=list(dict.fromkeys(evidence))[:10],
            unknowns=list(dict.fromkeys(unknowns))[:10],
            lineage=lineage,
        )

    def _score_action(self, item: ActionRecommendation) -> float:
        return (
            item.decision_value * 0.4
            + item.urgency * 0.25
            + item.uncertainty_reduction * 0.25
            - item.effort * 0.1
        )


__all__ = ["ActionCategory", "ActionRecommendation", "ActionResult", "ActionIntelligence"]
