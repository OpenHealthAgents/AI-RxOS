from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from app.opportunity_engine.intelligence import (
    EpistemicClass,
    IntelligenceEvidence,
    IntelligenceRuleFinding,
    IntelligenceValue,
    IntelligenceValueStatus,
    registered_model_prediction,
    unknown_value,
)

from .models import (
    ClinicalDevelopmentProfile,
    ClinicalExpertInterpretation,
    ClinicalIntelligence,
    ClinicalModelPrediction,
    ClinicalScoreLineage,
    ClinicalStage,
    EndpointReviewType,
    ObservedClinicalOutcome,
    TrialDesignEvaluation,
    TrialDesignType,
)

logger = logging.getLogger(__name__)


class ClinicalDevelopmentIntelligenceEngine:
    """
    Clinical Development Intelligence Engine.
    Evaluates:
    - stage
    - trial design
    - enrollment
    - population selection
    - biomarker enrichment
    - endpoint quality
    - ORR, CR, DOR, PFS, OS, clinical benefit
    - toxicity, discontinuation, dose optimization
    - trial execution, competitive clinical landscape

    Produces the 4 canonical scores:
    1. Clinical Success Probability (0.0 - 1.0)
    2. Clinical Readiness Score (0 - 100)
    3. Development Risk Score (0 - 100)
    4. Evidence Confidence (0.0 - 1.0)

    Strictly separates:
    - observed clinical outcome (facts)
    - model prediction (algorithmic)
    - expert interpretation (clinician/regulatory)
    - unknown (evidence gaps)
    """

    def __init__(self) -> None:
        self._canonical_data = self._load_canonical_benchmark_clinical_data()

    def evaluate_asset(
        self,
        asset_id: str,
        asset_name: Optional[str] = None,
        custom_outcomes: Optional[List[ObservedClinicalOutcome]] = None,
    ) -> ClinicalDevelopmentProfile:
        """
        Evaluates an asset's clinical development intelligence profile.
        Aggregates observed trials, generates model predictions and expert
        commentary, identifies unknowns, and computes the 4 canonical scores.
        """
        stored = self._canonical_data.get(asset_id, {})

        resolved_name = asset_name or stored.get("name", asset_id.capitalize())
        stage = stored.get("stage")
        if not stage:
            if custom_outcomes and len(custom_outcomes) > 0:
                stage = custom_outcomes[0].phase
            else:
                stage = ClinicalStage.PRECLINICAL

        # 1. Observed clinical outcomes
        outcomes = list(stored.get("observed_outcomes", []))
        if custom_outcomes:
            outcomes.extend(custom_outcomes)

        # 2. Trial designs
        trials = list(stored.get("trials_evaluated", []))

        # 3. Model predictions
        predictions = list(stored.get("model_predictions", []))

        # 4. Expert interpretations
        interpretations = list(stored.get("expert_interpretations", []))

        # 5. Unknowns & Evidence Gaps
        unknowns = list(stored.get("unknowns", []))

        # 6. Compute 4 Canonical Scores with explicit mathematical formula lineages
        success_prob, succ_lineage = self._derive_clinical_success_probability(stage, outcomes, trials)
        readiness_score, read_lineage = self._derive_clinical_readiness_score(stage, outcomes, trials)
        risk_score, risk_lineage = self._derive_development_risk_score(stage, outcomes, trials)
        confidence_score, conf_lineage = self._derive_evidence_confidence(stage, outcomes, trials)

        lineages = {
            "clinical_success_probability": succ_lineage,
            "clinical_readiness_score": read_lineage,
            "development_risk_score": risk_lineage,
            "evidence_confidence": conf_lineage,
        }

        # Collect additional gaps from lineages
        for lin in lineages.values():
            for gap in lin.evidence_gaps:
                if gap not in unknowns:
                    unknowns.append(gap)

        return ClinicalDevelopmentProfile(
            asset_id=asset_id,
            asset_name=resolved_name,
            stage=stage,
            clinical_success_probability=round(success_prob, 2),
            clinical_readiness_score=round(readiness_score, 1),
            development_risk_score=round(risk_score, 1),
            evidence_confidence=round(confidence_score, 2),
            trials_evaluated=trials,
            observed_clinical_outcomes=outcomes,
            model_predictions=predictions,
            expert_interpretations=interpretations,
            unknowns=unknowns,
            lineages=lineages,
            evaluated_at=datetime.now(timezone.utc),
        )

    def get_benchmark_profile(self, asset_id: str) -> ClinicalDevelopmentProfile:
        return self.evaluate_asset(asset_id)

    def list_benchmark_profiles(self) -> List[ClinicalDevelopmentProfile]:
        return [
            self.get_benchmark_profile("tucatinib"),
            self.get_benchmark_profile("zongertinib"),
            self.get_benchmark_profile("poziotinib"),
            self.get_benchmark_profile("neratinib"),
            self.get_benchmark_profile("ox-her2-01"),
        ]

    def evaluate_intelligence(
        self,
        asset_id: str,
        prediction_cutoff: date,
        *,
        tenant_id: Optional[str] = None,
        asset_name: Optional[str] = None,
        custom_outcomes: Optional[List[ObservedClinicalOutcome]] = None,
        feature_store: Any | None = None,
        model_registry: Any | None = None,
    ) -> ClinicalIntelligence:
        """Combine dated clinical facts with an exact registered Prompt 38 prediction, if available."""
        stored = self._canonical_data.get(asset_id, {})
        if custom_outcomes and any(item.tenant_id not in (None, tenant_id) for item in custom_outcomes):
            raise ValueError("Clinical outcomes must belong to the requested tenant.")
        all_outcomes = [
            item
            for item in (
                list(stored.get("observed_outcomes", [])) + list(custom_outcomes or [])
            )
            if item.tenant_id in (None, tenant_id)
        ]
        admissible = [
            item
            for item in all_outcomes
            if item.reported_date is not None
            and item.reported_date <= prediction_cutoff
        ]
        excluded = [item for item in all_outcomes if item not in admissible]

        def outcome_evidence(item: ObservedClinicalOutcome) -> IntelligenceEvidence:
            return IntelligenceEvidence(
                evidence_id=str(item.id),
                source_type="clinical_trial_outcome",
                source_reference=item.trial_id,
                citation=item.source_citation,
                observed_at=item.reported_date,
                confidence=None,
                epistemic_class=EpistemicClass.FACT,
                provenance={
                    "trial_title": item.trial_title,
                    "phase": item.phase.value,
                    "sample_size": item.sample_size,
                    "population": item.population,
                    "biomarker_status": item.biomarker_status,
                    "endpoint_review": item.endpoint_review.value,
                    "pmid": item.pmid,
                },
            )

        evidence = [outcome_evidence(item) for item in admissible]
        excluded_evidence = [
            IntelligenceEvidence(
                evidence_id=str(item.id),
                source_type="clinical_trial_outcome_excluded_from_snapshot",
                source_reference=item.trial_id,
                citation=item.source_citation,
                observed_at=item.reported_date,
                confidence=None,
                epistemic_class=EpistemicClass.FACT,
                provenance={
                    "exclusion_reason": (
                        "outcome_date_missing"
                        if item.reported_date is None
                        else "outcome_after_prediction_cutoff"
                    ),
                    "prediction_cutoff": prediction_cutoff.isoformat(),
                },
            )
            for item in excluded
        ]
        component, prediction = registered_model_prediction(
            model_name="clinical_success",
            asset_id=asset_id,
            prediction_cutoff=prediction_cutoff,
            tenant_id=tenant_id,
            registry=model_registry,
            feature_store=feature_store,
        )

        if prediction is not None and prediction.probability is not None:
            clinical_success = IntelligenceValue(
                name="clinical_success_probability",
                value=prediction.probability,
                status=IntelligenceValueStatus.AVAILABLE,
                epistemic_class=EpistemicClass.ML_PREDICTION,
                confidence=prediction.confidence,
                supporting_evidence=[
                    IntelligenceEvidence(
                        evidence_id=f"model_input:{reference}",
                        source_type="model_input_feature",
                        source_reference=reference,
                        confidence=None,
                        epistemic_class=EpistemicClass.ML_PREDICTION,
                        provenance={
                            "model_name": prediction.model_name,
                            "model_version": prediction.model_version,
                            "feature_version": prediction.feature_version,
                        },
                    )
                    for metadata in prediction.input_snapshot.get("observation_dates", {}).values()
                    for reference in metadata.get("evidence_references", [])
                ],
                provenance={
                    "model_name": prediction.model_name,
                    "model_version": prediction.model_version,
                    "feature_version": prediction.feature_version,
                    "prediction_cutoff": prediction.prediction_cutoff.isoformat()
                    if prediction.prediction_cutoff
                    else None,
                    "prediction_timestamp": prediction.prediction_timestamp.isoformat(),
                    "input_snapshot": prediction.input_snapshot,
                },
            )
        else:
            clinical_success = unknown_value(
                "clinical_success_probability",
                component.reason or "Clinical ML prediction is unavailable.",
                status=IntelligenceValueStatus.UNAVAILABLE,
                provenance={
                    "model_name": component.model_name,
                    "model_version": component.model_version,
                    "feature_version": component.feature_version,
                    "prediction_cutoff": prediction_cutoff.isoformat(),
                },
            )

        if admissible:
            phases = sorted({outcome.phase.value for outcome in admissible})
            readiness = IntelligenceValue(
                name="clinical_readiness",
                value={"documented_trial_phases": phases, "dated_outcome_count": len(admissible)},
                status=IntelligenceValueStatus.AVAILABLE,
                epistemic_class=EpistemicClass.DERIVED_FEATURE,
                confidence=None,
                supporting_evidence=evidence,
                provenance={
                    "rule": "summarize only phase and count from cutoff-valid reported trial outcomes",
                    "prediction_cutoff": prediction_cutoff.isoformat(),
                },
            )
            maturity = IntelligenceValue(
                name="evidence_maturity",
                value={"documented_trial_phases": phases, "dated_outcome_count": len(admissible)},
                status=IntelligenceValueStatus.AVAILABLE,
                epistemic_class=EpistemicClass.DERIVED_FEATURE,
                confidence=None,
                supporting_evidence=evidence,
                provenance={
                    "rule": "maturity reflects dated outcome records only; not probability of success",
                    "prediction_cutoff": prediction_cutoff.isoformat(),
                },
            )
            rule_findings = [
                IntelligenceRuleFinding(
                    rule_id="clinical:dated_trial_outcome_present",
                    result="cutoff_valid_clinical_outcomes_documented",
                    applied=True,
                    supporting_evidence_ids=[str(outcome.id) for outcome in admissible],
                    provenance={"phases": phases},
                )
            ]
        else:
            readiness = unknown_value(
                "clinical_readiness",
                "No dated clinical trial outcome is available at the prediction cutoff.",
                status=IntelligenceValueStatus.INSUFFICIENT_EVIDENCE,
            )
            maturity = unknown_value(
                "evidence_maturity",
                "No dated clinical trial outcome is available at the prediction cutoff.",
                status=IntelligenceValueStatus.INSUFFICIENT_EVIDENCE,
            )
            rule_findings = []

        development_risk = unknown_value(
            "development_risk",
            "No cutoff-valid clinical risk prediction is available; risk is not inferred from missing evidence.",
            status=IntelligenceValueStatus.UNAVAILABLE,
            provenance={"clinical_ml_model": "clinical_success"},
        )

        return ClinicalIntelligence(
            asset_id=asset_id,
            asset_name=asset_name or stored.get("name", asset_id.capitalize()),
            tenant_id=tenant_id,
            prediction_cutoff=prediction_cutoff,
            clinical_success_probability=clinical_success,
            clinical_readiness=readiness,
            development_risk=development_risk,
            evidence_maturity=maturity,
            evidence=evidence,
            excluded_undated_evidence=excluded_evidence,
            rule_findings=rule_findings,
            ml_component=component,
        )

    # ==============================================================================
    # 4 Canonical Score Derivations
    # ==============================================================================

    def _derive_clinical_success_probability(
        self,
        stage: ClinicalStage,
        outcomes: List[ObservedClinicalOutcome],
        trials: List[TrialDesignEvaluation],
    ) -> Tuple[float, ClinicalScoreLineage]:
        """
        Derives Bayesian Clinical Success Probability (0.01 - 0.99).
        Anchors on stage-specific historical baseline and applies likelihood updates
        based on observed effect sizes (ORR, PFS HR, OS HR), trial design rigor,
        and toxicity penalties.
        """
        stage_anchors = {
            ClinicalStage.APPROVED: 0.98,
            ClinicalStage.PHASE_III: 0.85,
            ClinicalStage.PHASE_II_III: 0.75,
            ClinicalStage.PHASE_II: 0.58,
            ClinicalStage.PHASE_IB: 0.42,
            ClinicalStage.PHASE_I: 0.28,
            ClinicalStage.PRECLINICAL: 0.12,
            ClinicalStage.CRL: 0.08,
            ClinicalStage.WITHDRAWN: 0.05,
            ClinicalStage.TERMINATED: 0.02,
        }

        base_p = stage_anchors.get(stage, 0.20)
        p = base_p
        inputs: Dict[str, Any] = {"stage_baseline": base_p}
        used_ids: List[UUID] = []
        gaps: List[str] = []

        if not outcomes:
            gaps.append(f"No observed clinical trial outcomes recorded; probability anchored to {stage.value} benchmark baseline.")
            return round(base_p, 2), ClinicalScoreLineage(
                score_name="Clinical Success Probability",
                formula="Stage_Baseline + Effect_Size_Updates - Toxicity_Penalties",
                inputs=inputs,
                observed_outcome_ids=[],
                calculated_value=base_p,
                evidence_gaps=gaps,
            )

        best_outcome = max(outcomes, key=lambda o: (o.orr_pct or 0.0, o.sample_size))
        used_ids.append(best_outcome.id)

        # 1. ORR Effect Size Update
        if best_outcome.orr_pct is not None:
            inputs["best_orr_pct"] = best_outcome.orr_pct
            if best_outcome.orr_pct >= 60.0:
                p += 0.10
            elif best_outcome.orr_pct >= 40.0:
                p += 0.06
            elif best_outcome.orr_pct < 25.0:
                p -= 0.12

        # 2. PFS & OS Survival Hazard Ratio
        if best_outcome.os_hazard_ratio is not None:
            inputs["os_hazard_ratio"] = best_outcome.os_hazard_ratio
            if best_outcome.os_hazard_ratio <= 0.70:
                p += 0.12
            elif best_outcome.os_hazard_ratio >= 0.90:
                p -= 0.08

        if best_outcome.pfs_hazard_ratio is not None:
            inputs["pfs_hazard_ratio"] = best_outcome.pfs_hazard_ratio
            if best_outcome.pfs_hazard_ratio <= 0.60:
                p += 0.08

        # 3. Trial Design Rigor
        if any(t.design_type == TrialDesignType.RANDOMIZED_CONTROLLED_TRIAL for t in trials):
            p += 0.06
            inputs["rct_bonus"] = True
        elif any(t.design_type == TrialDesignType.SINGLE_ARM_BASKET for t in trials):
            p -= 0.05
            gaps.append("Single-arm trial design increases regulatory confirmatory burden.")

        # 4. Toxicity Penalty
        if best_outcome.grade_3_plus_ae_pct is not None:
            inputs["grade_3_plus_ae_pct"] = best_outcome.grade_3_plus_ae_pct
            if best_outcome.grade_3_plus_ae_pct > 30.0:
                p -= 0.08
                gaps.append(f"Elevated Grade 3+ AE rate ({best_outcome.grade_3_plus_ae_pct}%) dampens success probability.")

        if best_outcome.treatment_discontinuation_pct is not None:
            inputs["treatment_discontinuation_pct"] = best_outcome.treatment_discontinuation_pct
            if best_outcome.treatment_discontinuation_pct > 15.0:
                p -= 0.06

        final_p = max(0.01, min(0.99, p))
        return round(final_p, 2), ClinicalScoreLineage(
            score_name="Clinical Success Probability",
            formula="Stage_Baseline + Effect_Size_Updates - Toxicity_Penalties",
            inputs=inputs,
            observed_outcome_ids=used_ids,
            calculated_value=round(final_p, 2),
            evidence_gaps=gaps,
        )

    def _derive_clinical_readiness_score(
        self,
        stage: ClinicalStage,
        outcomes: List[ObservedClinicalOutcome],
        trials: List[TrialDesignEvaluation],
    ) -> Tuple[float, ClinicalScoreLineage]:
        """
        Derives Clinical Readiness Score (0 - 100).
        Evaluates operational maturity, registrational package, companion diagnostics,
        and adjudication rigor.
        """
        stage_readiness = {
            ClinicalStage.APPROVED: 95.0,
            ClinicalStage.PHASE_III: 84.0,
            ClinicalStage.PHASE_II_III: 75.0,
            ClinicalStage.PHASE_II: 62.0,
            ClinicalStage.PHASE_IB: 48.0,
            ClinicalStage.PHASE_I: 35.0,
            ClinicalStage.PRECLINICAL: 15.0,
            ClinicalStage.CRL: 40.0,
            ClinicalStage.WITHDRAWN: 20.0,
            ClinicalStage.TERMINATED: 10.0,
        }

        score = stage_readiness.get(stage, 20.0)
        inputs: Dict[str, Any] = {"stage_baseline_readiness": score}
        used_ids: List[UUID] = [o.id for o in outcomes]
        gaps: List[str] = []

        if not outcomes:
            gaps.append("No clinical trial data points observed; program at preclinical stage.")
            return score, ClinicalScoreLineage(
                score_name="Clinical Readiness Score",
                formula="Stage_Baseline + Companion_Dx + Central_Adjudication - Project_Optimus_Gaps",
                inputs=inputs,
                observed_outcome_ids=[],
                calculated_value=score,
                evidence_gaps=gaps,
            )

        # Modifiers
        if any(t.biomarker_prospective for t in trials):
            score += 6.0
            inputs["prospective_biomarker_companion_dx"] = True
        else:
            gaps.append("Prospective companion diagnostic assay not integrated into trials.")

        if any(t.adjudication == EndpointReviewType.BLINDED_INDEPENDENT_CENTRAL_REVIEW for t in trials):
            score += 5.0
            inputs["bicr_central_adjudication"] = True
        else:
            gaps.append("Trial relies solely on investigator-assessed response criteria.")

        if any(not t.project_optimus_compliant for t in trials):
            score -= 8.0
            gaps.append("Dose optimization does not fully comply with FDA Project Optimus expectations.")

        final_score = max(0.0, min(100.0, score))
        return final_score, ClinicalScoreLineage(
            score_name="Clinical Readiness Score",
            formula="Stage_Baseline + Companion_Dx + Central_Adjudication - Project_Optimus_Gaps",
            inputs=inputs,
            observed_outcome_ids=used_ids,
            calculated_value=round(final_score, 1),
            evidence_gaps=gaps,
        )

    def _derive_development_risk_score(
        self,
        stage: ClinicalStage,
        outcomes: List[ObservedClinicalOutcome],
        trials: List[TrialDesignEvaluation],
    ) -> Tuple[float, ClinicalScoreLineage]:
        """
        Derives Development Risk Score (0 - 100). Higher = higher risk!
        Composites:
        - Severe toxicity (Grade 3+ AEs > 25%): +25 to +35 pts
        - Treatment discontinuation (> 15%): +20 pts
        - Single-arm basket trial accelerated approval vulnerability: +15 pts
        - Regulatory Complete Response Letter (CRL): +35 pts
        - Competitive obsolescence / crowded landscape: +10 pts
        """
        risk = 20.0  # Base pipeline uncertainty
        inputs: Dict[str, Any] = {"base_risk": 20.0}
        used_ids: List[UUID] = []
        gaps: List[str] = []

        if stage == ClinicalStage.PRECLINICAL:
            risk = 75.0
            inputs["preclinical_unverified_risk"] = 75.0
            gaps.append("Program is preclinical; human PK, clinical tolerability, and efficacy remain unproven.")
            return risk, ClinicalScoreLineage(
                score_name="Development Risk Score",
                formula="Base_Risk + Toxicity_Burden + Discontinuation_Risk + Design_Vulnerability + Regulatory_Flags",
                inputs=inputs,
                observed_outcome_ids=[],
                calculated_value=risk,
                evidence_gaps=gaps,
            )

        if stage == ClinicalStage.CRL:
            risk += 45.0
            inputs["regulatory_crl_flag"] = True
            gaps.append("Complete Response Letter (CRL) issued by regulatory agency.")

        for o in outcomes:
            used_ids.append(o.id)
            if o.grade_3_plus_ae_pct is not None:
                inputs["grade_3_plus_ae_pct"] = o.grade_3_plus_ae_pct
                if o.grade_3_plus_ae_pct >= 35.0:
                    risk += 30.0
                    gaps.append(f"High severe adverse event rate ({o.grade_3_plus_ae_pct}% Grade 3+) drives substantial safety risk.")
                elif o.grade_3_plus_ae_pct >= 25.0:
                    risk += 20.0

            if o.treatment_discontinuation_pct is not None:
                inputs["treatment_discontinuation_pct"] = o.treatment_discontinuation_pct
                if o.treatment_discontinuation_pct >= 15.0:
                    risk += 20.0
                    gaps.append(f"Elevated discontinuation rate ({o.treatment_discontinuation_pct}%) impacts patient adherence.")

            if o.dose_reduction_pct is not None and o.dose_reduction_pct >= 50.0:
                risk += 15.0
                gaps.append(f"Extensive dose reductions ({o.dose_reduction_pct}%) indicate narrow therapeutic index.")

        if any(t.design_type == TrialDesignType.SINGLE_ARM_BASKET for t in trials):
            risk += 12.0
            inputs["single_arm_accelerated_risk"] = True
            gaps.append("Single-arm design susceptible to FDA withdrawal if confirmatory trial underperforms.")

        final_risk = max(5.0, min(95.0, risk))
        return final_risk, ClinicalScoreLineage(
            score_name="Development Risk Score",
            formula="Base_Risk + Toxicity_Burden + Discontinuation_Risk + Design_Vulnerability + Regulatory_Flags",
            inputs=inputs,
            observed_outcome_ids=used_ids,
            calculated_value=round(final_risk, 1),
            evidence_gaps=gaps,
        )

    def _derive_evidence_confidence(
        self,
        stage: ClinicalStage,
        outcomes: List[ObservedClinicalOutcome],
        trials: List[TrialDesignEvaluation],
    ) -> Tuple[float, ClinicalScoreLineage]:
        """
        Derives Evidence Confidence (0.0 - 1.0).
        Calibrated by sample size, prospective design, randomized control,
        and BICR adjudication.
        """
        if not outcomes:
            return 0.20, ClinicalScoreLineage(
                score_name="Evidence Confidence",
                formula="Sample_Size (0.35) + Design_Rigor (0.25) + BICR (0.20) + Survival_Maturity (0.20)",
                inputs={"status": "Preclinical / No Clinical Evidence"},
                observed_outcome_ids=[],
                calculated_value=0.20,
                evidence_gaps=["No human clinical trials conducted."],
            )

        conf = 0.0
        used_ids = [o.id for o in outcomes]
        inputs: Dict[str, Any] = {}
        gaps: List[str] = []

        total_n = sum(o.sample_size for o in outcomes)
        inputs["total_patients_enrolled"] = total_n

        # 1. Sample Size (up to 0.35)
        if total_n >= 300:
            conf += 0.35
        elif total_n >= 100:
            conf += 0.25
        elif total_n >= 30:
            conf += 0.15
        else:
            conf += 0.08
            gaps.append(f"Small patient sample size (N={total_n}) limits statistical certainty.")

        # 2. Design Rigor (up to 0.25)
        if any(t.design_type == TrialDesignType.RANDOMIZED_CONTROLLED_TRIAL for t in trials):
            conf += 0.25
            inputs["rct_design"] = True
        else:
            conf += 0.12
            gaps.append("Non-randomized single-arm data lacks comparative baseline control.")

        # 3. BICR Adjudication (up to 0.20)
        if any(t.adjudication == EndpointReviewType.BLINDED_INDEPENDENT_CENTRAL_REVIEW for t in trials):
            conf += 0.20
            inputs["bicr_adjudication"] = True
        else:
            conf += 0.08
            gaps.append("Endpoints are investigator-assessed without blinded central review.")

        # 4. Survival Endpoint Maturity (up to 0.20)
        if any(o.os_months is not None for o in outcomes):
            conf += 0.20
            inputs["mature_overall_survival"] = True
        elif any(o.pfs_months is not None for o in outcomes):
            conf += 0.12
            gaps.append("Overall survival data not yet mature; evaluation relies on progression-free survival.")
        else:
            conf += 0.05
            gaps.append("Survival endpoints (PFS/OS) immature; relies solely on response rates.")

        final_conf = max(0.10, min(0.99, conf))
        return round(final_conf, 2), ClinicalScoreLineage(
            score_name="Evidence Confidence",
            formula="Sample_Size (0.35) + Design_Rigor (0.25) + BICR (0.20) + Survival_Maturity (0.20)",
            inputs=inputs,
            observed_outcome_ids=used_ids,
            calculated_value=round(final_conf, 2),
            evidence_gaps=gaps,
        )

    # ==============================================================================
    # Canonical Benchmark Data
    # ==============================================================================

    def _load_canonical_benchmark_clinical_data(self) -> Dict[str, Dict[str, Any]]:
        return {
            # 1. Tucatinib (Tukysa) — Approved Phase 3 Benchmark
            "tucatinib": {
                "name": "Tucatinib (Tukysa)",
                "stage": ClinicalStage.APPROVED,
                "trials_evaluated": [
                    TrialDesignEvaluation(
                        trial_id="NCT02614794",
                        design_type=TrialDesignType.RANDOMIZED_CONTROLLED_TRIAL,
                        enrollment_count=612,
                        sample_size_adequate=True,
                        comparator_arm="Trastuzumab + Capecitabine + Placebo",
                        blinding_method="Double-Blind",
                        project_optimus_compliant=True,
                        randomized_dose_optimization=True,
                        biomarker_prospective=True,
                        adjudication=EndpointReviewType.BLINDED_INDEPENDENT_CENTRAL_REVIEW,
                        execution_flags=["Pivotal Phase 3 Trial completed on schedule"],
                    ),
                ],
                "observed_outcomes": [
                    ObservedClinicalOutcome(
                        trial_id="NCT02614794",
                        trial_title="HER2CLIMB: Tucatinib vs Placebo with Trastuzumab and Capecitabine for HER2+ MBC",
                        phase=ClinicalStage.PHASE_III,
                        sample_size=612,
                        population="Locally advanced or metastatic HER2+ breast cancer previously treated with trastuzumab, pertuzumab, and T-DM1",
                        biomarker_status="HER2-positive (IHC 3+ or FISH amplified)",
                        orr_pct=40.6,
                        cr_pct=1.4,
                        dor_months=8.3,
                        pfs_months=7.8,
                        pfs_hazard_ratio=0.54,
                        os_months=21.9,
                        os_hazard_ratio=0.66,
                        cbr_pct=72.0,
                        grade_3_plus_ae_pct=12.9,
                        treatment_discontinuation_pct=5.7,
                        dose_reduction_pct=21.0,
                        endpoint_review=EndpointReviewType.BLINDED_INDEPENDENT_CENTRAL_REVIEW,
                        source_citation="Murthy et al. NEJM 2020; PMID:31825569",
                        pmid="31825569",
                    ),
                ],
                "model_predictions": [
                    ClinicalModelPrediction(
                        parameter="Probability of Regulatory Approval in Active Brain Metastases",
                        predicted_value=0.98,
                        confidence_interval_low=0.95,
                        confidence_interval_high=1.0,
                        model_name="Bayesian Approval Registry Model v2.4",
                    ),
                ],
                "expert_interpretations": [
                    ClinicalExpertInterpretation(
                        topic="Competitive Position in HER2+ MBC",
                        consensus_view="Standard of care in HER2+ metastatic breast cancer with active or treated brain metastases.",
                        regulatory_precedent="FDA Full Approval in April 2020 via Project Orbis.",
                        clinician_summary="Tucatinib demonstrated definitive overall survival improvement in HER2CLIMB with manageable diarrhea when combined with capecitabine.",
                    ),
                ],
                "unknowns": [
                    "Optimal sequencing relative to trastuzumab deruxtecan (T-DXd) in 2L vs 3L HER2+ setting remains a clinical debate.",
                ],
            },

            # 2. Zongertinib (BI 1810631) — Investigational Phase 1b/2 Mutant NSCLC Leader
            "zongertinib": {
                "name": "Zongertinib (BI 1810631)",
                "stage": ClinicalStage.PHASE_II,
                "trials_evaluated": [
                    TrialDesignEvaluation(
                        trial_id="NCT04886804",
                        design_type=TrialDesignType.SINGLE_ARM_EXPANSION,
                        enrollment_count=132,
                        sample_size_adequate=True,
                        comparator_arm=None,
                        blinding_method="Open-Label",
                        project_optimus_compliant=True,
                        randomized_dose_optimization=True,
                        biomarker_prospective=True,
                        adjudication=EndpointReviewType.BLINDED_INDEPENDENT_CENTRAL_REVIEW,
                        execution_flags=["Randomized dose finding cohort (120mg vs 240mg) complies with Project Optimus"],
                    ),
                ],
                "observed_outcomes": [
                    ObservedClinicalOutcome(
                        trial_id="NCT04886804",
                        trial_title="Beamion LUNG-1: Phase 1b/2 Study of Zongertinib in HER2-mutant Advanced NSCLC",
                        phase=ClinicalStage.PHASE_II,
                        sample_size=132,
                        population="Pretreated HER2-mutant advanced non-small cell lung cancer",
                        biomarker_status="Activating HER2 kinase domain mutation (Exon 20 insertion, L755S, etc.)",
                        orr_pct=73.8,
                        cr_pct=2.3,
                        dor_months=13.4,
                        pfs_months=12.4,
                        pfs_hazard_ratio=None,
                        os_months=None,
                        cbr_pct=92.5,
                        grade_3_plus_ae_pct=3.8,
                        treatment_discontinuation_pct=2.9,
                        dose_reduction_pct=8.5,
                        endpoint_review=EndpointReviewType.BLINDED_INDEPENDENT_CENTRAL_REVIEW,
                        source_citation="Beamion LUNG-1 Interim Analysis; Nature Cancer 2024; PMID:38718468",
                        pmid="38718468",
                    ),
                ],
                "model_predictions": [
                    ClinicalModelPrediction(
                        parameter="Phase II to Phase III Conversion Probability",
                        predicted_value=0.78,
                        confidence_interval_low=0.70,
                        confidence_interval_high=0.85,
                        model_name="Bayesian Oncology Transition Model v2.4",
                    ),
                    ClinicalModelPrediction(
                        parameter="Predicted Median PFS in Phase III Beamion LUNG-2",
                        predicted_value=13.2,
                        confidence_interval_low=10.5,
                        confidence_interval_high=16.0,
                    ),
                ],
                "expert_interpretations": [
                    ClinicalExpertInterpretation(
                        topic="Dose Optimization & Project Optimus",
                        consensus_view="Favorable dose optimization profile. 120 mg QD selected with minimal wild-type EGFR gastrointestinal toxicity.",
                        regulatory_precedent="FDA Breakthrough Therapy Designation granted in 2023.",
                        clinician_summary="Remarkable tolerability (only 3.8% Grade 3+ diarrhea) compares favorably against poziotinib (26%) and mobocertinib.",
                    ),
                ],
                "unknowns": [
                    "Long-term overall survival and head-to-head superiority against T-DXd in 1L HER2-mutant NSCLC pending Phase 3 Beamion LUNG-2 readout.",
                ],
            },

            # 3. Poziotinib (HM781-36B) — FDA Complete Response Letter (High Risk)
            "poziotinib": {
                "name": "Poziotinib (HM781-36B)",
                "stage": ClinicalStage.CRL,
                "trials_evaluated": [
                    TrialDesignEvaluation(
                        trial_id="NCT03318939",
                        design_type=TrialDesignType.SINGLE_ARM_BASKET,
                        enrollment_count=115,
                        sample_size_adequate=False,
                        comparator_arm=None,
                        blinding_method="Open-Label",
                        project_optimus_compliant=False,
                        randomized_dose_optimization=False,
                        biomarker_prospective=True,
                        adjudication=EndpointReviewType.BLINDED_INDEPENDENT_CENTRAL_REVIEW,
                        execution_flags=["FDA ODAC voted 9-4 that benefit did not outweigh risk", "CRL issued in Nov 2022"],
                    ),
                ],
                "observed_outcomes": [
                    ObservedClinicalOutcome(
                        trial_id="NCT03318939",
                        trial_title="ZENITH20: Poziotinib in Patients with HER2 Exon 20 Mutant NSCLC",
                        phase=ClinicalStage.PHASE_II,
                        sample_size=115,
                        population="Previously treated HER2 Exon 20 insertion NSCLC",
                        biomarker_status="HER2 Exon 20 insertion",
                        orr_pct=27.8,
                        cr_pct=0.0,
                        dor_months=5.1,
                        pfs_months=5.5,
                        pfs_hazard_ratio=None,
                        os_months=15.0,
                        cbr_pct=68.0,
                        grade_3_plus_ae_pct=26.0,
                        treatment_discontinuation_pct=12.0,
                        dose_reduction_pct=68.0,
                        endpoint_review=EndpointReviewType.BLINDED_INDEPENDENT_CENTRAL_REVIEW,
                        source_citation="Le et al. JCO 2022; PMID:35235434",
                        pmid="35235434",
                    ),
                ],
                "model_predictions": [
                    ClinicalModelPrediction(
                        parameter="Probability of Regulatory Approval without New Randomized Trial",
                        predicted_value=0.08,
                        confidence_interval_low=0.02,
                        confidence_interval_high=0.15,
                        model_name="Regulatory Resubmission Bayesian Model",
                    ),
                ],
                "expert_interpretations": [
                    ClinicalExpertInterpretation(
                        topic="Regulatory Viability and ODAC Consensus",
                        consensus_view="Unfavorable risk-benefit balance. 68% dose reduction rate and 26% severe diarrhea reflect a narrow therapeutic index.",
                        regulatory_precedent="FDA CRL issued November 2022 following negative ODAC advisory panel vote.",
                        clinician_summary="Single-arm trial design was deemed insufficient to justify accelerated approval given the marginal 27.8% ORR and severe toxicity.",
                    ),
                ],
                "unknowns": [
                    "Whether altered intermittent dosing regimens can sufficiently widen therapeutic window without compromising efficacy.",
                ],
            },

            # 4. Neratinib (Nerlynx) — Approved Adjuvant Pan-HER with High Diarrhea Burden
            "neratinib": {
                "name": "Neratinib (Nerlynx)",
                "stage": ClinicalStage.APPROVED,
                "trials_evaluated": [
                    TrialDesignEvaluation(
                        trial_id="NCT00878709",
                        design_type=TrialDesignType.RANDOMIZED_CONTROLLED_TRIAL,
                        enrollment_count=2840,
                        sample_size_adequate=True,
                        comparator_arm="Placebo",
                        blinding_method="Double-Blind",
                        project_optimus_compliant=False,
                        randomized_dose_optimization=False,
                        biomarker_prospective=True,
                        adjudication=EndpointReviewType.BLINDED_INDEPENDENT_CENTRAL_REVIEW,
                        execution_flags=["Pivotal Phase 3 ExteNET trial"],
                    ),
                ],
                "observed_outcomes": [
                    ObservedClinicalOutcome(
                        trial_id="NCT00878709",
                        trial_title="ExteNET: Extended Adjuvant Neratinib After Trastuzumab in Early HER2+ Breast Cancer",
                        phase=ClinicalStage.PHASE_III,
                        sample_size=2840,
                        population="Early-stage HER2-positive breast cancer completed adjuvant trastuzumab",
                        biomarker_status="HER2-positive (HR+/HER2+ derived greatest benefit)",
                        orr_pct=None,
                        pfs_months=None,
                        pfs_hazard_ratio=0.73,
                        os_months=None,
                        os_hazard_ratio=0.78,
                        grade_3_plus_ae_pct=40.0,
                        treatment_discontinuation_pct=16.8,
                        dose_reduction_pct=31.2,
                        endpoint_review=EndpointReviewType.BLINDED_INDEPENDENT_CENTRAL_REVIEW,
                        source_citation="Chan et al. Lancet Oncology 2016; PMID:26874378",
                        pmid="26874378",
                    ),
                ],
                "model_predictions": [
                    ClinicalModelPrediction(
                        parameter="Adjuvant Label Expansion Probability",
                        predicted_value=0.92,
                    ),
                ],
                "expert_interpretations": [
                    ClinicalExpertInterpretation(
                        topic="Gastrointestinal Toxicity Management",
                        consensus_view="Mandatory loperamide prophylaxis required. 40% Grade 3 diarrhea in pivotal trial remains a significant compliance barrier.",
                        regulatory_precedent="FDA Approval granted with boxed warning / guidance on antidiarrheal prophylaxis.",
                        clinician_summary="Benefit concentrated primarily in hormone receptor-positive HER2+ subset; real-world adherence impacted by tolerability.",
                    ),
                ],
                "unknowns": [
                    "Long-term compliance in real-world community oncology without aggressive antidiarrheal protocol adherence.",
                ],
            },

            # 5. OX-HER2-01 — Preclinical Academic Spinout Program
            "ox-her2-01": {
                "name": "OX-HER2-01",
                "stage": ClinicalStage.PRECLINICAL,
                "trials_evaluated": [],
                "observed_outcomes": [],  # Strictly empty: NO clinical trials conducted!
                "model_predictions": [
                    ClinicalModelPrediction(
                        parameter="Preclinical to Phase I IND Clearance Probability",
                        predicted_value=0.68,
                        confidence_interval_low=0.55,
                        confidence_interval_high=0.78,
                        model_name="Preclinical Translational Pipeline Model",
                    ),
                    ClinicalModelPrediction(
                        parameter="Predicted Phase I MTD Dose Range",
                        predicted_value=150.0,
                        confidence_interval_low=100.0,
                        confidence_interval_high=250.0,
                    ),
                ],
                "expert_interpretations": [
                    ClinicalExpertInterpretation(
                        topic="Translational Roadmap & IND Readiness",
                        consensus_view="Strong preclinical in vivo intracranial efficacy justifies Phase 1 entry, but human oral bioavailability projections require non-rodent GLP verification.",
                        regulatory_precedent="Follows precedent of tucatinib and osimertinib brain-penetrant small-molecule development.",
                        clinician_summary="Program is currently preclinical. No clinical trial design, enrollment, or patient response data exists.",
                    ),
                ],
                "unknowns": [
                    "No human clinical trials observed; clinical safety, oral pharmacokinetics, and patient response rates are unknown.",
                    "GLP toxicology in non-rodent species required before Phase 1 first-in-human trial initiation.",
                ],
            },
        }
