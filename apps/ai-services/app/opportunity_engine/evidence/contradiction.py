from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.opportunity_engine.domain.canonical_model import EvidencePolarity
from .models import (
    EvidenceConfidence,
    EvidenceQuality,
    EvidenceSource,
)
from .scoring import StudyDesignType


class DisagreementCategory(StrEnum):
    EFFICACY_DIVERGENCE = "efficacy_divergence"
    SAFETY_TOXICITY_CONFLICT = "safety_toxicity_conflict"
    CNS_PENETRATION_DISCREPANCY = "cns_penetration_discrepancy"
    RESISTANCE_EMERGENCE_DIVERGENCE = "resistance_emergence_divergence"
    SELECTIVITY_MARGIN_DISPUTE = "selectivity_margin_dispute"
    BIOMARKER_STRATIFICATION_DISCORDANCE = "biomarker_stratification_discordance"


class DisagreementResolutionStatus(StrEnum):
    UNRESOLVED_DISPUTE = "unresolved_dispute"
    PARTIALLY_EXPLAINED = "partially_explained"
    RESOLVED_BY_SUPERIOR_DESIGN = "resolved_by_superior_design"
    UNDER_ACTIVE_INVESTIGATION = "under_active_investigation"


class SilentSelectionViolationError(ValueError):
    """
    Raised when an automated pipeline, decision engine, or heuristic
    attempts to silently discard, suppress, or pick one credible source
    over another without explicitly recording and surfacing the contradiction.
    """
    pass


class ContradictoryClaim(BaseModel):
    """
    Structured claim participant in an explicit contradiction pair.
    Captures full provenance, dates, study design, quality, and confidence.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    claim_text: str
    polarity: EvidencePolarity
    source: EvidenceSource
    date: date
    study_design: StudyDesignType
    quality: EvidenceQuality
    confidence: EvidenceConfidence
    numeric_measurement: Optional[str] = None
    observed_endpoint: Optional[str] = None
    sample_size: Optional[int] = None


class ContradictionRecord(BaseModel):
    """
    Immutable pair of disagreeing claims with comparative deltas,
    mechanistic explanation, and epistemic guardrails.
    Never silently selects one claim.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    topic: str
    parameter_name: str
    category: DisagreementCategory
    status: DisagreementResolutionStatus = DisagreementResolutionStatus.UNRESOLVED_DISPUTE
    claim_a: ContradictoryClaim
    claim_b: ContradictoryClaim
    possible_explanation: str
    epistemic_warning: str
    resolution_recommendation: str
    quality_delta: float = 0.0
    confidence_delta: float = 0.0
    silent_selection_prevented: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="before")
    @classmethod
    def calculate_deltas_and_validate(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        claim_a = data.get("claim_a")
        claim_b = data.get("claim_b")

        if claim_a and claim_b:
            # Extract quality scores
            q_a = (
                claim_a.quality.quality_score
                if hasattr(claim_a, "quality")
                else claim_a.get("quality", {}).get("quality_score", 0.0)
            )
            q_b = (
                claim_b.quality.quality_score
                if hasattr(claim_b, "quality")
                else claim_b.get("quality", {}).get("quality_score", 0.0)
            )
            data["quality_delta"] = round(abs(float(q_a) - float(q_b)), 2)

            # Extract confidence scores
            c_a = (
                claim_a.confidence.score
                if hasattr(claim_a, "confidence")
                else claim_a.get("confidence", {}).get("score", 0.0)
            )
            c_b = (
                claim_b.confidence.score
                if hasattr(claim_b, "confidence")
                else claim_b.get("confidence", {}).get("score", 0.0)
            )
            data["confidence_delta"] = round(abs(float(c_a) - float(c_b)), 3)

            # Generate default epistemic warning if omitted
            if "epistemic_warning" not in data or not data["epistemic_warning"]:
                data["epistemic_warning"] = (
                    f"EPISTEMIC DISAGREEMENT DETECTED: Two credible sources disagree on '{data.get('topic', 'parameter')}'. "
                    f"Neither claim has been suppressed. Quality delta: {data['quality_delta']} pts; "
                    f"Confidence delta: {data['confidence_delta']}. Evaluate possible methodological divergence."
                )

        return data


class ContradictionReport(BaseModel):
    """
    Asset-level summary of all identified evidence contradictions.
    """
    model_config = ConfigDict(from_attributes=True)

    asset_id: UUID
    asset_name: str
    total_contradictions: int
    has_unresolved_disputes: bool
    contradictions: List[ContradictionRecord]
    epistemic_disclaimer: str = (
        "Zero-Silent-Selection Guarantee: Conflicting findings from peer-reviewed "
        "or clinical trial sources are retained in full. Decisions must not assume a "
        "favorable outcome until conflicting signals are adjudicated by confirmatory data."
    )


class ContradictionEngine:
    """
    Engine responsible for detecting, registering, explaining, and surfacing
    contradictory scientific evidence without silent suppression.
    """

    def __init__(self) -> None:
        self._contradictions: Dict[UUID, ContradictionRecord] = {}

    def register_contradiction(self, record: ContradictionRecord) -> ContradictionRecord:
        """Explicitly registers a contradictory evidence record."""
        # Enforce invariant: both claims must be present and distinct
        if record.claim_a.id == record.claim_b.id and record.claim_a.source.id == record.claim_b.source.id:
            raise ValueError("Contradiction requires two distinct claims or sources.")

        self._contradictions[record.id] = record
        return record

    def build_contradiction_pair(
        self,
        asset_id: UUID,
        topic: str,
        parameter_name: str,
        category: DisagreementCategory,
        claim_a: ContradictoryClaim,
        claim_b: ContradictoryClaim,
        possible_explanation: Optional[str] = None,
        status: DisagreementResolutionStatus = DisagreementResolutionStatus.UNRESOLVED_DISPUTE,
        resolution_recommendation: Optional[str] = None,
    ) -> ContradictionRecord:
        """
        Creates and stores a validated contradiction record for Claim A and Claim B.
        """
        explanation = possible_explanation or self.synthesize_explanation(category, claim_a, claim_b)
        recommendation = resolution_recommendation or (
            f"Commission prospective confirmatory protocol or stratified cohort testing to adjudicate '{parameter_name}'."
        )

        record = ContradictionRecord(
            asset_id=asset_id,
            topic=topic,
            parameter_name=parameter_name,
            category=category,
            status=status,
            claim_a=claim_a,
            claim_b=claim_b,
            possible_explanation=explanation,
            resolution_recommendation=recommendation,
        )
        return self.register_contradiction(record)

    def adjudicate_without_suppression(
        self,
        claim_a: ContradictoryClaim,
        claim_b: ContradictoryClaim,
        allow_silent_drop: bool = False,
    ) -> ContradictionRecord:
        """
        Adjudicates disagreement between two claims while strictly forbidding silent drop.
        """
        if allow_silent_drop:
            raise SilentSelectionViolationError(
                "VIOLATION: Silent selection is strictly prohibited by epistemic invariants. "
                "Both Claim A and Claim B must be preserved and surfaced to decision makers."
            )

        category = DisagreementCategory.EFFICACY_DIVERGENCE
        if "toxicity" in claim_a.claim_text.lower() or "safety" in claim_a.claim_text.lower():
            category = DisagreementCategory.SAFETY_TOXICITY_CONFLICT
        elif "cns" in claim_a.claim_text.lower() or "brain" in claim_a.claim_text.lower():
            category = DisagreementCategory.CNS_PENETRATION_DISCREPANCY

        record = ContradictionRecord(
            asset_id=claim_a.source.id,
            topic=f"Dispute: {claim_a.observed_endpoint or 'Observed Endpoint'}",
            parameter_name=claim_a.observed_endpoint or "endpoint",
            category=category,
            claim_a=claim_a,
            claim_b=claim_b,
            possible_explanation=self.synthesize_explanation(category, claim_a, claim_b),
            resolution_recommendation="Surface both claims in decision dossier with quality weighting.",
        )
        return self.register_contradiction(record)

    def get_contradictions_for_asset(self, asset_id: UUID) -> List[ContradictionRecord]:
        """Returns all registered contradictions for a specific asset."""
        return [c for c in self._contradictions.values() if c.asset_id == asset_id]

    def generate_contradiction_report(self, asset_id: UUID, asset_name: str) -> ContradictionReport:
        """Compiles a complete contradiction report for the asset."""
        contradictions = self.get_contradictions_for_asset(asset_id)
        has_unresolved = any(
            c.status == DisagreementResolutionStatus.UNRESOLVED_DISPUTE for c in contradictions
        )
        return ContradictionReport(
            asset_id=asset_id,
            asset_name=asset_name,
            total_contradictions=len(contradictions),
            has_unresolved_disputes=has_unresolved,
            contradictions=contradictions,
        )

    @staticmethod
    def synthesize_explanation(
        category: DisagreementCategory,
        claim_a: ContradictoryClaim,
        claim_b: ContradictoryClaim,
    ) -> str:
        """
        Formulates a scientifically plausible explanation for divergent findings
        based on study designs, sample sizes, publication dates, and biological context.
        """
        explanations: List[str] = []

        # 1. Study design disparity
        if claim_a.study_design != claim_b.study_design:
            explanations.append(
                f"Design disparity: Claim A utilized '{claim_a.study_design.value}' whereas "
                f"Claim B utilized '{claim_b.study_design.value}'. Clinical outcomes frequently diverge "
                f"from cell-free or preclinical disease models."
            )

        # 2. Sample size disparity
        if claim_a.sample_size and claim_b.sample_size:
            ratio = max(claim_a.sample_size, claim_b.sample_size) / max(min(claim_a.sample_size, claim_b.sample_size), 1)
            if ratio >= 3.0:
                larger = "Claim A" if claim_a.sample_size > claim_b.sample_size else "Claim B"
                explanations.append(
                    f"Sample size power divergence: {larger} evaluated N={max(claim_a.sample_size, claim_b.sample_size)} "
                    f"patients/samples compared to N={min(claim_a.sample_size, claim_b.sample_size)}, resulting in tighter confidence intervals."
                )

        # 3. Temporal evolution / recency
        if claim_a.date != claim_b.date:
            newer = "Claim A" if claim_a.date > claim_b.date else "Claim B"
            explanations.append(
                f"Temporal evolution: {newer} reflects newer data ({max(claim_a.date, claim_b.date)} vs {min(claim_a.date, claim_b.date)}), "
                f"which may incorporate optimized dosing schedules, enriched biomarker selection, or modern supportive care."
            )

        # 4. Domain-specific mechanistic hypotheses
        if category == DisagreementCategory.CNS_PENETRATION_DISCREPANCY:
            explanations.append(
                "Mechanistic hypothesis: Discrepancy may arise from active P-gp/BCRP efflux at human blood-brain barrier "
                "that is absent in cell-free permeability assays, or differential cerebrospinal fluid vs brain parenchymal partitioning."
            )
        elif category == DisagreementCategory.SAFETY_TOXICITY_CONFLICT:
            explanations.append(
                "Mechanistic hypothesis: Dose escalation intensity, prophylactic loperamide protocols, or patient performance status (ECOG 0 vs 1-2) "
                "commonly account for reported disparities in Grade 3+ diarrhea and adverse event rates."
            )
        elif category == DisagreementCategory.SELECTIVITY_MARGIN_DISPUTE:
            explanations.append(
                "Assay condition hypothesis: Discrepancy in wild-type EGFR sparing ratios is frequently caused by variations in ATP concentration "
                "([Km] vs 1mM physiological ATP) in biochemical kinase panels vs cellular auto-phosphorylation assays."
            )
        elif category == DisagreementCategory.RESISTANCE_EMERGENCE_DIVERGENCE:
            explanations.append(
                "Resistance profile hypothesis: Prior lines of therapy (e.g. heavily pretreated post-T-DXd vs naive) select for "
                "distinct secondary resistance mutations (e.g. C805S vs bypass MET amplification)."
            )

        if not explanations:
            return (
                "Observed divergence is currently unexplained by metadata differences. "
                "Differences in patient baseline characteristics, mutation allele frequencies, or assay calibration require investigation."
            )

        return " ".join(explanations)
