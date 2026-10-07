"""
Evidence Ranking Engine.

Ranks evidence candidates across the 9 canonical dimensions:
1. source quality (reputable peer-reviewed journals, regulatory filings, trial registries)
2. directness (direct clinical assay in human indication vs surrogate vs indirect)
3. recency (temporal freshness with decay penalty on obsolete evidence)
4. human relevance (direct human patients vs PDX vs animal vs cell-free assays)
5. study design (RCT double-blind > open label > prospective cohort > single arm > observational > in vitro)
6. sample size (statistical power based on cohort scale n)
7. peer review (formal peer review vs preprint vs unreviewed corporate deck)
8. confidence (calibrated probability score and variance interval)
9. temporal validity (valid within cutoff scope, no future leakage, unexpired validity)

Exposes:
- Composite ranking score (0.0 - 100.0)
- Detailed dimensional score breakdown
- Transparent ranking rationale explaining the score and tier
- Epistemic limitations & caveats
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.opportunity_engine.evidence.models import (
    ConfidenceLevel,
    EvidenceQuality,
    EvidenceConfidence,
    ProspectiveOrRetrospective,
    QualityGrade,
    RiskOfBias,
    SourceType,
)
from app.opportunity_engine.evidence.scoring import (
    DirectnessLevel,
    ModelRelevance,
    ReplicationStatus,
    StudyDesignType,
)


class EvidenceRankingTier(StrEnum):
    TIER_1_PINNACLE = "TIER_1_PINNACLE"      # Gold standard: Pivotal Phase 3 RCT, regulatory approvals, large human cohorts
    TIER_2_HIGH = "TIER_2_HIGH"              # Robust: Phase 1/2 prospective trials, high-impact peer review, large PDX
    TIER_3_MODERATE = "TIER_3_MODERATE"      # Exploratory: Preclinical pharmacology, cell lines, small observational
    TIER_4_LOW = "TIER_4_LOW"                # Preliminary: In vitro, computational, unreviewed corporate abstracts
    TIER_5_INSUFFICIENT = "TIER_5_INSUFFICIENT" # Disputed, contradicted, or temporally expired evidence


class RankingDimensionDetail(BaseModel):
    """Detailed score and justification for one of the 9 ranking dimensions."""
    model_config = ConfigDict(from_attributes=True)

    dimension: str
    weight: float
    raw_score: float = Field(ge=0.0, le=100.0)
    weighted_score: float
    justification: str


class EvidenceRankingRecord(BaseModel):
    """Ranked evidence item with complete rationale and provenance."""
    model_config = ConfigDict(from_attributes=True)

    ranking: int = Field(description="1-based integer position in rank order")
    evidence_id: str
    title: str
    source_citation: str
    source_type: str
    publication_date: Optional[date] = None

    # Scores
    composite_rank_score: float = Field(ge=0.0, le=100.0)
    ranking_tier: EvidenceRankingTier
    calibrated_confidence: float = Field(ge=0.0, le=1.0)
    is_temporally_valid: bool = True

    # 9 Dimension Scores & Weights
    dimension_scores: Dict[str, RankingDimensionDetail] = Field(default_factory=dict)

    # Rationale and transparency
    ranking_rationale: str = Field(description="Comprehensive multi-factor ranking rationale")
    key_strengths: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class EvidenceRankingResult(BaseModel):
    """Aggregate result from evidence ranking engine."""
    model_config = ConfigDict(from_attributes=True)

    query_context: Optional[str] = None
    as_of_date: date
    total_candidates: int
    ranked_evidence: List[EvidenceRankingRecord]
    ranking_summary: str


class EvidenceRankingEngine:
    """
    Ranks evidence items across 9 dimensions:
    1. source quality (15%)
    2. directness (15%)
    3. recency (10%)
    4. human relevance (15%)
    5. study design (15%)
    6. sample size (10%)
    7. peer review (10%)
    8. confidence (10%) - calibrated probability
    9. temporal validity (gatekeeper multiplier: 1.0 if valid, 0.2 if expired/leakage)
    """

    DIMENSION_WEIGHTS = {
        "source_quality": 0.15,
        "directness": 0.15,
        "recency": 0.10,
        "human_relevance": 0.15,
        "study_design": 0.15,
        "sample_size": 0.10,
        "peer_review": 0.10,
        "confidence": 0.10,
    }

    @classmethod
    def score_single_evidence(
        cls,
        evidence_id: str,
        title: str,
        source_citation: str,
        source_type: SourceType,
        directness: DirectnessLevel,
        is_human: bool,
        model_relevance: ModelRelevance,
        study_design: StudyDesignType,
        sample_size: Optional[int],
        peer_reviewed: bool,
        confidence_score: float,
        publication_date: Optional[date] = None,
        as_of_date: Optional[date] = None,
        valid_to_date: Optional[date] = None,
        prediction_cutoff: Optional[date] = None,
    ) -> EvidenceRankingRecord:
        ref_as_of = as_of_date or date.today()
        dim_details: Dict[str, RankingDimensionDetail] = {}
        strengths: List[str] = []
        limitations: List[str] = []

        # Normalize inputs if string was passed

        if isinstance(source_type, str):
            try:
                source_type = SourceType(source_type.lower())
            except ValueError:
                source_type = SourceType.PUBLICATION
        if isinstance(directness, str):
            try:
                directness = DirectnessLevel(directness.lower())
            except ValueError:
                directness = DirectnessLevel.DIRECT
        if isinstance(model_relevance, str):
            try:
                model_relevance = ModelRelevance(model_relevance.lower())
            except ValueError:
                model_relevance = ModelRelevance.DIRECT_HUMAN_CLINICAL
        if isinstance(study_design, str):
            try:
                study_design = StudyDesignType(study_design.lower())
            except ValueError:
                study_design = StudyDesignType.PHASE_1_2_SINGLE_ARM

        # 1. Source Quality (15%)
        sq_map = {
            SourceType.REGULATORY_SOURCE: (100.0, "Official Health Authority regulatory record (FDA/EMA/PMDA)."),
            SourceType.CLINICAL_TRIAL: (95.0, "Primary clinical trial protocol or registry result."),
            SourceType.PUBLICATION: (90.0, "Indexed scientific literature journal."),
            SourceType.SCIENTIFIC_DATABASE: (85.0, "Curated molecular biology database."),
            SourceType.PATENT: (80.0, "Granted patent specification."),
            SourceType.INSTITUTIONAL_SOURCE: (75.0, "Institutional cancer center protocol."),
            SourceType.CONFERENCE_ABSTRACT: (65.0, "Scientific conference abstract/poster."),
            SourceType.COMPANY_SOURCE: (55.0, "Commercial corporate deck or press disclosure."),
        }
        sq_score, sq_just = sq_map.get(source_type, (70.0, "Standard evidence source."))
        src_val = source_type.value if hasattr(source_type, "value") else str(source_type)
        if sq_score >= 90.0:
            strengths.append(f"High-quality authoritative source: {src_val}")
        else:
            limitations.append(f"Non-primary or lower authority source: {src_val}")
        dim_details["source_quality"] = RankingDimensionDetail(
            dimension="source_quality",
            weight=cls.DIMENSION_WEIGHTS["source_quality"],
            raw_score=sq_score,
            weighted_score=round(sq_score * cls.DIMENSION_WEIGHTS["source_quality"], 2),
            justification=sq_just,
        )


        # 2. Directness (15%)
        dir_map = {
            DirectnessLevel.DIRECT: (100.0, "Direct evidence testing intended asset in primary clinical cohort."),
            DirectnessLevel.PROXIMATE: (80.0, "Proximate mechanistic evidence in closely related model."),
            DirectnessLevel.SURROGATE: (60.0, "Surrogate endpoint or intermediate biomarker assessment."),
            DirectnessLevel.INDIRECT: (35.0, "Indirect distant pathway or analog extrapolation."),
        }
        dir_score, dir_just = dir_map.get(directness, (75.0, "Proximate evidence."))
        if directness == DirectnessLevel.DIRECT:
            strengths.append("Direct evidence testing asset in target disease setting")
        else:
            limitations.append(f"Indirect or surrogate evidence ({directness.value})")
        dim_details["directness"] = RankingDimensionDetail(
            dimension="directness",
            weight=cls.DIMENSION_WEIGHTS["directness"],
            raw_score=dir_score,
            weighted_score=round(dir_score * cls.DIMENSION_WEIGHTS["directness"], 2),
            justification=dir_just,
        )

        # 3. Recency (10%)
        rec_score = 80.0
        rec_just = "Moderate recency."
        if publication_date:
            age_years = (ref_as_of - publication_date).days / 365.25
            if age_years <= 1.0:
                rec_score = 100.0
                rec_just = f"Highly recent evidence published within the past year ({publication_date.isoformat()})."
                strengths.append("High recency (< 1 year old)")
            elif age_years <= 3.0:
                rec_score = 90.0
                rec_just = f"Recent evidence published within 3 years ({publication_date.isoformat()})."
            elif age_years <= 5.0:
                rec_score = 75.0
                rec_just = f"Evidence published within 5 years ({publication_date.isoformat()})."
            elif age_years <= 10.0:
                rec_score = 55.0
                rec_just = f"Older evidence published {age_years:.1f} years ago ({publication_date.isoformat()})."
                limitations.append(f"Older evidence ({age_years:.1f} years old); standard of care may have evolved")
            else:
                rec_score = 35.0
                rec_just = f"Historical evidence published over a decade ago ({publication_date.isoformat()})."
                limitations.append(f"Historical evidence ({age_years:.1f} years old)")
        dim_details["recency"] = RankingDimensionDetail(
            dimension="recency",
            weight=cls.DIMENSION_WEIGHTS["recency"],
            raw_score=rec_score,
            weighted_score=round(rec_score * cls.DIMENSION_WEIGHTS["recency"], 2),
            justification=rec_just,
        )

        # 4. Human Relevance (15%)
        hr_map = {
            ModelRelevance.DIRECT_HUMAN_CLINICAL: (100.0, "Direct human clinical trial patients."),
            ModelRelevance.PATIENT_DERIVED_XENOGRAFT: (80.0, "Patient-derived xenograft (PDX) closely recapitulating human histology."),
            ModelRelevance.SYNGENEIC_ANIMAL_MODEL: (68.0, "Immunocompetent syngeneic animal disease model."),
            ModelRelevance.ISOGENIC_ENGINEERED_LINE: (60.0, "Isogenic human CRISPR knock-in cellular line."),
            ModelRelevance.IMMORTALIZED_CELL_LINE: (45.0, "Established immortalized cell line."),
            ModelRelevance.RECOMBINANT_CELL_FREE_ASSAY: (35.0, "Cell-free biochemical recombinant protein assay."),
            ModelRelevance.COMPUTATIONAL_SILICO: (25.0, "In silico structural docking model."),
        }
        hr_score, hr_just = hr_map.get(model_relevance, (100.0 if is_human else 50.0, "Human clinical subjects" if is_human else "Preclinical model"))
        if is_human or model_relevance == ModelRelevance.DIRECT_HUMAN_CLINICAL:
            strengths.append("Direct human clinical patients")
        else:
            limitations.append(f"Preclinical non-human or cell-free model ({model_relevance.value})")
        dim_details["human_relevance"] = RankingDimensionDetail(
            dimension="human_relevance",
            weight=cls.DIMENSION_WEIGHTS["human_relevance"],
            raw_score=hr_score,
            weighted_score=round(hr_score * cls.DIMENSION_WEIGHTS["human_relevance"], 2),
            justification=hr_just,
        )

        # 5. Study Design (15%)
        sd_map = {
            StudyDesignType.RCT_DOUBLE_BLIND: (100.0, "Randomized double-blind controlled trial (Gold Standard)."),
            StudyDesignType.RCT_OPEN_LABEL: (88.0, "Randomized controlled open-label trial."),
            StudyDesignType.PROSPECTIVE_COHORT: (80.0, "Prospective pre-registered cohort study."),
            StudyDesignType.PHASE_1_2_SINGLE_ARM: (72.0, "Phase 1/2 single-arm prospective interventional trial."),
            StudyDesignType.EX_VIVO_PATIENT_TISSUE: (65.0, "Ex vivo patient primary explant."),
            StudyDesignType.IN_VIVO_ANIMAL_DISEASE_MODEL: (58.0, "In vivo disease model pharmacology."),
            StudyDesignType.RETROSPECTIVE_OBSERVATIONAL: (50.0, "Retrospective observational cohort study."),
            StudyDesignType.IN_VITRO_CELL_LINE: (42.0, "In vitro cell line culture assay."),
            StudyDesignType.BIOCHEMICAL_KINASE_ASSAY: (40.0, "Cell-free biochemical binding assay."),
            StudyDesignType.CASE_REPORT_SERIES: (35.0, "Anecdotal case report series."),
            StudyDesignType.COMPUTATIONAL_PREDICTION: (25.0, "In silico prediction."),
        }
        sd_score, sd_just = sd_map.get(study_design, (60.0, "Interventional study."))
        if sd_score >= 80.0:
            strengths.append(f"Rigorous study design: {study_design.value}")
        else:
            limitations.append(f"Study design limitations: {study_design.value}")
        dim_details["study_design"] = RankingDimensionDetail(
            dimension="study_design",
            weight=cls.DIMENSION_WEIGHTS["study_design"],
            raw_score=sd_score,
            weighted_score=round(sd_score * cls.DIMENSION_WEIGHTS["study_design"], 2),
            justification=sd_just,
        )

        # 6. Sample Size (10%)
        if sample_size is None or sample_size <= 0:
            sz_score = 30.0
            sz_just = "Sample size unreported."
            limitations.append("Unreported sample cohort size")
        elif sample_size >= 250:
            sz_score = 100.0
            sz_just = f"Adequately powered large sample size (n={sample_size})."
            strengths.append(f"Large statistical sample cohort (n={sample_size})")
        elif sample_size >= 80:
            sz_score = 85.0
            sz_just = f"Robust moderate sample size (n={sample_size})."
            strengths.append(f"Adequate cohort size (n={sample_size})")
        elif sample_size >= 25:
            sz_score = 70.0
            sz_just = f"Modest cohort size (n={sample_size})."
        elif sample_size >= 10:
            sz_score = 50.0
            sz_just = f"Small cohort size (n={sample_size})."
            limitations.append(f"Small cohort size (n={sample_size})")
        else:
            sz_score = 25.0
            sz_just = f"Very small sample size (n={sample_size})."
            limitations.append(f"Very small sample size (n={sample_size})")
        dim_details["sample_size"] = RankingDimensionDetail(
            dimension="sample_size",
            weight=cls.DIMENSION_WEIGHTS["sample_size"],
            raw_score=sz_score,
            weighted_score=round(sz_score * cls.DIMENSION_WEIGHTS["sample_size"], 2),
            justification=sz_just,
        )

        # 7. Peer Review (10%)
        if peer_reviewed:
            pr_score = 100.0
            pr_just = "Formally peer-reviewed by independent scientific reviewers."
            strengths.append("Verified peer-reviewed publication")
        else:
            pr_score = 35.0
            pr_just = "Unreviewed disclosure, preprint, or corporate presentation."
            limitations.append("Lacks independent peer review")
        dim_details["peer_review"] = RankingDimensionDetail(
            dimension="peer_review",
            weight=cls.DIMENSION_WEIGHTS["peer_review"],
            raw_score=pr_score,
            weighted_score=round(pr_score * cls.DIMENSION_WEIGHTS["peer_review"], 2),
            justification=pr_just,
        )

        # 8. Confidence (10%)
        cl_score = min(100.0, max(0.0, confidence_score * 100.0))
        cl_just = f"Calibrated certainty score of {confidence_score:.2f}."
        if confidence_score >= 0.90:
            strengths.append(f"High calibrated confidence ({confidence_score:.2f})")
        elif confidence_score < 0.70:
            limitations.append(f"Moderate/low calibrated confidence ({confidence_score:.2f})")
        dim_details["confidence"] = RankingDimensionDetail(
            dimension="confidence",
            weight=cls.DIMENSION_WEIGHTS["confidence"],
            raw_score=cl_score,
            weighted_score=round(cl_score * cls.DIMENSION_WEIGHTS["confidence"], 2),
            justification=cl_just,
        )

        # Calculate base 8-dimension weighted sum
        base_score = sum(d.weighted_score for d in dim_details.values())

        # 9. Temporal Validity (Gatekeeper & Validity Modifier)
        is_temporally_valid = True
        tv_penalty_multiplier = 1.0
        tv_notes = "Temporally valid and within cutoff bounds."

        # Anti-leakage check: If publication occurred after prediction cutoff
        if prediction_cutoff and publication_date and publication_date > prediction_cutoff:
            is_temporally_valid = False
            tv_penalty_multiplier = 0.10  # Future leakage cannot rank high
            tv_notes = f"Future information leakage: Published {publication_date} after cutoff {prediction_cutoff}."
            limitations.append(tv_notes)
        elif valid_to_date and valid_to_date < ref_as_of:
            is_temporally_valid = False
            tv_penalty_multiplier = 0.40  # Expired temporal validity
            tv_notes = f"Evidence expired on {valid_to_date.isoformat()} prior to as-of date."
            limitations.append(tv_notes)

        final_composite_score = round(base_score * tv_penalty_multiplier, 1)

        # Tier assignment
        if not is_temporally_valid:
            tier = EvidenceRankingTier.TIER_5_INSUFFICIENT
        elif final_composite_score >= 85.0:
            tier = EvidenceRankingTier.TIER_1_PINNACLE
        elif final_composite_score >= 70.0:
            tier = EvidenceRankingTier.TIER_2_HIGH
        elif final_composite_score >= 55.0:
            tier = EvidenceRankingTier.TIER_3_MODERATE
        else:
            tier = EvidenceRankingTier.TIER_4_LOW

        # Ranking Rationale Construction
        rationale_lines = [
            f"Ranked as {tier.value} with composite score {final_composite_score:.1f}/100.",
            f"Source: {sq_just}",
            f"Directness & Human Relevance: {dir_just} ({hr_just})",
            f"Study Rigor: {sd_just} {sz_just}",
            f"Peer Review & Confidence: {pr_just} {cl_just}",
        ]
        if not is_temporally_valid:
            rationale_lines.append(f"Temporal Validity Gatekeeper: {tv_notes}")
        rationale = " ".join(rationale_lines)

        return EvidenceRankingRecord(
            ranking=0,
            evidence_id=evidence_id,
            title=title,
            source_citation=source_citation,
            source_type=source_type.value,
            publication_date=publication_date,
            composite_rank_score=final_composite_score,
            ranking_tier=tier,
            calibrated_confidence=confidence_score,
            is_temporally_valid=is_temporally_valid,
            dimension_scores=dim_details,
            ranking_rationale=rationale,
            key_strengths=strengths,
            limitations=limitations,
        )

    @classmethod
    def rank_evidence_list(
        cls,
        evidence_items: List[Dict[str, Any]],
        as_of_date: Optional[date] = None,
        prediction_cutoff: Optional[date] = None,
        query_context: Optional[str] = None,
    ) -> EvidenceRankingResult:
        """
        Ranks a collection of evidence candidates descending by composite score.
        Assigns 1-based ranking and generates summary.
        """
        ref_date = as_of_date or date.today()
        scored_records: List[EvidenceRankingRecord] = []

        for item in evidence_items:
            rec = cls.score_single_evidence(
                evidence_id=str(item.get("id", uuid4())),
                title=item.get("title", "Untitled Evidence"),
                source_citation=item.get("citation", item.get("source_citation", "")),
                source_type=item.get("source_type", SourceType.PUBLICATION),
                directness=item.get("directness", DirectnessLevel.DIRECT),
                is_human=item.get("is_human", item.get("species", "Human") == "Human"),
                model_relevance=item.get("model_relevance", ModelRelevance.DIRECT_HUMAN_CLINICAL),
                study_design=item.get("study_design", StudyDesignType.PHASE_1_2_SINGLE_ARM),
                sample_size=item.get("sample_size"),
                peer_reviewed=item.get("peer_reviewed", True),
                confidence_score=float(item.get("confidence", item.get("confidence_score", 0.90))),
                publication_date=item.get("publication_date"),
                as_of_date=ref_date,
                valid_to_date=item.get("valid_to_date"),
                prediction_cutoff=prediction_cutoff,
            )
            scored_records.append(rec)

        # Sort descending by composite score, then by confidence
        scored_records.sort(key=lambda r: (r.composite_rank_score, r.calibrated_confidence), reverse=True)

        for idx, rec in enumerate(scored_records, start=1):
            rec.ranking = idx

        summary = (
            f"Ranked {len(scored_records)} evidence items as of {ref_date.isoformat()}. "
            f"Top evidence: '{scored_records[0].title if scored_records else 'None'}' "
            f"(Score: {scored_records[0].composite_rank_score if scored_records else 0.0})."
        )

        return EvidenceRankingResult(
            query_context=query_context,
            as_of_date=ref_date,
            total_candidates=len(scored_records),
            ranked_evidence=scored_records,
            ranking_summary=summary,
        )
