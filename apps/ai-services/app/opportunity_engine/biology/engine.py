from __future__ import annotations

import logging
import math
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from app.opportunity_engine.intelligence import (
    EpistemicClass,
    IntelligenceEvidence,
    IntelligenceRuleFinding,
    IntelligenceValue,
    IntelligenceValueStatus,
    cutoff_valid_knowledge_graph_evidence,
    evidence_confidence,
    registered_model_prediction,
    unknown_value,
)

from .models import (
    BiologyIntelligence,
    BiologyIntelligenceProfile,
    BiologyObservationType,
    DimensionEvaluation,
    EvaluationDimension,
    EvaluationDimensionState,
    RawBiologicalObservation,
    ScoreFormulaLineage,
)

logger = logging.getLogger(__name__)


class BiologyIntelligenceEngine:
    """
    Biology Intelligence Engine.
    Evaluates:
    - target validity
    - mechanistic rationale
    - potency
    - selectivity
    - on-target evidence
    - off-target risk
    - biomarker strategy
    - genetic evidence
    - functional evidence
    - translational evidence
    - model diversity
    - human evidence

    Produces the 6 canonical scores derived strictly from empirical evidence:
    1. Biology Validation Score
    2. Potency Score
    3. Selectivity Score
    4. Biomarker Score
    5. Mechanistic Confidence
    6. Translational Readiness

    Core principle:
    IC50 values, selectivity ratios, CRISPR evidence, genetic dependency,
    animal efficacy, patient-derived models, clinical response must be
    represented as raw observations before becoming scores.
    Never manually assign scores simply to make a dashboard look complete.
    """

    def __init__(self) -> None:
        self._canonical_observations: Dict[str, List[RawBiologicalObservation]] = (
            self._load_canonical_benchmark_observations()
        )

    def evaluate_asset(
        self,
        asset_id: str,
        asset_name: Optional[str] = None,
        custom_observations: Optional[List[RawBiologicalObservation]] = None,
    ) -> BiologyIntelligenceProfile:
        """
        Evaluates an asset by aggregating raw biological observations,
        evaluating the 12 dimensions, and computing the 6 canonical scores.
        """
        # 1. Resolve raw observations
        obs_list = list(self._canonical_observations.get(asset_id, []))
        if custom_observations:
            obs_list.extend(custom_observations)

        resolved_name = asset_name or asset_id.capitalize()
        if not obs_list and asset_id in self._canonical_observations:
            obs_list = self._canonical_observations[asset_id]

        # 2. Evaluate all 12 dimensions
        dimension_evals: Dict[str, DimensionEvaluation] = {}
        for dim in EvaluationDimension:
            dimension_evals[dim.value] = self._evaluate_dimension(dim, obs_list)

        # 3. Compute 6 canonical scores with explicit mathematical lineage
        unknowns: List[str] = []

        potency_score, pot_lineage = self._derive_potency_score(obs_list)
        selectivity_score, sel_lineage = self._derive_selectivity_score(obs_list)
        biomarker_score, bio_lineage = self._derive_biomarker_score(obs_list)
        mech_confidence, mech_lineage = self._derive_mechanistic_confidence(obs_list)
        bio_validation_score, val_lineage = self._derive_biology_validation_score(obs_list)
        trans_readiness, trans_lineage = self._derive_translational_readiness(obs_list)

        lineages = {
            "potency_score": pot_lineage,
            "selectivity_score": sel_lineage,
            "biomarker_score": bio_lineage,
            "mechanistic_confidence": mech_lineage,
            "biology_validation_score": val_lineage,
            "translational_readiness": trans_lineage,
        }

        # Collect unknowns from lineages and dimensions
        for lin in lineages.values():
            for gap in lin.evidence_gaps:
                if gap not in unknowns:
                    unknowns.append(gap)

        for d_eval in dimension_evals.values():
            if d_eval.state == EvaluationDimensionState.INSUFFICIENT_EVIDENCE:
                msg = f"Insufficient evidence: No empirical observation available for {d_eval.dimension.value.replace('_', ' ')}."
                if msg not in unknowns:
                    unknowns.append(msg)

        # 4. Compute calibrated overall confidence
        # Penalized by the number of missing dimensions
        missing_count = sum(
            1 for d in dimension_evals.values()
            if d.state == EvaluationDimensionState.INSUFFICIENT_EVIDENCE
        )
        base_confidence = 0.95
        confidence_penalty = missing_count * 0.08
        overall_confidence = max(0.20, min(1.0, round(base_confidence - confidence_penalty, 2)))

        return BiologyIntelligenceProfile(
            asset_id=asset_id,
            asset_name=resolved_name,
            biology_validation_score=round(bio_validation_score, 1),
            potency_score=round(potency_score, 1),
            selectivity_score=round(selectivity_score, 1),
            biomarker_score=round(biomarker_score, 1),
            mechanistic_confidence=round(mech_confidence, 2),
            translational_readiness=round(trans_readiness, 1),
            dimensions=dimension_evals,
            raw_observations=obs_list,
            lineages=lineages,
            overall_confidence=overall_confidence,
            unknowns=unknowns,
            evaluated_at=datetime.now(timezone.utc),
        )

    def get_benchmark_profile(self, asset_id: str) -> BiologyIntelligenceProfile:
        """Returns the pre-evaluated profile for a benchmark asset."""
        name_map = {
            "zongertinib": "Zongertinib (BI 1810631)",
            "tucatinib": "Tucatinib (Tukysa)",
            "poziotinib": "Poziotinib (HM781-36B)",
            "neratinib": "Neratinib (Nerlynx)",
            "ox-her2-01": "OX-HER2-01",
        }
        return self.evaluate_asset(asset_id, asset_name=name_map.get(asset_id, asset_id))

    def list_benchmark_profiles(self) -> List[BiologyIntelligenceProfile]:
        """Returns evaluated profiles for all 5 canonical benchmark assets."""
        return [
            self.get_benchmark_profile("zongertinib"),
            self.get_benchmark_profile("tucatinib"),
            self.get_benchmark_profile("poziotinib"),
            self.get_benchmark_profile("neratinib"),
            self.get_benchmark_profile("ox-her2-01"),
        ]

    def get_raw_observations_for_asset(self, asset_id: str) -> List[RawBiologicalObservation]:
        """Returns all raw biological observations for an asset."""
        return list(self._canonical_observations.get(asset_id, []))

    def evaluate_intelligence(
        self,
        asset_id: str,
        prediction_cutoff: date,
        *,
        tenant_id: Optional[str] = None,
        asset_name: Optional[str] = None,
        custom_observations: Optional[List[RawBiologicalObservation]] = None,
        feature_store: Any | None = None,
        model_registry: Any | None = None,
        knowledge_graph: Any | None = None,
    ) -> BiologyIntelligence:
        """Synthesize only cutoff-valid, attributable biological evidence and optional ML."""
        if custom_observations and any(
            item.asset_id.lower() != asset_id.lower()
            or item.tenant_id not in (None, tenant_id)
            for item in custom_observations
        ):
            raise ValueError("Biology observations must belong to the requested asset and tenant.")

        observations = self.get_raw_observations_for_asset(asset_id) + list(custom_observations or [])
        observations = [
            item for item in observations if item.tenant_id in (None, tenant_id)
        ]
        admissible = [
            item
            for item in observations
            if item.observation_date is not None
            and item.observation_date <= prediction_cutoff
        ]
        undated_or_future = [item for item in observations if item not in admissible]

        def observation_evidence(item: RawBiologicalObservation) -> IntelligenceEvidence:
            return IntelligenceEvidence(
                evidence_id=str(item.id),
                source_type="biological_observation",
                source_reference=item.pmid or item.nct_id or str(item.id),
                citation=item.source_citation,
                observed_at=item.observation_date,
                confidence=(
                    item.confidence if "confidence" in item.model_fields_set else None
                ),
                epistemic_class=EpistemicClass.FACT,
                provenance={
                    "asset_id": item.asset_id,
                    "parameter_name": item.parameter_name,
                    "observation_type": item.observation_type.value,
                    "unit": item.unit,
                    "assay_type": item.assay_type,
                    "target_or_gene": item.target_or_gene,
                    "model_system": item.model_system,
                },
            )

        observed_evidence = [observation_evidence(item) for item in admissible]
        excluded_evidence = [
            IntelligenceEvidence(
                evidence_id=str(item.id),
                source_type="biological_observation_excluded_from_snapshot",
                source_reference=item.pmid or item.nct_id or str(item.id),
                citation=item.source_citation,
                observed_at=item.observation_date,
                confidence=(
                    item.confidence if "confidence" in item.model_fields_set else None
                ),
                epistemic_class=EpistemicClass.FACT,
                provenance={
                    "exclusion_reason": (
                        "observation_date_missing"
                        if item.observation_date is None
                        else "observation_after_prediction_cutoff"
                    ),
                    "prediction_cutoff": prediction_cutoff.isoformat(),
                },
            )
            for item in undated_or_future
        ]
        kg_evidence = cutoff_valid_knowledge_graph_evidence(
            asset_id=asset_id,
            prediction_cutoff=prediction_cutoff,
            knowledge_graph=knowledge_graph,
        )

        _, potency_lineage = self._derive_potency_score(admissible)
        _, selectivity_lineage = self._derive_selectivity_score(admissible)
        _, biomarker_lineage = self._derive_biomarker_score(admissible)
        _, mechanism_lineage = self._derive_mechanistic_confidence(admissible)
        _, validation_lineage = self._derive_biology_validation_score(admissible)
        _, translational_lineage = self._derive_translational_readiness(admissible)
        lineage_by_output = {
            "biology_validation": validation_lineage,
            "potency": potency_lineage,
            "selectivity": selectivity_lineage,
            "mechanistic_confidence": mechanism_lineage,
            "biomarker_strength": biomarker_lineage,
            "translational_readiness": translational_lineage,
        }

        metrics: dict[str, IntelligenceValue] = {}
        for output_name, lineage in lineage_by_output.items():
            supporting = [
                observation_evidence(item)
                for item in admissible
                if str(item.id) in {str(value) for value in lineage.raw_observation_ids}
            ]
            if not supporting:
                metrics[output_name] = unknown_value(
                    output_name,
                    "No dated, cutoff-valid biological observation supports this metric.",
                    provenance={
                        "formula": lineage.formula,
                        "evidence_gaps": lineage.evidence_gaps,
                    },
                )
                continue
            metrics[output_name] = IntelligenceValue(
                name=output_name,
                value=lineage.calculated_value,
                status=IntelligenceValueStatus.AVAILABLE,
                epistemic_class=EpistemicClass.DERIVED_FEATURE,
                confidence=evidence_confidence(supporting),
                supporting_evidence=supporting,
                provenance={
                    "formula": lineage.formula,
                    "inputs": lineage.inputs,
                    "observation_ids": [str(value) for value in lineage.raw_observation_ids],
                    "prediction_cutoff": prediction_cutoff.isoformat(),
                },
            )

        model_component, prediction = registered_model_prediction(
            model_name="biology_translational",
            asset_id=asset_id,
            prediction_cutoff=prediction_cutoff,
            tenant_id=tenant_id,
            registry=model_registry,
            feature_store=feature_store,
        )
        if prediction is not None and prediction.probability is not None:
            model_evidence = [
                IntelligenceEvidence(
                    evidence_id=f"feature:{name}",
                    source_type="model_input_feature",
                    source_reference=reference,
                    confidence=None,
                    epistemic_class=EpistemicClass.ML_PREDICTION,
                    provenance={"feature_name": name, "model_version": prediction.model_version},
                )
                for name, metadata in prediction.input_snapshot.get("observation_dates", {}).items()
                for reference in metadata.get("evidence_references", [])
            ]
            metrics["translational_readiness"] = IntelligenceValue(
                name="translational_readiness",
                value=prediction.probability,
                status=IntelligenceValueStatus.AVAILABLE,
                epistemic_class=EpistemicClass.ML_PREDICTION,
                confidence=prediction.confidence,
                supporting_evidence=model_evidence,
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

        rule_findings: list[IntelligenceRuleFinding] = []
        for dimension in EvaluationDimension:
            evaluated = self._evaluate_dimension(dimension, admissible)
            if not evaluated.raw_observation_ids:
                continue
            rule_findings.append(
                IntelligenceRuleFinding(
                    rule_id=f"biology_dimension:{dimension.value}",
                    result=evaluated.state.value,
                    applied=True,
                    supporting_evidence_ids=[str(value) for value in evaluated.raw_observation_ids],
                    provenance={
                        "findings": evaluated.findings,
                        "prediction_cutoff": prediction_cutoff.isoformat(),
                    },
                )
            )
        if kg_evidence:
            rule_findings.append(
                IntelligenceRuleFinding(
                    rule_id="kg:provenance_backed_biology_relationships",
                    result="cutoff_valid_relationship_evidence_present",
                    applied=True,
                    supporting_evidence_ids=[item.evidence_id for item in kg_evidence],
                    provenance={"relationship_count": len(kg_evidence)},
                )
            )

        return BiologyIntelligence(
            asset_id=asset_id,
            asset_name=asset_name or asset_id.capitalize(),
            tenant_id=tenant_id,
            prediction_cutoff=prediction_cutoff,
            biology_validation=metrics["biology_validation"],
            potency=metrics["potency"],
            selectivity=metrics["selectivity"],
            mechanistic_confidence=metrics["mechanistic_confidence"],
            biomarker_strength=metrics["biomarker_strength"],
            translational_readiness=metrics["translational_readiness"],
            evidence=observed_evidence,
            excluded_undated_evidence=excluded_evidence,
            knowledge_graph_evidence=kg_evidence,
            rule_findings=rule_findings,
            ml_component=model_component,
        )

    # ==============================================================================
    # Dimension Evaluation Logic
    # ==============================================================================

    def _evaluate_dimension(
        self,
        dimension: EvaluationDimension,
        observations: List[RawBiologicalObservation],
    ) -> DimensionEvaluation:
        """Evaluates one of the 12 biological dimensions against raw observations."""
        type_mapping = {
            EvaluationDimension.TARGET_VALIDITY: [BiologyObservationType.TARGET_VALIDITY],
            EvaluationDimension.MECHANISTIC_RATIONALE: [BiologyObservationType.MECHANISTIC_RATIONALE],
            EvaluationDimension.POTENCY: [BiologyObservationType.IC50_BIOCHEMICAL, BiologyObservationType.IC50_CELLULAR],
            EvaluationDimension.SELECTIVITY: [BiologyObservationType.SELECTIVITY_RATIO],
            EvaluationDimension.ON_TARGET_EVIDENCE: [BiologyObservationType.ON_TARGET_ENGAGEMENT],
            EvaluationDimension.OFF_TARGET_RISK: [BiologyObservationType.OFF_TARGET_RISK],
            EvaluationDimension.BIOMARKER_STRATEGY: [BiologyObservationType.BIOMARKER_STRATEGY],
            EvaluationDimension.GENETIC_EVIDENCE: [BiologyObservationType.GENETIC_EVIDENCE, BiologyObservationType.CRISPR_DEPENDENCY],
            EvaluationDimension.FUNCTIONAL_EVIDENCE: [BiologyObservationType.FUNCTIONAL_EVIDENCE],
            EvaluationDimension.TRANSLATIONAL_EVIDENCE: [BiologyObservationType.ANIMAL_EFFICACY],
            EvaluationDimension.MODEL_DIVERSITY: [BiologyObservationType.PATIENT_DERIVED_MODELS],
            EvaluationDimension.HUMAN_EVIDENCE: [BiologyObservationType.CLINICAL_RESPONSE],
        }

        matched_types = type_mapping.get(dimension, [])
        relevant_obs = [o for o in observations if o.observation_type in matched_types]

        if not relevant_obs:
            return DimensionEvaluation(
                dimension=dimension,
                state=EvaluationDimensionState.INSUFFICIENT_EVIDENCE,
                raw_observation_ids=[],
                raw_values_summary={},
                score_contribution=0.0,
                confidence=0.0,
                findings=f"No empirical observations recorded for {dimension.value.replace('_', ' ')}.",
                evidence_citations=[],
            )

        citations = [o.source_citation for o in relevant_obs]
        obs_ids = [o.id for o in relevant_obs]
        summary_dict = {o.parameter_name: f"{o.normalized_value} {o.unit or ''}".strip() for o in relevant_obs}

        # Check for contradictions
        has_negative = any(o.normalized_value < 0 and o.observation_type != BiologyObservationType.CRISPR_DEPENDENCY for o in relevant_obs)
        state = EvaluationDimensionState.CONTRADICTORY if has_negative else EvaluationDimensionState.VERIFIED_FACT

        # Average confidence of observations
        avg_conf = sum(o.confidence for o in relevant_obs) / len(relevant_obs)
        findings = "; ".join([f"{o.parameter_name}: {o.raw_text_value}" for o in relevant_obs])

        return DimensionEvaluation(
            dimension=dimension,
            state=state,
            raw_observation_ids=obs_ids,
            raw_values_summary=summary_dict,
            score_contribution=100.0,
            confidence=round(avg_conf, 2),
            findings=findings,
            evidence_citations=citations,
        )

    # ==============================================================================
    # 6 Canonical Score Derivations
    # ==============================================================================

    def _derive_potency_score(
        self,
        observations: List[RawBiologicalObservation],
    ) -> Tuple[float, ScoreFormulaLineage]:
        """
        Derives Potency Score (0 - 100) strictly from empirical IC50 values.
        Formula:
          f(IC50) = clamp(100 - 25 * log10(max(IC50, 0.5) / 0.5), 0, 100)
          Score = 0.4 * f(IC50_enz) + 0.6 * f(IC50_cell)
        """
        enz_obs = next((o for o in observations if o.observation_type == BiologyObservationType.IC50_BIOCHEMICAL), None)
        cell_obs = next((o for o in observations if o.observation_type == BiologyObservationType.IC50_CELLULAR), None)

        used_ids: List[UUID] = []
        inputs: Dict[str, Any] = {}
        gaps: List[str] = []

        if not enz_obs and not cell_obs:
            return 0.0, ScoreFormulaLineage(
                score_name="Potency Score",
                formula="f(IC50) = clamp(100 - 25*log10(IC50/0.5), 0, 100); 0.4*enz + 0.6*cell",
                inputs={},
                raw_observation_ids=[],
                calculated_value=0.0,
                confidence_penalty_applied=1.0,
                evidence_gaps=["No biochemical or cellular IC50 measurements available."],
            )

        def ic50_to_score(val: float) -> float:
            if val <= 0.5:
                return 100.0
            return max(0.0, min(100.0, 100.0 - 25.0 * math.log10(val / 0.5)))

        penalty = 0.0
        if enz_obs and cell_obs:
            used_ids = [enz_obs.id, cell_obs.id]
            inputs = {"ic50_biochemical_nM": enz_obs.normalized_value, "ic50_cellular_nM": cell_obs.normalized_value}
            score = 0.4 * ic50_to_score(enz_obs.normalized_value) + 0.6 * ic50_to_score(cell_obs.normalized_value)
        elif cell_obs:
            used_ids = [cell_obs.id]
            inputs = {"ic50_cellular_nM": cell_obs.normalized_value}
            score = ic50_to_score(cell_obs.normalized_value) * 0.90
            penalty = 0.10
            gaps.append("Biochemical IC50 is missing; cellular IC50 used with 10% penalty.")
        else:
            assert enz_obs is not None
            used_ids = [enz_obs.id]
            inputs = {"ic50_biochemical_nM": enz_obs.normalized_value}
            score = ic50_to_score(enz_obs.normalized_value) * 0.85
            penalty = 0.15
            gaps.append("Cellular anti-proliferation IC50 is missing; biochemical IC50 used with 15% penalty.")

        return max(0.0, min(100.0, score)), ScoreFormulaLineage(
            score_name="Potency Score",
            formula="0.4 * f(IC50_enz) + 0.6 * f(IC50_cell) where f(x) = 100 - 25*log10(x/0.5)",
            inputs=inputs,
            raw_observation_ids=used_ids,
            calculated_value=round(score, 2),
            confidence_penalty_applied=penalty,
            evidence_gaps=gaps,
        )

    def _derive_selectivity_score(
        self,
        observations: List[RawBiologicalObservation],
    ) -> Tuple[float, ScoreFormulaLineage]:
        """
        Derives Selectivity Score (0 - 100) strictly from fold selectivity ratios
        and off-target kinome promiscuity hit rate.
        Formula:
          g(R) = clamp(10 + 45 * log10(max(R, 1.0)), 0, 100)
          Deducts kinome hit rate: penalty = kinome_hits_pct * 0.5
        """
        ratio_obs = next((o for o in observations if o.observation_type == BiologyObservationType.SELECTIVITY_RATIO), None)
        off_obs = next((o for o in observations if o.observation_type == BiologyObservationType.OFF_TARGET_RISK), None)

        if not ratio_obs:
            return 0.0, ScoreFormulaLineage(
                score_name="Selectivity Score",
                formula="g(R) = 10 + 45*log10(R) - (kinome_hits_pct * 0.5)",
                inputs={},
                raw_observation_ids=[],
                calculated_value=0.0,
                confidence_penalty_applied=1.0,
                evidence_gaps=["No fold-selectivity ratio vs counter-target (e.g. WT EGFR) observed."],
            )

        R = max(1.0, ratio_obs.normalized_value)
        base_score = 10.0 + 45.0 * math.log10(R)
        base_score = max(0.0, min(100.0, base_score))

        used_ids = [ratio_obs.id]
        inputs: Dict[str, Any] = {"fold_selectivity_ratio": ratio_obs.normalized_value}
        gaps: List[str] = []

        penalty = 0.0
        if off_obs:
            used_ids.append(off_obs.id)
            inputs["kinome_off_target_hits_pct"] = off_obs.normalized_value
            penalty = off_obs.normalized_value * 0.5
            if off_obs.normalized_value > 10.0:
                gaps.append(f"Elevated off-target kinome hit rate ({off_obs.normalized_value}%) reduces selectivity score.")
        else:
            gaps.append("Off-target kinome panel screening not provided.")

        final_score = max(0.0, min(100.0, base_score - penalty))

        return final_score, ScoreFormulaLineage(
            score_name="Selectivity Score",
            formula="g(R) = 10 + 45*log10(R) - (kinome_hits_pct * 0.5)",
            inputs=inputs,
            raw_observation_ids=used_ids,
            calculated_value=round(final_score, 2),
            confidence_penalty_applied=round(penalty, 2),
            evidence_gaps=gaps,
        )

    def _derive_biomarker_score(
        self,
        observations: List[RawBiologicalObservation],
    ) -> Tuple[float, ScoreFormulaLineage]:
        """
        Derives Biomarker Score (0 - 100) based on mutational specificity,
        genomic dependency shift, and companion diagnostic assay feasibility.
        """
        bio_obs = [o for o in observations if o.observation_type == BiologyObservationType.BIOMARKER_STRATEGY]
        gen_obs = [o for o in observations if o.observation_type == BiologyObservationType.GENETIC_EVIDENCE]

        if not bio_obs and not gen_obs:
            return 0.0, ScoreFormulaLineage(
                score_name="Biomarker Score",
                formula="Defined mutation (35) + Mutant/WT shift (35) + Companion diagnostic (30)",
                inputs={},
                raw_observation_ids=[],
                calculated_value=0.0,
                confidence_penalty_applied=1.0,
                evidence_gaps=["No biomarker stratification or mutational sensitivity evidence found."],
            )

        score = 0.0
        inputs: Dict[str, Any] = {}
        used_ids: List[UUID] = []
        gaps: List[str] = []

        has_defined_genomic_driver = False
        has_companion_diagnostic = False
        has_differential_sensitivity = False

        for o in bio_obs:
            used_ids.append(o.id)
            inputs[o.parameter_name] = o.normalized_value
            combined_text = f"{o.parameter_name} {o.raw_text_value}".lower()
            if any(term in combined_text for term in ("mutation", "mutant", "exon", "amplif", "alteration", "ihc", "fish")):
                has_defined_genomic_driver = True
            if any(term in combined_text for term in ("companion", "diagnostic", "assay", "ngs", "pcr", "liquid biopsy")):
                has_companion_diagnostic = True

        for o in gen_obs:
            used_ids.append(o.id)
            inputs[o.parameter_name] = o.normalized_value
            has_differential_sensitivity = True

        # Check CRISPR dependency or fold selectivity ratio as supporting genomic sensitivity
        crispr = next((o for o in observations if o.observation_type == BiologyObservationType.CRISPR_DEPENDENCY), None)
        if crispr and crispr.normalized_value <= -0.5:
            if crispr.id not in used_ids:
                used_ids.append(crispr.id)
            inputs["crispr_dependency_support"] = crispr.normalized_value
            has_differential_sensitivity = True

        sel_ratio = next((o for o in observations if o.observation_type == BiologyObservationType.SELECTIVITY_RATIO), None)
        if sel_ratio and sel_ratio.normalized_value >= 10.0:
            if sel_ratio.id not in used_ids:
                used_ids.append(sel_ratio.id)
            inputs["selectivity_margin_support"] = sel_ratio.normalized_value
            has_differential_sensitivity = True

        if has_defined_genomic_driver:
            score += 35.0
        else:
            gaps.append("Defined genomic driver mutation or amplification not identified.")

        if has_differential_sensitivity:
            score += 35.0
        else:
            gaps.append("Differential mutant vs wild-type sensitivity or oncogene addiction unverified.")

        if has_companion_diagnostic:
            score += 30.0
        else:
            gaps.append("Clinical companion diagnostic assay (NGS/PCR/IHC) unvalidated.")

        final_score = max(0.0, min(100.0, score))
        return final_score, ScoreFormulaLineage(
            score_name="Biomarker Score",
            formula="Defined mutation (35) + Differential sensitivity (35) + Companion Dx (30)",
            inputs=inputs,
            raw_observation_ids=used_ids,
            calculated_value=round(final_score, 2),
            confidence_penalty_applied=0.0,
            evidence_gaps=gaps,
        )

    def _derive_mechanistic_confidence(
        self,
        observations: List[RawBiologicalObservation],
    ) -> Tuple[float, ScoreFormulaLineage]:
        """
        Derives Mechanistic Confidence (0.0 - 1.0) strictly from:
        - On-target engagement (CETSA Delta Tm >= 2.0 C or phospho-IC50 <= 20 nM): +0.35
        - On-target resistance proof (e.g. C805S/T790M gatekeeper rescue): +0.35
        - Clean selectivity / absence of unexplained cytotoxic mechanism: +0.30
        """
        target_eng = next((o for o in observations if o.observation_type == BiologyObservationType.ON_TARGET_ENGAGEMENT), None)
        mech_rat = next((o for o in observations if o.observation_type == BiologyObservationType.MECHANISTIC_RATIONALE), None)
        ratio_obs = next((o for o in observations if o.observation_type == BiologyObservationType.SELECTIVITY_RATIO), None)

        score = 0.0
        used_ids: List[UUID] = []
        inputs: Dict[str, Any] = {}
        gaps: List[str] = []

        if target_eng:
            used_ids.append(target_eng.id)
            inputs[target_eng.parameter_name] = target_eng.normalized_value
            score += 0.35
        else:
            gaps.append("Target engagement (e.g. CETSA thermal shift or intracellular target phosphorylation) unverified.")

        if mech_rat:
            used_ids.append(mech_rat.id)
            inputs[mech_rat.parameter_name] = mech_rat.raw_text_value
            score += 0.35
        else:
            gaps.append("Direct mechanistic binding mode and gatekeeper resistance verification missing.")

        if ratio_obs and ratio_obs.normalized_value >= 10.0:
            used_ids.append(ratio_obs.id)
            inputs["selectivity_margin"] = ratio_obs.normalized_value
            score += 0.30
        elif ratio_obs:
            used_ids.append(ratio_obs.id)
            inputs["selectivity_margin"] = ratio_obs.normalized_value
            score += 0.15
            gaps.append("Narrow selectivity margin raises risk of off-target mechanistic confounding.")
        else:
            gaps.append("Selectivity window unverified; mechanistic specificity uncertain.")

        final_score = max(0.0, min(1.0, score))
        return final_score, ScoreFormulaLineage(
            score_name="Mechanistic Confidence",
            formula="Target engagement (0.35) + Resistance proof (0.35) + Selectivity margin (0.30)",
            inputs=inputs,
            raw_observation_ids=used_ids,
            calculated_value=round(final_score, 2),
            confidence_penalty_applied=round(1.0 - final_score, 2),
            evidence_gaps=gaps,
        )

    def _derive_biology_validation_score(
        self,
        observations: List[RawBiologicalObservation],
    ) -> Tuple[float, ScoreFormulaLineage]:
        """
        Derives Biology Validation Score (0 - 100) from:
        - Genetic dependency (CRISPR DepMap Chronos <= -0.5): 35 pts
        - Target validity (Human oncogene driver in ClinVar/TCGA): 35 pts
        - Functional evidence (Apoptosis induction >= 3.0x): 30 pts
        """
        crispr_obs = next((o for o in observations if o.observation_type == BiologyObservationType.CRISPR_DEPENDENCY), None)
        target_obs = next((o for o in observations if o.observation_type == BiologyObservationType.TARGET_VALIDITY), None)
        func_obs = next((o for o in observations if o.observation_type == BiologyObservationType.FUNCTIONAL_EVIDENCE), None)

        score = 0.0
        used_ids: List[UUID] = []
        inputs: Dict[str, Any] = {}
        gaps: List[str] = []

        if crispr_obs:
            used_ids.append(crispr_obs.id)
            inputs["crispr_chronos_score"] = crispr_obs.normalized_value
            if crispr_obs.normalized_value <= -0.5:
                score += 35.0
            else:
                score += 20.0
        else:
            gaps.append("No CRISPR knockout or genetic dependency screen (e.g. DepMap) observed.")

        if target_obs:
            used_ids.append(target_obs.id)
            inputs["target_validity"] = target_obs.raw_text_value
            score += 35.0
        else:
            gaps.append("No canonical human target disease association documented.")

        if func_obs:
            used_ids.append(func_obs.id)
            inputs["functional_evidence"] = func_obs.normalized_value
            if func_obs.normalized_value >= 3.0:
                score += 30.0
            else:
                score += 15.0
        else:
            gaps.append("No functional in vitro phenotype assays (e.g. apoptosis, colony formation) observed.")

        final_score = max(0.0, min(100.0, score))
        return final_score, ScoreFormulaLineage(
            score_name="Biology Validation Score",
            formula="Genetic dependency (35) + Target validity (35) + Functional assay (30)",
            inputs=inputs,
            raw_observation_ids=used_ids,
            calculated_value=round(final_score, 2),
            confidence_penalty_applied=round(100.0 - final_score, 2),
            evidence_gaps=gaps,
        )

    def _derive_translational_readiness(
        self,
        observations: List[RawBiologicalObservation],
    ) -> Tuple[float, ScoreFormulaLineage]:
        """
        Derives Translational Readiness (0 - 100) from:
        - In vivo animal efficacy (Xenograft TGI >= 80%): 35 pts
        - Model diversity (Count of distinct model systems tested >= 3: 30 pts; 2: 18 pts; 1: 8 pts)
        - Human clinical evidence (Phase 1/2 clinical ORR >= 50%: 35 pts; 25-50%: 20 pts; no clinical data: 0 pts)
        """
        animal_obs = next((o for o in observations if o.observation_type == BiologyObservationType.ANIMAL_EFFICACY), None)
        models_obs = next((o for o in observations if o.observation_type == BiologyObservationType.PATIENT_DERIVED_MODELS), None)
        human_obs = next((o for o in observations if o.observation_type == BiologyObservationType.CLINICAL_RESPONSE), None)

        score = 0.0
        used_ids: List[UUID] = []
        inputs: Dict[str, Any] = {}
        gaps: List[str] = []

        if animal_obs:
            used_ids.append(animal_obs.id)
            inputs["animal_tgi_percent"] = animal_obs.normalized_value
            if animal_obs.normalized_value >= 80.0:
                score += 35.0
            else:
                score += max(0.0, (animal_obs.normalized_value / 80.0) * 35.0)
        else:
            gaps.append("No in vivo animal xenograft or intracranial efficacy data observed.")

        if models_obs:
            used_ids.append(models_obs.id)
            cnt = int(models_obs.normalized_value)
            inputs["distinct_model_classes_count"] = cnt
            if cnt >= 3:
                score += 30.0
            elif cnt == 2:
                score += 18.0
            else:
                score += 8.0
        else:
            gaps.append("Model diversity unverified (e.g. CDX, PDX, organoid models).")

        if human_obs:
            used_ids.append(human_obs.id)
            orr = human_obs.normalized_value
            inputs["clinical_orr_percent"] = orr
            if orr >= 50.0:
                score += 35.0
            elif orr >= 25.0:
                score += 20.0
            else:
                score += 10.0
        else:
            gaps.append("No human clinical trial data observed (program is preclinical or lacks patient response evidence).")

        final_score = max(0.0, min(100.0, score))
        return final_score, ScoreFormulaLineage(
            score_name="Translational Readiness",
            formula="In vivo animal efficacy (35) + Model diversity (30) + Human clinical response (35)",
            inputs=inputs,
            raw_observation_ids=used_ids,
            calculated_value=round(final_score, 2),
            confidence_penalty_applied=round(100.0 - final_score, 2),
            evidence_gaps=gaps,
        )

    # ==============================================================================
    # Canonical Benchmark Asset Observations
    # ==============================================================================

    def _load_canonical_benchmark_observations(self) -> Dict[str, List[RawBiologicalObservation]]:
        """Preloads empirical raw ground truth biological observations for canonical assets."""
        return {
            # 1. Zongertinib (BI 1810631)
            "zongertinib": [
                RawBiologicalObservation(
                    asset_id="zongertinib",
                    parameter_name="IC50_biochemical_HER2_WT",
                    observation_type=BiologyObservationType.IC50_BIOCHEMICAL,
                    raw_text_value="0.8 nM against recombinant HER2 kinase domain",
                    normalized_value=0.8,
                    unit="nM",
                    assay_type="Enzymatic Kinase Assay",
                    target_or_gene="HER2",
                    source_citation="Wilding et al. Nature Cancer 2024; PMID:38718468",
                    pmid="38718468",
                ),
                RawBiologicalObservation(
                    asset_id="zongertinib",
                    parameter_name="IC50_cellular_HER2_Exon20",
                    observation_type=BiologyObservationType.IC50_CELLULAR,
                    raw_text_value="1.9 nM in Ba/F3 HER2 Exon 20 A775_G776insYVMA cells",
                    normalized_value=1.9,
                    unit="nM",
                    assay_type="Cell Viability CTG",
                    target_or_gene="HER2",
                    model_system="Ba/F3 Exon20 and NCI-H1781",
                    source_citation="Wilding et al. Nature Cancer 2024; PMID:38718468",
                    pmid="38718468",
                ),
                RawBiologicalObservation(
                    asset_id="zongertinib",
                    parameter_name="selectivity_ratio_WT_EGFR",
                    observation_type=BiologyObservationType.SELECTIVITY_RATIO,
                    raw_text_value="59.0-fold selectivity margin vs wild-type EGFR (WT EGFR IC50 = 112.1 nM)",
                    normalized_value=59.0,
                    unit="fold",
                    assay_type="Comparative Proliferation Assay",
                    target_or_gene="EGFR",
                    source_citation="Wilding et al. Nature Cancer 2024; PMID:38718468",
                    pmid="38718468",
                ),
                RawBiologicalObservation(
                    asset_id="zongertinib",
                    parameter_name="off_target_kinome_hits_pct",
                    observation_type=BiologyObservationType.OFF_TARGET_RISK,
                    raw_text_value="1.2% off-target kinase hits in 400+ kinase screening panel at 1 uM",
                    normalized_value=1.2,
                    unit="percent",
                    assay_type="KinomeScan 468 kinases",
                    source_citation="Wilding et al. Nature Cancer 2024; PMID:38718468",
                    pmid="38718468",
                ),
                RawBiologicalObservation(
                    asset_id="zongertinib",
                    parameter_name="target_validity_ERBB2_driver",
                    observation_type=BiologyObservationType.TARGET_VALIDITY,
                    raw_text_value="ERBB2 activating kinase domain mutations are oncogenic drivers across lung and breast carcinomas",
                    normalized_value=1.0,
                    source_citation="ClinVar & TCGA ERBB2 Pan-Cancer Atlas 2023",
                ),
                RawBiologicalObservation(
                    asset_id="zongertinib",
                    parameter_name="mechanistic_rationale_covalent_sparing",
                    observation_type=BiologyObservationType.MECHANISTIC_RATIONALE,
                    raw_text_value="Covalent ATP-competitive inhibitor binding selectively to the inactive C-helix-out conformation of mutant HER2 sparing WT EGFR",
                    normalized_value=1.0,
                    source_citation="Wilding et al. Nature Cancer 2024; PMID:38718468",
                    pmid="38718468",
                ),
                RawBiologicalObservation(
                    asset_id="zongertinib",
                    parameter_name="target_engagement_CETSA_Tm",
                    observation_type=BiologyObservationType.ON_TARGET_ENGAGEMENT,
                    raw_text_value="CETSA thermal shift Delta Tm = +4.8 C on cellular HER2; phospho-HER2 ablation IC50 = 2.4 nM",
                    normalized_value=4.8,
                    unit="deg_C",
                    assay_type="Cellular Thermal Shift Assay",
                    source_citation="Wilding et al. Nature Cancer 2024; PMID:38718468",
                    pmid="38718468",
                ),
                RawBiologicalObservation(
                    asset_id="zongertinib",
                    parameter_name="biomarker_strategy_exon20_and_mutants",
                    observation_type=BiologyObservationType.BIOMARKER_STRATEGY,
                    raw_text_value="Stratification by HER2 kinase domain mutations (Exon 20 insertions, L755S, V777L) via validated NGS companion diagnostic assay",
                    normalized_value=1.0,
                    source_citation="Beamion LUNG-1 Biomarker Subprotocol (NCT04886804)",
                    nct_id="NCT04886804",
                ),
                RawBiologicalObservation(
                    asset_id="zongertinib",
                    parameter_name="crispr_chronos_score",
                    observation_type=BiologyObservationType.CRISPR_DEPENDENCY,
                    raw_text_value="DepMap Chronos score = -1.15 in HER2-mutant cell lines (strong essential oncogenic dependency)",
                    normalized_value=-1.15,
                    unit="Chronos score",
                    assay_type="DepMap Achilles CRISPR Screen",
                    source_citation="DepMap Public 24Q2 ERBB2 Dependency",
                ),
                RawBiologicalObservation(
                    asset_id="zongertinib",
                    parameter_name="functional_apoptosis_induction",
                    observation_type=BiologyObservationType.FUNCTIONAL_EVIDENCE,
                    raw_text_value="4.2-fold induction of cleaved PARP and Caspase 3/7 at 10 nM; G1 cell cycle arrest",
                    normalized_value=4.2,
                    unit="fold_induction",
                    assay_type="Apoptosis Luminescent Assay",
                    source_citation="Wilding et al. Nature Cancer 2024; PMID:38718468",
                    pmid="38718468",
                ),
                RawBiologicalObservation(
                    asset_id="zongertinib",
                    parameter_name="animal_tgi_percent",
                    observation_type=BiologyObservationType.ANIMAL_EFFICACY,
                    raw_text_value="94.5% tumor growth inhibition (TGI) in NCI-H1781 xenografts; intracranial brain metastasis regression",
                    normalized_value=94.5,
                    unit="percent",
                    assay_type="CDX Xenograft Model",
                    model_system="NCI-H1781 CDX and intracranial Ba/F3 models",
                    source_citation="Wilding et al. Nature Cancer 2024; PMID:38718468",
                    pmid="38718468",
                ),
                RawBiologicalObservation(
                    asset_id="zongertinib",
                    parameter_name="patient_derived_model_count",
                    observation_type=BiologyObservationType.PATIENT_DERIVED_MODELS,
                    raw_text_value="4 distinct model systems tested: cell line xenografts, patient-derived xenografts (PDX), patient-derived organoids (PDO), and orthotopic intracranial models",
                    normalized_value=4.0,
                    unit="model_systems_count",
                    source_citation="Boehringer Ingelheim Preclinical Dossier 2024",
                ),
                RawBiologicalObservation(
                    asset_id="zongertinib",
                    parameter_name="clinical_response_ORR",
                    observation_type=BiologyObservationType.CLINICAL_RESPONSE,
                    raw_text_value="73.8% confirmed Objective Response Rate (ORR) in Phase 1b/2 Beamion LUNG-1 trial",
                    normalized_value=73.8,
                    unit="percent",
                    assay_type="Phase 1b/2 Trial",
                    source_citation="Beamion LUNG-1 Clinical Trial; NCT04886804",
                    nct_id="NCT04886804",
                ),
            ],
            # 2. Tucatinib (ONT-380)
            "tucatinib": [
                RawBiologicalObservation(
                    asset_id="tucatinib",
                    parameter_name="IC50_biochemical_HER2",
                    observation_type=BiologyObservationType.IC50_BIOCHEMICAL,
                    raw_text_value="6.9 nM enzymatic IC50 against HER2",
                    normalized_value=6.9,
                    unit="nM",
                    source_citation="Phenix et al. Cancer Res 2016",
                ),
                RawBiologicalObservation(
                    asset_id="tucatinib",
                    parameter_name="IC50_cellular_HER2",
                    observation_type=BiologyObservationType.IC50_CELLULAR,
                    raw_text_value="8.0 nM in HER2-amplified BT474 cells",
                    normalized_value=8.0,
                    unit="nM",
                    source_citation="Phenix et al. Cancer Res 2016",
                ),
                RawBiologicalObservation(
                    asset_id="tucatinib",
                    parameter_name="selectivity_ratio_WT_EGFR",
                    observation_type=BiologyObservationType.SELECTIVITY_RATIO,
                    raw_text_value="49.0-fold selectivity vs wild-type EGFR (WT EGFR IC50 = 392.0 nM)",
                    normalized_value=49.0,
                    unit="fold",
                    source_citation="Phenix et al. Cancer Res 2016",
                ),
                RawBiologicalObservation(
                    asset_id="tucatinib",
                    parameter_name="off_target_kinome_hits_pct",
                    observation_type=BiologyObservationType.OFF_TARGET_RISK,
                    raw_text_value="3.5% off-target hit rate in kinase screening panel",
                    normalized_value=3.5,
                    unit="percent",
                    source_citation="Phenix et al. Cancer Res 2016",
                ),
                RawBiologicalObservation(
                    asset_id="tucatinib",
                    parameter_name="target_validity_HER2",
                    observation_type=BiologyObservationType.TARGET_VALIDITY,
                    raw_text_value="HER2 amplification validated in 20% of metastatic breast cancers",
                    normalized_value=1.0,
                    source_citation="NCCN Breast Cancer Guidelines 2024",
                ),
                RawBiologicalObservation(
                    asset_id="tucatinib",
                    parameter_name="mechanistic_rationale_reversible",
                    observation_type=BiologyObservationType.MECHANISTIC_RATIONALE,
                    raw_text_value="Reversible ATP-competitive kinase inhibitor highly selective for HER2 over EGFR",
                    normalized_value=1.0,
                    source_citation="Phenix et al. Cancer Res 2016",
                ),
                RawBiologicalObservation(
                    asset_id="tucatinib",
                    parameter_name="target_engagement_pHER2",
                    observation_type=BiologyObservationType.ON_TARGET_ENGAGEMENT,
                    raw_text_value="Intracellular phospho-HER2 inhibition IC50 = 8.5 nM",
                    normalized_value=8.5,
                    unit="nM",
                    source_citation="Phenix et al. Cancer Res 2016",
                ),
                RawBiologicalObservation(
                    asset_id="tucatinib",
                    parameter_name="biomarker_strategy_HER2_amp",
                    observation_type=BiologyObservationType.BIOMARKER_STRATEGY,
                    raw_text_value="Stratified by HER2 amplification (IHC 3+ / FISH+) with companion FDA-approved diagnostics",
                    normalized_value=1.0,
                    source_citation="FDA Approval Label Tukysa 2020",
                ),
                RawBiologicalObservation(
                    asset_id="tucatinib",
                    parameter_name="crispr_chronos_score",
                    observation_type=BiologyObservationType.CRISPR_DEPENDENCY,
                    raw_text_value="DepMap Chronos score = -0.92 in HER2+ cell lines",
                    normalized_value=-0.92,
                    source_citation="DepMap 24Q2",
                ),
                RawBiologicalObservation(
                    asset_id="tucatinib",
                    parameter_name="functional_apoptosis_induction",
                    observation_type=BiologyObservationType.FUNCTIONAL_EVIDENCE,
                    raw_text_value="3.1-fold apoptosis induction in BT474 lines",
                    normalized_value=3.1,
                    unit="fold_induction",
                    source_citation="Phenix et al. Cancer Res 2016",
                ),
                RawBiologicalObservation(
                    asset_id="tucatinib",
                    parameter_name="animal_tgi_percent",
                    observation_type=BiologyObservationType.ANIMAL_EFFICACY,
                    raw_text_value="86.0% tumor growth inhibition in BT474 xenografts and survival gain in intracranial models",
                    normalized_value=86.0,
                    unit="percent",
                    source_citation="Phenix et al. Cancer Res 2016",
                ),
                RawBiologicalObservation(
                    asset_id="tucatinib",
                    parameter_name="patient_derived_model_count",
                    observation_type=BiologyObservationType.PATIENT_DERIVED_MODELS,
                    raw_text_value="3 distinct model systems tested (CDX, PDX, intracranial models)",
                    normalized_value=3.0,
                    unit="count",
                    source_citation="Phenix et al. Cancer Res 2016",
                ),
                RawBiologicalObservation(
                    asset_id="tucatinib",
                    parameter_name="clinical_response_ORR",
                    observation_type=BiologyObservationType.CLINICAL_RESPONSE,
                    raw_text_value="40.6% confirmed ORR in HER2CLIMB Phase 3 trial (Murthy et al. NEJM 2020)",
                    normalized_value=40.6,
                    unit="percent",
                    source_citation="Murthy et al. NEJM 2020; PMID:31825569",
                    pmid="31825569",
                ),
            ],
            # 3. Poziotinib (HM781-36B)
            "poziotinib": [
                RawBiologicalObservation(
                    asset_id="poziotinib",
                    parameter_name="IC50_biochemical_HER2",
                    observation_type=BiologyObservationType.IC50_BIOCHEMICAL,
                    raw_text_value="1.0 nM potent enzymatic IC50",
                    normalized_value=1.0,
                    unit="nM",
                    source_citation="Robichaux et al. Nature Medicine 2018",
                ),
                RawBiologicalObservation(
                    asset_id="poziotinib",
                    parameter_name="IC50_cellular_HER2_Exon20",
                    observation_type=BiologyObservationType.IC50_CELLULAR,
                    raw_text_value="1.9 nM in Exon 20 mutant cells",
                    normalized_value=1.9,
                    unit="nM",
                    source_citation="Robichaux et al. Nature Medicine 2018",
                ),
                RawBiologicalObservation(
                    asset_id="poziotinib",
                    parameter_name="selectivity_ratio_WT_EGFR",
                    observation_type=BiologyObservationType.SELECTIVITY_RATIO,
                    raw_text_value="1.2-fold selectivity vs wild-type EGFR (WT EGFR IC50 = 2.3 nM; essentially unselective)",
                    normalized_value=1.2,
                    unit="fold",
                    source_citation="Robichaux et al. Nature Medicine 2018",
                ),
                RawBiologicalObservation(
                    asset_id="poziotinib",
                    parameter_name="off_target_kinome_hits_pct",
                    observation_type=BiologyObservationType.OFF_TARGET_RISK,
                    raw_text_value="18.0% off-target kinase hits; narrow therapeutic window with high diarrhea rate",
                    normalized_value=18.0,
                    unit="percent",
                    source_citation="Robichaux et al. Nature Medicine 2018",
                ),
                RawBiologicalObservation(
                    asset_id="poziotinib",
                    parameter_name="target_validity_HER2",
                    observation_type=BiologyObservationType.TARGET_VALIDITY,
                    raw_text_value="HER2 Exon 20 insertion oncogenic driver",
                    normalized_value=1.0,
                    source_citation="Le et al. JCO 2022; PMID:35235434",
                ),
                RawBiologicalObservation(
                    asset_id="poziotinib",
                    parameter_name="mechanistic_rationale_pan_HER",
                    observation_type=BiologyObservationType.MECHANISTIC_RATIONALE,
                    raw_text_value="Irreversible covalent pan-ErbB inhibitor binding steric pocket",
                    normalized_value=1.0,
                    source_citation="Robichaux et al. Nature Medicine 2018",
                ),
                RawBiologicalObservation(
                    asset_id="poziotinib",
                    parameter_name="target_engagement_pHER2",
                    observation_type=BiologyObservationType.ON_TARGET_ENGAGEMENT,
                    raw_text_value="Phospho-HER2 inhibition IC50 = 2.0 nM",
                    normalized_value=2.0,
                    unit="nM",
                    source_citation="Robichaux et al. Nature Medicine 2018",
                ),
                RawBiologicalObservation(
                    asset_id="poziotinib",
                    parameter_name="biomarker_strategy_exon20",
                    observation_type=BiologyObservationType.BIOMARKER_STRATEGY,
                    raw_text_value="Stratified by HER2 exon 20 insertion mutations",
                    normalized_value=1.0,
                    source_citation="ZENITH20 Protocol (NCT03318939)",
                ),
                RawBiologicalObservation(
                    asset_id="poziotinib",
                    parameter_name="crispr_chronos_score",
                    observation_type=BiologyObservationType.CRISPR_DEPENDENCY,
                    raw_text_value="Chronos score = -0.85 in HER2-dependent models",
                    normalized_value=-0.85,
                    source_citation="DepMap 24Q2",
                ),
                RawBiologicalObservation(
                    asset_id="poziotinib",
                    parameter_name="functional_apoptosis_induction",
                    observation_type=BiologyObservationType.FUNCTIONAL_EVIDENCE,
                    raw_text_value="2.5-fold apoptosis induction",
                    normalized_value=2.5,
                    unit="fold_induction",
                    source_citation="Robichaux et al. Nature Medicine 2018",
                ),
                RawBiologicalObservation(
                    asset_id="poziotinib",
                    parameter_name="animal_tgi_percent",
                    observation_type=BiologyObservationType.ANIMAL_EFFICACY,
                    raw_text_value="78.0% tumor growth inhibition in xenografts",
                    normalized_value=78.0,
                    unit="percent",
                    source_citation="Robichaux et al. Nature Medicine 2018",
                ),
                RawBiologicalObservation(
                    asset_id="poziotinib",
                    parameter_name="patient_derived_model_count",
                    observation_type=BiologyObservationType.PATIENT_DERIVED_MODELS,
                    raw_text_value="2 model systems tested (CDX and PDX)",
                    normalized_value=2.0,
                    unit="count",
                    source_citation="Robichaux et al. Nature Medicine 2018",
                ),
                RawBiologicalObservation(
                    asset_id="poziotinib",
                    parameter_name="clinical_response_ORR",
                    observation_type=BiologyObservationType.CLINICAL_RESPONSE,
                    raw_text_value="27.8% ORR in ZENITH20; narrow therapeutic index, FDA Complete Response Letter",
                    normalized_value=27.8,
                    unit="percent",
                    source_citation="Le et al. JCO 2022; PMID:35235434",
                    pmid="35235434",
                ),
            ],
            # 4. Neratinib (HKI-272)
            "neratinib": [
                RawBiologicalObservation(
                    asset_id="neratinib",
                    parameter_name="IC50_biochemical_HER2",
                    observation_type=BiologyObservationType.IC50_BIOCHEMICAL,
                    raw_text_value="3.0 nM enzymatic IC50",
                    normalized_value=3.0,
                    unit="nM",
                    source_citation="Rabindran et al. Cancer Res 2004",
                ),
                RawBiologicalObservation(
                    asset_id="neratinib",
                    parameter_name="IC50_cellular_HER2",
                    observation_type=BiologyObservationType.IC50_CELLULAR,
                    raw_text_value="5.0 nM in HER2+ cell proliferation",
                    normalized_value=5.0,
                    unit="nM",
                    source_citation="Rabindran et al. Cancer Res 2004",
                ),
                RawBiologicalObservation(
                    asset_id="neratinib",
                    parameter_name="selectivity_ratio_WT_EGFR",
                    observation_type=BiologyObservationType.SELECTIVITY_RATIO,
                    raw_text_value="1.8-fold selectivity vs wild-type EGFR (WT EGFR IC50 = 9.0 nM)",
                    normalized_value=1.8,
                    unit="fold",
                    source_citation="Rabindran et al. Cancer Res 2004",
                ),
                RawBiologicalObservation(
                    asset_id="neratinib",
                    parameter_name="off_target_kinome_hits_pct",
                    observation_type=BiologyObservationType.OFF_TARGET_RISK,
                    raw_text_value="15.0% off-target hits in kinome screen; Grade 3+ diarrhea in 40.0% of patients",
                    normalized_value=15.0,
                    unit="percent",
                    source_citation="Rabindran et al. Cancer Res 2004",
                ),
                RawBiologicalObservation(
                    asset_id="neratinib",
                    parameter_name="target_validity_HER2",
                    observation_type=BiologyObservationType.TARGET_VALIDITY,
                    raw_text_value="HER2 amplification validated in early and metastatic breast cancer",
                    normalized_value=1.0,
                    source_citation="Chan et al. Lancet Oncology 2016",
                ),
                RawBiologicalObservation(
                    asset_id="neratinib",
                    parameter_name="mechanistic_rationale_pan_HER",
                    observation_type=BiologyObservationType.MECHANISTIC_RATIONALE,
                    raw_text_value="Irreversible covalent pan-ErbB TKI",
                    normalized_value=1.0,
                    source_citation="Rabindran et al. Cancer Res 2004",
                ),
                RawBiologicalObservation(
                    asset_id="neratinib",
                    parameter_name="target_engagement_pHER2",
                    observation_type=BiologyObservationType.ON_TARGET_ENGAGEMENT,
                    raw_text_value="Phospho-HER2 inhibition IC50 = 5.2 nM",
                    normalized_value=5.2,
                    unit="nM",
                    source_citation="Rabindran et al. Cancer Res 2004",
                ),
                RawBiologicalObservation(
                    asset_id="neratinib",
                    parameter_name="biomarker_strategy_HER2_amp",
                    observation_type=BiologyObservationType.BIOMARKER_STRATEGY,
                    raw_text_value="Extended adjuvant HER2+ breast cancer following trastuzumab",
                    normalized_value=1.0,
                    source_citation="Chan et al. Lancet Oncology 2016",
                ),
                RawBiologicalObservation(
                    asset_id="neratinib",
                    parameter_name="crispr_chronos_score",
                    observation_type=BiologyObservationType.CRISPR_DEPENDENCY,
                    raw_text_value="DepMap Chronos score = -0.80",
                    normalized_value=-0.80,
                    source_citation="DepMap 24Q2",
                ),
                RawBiologicalObservation(
                    asset_id="neratinib",
                    parameter_name="functional_apoptosis_induction",
                    observation_type=BiologyObservationType.FUNCTIONAL_EVIDENCE,
                    raw_text_value="2.2-fold apoptosis induction in HER2+ models",
                    normalized_value=2.2,
                    unit="fold_induction",
                    source_citation="Rabindran et al. Cancer Res 2004",
                ),
                RawBiologicalObservation(
                    asset_id="neratinib",
                    parameter_name="animal_tgi_percent",
                    observation_type=BiologyObservationType.ANIMAL_EFFICACY,
                    raw_text_value="75.0% tumor growth inhibition in xenografts",
                    normalized_value=75.0,
                    unit="percent",
                    source_citation="Rabindran et al. Cancer Res 2004",
                ),
                RawBiologicalObservation(
                    asset_id="neratinib",
                    parameter_name="patient_derived_model_count",
                    observation_type=BiologyObservationType.PATIENT_DERIVED_MODELS,
                    raw_text_value="2 model systems (CDX and cell lines)",
                    normalized_value=2.0,
                    unit="count",
                    source_citation="Rabindran et al. Cancer Res 2004",
                ),
                RawBiologicalObservation(
                    asset_id="neratinib",
                    parameter_name="clinical_response_ORR",
                    observation_type=BiologyObservationType.CLINICAL_RESPONSE,
                    raw_text_value="Adjuvant invasive disease-free survival benefit in ExteNET Phase 3 trial",
                    normalized_value=32.0,
                    unit="percent_efficacy_proxy",
                    source_citation="Chan et al. Lancet Oncology 2016; PMID:26874378",
                    pmid="26874378",
                ),
            ],
            # 5. OX-HER2-01 (Preclinical Academic Spinout)
            "ox-her2-01": [
                RawBiologicalObservation(
                    asset_id="ox-her2-01",
                    parameter_name="IC50_biochemical_HER2",
                    observation_type=BiologyObservationType.IC50_BIOCHEMICAL,
                    raw_text_value="0.6 nM against HER2 kinase domain",
                    normalized_value=0.6,
                    unit="nM",
                    source_citation="Oxford University Innovation Dossier 2024",
                ),
                RawBiologicalObservation(
                    asset_id="ox-her2-01",
                    parameter_name="IC50_cellular_HER2_mutant",
                    observation_type=BiologyObservationType.IC50_CELLULAR,
                    raw_text_value="2.1 nM in Ba/F3 mutant cells",
                    normalized_value=2.1,
                    unit="nM",
                    source_citation="Oxford University Innovation Dossier 2024",
                ),
                RawBiologicalObservation(
                    asset_id="ox-her2-01",
                    parameter_name="selectivity_ratio_WT_EGFR",
                    observation_type=BiologyObservationType.SELECTIVITY_RATIO,
                    raw_text_value="75.0-fold selectivity margin vs wild-type EGFR (WT EGFR IC50 = 157.5 nM)",
                    normalized_value=75.0,
                    unit="fold",
                    source_citation="Oxford University Innovation Dossier 2024",
                ),
                RawBiologicalObservation(
                    asset_id="ox-her2-01",
                    parameter_name="off_target_kinome_hits_pct",
                    observation_type=BiologyObservationType.OFF_TARGET_RISK,
                    raw_text_value="2.0% off-target hits in kinome screen",
                    normalized_value=2.0,
                    unit="percent",
                    source_citation="Oxford University Innovation Dossier 2024",
                ),
                RawBiologicalObservation(
                    asset_id="ox-her2-01",
                    parameter_name="target_validity_HER2",
                    observation_type=BiologyObservationType.TARGET_VALIDITY,
                    raw_text_value="HER2 driver validation in brain metastases",
                    normalized_value=1.0,
                    source_citation="Oxford University Innovation Dossier 2024",
                ),
                RawBiologicalObservation(
                    asset_id="ox-her2-01",
                    parameter_name="mechanistic_rationale_covalent_brain",
                    observation_type=BiologyObservationType.MECHANISTIC_RATIONALE,
                    raw_text_value="Brain-penetrant covalent TKI with low P-gp/BCRP substrate efflux",
                    normalized_value=1.0,
                    source_citation="Oxford University Innovation Dossier 2024",
                ),
                RawBiologicalObservation(
                    asset_id="ox-her2-01",
                    parameter_name="target_engagement_CETSA",
                    observation_type=BiologyObservationType.ON_TARGET_ENGAGEMENT,
                    raw_text_value="CETSA thermal shift Delta Tm = +5.1 C",
                    normalized_value=5.1,
                    unit="deg_C",
                    source_citation="Oxford University Innovation Dossier 2024",
                ),
                RawBiologicalObservation(
                    asset_id="ox-her2-01",
                    parameter_name="biomarker_strategy_intracranial_mutant",
                    observation_type=BiologyObservationType.BIOMARKER_STRATEGY,
                    raw_text_value="Stratified by HER2-mutant brain metastases",
                    normalized_value=1.0,
                    source_citation="Oxford University Innovation Dossier 2024",
                ),
                RawBiologicalObservation(
                    asset_id="ox-her2-01",
                    parameter_name="crispr_chronos_score",
                    observation_type=BiologyObservationType.CRISPR_DEPENDENCY,
                    raw_text_value="Chronos score = -1.10",
                    normalized_value=-1.10,
                    source_citation="DepMap 24Q2",
                ),
                RawBiologicalObservation(
                    asset_id="ox-her2-01",
                    parameter_name="functional_apoptosis_induction",
                    observation_type=BiologyObservationType.FUNCTIONAL_EVIDENCE,
                    raw_text_value="3.8-fold apoptosis induction",
                    normalized_value=3.8,
                    unit="fold_induction",
                    source_citation="Oxford University Innovation Dossier 2024",
                ),
                RawBiologicalObservation(
                    asset_id="ox-her2-01",
                    parameter_name="animal_tgi_percent",
                    observation_type=BiologyObservationType.ANIMAL_EFFICACY,
                    raw_text_value="91.0% tumor growth inhibition in intracranial orthotopic xenografts",
                    normalized_value=91.0,
                    unit="percent",
                    source_citation="Oxford University Innovation Dossier 2024",
                ),
                RawBiologicalObservation(
                    asset_id="ox-her2-01",
                    parameter_name="patient_derived_model_count",
                    observation_type=BiologyObservationType.PATIENT_DERIVED_MODELS,
                    raw_text_value="2 model systems (CDX and orthotopic brain met models; no human PDX yet)",
                    normalized_value=2.0,
                    unit="count",
                    source_citation="Oxford University Innovation Dossier 2024",
                ),
                # Notice: OX-HER2-01 is PRECLINICAL. It has NO clinical trial observations!
                # The engine must NOT invent clinical response or award human points!
            ],
        }
