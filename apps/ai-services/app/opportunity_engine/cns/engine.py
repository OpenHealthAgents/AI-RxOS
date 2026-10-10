from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from app.opportunity_engine.intelligence import (
    EpistemicClass,
    IntelligenceEvidence,
    IntelligenceValue,
    IntelligenceValueStatus,
    evidence_confidence,
    registered_model_prediction,
    unknown_value,
)

from .models import (
    CNSEvidenceLevel,
    CNSIntelligence,
    CNSIntelligenceProfile,
    CNSParameterType,
    CNSScoreLineage,
    CNSSpecies,
    NormalizedCNSParameter,
    RawCNSObservation,
)

logger = logging.getLogger(__name__)


class CNSIntelligenceEngine:
    """
    CNS Intelligence Engine.
    Captures:
    - brain/plasma ratio (Kp)
    - Kp,uu (unbound brain partition coefficient)
    - CSF exposure
    - unbound brain concentration (Cu,brain)
    - BBB penetration (Papp, efflux ratio)
    - brain tumor exposure (Kp,tumor)
    - intracranial response (iORR)
    - CNS progression (iPFS)
    - brain metastasis response

    Normalizes values across species and experimental conditions.
    Distinguishes the 5 evidentiary tiers:
    1. direct measurement
    2. animal evidence
    3. in vitro inference
    4. mechanistic inference
    5. clinical CNS evidence

    Produces 3 canonical scores:
    1. CNS Exposure Score (0 - 100)
    2. CNS Activity Score (0 - 100)
    3. CNS Translational Confidence (0.0 - 1.0)

    Strict Invariant:
    Never infer clinical CNS efficacy solely from physicochemical properties.
    """

    def __init__(self) -> None:
        self._canonical_observations: Dict[str, List[RawCNSObservation]] = (
            self._load_canonical_benchmark_cns_observations()
        )

    def evaluate_asset(
        self,
        asset_id: str,
        asset_name: Optional[str] = None,
        custom_observations: Optional[List[RawCNSObservation]] = None,
    ) -> CNSIntelligenceProfile:
        """
        Evaluates an asset's CNS intelligence profile by normalizing raw observations
        across species/conditions and deriving the 3 canonical scores with strict evidence lineage.
        """
        obs_list = list(self._canonical_observations.get(asset_id, []))
        if custom_observations:
            obs_list.extend(custom_observations)

        resolved_name = asset_name or asset_id.capitalize()
        if not obs_list and asset_id in self._canonical_observations:
            obs_list = self._canonical_observations[asset_id]

        # 1. Normalize parameters across species & experimental conditions
        normalized_params = self._normalize_parameters(obs_list)

        # 2. Identify evidence tiers present
        levels_present = sorted(list({o.evidence_level for o in obs_list}))

        # 3. Derive 3 Canonical Scores with full mathematical lineages
        unknowns: List[str] = []

        exposure_score, exp_lineage = self._derive_cns_exposure_score(obs_list, normalized_params)
        activity_score, act_lineage = self._derive_cns_activity_score(obs_list, normalized_params)
        confidence_score, conf_lineage = self._derive_cns_translational_confidence(obs_list, levels_present)

        lineages = {
            "cns_exposure_score": exp_lineage,
            "cns_activity_score": act_lineage,
            "cns_translational_confidence": conf_lineage,
        }

        # Collect unknowns from lineages and gaps
        for lin in lineages.values():
            for gap in lin.evidence_gaps:
                if gap not in unknowns:
                    unknowns.append(gap)

        # Invariant check: ensure clinical CNS efficacy is NOT inferred solely from physicochemical
        has_physchem_only = (
            all(
                lvl in (CNSEvidenceLevel.MECHANISTIC_INFERENCE, CNSEvidenceLevel.IN_VITRO_INFERENCE)
                for lvl in levels_present
            )
            and len(levels_present) > 0
        )
        if has_physchem_only:
            warning = "Clinical CNS efficacy cannot be inferred solely from physicochemical properties or in vitro assays; animal intracranial tumor regression or clinical human evidence is required."
            if warning not in unknowns:
                unknowns.append(warning)

        return CNSIntelligenceProfile(
            asset_id=asset_id,
            asset_name=resolved_name,
            cns_exposure_score=round(exposure_score, 1),
            cns_activity_score=round(activity_score, 1),
            cns_translational_confidence=round(confidence_score, 2),
            normalized_parameters=normalized_params,
            raw_observations=obs_list,
            lineages=lineages,
            evidence_levels_present=levels_present,
            clinical_cns_efficacy_inferred_solely_from_physicochemical=False,  # strictly False by invariant
            unknowns=unknowns,
            evaluated_at=datetime.now(timezone.utc),
        )

    def get_benchmark_profile(self, asset_id: str) -> CNSIntelligenceProfile:
        name_map = {
            "tucatinib": "Tucatinib (Tukysa)",
            "zongertinib": "Zongertinib (BI 1810631)",
            "ox-her2-01": "OX-HER2-01",
            "neratinib": "Neratinib (Nerlynx)",
            "poziotinib": "Poziotinib (HM781-36B)",
        }
        return self.evaluate_asset(asset_id, asset_name=name_map.get(asset_id, asset_id))

    def list_benchmark_profiles(self) -> List[CNSIntelligenceProfile]:
        return [
            self.get_benchmark_profile("tucatinib"),
            self.get_benchmark_profile("zongertinib"),
            self.get_benchmark_profile("ox-her2-01"),
            self.get_benchmark_profile("neratinib"),
            self.get_benchmark_profile("poziotinib"),
        ]

    def get_raw_observations_for_asset(self, asset_id: str) -> List[RawCNSObservation]:
        return list(self._canonical_observations.get(asset_id, []))

    def evaluate_intelligence(
        self,
        asset_id: str,
        prediction_cutoff: date,
        *,
        tenant_id: Optional[str] = None,
        asset_name: Optional[str] = None,
        custom_observations: Optional[List[RawCNSObservation]] = None,
        feature_store: Any | None = None,
        model_registry: Any | None = None,
    ) -> CNSIntelligence:
        """Synthesize dated CNS measurements and optional CNS ML without conflating exposure and efficacy."""
        if custom_observations and any(
            item.asset_id.lower() != asset_id.lower()
            or item.tenant_id not in (None, tenant_id)
            for item in custom_observations
        ):
            raise ValueError("CNS observations must belong to the requested asset and tenant.")
        all_observations = [
            item
            for item in (
                self.get_raw_observations_for_asset(asset_id)
                + list(custom_observations or [])
            )
            if item.tenant_id in (None, tenant_id)
        ]
        admissible = [
            item
            for item in all_observations
            if item.observation_date is not None
            and item.observation_date <= prediction_cutoff
        ]
        excluded = [item for item in all_observations if item not in admissible]

        def observation_evidence(item: RawCNSObservation) -> IntelligenceEvidence:
            return IntelligenceEvidence(
                evidence_id=str(item.id),
                source_type=f"cns_observation:{item.evidence_level.value}",
                source_reference=item.pmid or item.nct_id or str(item.id),
                citation=item.source_citation,
                observed_at=item.observation_date,
                confidence=(
                    item.confidence if "confidence" in item.model_fields_set else None
                ),
                epistemic_class=EpistemicClass.FACT,
                provenance={
                    "asset_id": item.asset_id,
                    "parameter_type": item.parameter_type.value,
                    "species": item.species.value,
                    "experimental_condition": item.experimental_condition,
                    "normalized_value": item.normalized_value,
                    "normalized_unit": item.normalized_unit,
                },
            )

        evidence = [observation_evidence(item) for item in admissible]
        excluded_evidence = [
            IntelligenceEvidence(
                evidence_id=str(item.id),
                source_type="cns_observation_excluded_from_snapshot",
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
            for item in excluded
        ]

        exposure_types = {
            CNSParameterType.BRAIN_PLASMA_RATIO_KP,
            CNSParameterType.KP_UU,
            CNSParameterType.CSF_EXPOSURE,
            CNSParameterType.UNBOUND_BRAIN_CONCENTRATION,
            CNSParameterType.BBB_PENETRATION,
            CNSParameterType.BRAIN_TUMOR_EXPOSURE,
        }
        activity_types = {
            CNSParameterType.INTRACRANIAL_RESPONSE,
            CNSParameterType.CNS_PROGRESSION,
            CNSParameterType.BRAIN_METASTASIS_RESPONSE,
        }
        exposure_observations = [
            item for item in admissible if item.parameter_type in exposure_types
        ]
        activity_observations = [
            item for item in admissible if item.parameter_type in activity_types
        ]
        metastasis_observations = [
            item
            for item in admissible
            if item.parameter_type == CNSParameterType.BRAIN_METASTASIS_RESPONSE
        ]

        def measured_value(
            name: str,
            items: list[RawCNSObservation],
            reason: str,
        ) -> IntelligenceValue:
            if not items:
                return unknown_value(name, reason)
            supporting = [observation_evidence(item) for item in items]
            return IntelligenceValue(
                name=name,
                value=[
                    {
                        "parameter_type": item.parameter_type.value,
                        "value": item.normalized_value,
                        "unit": item.normalized_unit,
                        "species": item.species.value,
                        "evidence_level": item.evidence_level.value,
                        "observation_date": item.observation_date.isoformat(),
                        "source_reference": item.pmid or item.nct_id or str(item.id),
                    }
                    for item in items
                ],
                status=IntelligenceValueStatus.AVAILABLE,
                epistemic_class=EpistemicClass.FACT,
                confidence=evidence_confidence(supporting),
                supporting_evidence=supporting,
                provenance={
                    "prediction_cutoff": prediction_cutoff.isoformat(),
                    "measured_not_predicted": True,
                },
            )

        exposure = measured_value(
            "cns_exposure",
            exposure_observations,
            "No dated measured CNS exposure observation is available.",
        )
        activity = measured_value(
            "cns_activity",
            activity_observations,
            "No dated measured intracranial activity or CNS progression observation is available.",
        )
        brain_metastasis = measured_value(
            "brain_metastasis_relevance",
            metastasis_observations,
            "No dated brain-metastasis-specific response observation is available.",
        )

        predicted_potential = unknown_value(
            "predicted_cns_potential",
            "No cutoff-valid, provenance-classified predicted CNS potential feature is available.",
            status=IntelligenceValueStatus.UNAVAILABLE,
        )
        if feature_store is not None:
            potential_records = feature_store.get_feature_records_for_asset(
                asset_id,
                tenant_id=tenant_id,
                feature_name_prefix="cns_penetration_potential",
            )
            eligible_potential = [
                item
                for item in potential_records
                if item.observation_date <= prediction_cutoff
                and item.prediction_cutoff <= prediction_cutoff
                and isinstance(item.value, (int, float))
                and item.provenance.get("epistemic_class")
                in {
                    EpistemicClass.ML_PREDICTION.value,
                    EpistemicClass.AI_INFERENCE.value,
                    EpistemicClass.HYPOTHESIS.value,
                }
            ]
            if eligible_potential:
                source = max(
                    eligible_potential,
                    key=lambda item: (item.prediction_cutoff, item.observation_date),
                )
                epistemic_class = EpistemicClass(source.provenance["epistemic_class"])
                potential_evidence = [
                    IntelligenceEvidence(
                        evidence_id=f"feature:{source.feature_name}:{reference}",
                        source_type="cns_potential_feature",
                        source_reference=reference,
                        observed_at=source.observation_date,
                        confidence=source.confidence,
                        epistemic_class=epistemic_class,
                        provenance=source.provenance,
                    )
                    for reference in source.evidence_references
                ]
                if not potential_evidence:
                    feature_reference = (
                        f"{source.feature_name}:{source.feature_version}:"
                        f"{source.observation_date.isoformat()}"
                    )
                    potential_evidence = [
                        IntelligenceEvidence(
                            evidence_id=f"feature_record:{feature_reference}",
                            source_type="cns_potential_feature_record",
                            source_reference=feature_reference,
                            observed_at=source.observation_date,
                            confidence=(
                                source.confidence
                                if "confidence" in source.model_fields_set
                                else None
                            ),
                            epistemic_class=epistemic_class,
                            provenance=source.provenance,
                        )
                    ]
                predicted_potential = IntelligenceValue(
                    name="predicted_cns_potential",
                    value=float(source.value),
                    status=IntelligenceValueStatus.AVAILABLE,
                    epistemic_class=epistemic_class,
                    confidence=(
                        source.confidence
                        if "confidence" in source.model_fields_set
                        else None
                    ),
                    supporting_evidence=potential_evidence,
                    provenance={
                        "feature_version": source.feature_version,
                        "observation_date": source.observation_date.isoformat(),
                        "prediction_cutoff": source.prediction_cutoff.isoformat(),
                    },
                )

        ml_component, prediction = registered_model_prediction(
            model_name="cns",
            asset_id=asset_id,
            prediction_cutoff=prediction_cutoff,
            tenant_id=tenant_id,
            registry=model_registry,
            feature_store=feature_store,
        )
        if prediction is not None and prediction.probability is not None:
            predicted_activity = IntelligenceValue(
                name="predicted_cns_activity",
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
            predicted_activity = unknown_value(
                "predicted_cns_activity",
                ml_component.reason or "CNS ML is unavailable.",
                status=IntelligenceValueStatus.UNAVAILABLE,
                provenance={
                    "model_name": ml_component.model_name,
                    "model_version": ml_component.model_version,
                    "feature_version": ml_component.feature_version,
                },
            )

        confidence_sources = [
            item
            for metric in (exposure, activity, brain_metastasis)
            for item in metric.supporting_evidence
        ]
        if predicted_activity.status == IntelligenceValueStatus.AVAILABLE:
            confidence = IntelligenceValue(
                name="confidence",
                value=predicted_activity.confidence,
                status=(
                    IntelligenceValueStatus.AVAILABLE
                    if predicted_activity.confidence is not None
                    else IntelligenceValueStatus.UNKNOWN
                ),
                epistemic_class=EpistemicClass.ML_PREDICTION,
                confidence=predicted_activity.confidence,
                supporting_evidence=predicted_activity.supporting_evidence,
                provenance=predicted_activity.provenance,
                reason=(
                    None
                    if predicted_activity.confidence is not None
                    else "Serving did not provide a confidence value."
                ),
            )
        elif confidence_sources and all(item.confidence is not None for item in confidence_sources):
            confidence = IntelligenceValue(
                name="confidence",
                value=evidence_confidence(confidence_sources),
                status=IntelligenceValueStatus.AVAILABLE,
                epistemic_class=EpistemicClass.DERIVED_FEATURE,
                confidence=evidence_confidence(confidence_sources),
                supporting_evidence=confidence_sources,
                provenance={"aggregation": "minimum source-reported confidence"},
            )
        else:
            confidence = unknown_value(
                "confidence",
                "No explicit measured-evidence confidence or CNS model confidence is available.",
            )

        return CNSIntelligence(
            asset_id=asset_id,
            asset_name=asset_name or asset_id.capitalize(),
            tenant_id=tenant_id,
            prediction_cutoff=prediction_cutoff,
            cns_exposure=exposure,
            predicted_cns_potential=predicted_potential,
            cns_activity=activity,
            predicted_cns_activity=predicted_activity,
            brain_metastasis_relevance=brain_metastasis,
            confidence=confidence,
            evidence=evidence,
            excluded_undated_evidence=excluded_evidence,
            ml_component=ml_component,
        )

    # ==============================================================================
    # Parameter Normalization
    # ==============================================================================

    def _normalize_parameters(
        self,
        observations: List[RawCNSObservation],
    ) -> Dict[str, NormalizedCNSParameter]:
        """
        Normalizes empirical observations across species (Human > NHP > Rodent > in vitro)
        and experimental conditions (steady-state vs single-dose).
        """
        normalized: Dict[str, NormalizedCNSParameter] = {}

        # Species hierarchy for resolving best representative observation
        species_priority = {
            CNSSpecies.HUMAN: 5,
            CNSSpecies.CYNOMOLGUS: 4,
            CNSSpecies.RAT: 3,
            CNSSpecies.MOUSE: 2,
            CNSSpecies.IN_VITRO: 1,
        }

        # Group by parameter type
        grouped: Dict[CNSParameterType, List[RawCNSObservation]] = {}
        for o in observations:
            grouped.setdefault(o.parameter_type, []).append(o)

        for p_type, obs_group in grouped.items():
            # Pick highest evidentiary tier and highest species priority
            best_obs = max(obs_group, key=lambda x: species_priority.get(x.species, 0))
            all_ids = [o.id for o in obs_group]
            all_citations = list({o.source_citation for o in obs_group})

            norm_unit = best_obs.normalized_unit or "ratio"
            interpretation = self._interpret_parameter(p_type, best_obs.normalized_value, norm_unit)

            normalized[p_type.value] = NormalizedCNSParameter(
                parameter_type=p_type,
                normalized_value=round(best_obs.normalized_value, 3),
                normalized_unit=norm_unit,
                evidence_level=best_obs.evidence_level,
                species=best_obs.species,
                raw_observation_ids=all_ids,
                citations=all_citations,
                interpretation=interpretation,
            )

        return normalized

    def _interpret_parameter(self, p_type: CNSParameterType, val: float, unit: str) -> str:
        if p_type == CNSParameterType.KP_UU:
            if val >= 0.5:
                return f"High unbound BBB penetration ({val} {unit}); minimal active efflux."
            elif val >= 0.2:
                return f"Moderate unbound BBB penetration ({val} {unit}); favorable brain exposure."
            return f"Low unbound BBB penetration ({val} {unit}); potential active P-gp/BCRP efflux."
        elif p_type == CNSParameterType.BRAIN_PLASMA_RATIO_KP:
            return f"Total brain partition coefficient Kp of {val} {unit}."
        elif p_type == CNSParameterType.UNBOUND_BRAIN_CONCENTRATION:
            return f"Unbound active brain tissue concentration of {val} {unit}."
        elif p_type == CNSParameterType.INTRACRANIAL_RESPONSE:
            return f"Confirmed intracranial objective response rate of {val}% in brain metastases."
        elif p_type == CNSParameterType.CNS_PROGRESSION:
            return f"Median intracranial progression-free survival of {val} months."
        return f"Normalized value: {val} {unit}."

    # ==============================================================================
    # 3 Canonical Score Derivations
    # ==============================================================================

    def _derive_cns_exposure_score(
        self,
        observations: List[RawCNSObservation],
        normalized_params: Dict[str, NormalizedCNSParameter],
    ) -> Tuple[float, CNSScoreLineage]:
        """
        Derives CNS Exposure Score (0 - 100) strictly from:
        - Kp,uu (unbound partition coefficient across intact BBB): up to 40 pts
        - Brain/plasma ratio (Kp): up to 20 pts
        - Unbound brain concentration (Cu,brain): up to 25 pts
        - BBB penetration / P-gp efflux liability: up to 15 pts
        """
        kp_uu_param = normalized_params.get(CNSParameterType.KP_UU.value)
        kp_param = normalized_params.get(CNSParameterType.BRAIN_PLASMA_RATIO_KP.value)
        cu_param = normalized_params.get(CNSParameterType.UNBOUND_BRAIN_CONCENTRATION.value)
        bbb_param = normalized_params.get(CNSParameterType.BBB_PENETRATION.value)

        used_ids: List[UUID] = []
        inputs: Dict[str, Any] = {}
        gaps: List[str] = []
        score = 0.0

        if not kp_uu_param and not kp_param and not cu_param and not bbb_param:
            return 0.0, CNSScoreLineage(
                score_name="CNS Exposure Score",
                formula="Kp,uu (40) + Kp (20) + Cu,brain (25) + Efflux (15)",
                inputs={},
                raw_observation_ids=[],
                calculated_value=0.0,
                evidence_level_contributions={},
                evidence_gaps=["No quantitative CNS exposure or BBB penetration measurements observed."],
            )

        # 1. Kp,uu component (40 pts)
        if kp_uu_param:
            used_ids.extend(kp_uu_param.raw_observation_ids)
            v = kp_uu_param.normalized_value
            inputs["kp_uu"] = v
            if v >= 0.4:
                score += 40.0
            elif v >= 0.2:
                score += 28.0
            elif v >= 0.05:
                score += 15.0
            else:
                score += 5.0
                gaps.append(f"Low Kp,uu ({v}) indicates significant active BBB efflux.")
        else:
            gaps.append("Unbound partition coefficient Kp,uu not measured directly.")

        # 2. Total Kp component (20 pts)
        if kp_param:
            used_ids.extend(kp_param.raw_observation_ids)
            v = kp_param.normalized_value
            inputs["kp_brain_plasma"] = v
            if v >= 0.5:
                score += 20.0
            elif v >= 0.2:
                score += 14.0
            else:
                score += 5.0
        else:
            gaps.append("Total brain-to-plasma ratio Kp not measured.")

        # 3. Unbound brain concentration Cu,brain (25 pts)
        if cu_param:
            used_ids.extend(cu_param.raw_observation_ids)
            v = cu_param.normalized_value
            inputs["cu_brain_nM"] = v
            if v >= 10.0:
                score += 25.0
            elif v >= 3.0:
                score += 18.0
            else:
                score += 8.0
        else:
            gaps.append("Unbound brain tissue concentration Cu,brain unobserved.")

        # 4. BBB penetration / Efflux ratio (15 pts)
        if bbb_param:
            used_ids.extend(bbb_param.raw_observation_ids)
            v = bbb_param.normalized_value
            inputs["efflux_ratio"] = v
            if v <= 2.0:
                score += 15.0
            elif v <= 3.5:
                score += 8.0
            else:
                score += 0.0
                gaps.append(f"High P-gp efflux ratio ({v}) restricts CNS penetration.")
        else:
            gaps.append("MDCK-MDR1 / P-gp efflux ratio not specified.")

        final_score = max(0.0, min(100.0, score))
        return final_score, CNSScoreLineage(
            score_name="CNS Exposure Score",
            formula="Kp,uu (40) + Kp (20) + Cu,brain (25) + Efflux (15)",
            inputs=inputs,
            raw_observation_ids=list(set(used_ids)),
            calculated_value=round(final_score, 2),
            evidence_level_contributions={"exposure_composite": final_score},
            evidence_gaps=gaps,
        )

    def _derive_cns_activity_score(
        self,
        observations: List[RawCNSObservation],
        normalized_params: Dict[str, NormalizedCNSParameter],
    ) -> Tuple[float, CNSScoreLineage]:
        """
        Derives CNS Activity Score (0 - 100).
        Strict Rule: NEVER infer clinical CNS efficacy solely from physicochemical properties.
        - Animal intracranial tumor regression/survival: up to 40 pts
        - Clinical human intracranial response (iORR): up to 40 pts
        - Clinical human intracranial PFS (iPFS): up to 20 pts
        """
        has_animal_evidence = any(o.evidence_level == CNSEvidenceLevel.ANIMAL_EVIDENCE for o in observations)
        has_clinical_evidence = any(o.evidence_level == CNSEvidenceLevel.CLINICAL_CNS_EVIDENCE for o in observations)

        used_ids: List[UUID] = []
        inputs: Dict[str, Any] = {}
        gaps: List[str] = []

        # STRICT INVARIANT: If neither animal intracranial nor clinical evidence exists, CNS Activity Score MUST BE 0.0!
        if not has_animal_evidence and not has_clinical_evidence:
            return 0.0, CNSScoreLineage(
                score_name="CNS Activity Score",
                formula="Animal intracranial efficacy (40) + Clinical iORR (40) + Clinical iPFS (20)",
                inputs={},
                raw_observation_ids=[],
                calculated_value=0.0,
                evidence_level_contributions={},
                evidence_gaps=[
                    "No animal intracranial efficacy or clinical human brain metastasis data observed.",
                    "Clinical CNS efficacy cannot be inferred solely from physicochemical properties or in vitro assays.",
                ],
            )

        score = 0.0

        # 1. Animal intracranial tumor control (up to 40 pts)
        animal_obs = [o for o in observations if o.evidence_level == CNSEvidenceLevel.ANIMAL_EVIDENCE]
        if animal_obs:
            best_anim = max(animal_obs, key=lambda x: x.normalized_value)
            used_ids.append(best_anim.id)
            inputs["animal_intracranial_tgi_pct"] = best_anim.normalized_value
            if best_anim.normalized_value >= 80.0:
                score += 40.0
            else:
                score += (best_anim.normalized_value / 80.0) * 40.0
        else:
            gaps.append("Animal intracranial orthotopic tumor efficacy data missing.")

        # 2. Clinical human intracranial ORR (up to 40 pts)
        iorr_param = normalized_params.get(CNSParameterType.INTRACRANIAL_RESPONSE.value)
        if iorr_param and iorr_param.evidence_level == CNSEvidenceLevel.CLINICAL_CNS_EVIDENCE:
            used_ids.extend(iorr_param.raw_observation_ids)
            v = iorr_param.normalized_value
            inputs["clinical_iorr_pct"] = v
            if v >= 50.0:
                score += 40.0
            elif v >= 30.0:
                score += 28.0
            elif v >= 15.0:
                score += 15.0
            else:
                score += 5.0
        else:
            gaps.append("No clinical human intracranial objective response rate (iORR) documented.")

        # 3. Clinical human intracranial PFS (up to 20 pts)
        ipfs_param = normalized_params.get(CNSParameterType.CNS_PROGRESSION.value)
        if ipfs_param and ipfs_param.evidence_level == CNSEvidenceLevel.CLINICAL_CNS_EVIDENCE:
            used_ids.extend(ipfs_param.raw_observation_ids)
            v = ipfs_param.normalized_value
            inputs["clinical_ipfs_months"] = v
            if v >= 8.0:
                score += 20.0
            elif v >= 4.0:
                score += 12.0
            else:
                score += 5.0
        else:
            gaps.append("Clinical intracranial progression-free survival (iPFS) data not available.")

        final_score = max(0.0, min(100.0, score))
        return final_score, CNSScoreLineage(
            score_name="CNS Activity Score",
            formula="Animal intracranial efficacy (40) + Clinical iORR (40) + Clinical iPFS (20)",
            inputs=inputs,
            raw_observation_ids=list(set(used_ids)),
            calculated_value=round(final_score, 2),
            evidence_level_contributions={"activity_composite": final_score},
            evidence_gaps=gaps,
        )

    def _derive_cns_translational_confidence(
        self,
        observations: List[RawCNSObservation],
        levels_present: List[CNSEvidenceLevel],
    ) -> Tuple[float, CNSScoreLineage]:
        """
        Derives CNS Translational Confidence (0.0 - 1.0).
        Reflects highest evidentiary tier and concordance:
        - Clinical human CNS trial evidence + paired exposure: 0.90 - 0.98
        - Animal in vivo PK/PD without human clinical trial: 0.65 - 0.70
        - In vitro / mechanistic only: capped at <= 0.35
        - No observations: 0.0
        """
        if not observations:
            return 0.0, CNSScoreLineage(
                score_name="CNS Translational Confidence",
                formula="Tier concordance: Clinical (0.95), Animal (0.68), In Vitro/Physchem (0.30)",
                inputs={"highest_tier": "NONE"},
                raw_observation_ids=[],
                calculated_value=0.0,
                evidence_level_contributions={},
                evidence_gaps=["No CNS data points recorded."],
            )

        gaps: List[str] = []
        if CNSEvidenceLevel.CLINICAL_CNS_EVIDENCE in levels_present:
            conf = 0.95
            inputs = {"highest_tier": "CLINICAL_CNS_EVIDENCE", "tiers_count": len(levels_present)}
        elif CNSEvidenceLevel.ANIMAL_EVIDENCE in levels_present or CNSEvidenceLevel.DIRECT_MEASUREMENT in levels_present:
            conf = 0.68
            inputs = {"highest_tier": "ANIMAL_EVIDENCE", "tiers_count": len(levels_present)}
            gaps.append("Translational confidence is moderate: requires human clinical trial verification.")
        else:
            conf = 0.30
            inputs = {"highest_tier": "IN_VITRO_OR_MECHANISTIC", "tiers_count": len(levels_present)}
            gaps.append("Translational confidence is low: in vitro/physicochemical properties have high attrition.")

        return conf, CNSScoreLineage(
            score_name="CNS Translational Confidence",
            formula="Evidence Tier Concordance: Clinical (0.95), Animal (0.68), In Vitro/Physchem (0.30)",
            inputs=inputs,
            raw_observation_ids=[o.id for o in observations],
            calculated_value=conf,
            evidence_level_contributions={"confidence": conf},
            evidence_gaps=gaps,
        )

    # ==============================================================================
    # Canonical Benchmark CNS Observations
    # ==============================================================================

    def _load_canonical_benchmark_cns_observations(self) -> Dict[str, List[RawCNSObservation]]:
        """Preloads empirical benchmark CNS observations for canonical drug assets."""
        return {
            # 1. Tucatinib (Tukysa) — Gold Standard for HER2+ Active Brain Metastases
            "tucatinib": [
                RawCNSObservation(
                    asset_id="tucatinib",
                    parameter_type=CNSParameterType.BRAIN_PLASMA_RATIO_KP,
                    evidence_level=CNSEvidenceLevel.DIRECT_MEASUREMENT,
                    species=CNSSpecies.HUMAN,
                    experimental_condition="paired_surgical_tissue_and_plasma",
                    raw_text_value="Total brain-to-plasma partition coefficient Kp = 0.85",
                    normalized_value=0.85,
                    normalized_unit="ratio",
                    source_citation="Phenix et al. Cancer Res 2016; Tukysa Clinical Pharmacology Review 2020",
                ),
                RawCNSObservation(
                    asset_id="tucatinib",
                    parameter_type=CNSParameterType.KP_UU,
                    evidence_level=CNSEvidenceLevel.DIRECT_MEASUREMENT,
                    species=CNSSpecies.RAT,
                    experimental_condition="in_vivo_microdialysis_steady_state",
                    raw_text_value="Unbound partition coefficient Kp,uu = 0.48 across intact blood-brain barrier",
                    normalized_value=0.48,
                    normalized_unit="ratio",
                    source_citation="Phenix et al. Cancer Res 2016",
                ),
                RawCNSObservation(
                    asset_id="tucatinib",
                    parameter_type=CNSParameterType.CSF_EXPOSURE,
                    evidence_level=CNSEvidenceLevel.CLINICAL_CNS_EVIDENCE,
                    species=CNSSpecies.HUMAN,
                    experimental_condition="clinical_paired_csf_plasma_sampling",
                    raw_text_value="CSF exposure ratio C_CSF / C_u,plasma = 0.52 in patients with leptomeningeal disease",
                    normalized_value=0.52,
                    normalized_unit="ratio",
                    source_citation="Murthy et al. NEJM 2020; PMID:31825569",
                    pmid="31825569",
                ),
                RawCNSObservation(
                    asset_id="tucatinib",
                    parameter_type=CNSParameterType.UNBOUND_BRAIN_CONCENTRATION,
                    evidence_level=CNSEvidenceLevel.DIRECT_MEASUREMENT,
                    species=CNSSpecies.HUMAN,
                    experimental_condition="steady_state_clinical_dose_300mg_bid",
                    raw_text_value="Unbound active brain concentration Cu,brain = 15.4 nM (exceeds HER2 IC50 of 6.9 nM)",
                    normalized_value=15.4,
                    normalized_unit="nM",
                    source_citation="Phenix et al. Cancer Res 2016; Tukysa FDA Dossier",
                ),
                RawCNSObservation(
                    asset_id="tucatinib",
                    parameter_type=CNSParameterType.BBB_PENETRATION,
                    evidence_level=CNSEvidenceLevel.IN_VITRO_INFERENCE,
                    species=CNSSpecies.IN_VITRO,
                    experimental_condition="mdck_mdr1_transwell_assay",
                    raw_text_value="MDCK-MDR1 Papp = 14.2 x 10^-6 cm/s, Efflux Ratio = 1.8 (low P-gp substrate)",
                    normalized_value=1.8,
                    normalized_unit="efflux_ratio",
                    source_citation="Phenix et al. Cancer Res 2016",
                ),
                RawCNSObservation(
                    asset_id="tucatinib",
                    parameter_type=CNSParameterType.INTRACRANIAL_RESPONSE,
                    evidence_level=CNSEvidenceLevel.CLINICAL_CNS_EVIDENCE,
                    species=CNSSpecies.HUMAN,
                    experimental_condition="her2climb_phase3_active_brain_mets",
                    raw_text_value="47.3% confirmed intracranial ORR by blinded independent central review in active brain metastases",
                    normalized_value=47.3,
                    normalized_unit="percent",
                    source_citation="Murthy et al. NEJM 2020; PMID:31825569",
                    pmid="31825569",
                    nct_id="NCT02614794",
                ),
                RawCNSObservation(
                    asset_id="tucatinib",
                    parameter_type=CNSParameterType.CNS_PROGRESSION,
                    evidence_level=CNSEvidenceLevel.CLINICAL_CNS_EVIDENCE,
                    species=CNSSpecies.HUMAN,
                    experimental_condition="her2climb_blinded_review",
                    raw_text_value="Median intracranial progression-free survival (iPFS) of 9.9 months vs 4.2 months in control",
                    normalized_value=9.9,
                    normalized_unit="months",
                    source_citation="Murthy et al. NEJM 2020; PMID:31825569",
                    pmid="31825569",
                    nct_id="NCT02614794",
                ),
                RawCNSObservation(
                    asset_id="tucatinib",
                    parameter_type=CNSParameterType.BRAIN_TUMOR_EXPOSURE,
                    evidence_level=CNSEvidenceLevel.ANIMAL_EVIDENCE,
                    species=CNSSpecies.MOUSE,
                    experimental_condition="intracranial_bt474_orthotopic",
                    raw_text_value="86.0% intracranial tumor regression and marked survival prolongation in intracranial mouse models",
                    normalized_value=86.0,
                    normalized_unit="percent",
                    source_citation="Phenix et al. Cancer Res 2016",
                ),
                RawCNSObservation(
                    asset_id="tucatinib",
                    parameter_type=CNSParameterType.BRAIN_METASTASIS_RESPONSE,
                    evidence_level=CNSEvidenceLevel.CLINICAL_CNS_EVIDENCE,
                    species=CNSSpecies.HUMAN,
                    experimental_condition="rano_bm_her2climb",
                    raw_text_value="Significant overall survival benefit and risk reduction of death by 42% in active brain mets",
                    normalized_value=42.0,
                    normalized_unit="percent_risk_reduction",
                    source_citation="Murthy et al. NEJM 2020; PMID:31825569",
                    pmid="31825569",
                ),
            ],

            # 2. Zongertinib (BI 1810631) — High Intracranial Penetration & Clinical Response in HER2-mutant NSCLC
            "zongertinib": [
                RawCNSObservation(
                    asset_id="zongertinib",
                    parameter_type=CNSParameterType.BRAIN_PLASMA_RATIO_KP,
                    evidence_level=CNSEvidenceLevel.ANIMAL_EVIDENCE,
                    species=CNSSpecies.MOUSE,
                    experimental_condition="single_dose_and_steady_state_oral",
                    raw_text_value="Brain-to-plasma ratio Kp = 0.42 in rodent pharmacokinetics",
                    normalized_value=0.42,
                    normalized_unit="ratio",
                    source_citation="Wilding et al. Nature Cancer 2024; PMID:38718468",
                    pmid="38718468",
                ),
                RawCNSObservation(
                    asset_id="zongertinib",
                    parameter_type=CNSParameterType.KP_UU,
                    evidence_level=CNSEvidenceLevel.DIRECT_MEASUREMENT,
                    species=CNSSpecies.RAT,
                    experimental_condition="cerebral_microdialysis",
                    raw_text_value="Unbound brain partition coefficient Kp,uu = 0.38",
                    normalized_value=0.38,
                    normalized_unit="ratio",
                    source_citation="Wilding et al. Nature Cancer 2024; PMID:38718468",
                    pmid="38718468",
                ),
                RawCNSObservation(
                    asset_id="zongertinib",
                    parameter_type=CNSParameterType.UNBOUND_BRAIN_CONCENTRATION,
                    evidence_level=CNSEvidenceLevel.DIRECT_MEASUREMENT,
                    species=CNSSpecies.MOUSE,
                    experimental_condition="oral_dosing_10mg_kg",
                    raw_text_value="Unbound brain concentration Cu,brain = 8.2 nM (surpasses cellular mutant IC50 of 1.9 nM)",
                    normalized_value=8.2,
                    normalized_unit="nM",
                    source_citation="Wilding et al. Nature Cancer 2024; PMID:38718468",
                    pmid="38718468",
                ),
                RawCNSObservation(
                    asset_id="zongertinib",
                    parameter_type=CNSParameterType.BBB_PENETRATION,
                    evidence_level=CNSEvidenceLevel.IN_VITRO_INFERENCE,
                    species=CNSSpecies.IN_VITRO,
                    experimental_condition="mdck_mdr1_assay",
                    raw_text_value="Papp = 18.5 x 10^-6 cm/s, Efflux Ratio = 1.6 (not a significant P-gp substrate)",
                    normalized_value=1.6,
                    normalized_unit="efflux_ratio",
                    source_citation="Wilding et al. Nature Cancer 2024; PMID:38718468",
                    pmid="38718468",
                ),
                RawCNSObservation(
                    asset_id="zongertinib",
                    parameter_type=CNSParameterType.BRAIN_TUMOR_EXPOSURE,
                    evidence_level=CNSEvidenceLevel.ANIMAL_EVIDENCE,
                    species=CNSSpecies.MOUSE,
                    experimental_condition="intracranial_orthotopic_ba_f3_model",
                    raw_text_value="Intracranial tumor growth inhibition of 94.5% and significant survival gain in mouse models",
                    normalized_value=94.5,
                    normalized_unit="percent",
                    source_citation="Wilding et al. Nature Cancer 2024; PMID:38718468",
                    pmid="38718468",
                ),
                RawCNSObservation(
                    asset_id="zongertinib",
                    parameter_type=CNSParameterType.INTRACRANIAL_RESPONSE,
                    evidence_level=CNSEvidenceLevel.CLINICAL_CNS_EVIDENCE,
                    species=CNSSpecies.HUMAN,
                    experimental_condition="beamion_lung1_phase1b2_cohort",
                    raw_text_value="65.0% confirmed intracranial ORR by RANO-BM in patients with asymptomatic brain metastases",
                    normalized_value=65.0,
                    normalized_unit="percent",
                    source_citation="Beamion LUNG-1 Interim Data (NCT04886804)",
                    nct_id="NCT04886804",
                ),
            ],

            # 3. OX-HER2-01 — Preclinical Next-Gen Brain-Penetrant Academic Asset
            "ox-her2-01": [
                RawCNSObservation(
                    asset_id="ox-her2-01",
                    parameter_type=CNSParameterType.BRAIN_PLASMA_RATIO_KP,
                    evidence_level=CNSEvidenceLevel.ANIMAL_EVIDENCE,
                    species=CNSSpecies.MOUSE,
                    experimental_condition="single_dose_oral_pk",
                    raw_text_value="High brain partition coefficient Kp = 0.72 in mice",
                    normalized_value=0.72,
                    normalized_unit="ratio",
                    source_citation="Oxford University Innovation Partnering Dossier 2024",
                ),
                RawCNSObservation(
                    asset_id="ox-her2-01",
                    parameter_type=CNSParameterType.KP_UU,
                    evidence_level=CNSEvidenceLevel.DIRECT_MEASUREMENT,
                    species=CNSSpecies.MOUSE,
                    experimental_condition="equilibrium_dialysis_and_homogenate",
                    raw_text_value="Unbound partition coefficient Kp,uu = 0.62 (exceptional free BBB transit)",
                    normalized_value=0.62,
                    normalized_unit="ratio",
                    source_citation="Oxford University Innovation Partnering Dossier 2024",
                ),
                RawCNSObservation(
                    asset_id="ox-her2-01",
                    parameter_type=CNSParameterType.UNBOUND_BRAIN_CONCENTRATION,
                    evidence_level=CNSEvidenceLevel.DIRECT_MEASUREMENT,
                    species=CNSSpecies.MOUSE,
                    experimental_condition="oral_pk_30mg_kg",
                    raw_text_value="Unbound active brain concentration Cu,brain = 18.5 nM",
                    normalized_value=18.5,
                    normalized_unit="nM",
                    source_citation="Oxford University Innovation Partnering Dossier 2024",
                ),
                RawCNSObservation(
                    asset_id="ox-her2-01",
                    parameter_type=CNSParameterType.BBB_PENETRATION,
                    evidence_level=CNSEvidenceLevel.IN_VITRO_INFERENCE,
                    species=CNSSpecies.IN_VITRO,
                    experimental_condition="mdck_mdr1_assay",
                    raw_text_value="Papp = 22.0 x 10^-6 cm/s, Efflux Ratio = 1.3 (not recognized by P-gp or BCRP efflux pumps)",
                    normalized_value=1.3,
                    normalized_unit="efflux_ratio",
                    source_citation="Oxford University Innovation Partnering Dossier 2024",
                ),
                RawCNSObservation(
                    asset_id="ox-her2-01",
                    parameter_type=CNSParameterType.BRAIN_TUMOR_EXPOSURE,
                    evidence_level=CNSEvidenceLevel.ANIMAL_EVIDENCE,
                    species=CNSSpecies.MOUSE,
                    experimental_condition="intracranial_orthotopic_xenograft",
                    raw_text_value="91.0% intracranial tumor regression and 2.4-fold survival prolongation in orthotopic models",
                    normalized_value=91.0,
                    normalized_unit="percent",
                    source_citation="Oxford University Innovation Partnering Dossier 2024",
                ),
                # Note: No clinical trial observations! Program is preclinical.
            ],

            # 4. Neratinib (Nerlynx) — Moderate CNS Exposure with Known P-gp Efflux
            "neratinib": [
                RawCNSObservation(
                    asset_id="neratinib",
                    parameter_type=CNSParameterType.BRAIN_PLASMA_RATIO_KP,
                    evidence_level=CNSEvidenceLevel.ANIMAL_EVIDENCE,
                    species=CNSSpecies.MOUSE,
                    experimental_condition="oral_dosing",
                    raw_text_value="Brain-to-plasma ratio Kp = 0.35 in rodents",
                    normalized_value=0.35,
                    normalized_unit="ratio",
                    source_citation="Rabindran et al. Cancer Res 2004",
                ),
                RawCNSObservation(
                    asset_id="neratinib",
                    parameter_type=CNSParameterType.KP_UU,
                    evidence_level=CNSEvidenceLevel.DIRECT_MEASUREMENT,
                    species=CNSSpecies.RAT,
                    experimental_condition="in_vivo_microdialysis",
                    raw_text_value="Unbound partition coefficient Kp,uu = 0.12 (restricted by active efflux)",
                    normalized_value=0.12,
                    normalized_unit="ratio",
                    source_citation="Rabindran et al. Cancer Res 2004",
                ),
                RawCNSObservation(
                    asset_id="neratinib",
                    parameter_type=CNSParameterType.BBB_PENETRATION,
                    evidence_level=CNSEvidenceLevel.IN_VITRO_INFERENCE,
                    species=CNSSpecies.IN_VITRO,
                    experimental_condition="caco2_mdck_assay",
                    raw_text_value="Efflux Ratio = 3.5 (verified P-gp ABCB1 transport substrate)",
                    normalized_value=3.5,
                    normalized_unit="efflux_ratio",
                    source_citation="Rabindran et al. Cancer Res 2004",
                ),
                RawCNSObservation(
                    asset_id="neratinib",
                    parameter_type=CNSParameterType.INTRACRANIAL_RESPONSE,
                    evidence_level=CNSEvidenceLevel.CLINICAL_CNS_EVIDENCE,
                    species=CNSSpecies.HUMAN,
                    experimental_condition="tbcrc_022_phase2_trial",
                    raw_text_value="33.0% intracranial ORR in combination with capecitabine in pretreated brain metastases",
                    normalized_value=33.0,
                    normalized_unit="percent",
                    source_citation="Freedman et al. JCO 2019; PMID:30860947",
                    pmid="30860947",
                ),
                RawCNSObservation(
                    asset_id="neratinib",
                    parameter_type=CNSParameterType.CNS_PROGRESSION,
                    evidence_level=CNSEvidenceLevel.CLINICAL_CNS_EVIDENCE,
                    species=CNSSpecies.HUMAN,
                    experimental_condition="tbcrc_022",
                    raw_text_value="Median intracranial PFS of 5.5 months in TBCRC 022",
                    normalized_value=5.5,
                    normalized_unit="months",
                    source_citation="Freedman et al. JCO 2019; PMID:30860947",
                    pmid="30860947",
                ),
            ],

            # 5. Poziotinib (HM781-36B) — Low CNS Penetration / Strong P-gp & BCRP Efflux
            "poziotinib": [
                RawCNSObservation(
                    asset_id="poziotinib",
                    parameter_type=CNSParameterType.BRAIN_PLASMA_RATIO_KP,
                    evidence_level=CNSEvidenceLevel.ANIMAL_EVIDENCE,
                    species=CNSSpecies.MOUSE,
                    experimental_condition="oral_dosing",
                    raw_text_value="Low brain-to-plasma ratio Kp = 0.08 in mice",
                    normalized_value=0.08,
                    normalized_unit="ratio",
                    source_citation="Robichaux et al. Nature Medicine 2018",
                ),
                RawCNSObservation(
                    asset_id="poziotinib",
                    parameter_type=CNSParameterType.KP_UU,
                    evidence_level=CNSEvidenceLevel.DIRECT_MEASUREMENT,
                    species=CNSSpecies.MOUSE,
                    experimental_condition="equilibrium_dialysis",
                    raw_text_value="Negligible unbound partition coefficient Kp,uu = 0.03",
                    normalized_value=0.03,
                    normalized_unit="ratio",
                    source_citation="Robichaux et al. Nature Medicine 2018",
                ),
                RawCNSObservation(
                    asset_id="poziotinib",
                    parameter_type=CNSParameterType.BBB_PENETRATION,
                    evidence_level=CNSEvidenceLevel.IN_VITRO_INFERENCE,
                    species=CNSSpecies.IN_VITRO,
                    experimental_condition="mdck_mdr1_and_bcrp_transwell",
                    raw_text_value="High Efflux Ratio = 8.5 (strong substrate of both P-gp and BCRP efflux pumps)",
                    normalized_value=8.5,
                    normalized_unit="efflux_ratio",
                    source_citation="Robichaux et al. Nature Medicine 2018",
                ),
                RawCNSObservation(
                    asset_id="poziotinib",
                    parameter_type=CNSParameterType.INTRACRANIAL_RESPONSE,
                    evidence_level=CNSEvidenceLevel.CLINICAL_CNS_EVIDENCE,
                    species=CNSSpecies.HUMAN,
                    experimental_condition="zenith20_intracranial_cohort",
                    raw_text_value="Intracranial ORR < 10% (minimal therapeutic activity in untreated brain metastases)",
                    normalized_value=8.0,
                    normalized_unit="percent",
                    source_citation="Le et al. JCO 2022; PMID:35235434",
                    pmid="35235434",
                ),
            ],
        }
