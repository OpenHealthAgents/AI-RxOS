from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from .models import (
    ConfidenceLevel,
    EvidenceQuality,
    EvidenceConfidence,
    ProspectiveOrRetrospective,
    QualityGrade,
    RiskOfBias,
    SourceType,
)


class StudyDesignType(StrEnum):
    RCT_DOUBLE_BLIND = "rct_double_blind"
    RCT_OPEN_LABEL = "rct_open_label"
    PROSPECTIVE_COHORT = "prospective_cohort"
    PHASE_1_2_SINGLE_ARM = "phase_1_2_single_arm"
    RETROSPECTIVE_OBSERVATIONAL = "retrospective_observational"
    IN_VIVO_ANIMAL_DISEASE_MODEL = "in_vivo_animal_disease_model"
    EX_VIVO_PATIENT_TISSUE = "ex_vivo_patient_tissue"
    IN_VITRO_CELL_LINE = "in_vitro_cell_line"
    BIOCHEMICAL_KINASE_ASSAY = "biochemical_kinase_assay"
    CASE_REPORT_SERIES = "case_report_series"
    COMPUTATIONAL_PREDICTION = "computational_prediction"


class ModelRelevance(StrEnum):
    DIRECT_HUMAN_CLINICAL = "direct_human_clinical"
    PATIENT_DERIVED_XENOGRAFT = "patient_derived_xenograft"
    SYNGENEIC_ANIMAL_MODEL = "syngeneic_animal_model"
    ISOGENIC_ENGINEERED_LINE = "isogenic_engineered_line"
    IMMORTALIZED_CELL_LINE = "immortalized_cell_line"
    RECOMBINANT_CELL_FREE_ASSAY = "recombinant_cell_free_assay"
    COMPUTATIONAL_SILICO = "computational_silico"


class DirectnessLevel(StrEnum):
    DIRECT = "direct"                  # Direct test of exact asset in primary human indication
    PROXIMATE = "proximate"            # Highly related model / mechanistic proof in relevant species
    SURROGATE = "surrogate"            # Surrogate endpoint or intermediate biomarker
    INDIRECT = "indirect"              # Distant analog or general pathway modulation


class ReplicationStatus(StrEnum):
    INDEPENDENTLY_REPLICATED = "independently_replicated"   # Confirmed by independent lab/consortium
    INTERNALLY_REPLICATED = "internally_replicated"         # Replicated across distinct cohorts/runs
    SINGLE_STUDY_UNREPLICATED = "single_study_unreplicated" # Only one isolated report
    CONTRADICTED = "contradicted"                           # Disputed by conflicting follow-up studies


class LowEvidenceConversionError(ValueError):
    """
    Raised when an evaluation pipeline attempts to inflate low-evidence or low-rigor
    observations into high-confidence claims or recommendations.
    Strict epistemic invariant: Never convert low evidence into high-confidence claims.
    """
    pass


class QualityDimensionScore(BaseModel):
    """Score and rationale for a single evidence quality dimension."""
    model_config = ConfigDict(from_attributes=True)
    dimension: str
    weight: float
    raw_score: float = Field(ge=0.0, le=100.0)
    weighted_score: float
    notes: str


class EvidenceQualityAppraisal(BaseModel):
    """
    Comprehensive 10-dimension evidence quality evaluation:
    1. peer review
    2. study design
    3. sample size
    4. model relevance
    5. human evidence
    6. prospective design
    7. replication
    8. source quality
    9. directness
    10. recency

    Exposes:
    - quality (score, grade, breakdown)
    - confidence (calibrated probability, epistemic/aleatoric uncertainty)
    - limitations (transparent list of epistemic cautions and biases)
    """
    model_config = ConfigDict(from_attributes=True)

    # Core scores
    overall_quality_score: float = Field(ge=0.0, le=100.0)
    quality_grade: QualityGrade
    calibrated_confidence: float = Field(ge=0.0, le=1.0)
    confidence_level: ConfidenceLevel

    # The 10 Dimension Evaluations
    dimension_scores: Dict[str, QualityDimensionScore]
    scoring_breakdown: Dict[str, float]

    # Required Exposures
    quality: EvidenceQuality
    confidence: EvidenceConfidence
    limitations: List[str] = Field(default_factory=list)

    # Epistemic Gates
    is_high_confidence_claim_allowed: bool
    epistemic_warning: Optional[str] = None


class EvidenceQualityEngine:
    """
    Rigorously appraises scientific evidence quality using modified GRADE
    and Oxford Centre for Evidence-Based Medicine principles.

    Evaluates:
    - peer review
    - study design
    - sample size
    - model relevance
    - human evidence
    - prospective design
    - replication
    - source quality
    - directness
    - recency

    Guarantees:
    - Never converts low evidence (Quality Grade C/D or quality_score < 70) into high-confidence claims.
    - Exposes quality, confidence, and transparent limitations.
    """

    # Dimension Weights summing to 1.0
    WEIGHTS = {
        "peer_review": 0.10,
        "study_design": 0.15,
        "sample_size": 0.10,
        "model_relevance": 0.10,
        "human_evidence": 0.15,
        "prospective_design": 0.10,
        "replication": 0.10,
        "source_quality": 0.10,
        "directness": 0.10,
        "recency": 0.00,  # Recency applied as calibrated decay modifier
    }

    @classmethod
    def evaluate(
        cls,
        peer_reviewed: bool,
        study_design: StudyDesignType,
        sample_size: Optional[int],
        model_relevance: ModelRelevance,
        is_human: bool,
        prospective_or_retrospective: ProspectiveOrRetrospective,
        replication_status: ReplicationStatus,
        source_type: SourceType,
        directness: DirectnessLevel = DirectnessLevel.DIRECT,
        publication_date: Optional[date] = None,
        as_of_date: Optional[date] = None,
        risk_of_bias: RiskOfBias = RiskOfBias.LOW,
    ) -> EvidenceQualityAppraisal:
        limitations: List[str] = []
        dim_scores: Dict[str, QualityDimensionScore] = {}

        # 1. Peer Review (Weight: 10%)
        if peer_reviewed:
            pr_score = 100.0
            pr_notes = "Formally peer-reviewed in indexed scientific literature."
        else:
            pr_score = 35.0
            pr_notes = "Unreviewed disclosure, preprint, or non-peer-reviewed corporate presentation."
            limitations.append("Lacks formal independent peer review; subject to publication bias.")
        dim_scores["peer_review"] = QualityDimensionScore(
            dimension="peer_review",
            weight=cls.WEIGHTS["peer_review"],
            raw_score=pr_score,
            weighted_score=pr_score * cls.WEIGHTS["peer_review"],
            notes=pr_notes,
        )

        # 2. Study Design (Weight: 15%)
        design_map = {
            StudyDesignType.RCT_DOUBLE_BLIND: (100.0, "Gold-standard randomized double-blind controlled trial."),
            StudyDesignType.RCT_OPEN_LABEL: (88.0, "Randomized controlled open-label trial."),
            StudyDesignType.PROSPECTIVE_COHORT: (80.0, "Well-controlled prospective longitudinal cohort."),
            StudyDesignType.PHASE_1_2_SINGLE_ARM: (72.0, "Phase 1/2 single-arm clinical trial."),
            StudyDesignType.EX_VIVO_PATIENT_TISSUE: (65.0, "Ex vivo patient-derived primary tissue or explant."),
            StudyDesignType.IN_VIVO_ANIMAL_DISEASE_MODEL: (58.0, "In vivo animal disease pharmacology model."),
            StudyDesignType.RETROSPECTIVE_OBSERVATIONAL: (50.0, "Retrospective observational / real-world dataset."),
            StudyDesignType.IN_VITRO_CELL_LINE: (42.0, "In vitro established cell line screening."),
            StudyDesignType.BIOCHEMICAL_KINASE_ASSAY: (40.0, "Cell-free biochemical kinase / target binding assay."),
            StudyDesignType.CASE_REPORT_SERIES: (35.0, "Anecdotal clinical case report series."),
            StudyDesignType.COMPUTATIONAL_PREDICTION: (25.0, "In silico computational structural prediction."),
        }
        sd_score, sd_notes = design_map.get(study_design, (50.0, "Standard observational study."))
        if study_design in (StudyDesignType.RETROSPECTIVE_OBSERVATIONAL, StudyDesignType.CASE_REPORT_SERIES):
            limitations.append(f"Non-randomized observational design ({study_design.value}) vulnerable to confounding.")
        elif study_design in (StudyDesignType.IN_VITRO_CELL_LINE, StudyDesignType.BIOCHEMICAL_KINASE_ASSAY, StudyDesignType.COMPUTATIONAL_PREDICTION):
            limitations.append(f"Preclinical in vitro or computational design ({study_design.value}) requires clinical translation validation.")
        dim_scores["study_design"] = QualityDimensionScore(
            dimension="study_design",
            weight=cls.WEIGHTS["study_design"],
            raw_score=sd_score,
            weighted_score=sd_score * cls.WEIGHTS["study_design"],
            notes=sd_notes,
        )

        # 3. Sample Size (Weight: 10%)
        if sample_size is None or sample_size <= 0:
            sz_score = 30.0
            sz_notes = "Sample size unreported or indeterminable."
            limitations.append("Unreported sample size restricts statistical certainty.")
        elif sample_size >= 250:
            sz_score = 100.0
            sz_notes = f"Adequately powered large sample size (n={sample_size})."
        elif sample_size >= 80:
            sz_score = 85.0
            sz_notes = f"Moderate robust sample size (n={sample_size})."
        elif sample_size >= 25:
            sz_score = 70.0
            sz_notes = f"Modest cohort size (n={sample_size})."
        elif sample_size >= 10:
            sz_score = 50.0
            sz_notes = f"Small cohort size (n={sample_size})."
            limitations.append(f"Small sample cohort (n={sample_size}) increases risk of random variation.")
        else:
            sz_score = 25.0
            sz_notes = f"Very small sample size (n={sample_size})."
            limitations.append(f"Very small sample size (n={sample_size}) limits statistical power.")
        dim_scores["sample_size"] = QualityDimensionScore(
            dimension="sample_size",
            weight=cls.WEIGHTS["sample_size"],
            raw_score=sz_score,
            weighted_score=sz_score * cls.WEIGHTS["sample_size"],
            notes=sz_notes,
        )

        # 4. Model Relevance (Weight: 10%)
        model_map = {
            ModelRelevance.DIRECT_HUMAN_CLINICAL: (100.0, "Direct human clinical patients."),
            ModelRelevance.PATIENT_DERIVED_XENOGRAFT: (80.0, "Patient-derived xenograft (PDX) closely reflecting human histology."),
            ModelRelevance.SYNGENEIC_ANIMAL_MODEL: (68.0, "Syngeneic immunocompetent murine model."),
            ModelRelevance.ISOGENIC_ENGINEERED_LINE: (60.0, "Isogenic CRISPR-engineered cell line."),
            ModelRelevance.IMMORTALIZED_CELL_LINE: (45.0, "Standard immortalized non-isogenic cell line."),
            ModelRelevance.RECOMBINANT_CELL_FREE_ASSAY: (35.0, "Cell-free recombinant target assay."),
            ModelRelevance.COMPUTATIONAL_SILICO: (25.0, "In silico docking simulation."),
        }
        mr_score, mr_notes = model_map.get(model_relevance, (50.0, "Standard biological model."))
        if model_relevance in (ModelRelevance.IMMORTALIZED_CELL_LINE, ModelRelevance.RECOMBINANT_CELL_FREE_ASSAY):
            limitations.append("Cell line / cell-free model lacks physiological tumor microenvironment.")
        dim_scores["model_relevance"] = QualityDimensionScore(
            dimension="model_relevance",
            weight=cls.WEIGHTS["model_relevance"],
            raw_score=mr_score,
            weighted_score=mr_score * cls.WEIGHTS["model_relevance"],
            notes=mr_notes,
        )

        # 5. Human Evidence (Weight: 15%)
        if is_human:
            he_score = 100.0
            he_notes = "Direct human clinical evidence."
        else:
            he_score = 40.0
            he_notes = "Non-human preclinical model."
            limitations.append("Non-human model; interspecies pharmacokinetics and target biology differences apply.")
        dim_scores["human_evidence"] = QualityDimensionScore(
            dimension="human_evidence",
            weight=cls.WEIGHTS["human_evidence"],
            raw_score=he_score,
            weighted_score=he_score * cls.WEIGHTS["human_evidence"],
            notes=he_notes,
        )

        # 6. Prospective Design (Weight: 10%)
        if prospective_or_retrospective == ProspectiveOrRetrospective.PROSPECTIVE:
            pd_score = 100.0
            pd_notes = "Rigorous pre-registered prospective study protocol."
        elif prospective_or_retrospective == ProspectiveOrRetrospective.RETROSPECTIVE:
            pd_score = 45.0
            pd_notes = "Retrospective chart or record review."
            limitations.append("Retrospective analysis subject to selection and recall biases.")
        else:
            pd_score = 65.0
            pd_notes = "Preclinical assay / not applicable."
        dim_scores["prospective_design"] = QualityDimensionScore(
            dimension="prospective_design",
            weight=cls.WEIGHTS["prospective_design"],
            raw_score=pd_score,
            weighted_score=pd_score * cls.WEIGHTS["prospective_design"],
            notes=pd_notes,
        )

        # 7. Replication (Weight: 10%)
        rep_map = {
            ReplicationStatus.INDEPENDENTLY_REPLICATED: (100.0, "Findings independently confirmed by external group."),
            ReplicationStatus.INTERNALLY_REPLICATED: (82.0, "Replicated internally across distinct validation series."),
            ReplicationStatus.SINGLE_STUDY_UNREPLICATED: (52.0, "Single isolated report without published replication."),
            ReplicationStatus.CONTRADICTED: (20.0, "Findings challenged or contradicted by subsequent studies."),
        }
        rep_score, rep_notes = rep_map.get(replication_status, (52.0, "Single study."))
        if replication_status == ReplicationStatus.SINGLE_STUDY_UNREPLICATED:
            limitations.append("Single unconfirmed study; replication across independent labs recommended.")
        elif replication_status == ReplicationStatus.CONTRADICTED:
            limitations.append("Contradictory findings reported in subsequent literature; disputed claim.")
        dim_scores["replication"] = QualityDimensionScore(
            dimension="replication",
            weight=cls.WEIGHTS["replication"],
            raw_score=rep_score,
            weighted_score=rep_score * cls.WEIGHTS["replication"],
            notes=rep_notes,
        )

        # 8. Source Quality (Weight: 10%)
        source_map = {
            SourceType.PUBLICATION: (92.0, "Peer-reviewed biomedical journal."),
            SourceType.CLINICAL_TRIAL: (95.0, "Primary regulatory trial registry (ClinicalTrials.gov/EudraCT)."),
            SourceType.REGULATORY_SOURCE: (100.0, "Health Authority (FDA, EMA, PMDA) official documentation."),
            SourceType.PATENT: (85.0, "Granted patent specification with verified enablement."),
            SourceType.COMPANY_SOURCE: (60.0, "Corporate disclosure / press release."),
            SourceType.CONFERENCE_ABSTRACT: (65.0, "Scientific conference abstract/poster."),
            SourceType.SCIENTIFIC_DATABASE: (88.0, "Curated scientific database (ChEMBL, UniProt)."),
            SourceType.INSTITUTIONAL_SOURCE: (78.0, "Academic or cancer center internal protocol."),
        }
        sq_score, sq_notes = source_map.get(source_type, (75.0, "Standard source."))
        if source_type in (SourceType.COMPANY_SOURCE, SourceType.CONFERENCE_ABSTRACT):
            limitations.append(f"Source type '{source_type.value}' lacks peer-reviewed full methodological details.")
        dim_scores["source_quality"] = QualityDimensionScore(
            dimension="source_quality",
            weight=cls.WEIGHTS["source_quality"],
            raw_score=sq_score,
            weighted_score=sq_score * cls.WEIGHTS["source_quality"],
            notes=sq_notes,
        )

        # 9. Directness (Weight: 10%)
        dir_map = {
            DirectnessLevel.DIRECT: (100.0, "Direct measurement of target molecule in primary disease setting."),
            DirectnessLevel.PROXIMATE: (80.0, "Proximate model testing closely related mechanistically."),
            DirectnessLevel.SURROGATE: (60.0, "Surrogate endpoint or indirect biomarker marker."),
            DirectnessLevel.INDIRECT: (35.0, "Indirect distant extrapolation."),
        }
        dir_score, dir_notes = dir_map.get(directness, (80.0, "Proximate evidence."))
        if directness in (DirectnessLevel.SURROGATE, DirectnessLevel.INDIRECT):
            limitations.append(f"Indirect or surrogate measurement ({directness.value}) requires clinical outcome verification.")
        dim_scores["directness"] = QualityDimensionScore(
            dimension="directness",
            weight=cls.WEIGHTS["directness"],
            raw_score=dir_score,
            weighted_score=dir_score * cls.WEIGHTS["directness"],
            notes=dir_notes,
        )

        # 10. Recency & Risk of Bias Modifiers
        raw_weighted_total = sum(ds.weighted_score for ds in dim_scores.values())

        # Recency evaluation: if older than 5 years, apply mild decay; older than 10, moderate decay
        if publication_date and as_of_date:
            age_years = (as_of_date - publication_date).days / 365.25
            if age_years > 10.0:
                raw_weighted_total *= 0.88
                dim_scores["recency"] = QualityDimensionScore(
                    dimension="recency",
                    weight=0.0,
                    raw_score=60.0,
                    weighted_score=0.0,
                    notes=f"Published {age_years:.1f} years ago; historical standard of care may have shifted.",
                )
                limitations.append(f"Older study published {age_years:.1f} years ago; competitive comparator standard may be superseded.")
            elif age_years > 5.0:
                raw_weighted_total *= 0.95
                dim_scores["recency"] = QualityDimensionScore(
                    dimension="recency",
                    weight=0.0,
                    raw_score=80.0,
                    weighted_score=0.0,
                    notes=f"Published {age_years:.1f} years ago.",
                )
            else:
                dim_scores["recency"] = QualityDimensionScore(
                    dimension="recency",
                    weight=0.0,
                    raw_score=100.0,
                    weighted_score=0.0,
                    notes=f"Recent evidence ({age_years:.1f} years old).",
                )
        else:
            dim_scores["recency"] = QualityDimensionScore(
                dimension="recency",
                weight=0.0,
                raw_score=95.0,
                weighted_score=0.0,
                notes="Recent evidence.",
            )

        # Risk of Bias Penalty
        if risk_of_bias == RiskOfBias.HIGH:
            raw_weighted_total -= 18.0
            limitations.append("High risk of bias identified in study execution or reporting.")
        elif risk_of_bias == RiskOfBias.MODERATE or risk_of_bias == RiskOfBias.UNCLEAR:
            raw_weighted_total -= 7.0
            limitations.append("Moderate or unclear risk of bias noted.")

        # Bound overall quality score between 5.0 and 100.0
        overall_score = max(5.0, min(100.0, round(raw_weighted_total, 1)))

        # Assign GRADE Quality Grade
        if overall_score >= 85.0:
            quality_grade = QualityGrade.GRADE_A_HIGH
        elif overall_score >= 70.0:
            quality_grade = QualityGrade.GRADE_B_MODERATE
        elif overall_score >= 50.0:
            quality_grade = QualityGrade.GRADE_C_LOW
        else:
            quality_grade = QualityGrade.GRADE_D_VERY_LOW

        # Calibrate Confidence
        # Strictly proportional to overall quality score; epistemic invariant forbids high confidence on low evidence!
        calibrated_conf = round(max(0.05, min(0.99, (overall_score / 100.0) * 0.98)), 3)

        if calibrated_conf >= 0.85 and overall_score >= 80.0:
            conf_level = ConfidenceLevel.VERY_HIGH
        elif calibrated_conf >= 0.70 and overall_score >= 70.0:
            conf_level = ConfidenceLevel.HIGH
        elif calibrated_conf >= 0.50 and overall_score >= 50.0:
            conf_level = ConfidenceLevel.MEDIUM
        elif calibrated_conf >= 0.30:
            conf_level = ConfidenceLevel.LOW
        else:
            conf_level = ConfidenceLevel.INSUFFICIENT

        # Epistemic invariant check: Never convert low evidence into high-confidence claims!
        # Low evidence = Grade C/D or quality_score < 70
        is_low_evidence = overall_score < 70.0 or quality_grade in (QualityGrade.GRADE_C_LOW, QualityGrade.GRADE_D_VERY_LOW)
        is_high_conf_allowed = not is_low_evidence

        epistemic_warning = None
        if is_low_evidence:
            epistemic_warning = (
                f"EPISTEMIC SAFETY INVARIANT: Evidence quality is {quality_grade.value} (Score: {overall_score}/100). "
                "Conversion into high-confidence strategic claims or definitive clinical hypotheses is strictly prohibited."
            )

        # Build EvidenceQuality schema
        quality_obj = EvidenceQuality(
            quality_score=overall_score,
            methodological_rigor=dim_scores["study_design"].raw_score,
            risk_of_bias=risk_of_bias,
            reproducibility_flag=overall_score >= 70.0 and replication_status != ReplicationStatus.CONTRADICTED,
            quality_grade=quality_grade,
            scoring_breakdown={k: v.raw_score for k, v in dim_scores.items()},
        )

        # Build EvidenceConfidence schema
        conf_obj = EvidenceConfidence(
            score=calibrated_conf,
            confidence_interval_low=max(0.0, calibrated_conf - 0.08),
            confidence_interval_high=min(1.0, calibrated_conf + 0.05),
            confidence_level=conf_level,
            epistemic_uncertainty=round(1.0 - calibrated_conf, 3),
            aleatoric_uncertainty=0.05 if is_human else 0.15,
            calibration_notes=f"Calibrated across 10 dimensions for {study_design.value}.",
        )

        return EvidenceQualityAppraisal(
            overall_quality_score=overall_score,
            quality_grade=quality_grade,
            calibrated_confidence=calibrated_conf,
            confidence_level=conf_level,
            dimension_scores=dim_scores,
            scoring_breakdown={k: v.raw_score for k, v in dim_scores.items()},
            quality=quality_obj,
            confidence=conf_obj,
            limitations=limitations,
            is_high_confidence_claim_allowed=is_high_conf_allowed,
            epistemic_warning=epistemic_warning,
        )

    @classmethod
    def assert_claim_confidence_invariants(
        cls,
        appraisal: EvidenceQualityAppraisal,
        claimed_confidence: float,
        claim_text: str,
    ) -> None:
        """
        Enforces the epistemic safety rule:
        Never convert low evidence into high-confidence claims.
        Raises LowEvidenceConversionError if violated.
        """
        if not appraisal.is_high_confidence_claim_allowed and claimed_confidence >= 0.70:
            raise LowEvidenceConversionError(
                f"Epistemic violation: Attempted to assert high confidence ({claimed_confidence:.2f}) "
                f"for claim '{claim_text}', but evidence quality is low ({appraisal.quality_grade.value}, "
                f"score={appraisal.overall_quality_score:.1f}). "
                f"Limitations: {'; '.join(appraisal.limitations)}"
            )
