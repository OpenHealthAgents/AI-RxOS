"""
Label Generator and Dataset Builder.

This module implements the existing ML labeling and historical snapshot dataset
logic while preserving the repository's temporal and provenance constraints.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Dict, List, Optional

from app.opportunity_engine.data.fixtures import list_fixture_assets
from app.opportunity_engine.domain.schemas import AssetIntelligence

from .features import FeatureStore
from .models import DatasetRecord, FeatureRecord, MLDataset, TargetLabel


class LabelGenerator:
    """Generates Prompt 30-style labels with provenance and cutoff metadata."""

    DEFAULT_TARGET_NAME = "opportunity_pursuit_success"
    DEFAULT_PREDICTION_CUTOFF = date(2024, 1, 1)
    SAFETY_TARGETS = (
        "grade_ge_3_ae",
        "dlt",
        "discontinuation",
        "organ_toxicity",
        "therapeutic_index_risk",
    )
    RESISTANCE_TARGETS = (
        "target_mutation",
        "target_amplification",
        "bypass_signaling",
        "downstream_activation",
        "pathway_adaptation",
        "phenotypic_escape",
        "tumor_microenvironment",
        "metabolic_adaptation",
    )
    OPPORTUNITY_SUCCESS_TARGET = "opportunity_success"
    REQUIRED_LABELS = [
        "IND_achieved",
        "phase_I_success",
        "phase_II_success",
        "phase_III_success",
        "regulatory_approval",
        "termination",
        "efficacy_failure",
        "toxicity_failure",
        "strategic_failure",
    ]

    @classmethod
    def _build_label_record(
        cls,
        asset: AssetIntelligence,
        target_name: str,
        prediction_cutoff: date,
        tenant_id: Optional[str],
        outcome_value: Optional[float],
        label_version: str = "v1",
        derivation_method: str = "prompt_30_label_derivation",
        confidence: float = 0.9,
    ) -> TargetLabel:
        base = {
            "entity_id": asset.id,
            "asset_id": asset.id,
            "asset": asset.id,
            "tenant_id": tenant_id,
            "observation_date": prediction_cutoff,
            "prediction_cutoff": prediction_cutoff,
            "label_version": label_version,
            "derivation_method": derivation_method,
            "confidence": confidence,
            "provenance": {
                "asset_name": asset.name,
                "source_count": len(asset.supporting_evidence),
                "feature_family": "prompt_30",
                "evidence_basis": "canonical_asset_profile",
                "prediction_cutoff": prediction_cutoff.isoformat(),
                "target_name": target_name,
            },
            "evidence_references": [ev.id for ev in asset.supporting_evidence],
        }
        return TargetLabel(
            target_name=target_name,
            outcome_value=outcome_value,
            observation_horizon_date=prediction_cutoff,
            is_known_at_cutoff=outcome_value is not None,
            outcome_evidence_id=f"ev-label-{asset.id}-{target_name}",
            **base,
        )

    @classmethod
    def generate_labels(
        cls,
        assets: List[AssetIntelligence],
        prediction_cutoff: Optional[date] = None,
        tenant_id: Optional[str] = None,
        include_all_required_labels: bool = False,
        label_names: Optional[List[str]] = None,
    ) -> Dict[str, TargetLabel]:
        """Generate labels for an asset set.

        Legacy/default behavior returns one binary target per asset for compatibility
        with the existing ML subsystem tests. When Prompt-30-specific coverage is
        requested, the full catalog of required labels is generated and unknown
        outcomes remain None rather than being coerced to 0 or 1.
        """
        cutoff = prediction_cutoff or cls.DEFAULT_PREDICTION_CUTOFF
        labels: Dict[str, TargetLabel] = {}

        requested_names = list(label_names or [])
        if include_all_required_labels:
            requested_names = requested_names or list(cls.REQUIRED_LABELS)
        elif not requested_names:
            requested_names = [cls.DEFAULT_TARGET_NAME]

        for asset in assets:
            for label_name in requested_names:
                if label_name == cls.DEFAULT_TARGET_NAME:
                    stage_value = getattr(asset.stage, "value", "")
                    outcome_value = 1.0 if "Approved" in stage_value or "Phase III" in stage_value or "Phase II" in stage_value else 0.0
                    label = cls._build_label_record(
                        asset,
                        label_name,
                        cutoff,
                        tenant_id,
                        outcome_value=outcome_value,
                    )
                else:
                    label = cls._build_label_record(
                        asset,
                        label_name,
                        cutoff,
                        tenant_id,
                        outcome_value=None,
                        derivation_method="prompt_30_label_derivation",
                        confidence=0.0,
                    )
                labels[f"{asset.id.lower()}:{label_name}"] = label

        return labels

    @classmethod
    def generate_translational_labels(
        cls,
        assets: List[AssetIntelligence],
        prediction_cutoff: Optional[date] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, TargetLabel]:
        """Preserve translational outcomes as unknown unless observed labels are supplied."""
        cutoff = prediction_cutoff or cls.DEFAULT_PREDICTION_CUTOFF
        labels: Dict[str, TargetLabel] = {}
        for asset in assets:
            label = cls._build_label_record(
                asset,
                "translational_potential",
                cutoff,
                tenant_id,
                outcome_value=None,
                derivation_method="unknown_without_observed_translational_outcome",
                confidence=0.0,
            )
            label.provenance["label_status"] = "unknown_without_observed_translational_outcome"
            label.outcome_evidence_id = None
            label.evidence_references = []
            labels[f"{asset.id.lower()}:translational_potential"] = label
        return labels

    @classmethod
    def generate_clinical_success_labels(
        cls,
        assets: List[AssetIntelligence],
        prediction_cutoff: Optional[date] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, TargetLabel]:
        """Preserve unknown clinical outcomes; stage is not a proxy for trial success."""
        cutoff = prediction_cutoff or cls.DEFAULT_PREDICTION_CUTOFF
        labels: Dict[str, TargetLabel] = {}
        for asset in assets:
            outcomes: Dict[str, Optional[float]] = {
                "phase_II_success": None,
                "phase_III_success": None,
                "regulatory_success": None,
                "failure_probability": None,
            }

            for label_name, outcome_value in outcomes.items():
                label = cls._build_label_record(
                    asset,
                    label_name,
                    cutoff,
                    tenant_id,
                    outcome_value=outcome_value,
                    derivation_method="unknown_without_observed_clinical_outcome",
                    confidence=0.0,
                )
                label.provenance["label_status"] = "unknown_without_observed_clinical_outcome"
                label.outcome_evidence_id = None
                label.evidence_references = []
                labels[f"{asset.id.lower()}:{label_name}"] = label
        return labels

    @staticmethod
    def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def generate_patient_response_labels_unknown(
        cls,
        assets: List[AssetIntelligence],
        prediction_cutoff: Optional[date] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, TargetLabel]:
        """Explicitly preserve missing patient-level outcomes as unknown."""
        cutoff = prediction_cutoff or cls.DEFAULT_PREDICTION_CUTOFF
        labels: Dict[str, TargetLabel] = {}
        for asset in assets:
            label = cls._build_label_record(
                asset,
                "patient_response",
                cutoff,
                tenant_id,
                outcome_value=None,
                derivation_method="unavailable_patient_level_outcome",
                confidence=0.0,
            )
            label.provenance["label_status"] = "unknown_no_patient_level_response_outcome"
            labels[f"{asset.id.lower()}:patient_response"] = label
        return labels

    @classmethod
    def generate_patient_response_labels(
        cls,
        assets: List[AssetIntelligence],
        prediction_cutoff: Optional[date] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, TargetLabel]:
        """Explicitly preserve patient-response labels as unknown when no real outcome exists.

        This is the production-safe default. Synthetic or deterministic outcomes are only
        permitted in the dedicated test-only fixture path, not in the general asset label
        generator used by historical dataset construction.
        """
        return cls.generate_patient_response_labels_unknown(
            assets,
            prediction_cutoff=prediction_cutoff,
            tenant_id=tenant_id,
        )

    @classmethod
    def generate_patient_response_test_labels(
        cls,
        prediction_cutoff: date,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, TargetLabel]:
        """Return fixed binary outcomes explicitly scoped to the Prompt 39 test fixture."""
        outcomes = [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 1.0, 1.0]
        labels: Dict[str, TargetLabel] = {}
        for index, outcome in enumerate(outcomes):
            entity_id = f"patient_response_test_{index + 1:02d}"
            labels[entity_id.lower()] = TargetLabel(
                entity_id=entity_id,
                asset_id=entity_id,
                asset=entity_id,
                tenant_id=tenant_id,
                target_name="patient_response",
                outcome_value=outcome,
                observation_horizon_date=prediction_cutoff,
                observation_date=prediction_cutoff,
                prediction_cutoff=prediction_cutoff,
                is_known_at_cutoff=True,
                outcome_evidence_id=f"test-only:{entity_id}:response-label",
                evidence_references=[f"test-only:{entity_id}:response-label"],
                label_version="test-v1",
                derivation_method="prompt_39_deterministic_test_fixture",
                confidence=1.0,
                provenance={
                    "test_only": True,
                    "scientific_evidence": False,
                    "prediction_cutoff": prediction_cutoff.isoformat(),
                },
            )
        return labels

    @classmethod
    def generate_safety_labels(
        cls,
        assets: List[AssetIntelligence],
        prediction_cutoff: Optional[date] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, TargetLabel]:
        """Retain unknown safety outcomes when no observed outcome source is available."""
        cutoff = prediction_cutoff or cls.DEFAULT_PREDICTION_CUTOFF
        labels: Dict[str, TargetLabel] = {}
        for asset in assets:
            label = cls._build_label_record(
                asset,
                "safety",
                cutoff,
                tenant_id,
                outcome_value=None,
                derivation_method="unavailable_observed_safety_outcome",
                confidence=0.0,
            )
            label.provenance["label_status"] = "unknown_no_observed_safety_outcome"
            label.outcome_evidence_id = None
            label.evidence_references = []
            labels[f"{asset.id.lower()}:safety"] = label
        return labels

    @classmethod
    def generate_safety_outcome_labels(
        cls,
        assets: List[AssetIntelligence],
        prediction_cutoff: Optional[date] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, TargetLabel]:
        """Create unknown endpoint labels for unsupported/unobserved clinical outcomes."""
        cutoff = prediction_cutoff or cls.DEFAULT_PREDICTION_CUTOFF
        labels: Dict[str, TargetLabel] = {}
        for asset in assets:
            for target_name in cls.SAFETY_TARGETS:
                label = cls._build_label_record(
                    asset,
                    target_name,
                    cutoff,
                    tenant_id,
                    outcome_value=None,
                    derivation_method="unavailable_observed_safety_outcome",
                    confidence=0.0,
                )
                label.provenance["label_status"] = "unknown_no_observed_safety_outcome"
                label.outcome_evidence_id = None
                label.evidence_references = []
                labels[f"{asset.id.lower()}:{target_name}"] = label
        return labels

    @classmethod
    def generate_safety_test_labels(
        cls,
        prediction_cutoff: date,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Dict[str, TargetLabel]]:
        """Return fixed endpoint labels explicitly scoped to the Prompt 40 test fixture."""
        outcomes = {
            "grade_ge_3_ae": [0, 1] * 8,
            "dlt": [0, 0, 1, 1] * 4,
            "discontinuation": [0, 1, 1, 0] * 4,
            "organ_toxicity": [0, 0, 1, 0, 1, 1, 0, 1] * 2,
            "therapeutic_index_risk": [0, 1, 0, 0, 1, 1, 1, 0] * 2,
        }
        labels: Dict[str, Dict[str, TargetLabel]] = {}
        for index in range(16):
            entity_id = f"safety_test_{index + 1:02d}"
            labels[entity_id.lower()] = {}
            for target_name in cls.SAFETY_TARGETS:
                outcome = float(outcomes[target_name][index])
                labels[entity_id.lower()][target_name] = TargetLabel(
                    entity_id=entity_id,
                    asset_id=entity_id,
                    asset=entity_id,
                    tenant_id=tenant_id,
                    target_name=target_name,
                    outcome_value=outcome,
                    observation_horizon_date=prediction_cutoff,
                    observation_date=prediction_cutoff,
                    prediction_cutoff=prediction_cutoff,
                    is_known_at_cutoff=True,
                    outcome_evidence_id=f"test-only:{entity_id}:{target_name}",
                    evidence_references=[f"test-only:{entity_id}:{target_name}"],
                    label_version="test-v1",
                    derivation_method="prompt_40_deterministic_test_fixture",
                    confidence=1.0,
                    provenance={
                        "test_only": True,
                        "scientific_evidence": False,
                        "prediction_cutoff": prediction_cutoff.isoformat(),
                    },
                )
        return labels

    @classmethod
    def generate_cns_labels(
        cls,
        assets: List[AssetIntelligence],
        prediction_cutoff: Optional[date] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, TargetLabel]:
        """Keep CNS efficacy unknown unless an explicitly observed outcome is available."""
        cutoff = prediction_cutoff or cls.DEFAULT_PREDICTION_CUTOFF
        return {
            f"{asset.id.lower()}:cns_clinical_efficacy": TargetLabel(
                entity_id=asset.id,
                asset_id=asset.id,
                asset=asset.id,
                tenant_id=tenant_id,
                target_name="cns_clinical_efficacy",
                outcome_value=None,
                observation_horizon_date=None,
                observation_date=None,
                prediction_cutoff=cutoff,
                is_known_at_cutoff=False,
                outcome_evidence_id=None,
                evidence_references=[],
                label_version="v1",
                derivation_method="unavailable_without_dated_observed_cns_outcome",
                confidence=0.0,
                provenance={
                    "label_status": "unknown_without_dated_observed_cns_outcome",
                    "prediction_cutoff": cutoff.isoformat(),
                    "tenant_id": tenant_id,
                },
            )
            for asset in assets
        }

    @classmethod
    def generate_resistance_labels(
        cls,
        assets: List[AssetIntelligence],
        prediction_cutoff: Optional[date] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Dict[str, TargetLabel]]:
        """Keep resistance outcomes unknown unless explicitly observed, dated labels exist."""
        cutoff = prediction_cutoff or cls.DEFAULT_PREDICTION_CUTOFF
        labels: Dict[str, Dict[str, TargetLabel]] = {}
        for asset in assets:
            labels[asset.id.lower()] = {}
            for target_name in cls.RESISTANCE_TARGETS:
                labels[asset.id.lower()][target_name] = TargetLabel(
                    entity_id=asset.id,
                    asset_id=asset.id,
                    asset=asset.id,
                    tenant_id=tenant_id,
                    target_name=target_name,
                    outcome_value=None,
                    observation_horizon_date=None,
                    observation_date=None,
                    prediction_cutoff=cutoff,
                    is_known_at_cutoff=False,
                    outcome_evidence_id=None,
                    evidence_references=[],
                    label_version="v1",
                    derivation_method="unavailable_without_dated_observed_resistance_outcome",
                    confidence=0.0,
                    provenance={
                        "label_status": "unknown_without_dated_observed_resistance_outcome",
                        "prediction_cutoff": cutoff.isoformat(),
                        "tenant_id": tenant_id,
                    },
                )
        return labels

    @classmethod
    def generate_opportunity_labels(
        cls,
        assets: List[AssetIntelligence],
        prediction_cutoff: Optional[date] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, TargetLabel]:
        """Keep opportunity success unknown until an explicit observed label is stored."""
        cutoff = prediction_cutoff or cls.DEFAULT_PREDICTION_CUTOFF
        return {
            f"{asset.id.lower()}:{cls.OPPORTUNITY_SUCCESS_TARGET}": TargetLabel(
                entity_id=asset.id,
                asset_id=asset.id,
                asset=asset.id,
                tenant_id=tenant_id,
                target_name=cls.OPPORTUNITY_SUCCESS_TARGET,
                outcome_value=None,
                observation_horizon_date=None,
                observation_date=None,
                prediction_cutoff=cutoff,
                is_known_at_cutoff=False,
                outcome_evidence_id=None,
                evidence_references=[],
                label_version="v1",
                derivation_method="unavailable_without_observed_opportunity_success_outcome",
                confidence=0.0,
                provenance={
                    "label_status": "unknown_without_observed_opportunity_success_outcome",
                    "prediction_cutoff": cutoff.isoformat(),
                    "tenant_id": tenant_id,
                },
            )
            for asset in assets
        }


class DatasetBuilder:
    """Builds historical ML datasets while preserving temporal and provenance constraints."""

    CNS_FEATURES = (
        "molecular_weight",
        "logp",
        "tpsa",
        "bbb_permeability",
        "transporter_efflux",
        "protein_binding",
        "kp",
        "kp_uu",
        "csf_exposure",
        "prior_intracranial_activity",
    )
    CNS_MEASURED_EVIDENCE_FEATURES = frozenset(
        {"kp", "kp_uu", "csf_exposure", "prior_intracranial_activity"}
    )
    CNS_PREDICTED_EVIDENCE_FEATURES = (
        "cns_penetration_potential",
        "predicted_cns_potential",
    )
    RESISTANCE_FEATURES = (
        "target_biology_signal",
        "known_resistance_evidence",
        "pathway_topology_evidence",
        "clinical_progression_evidence",
        "mutation_evidence",
        "combination_evidence",
    )
    MINIMUM_LABELLED_ROWS = 20
    MINIMUM_ROWS_PER_CLASS = 5
    OPPORTUNITY_SIGNAL_FEATURES = {
        "biology": (
            "target_selectivity_score",
            "biochemical_potency_score",
            "potency",
            "selectivity",
        ),
        "clinical_probability": (
            "clinical_success_probability",
            "phase_II_success_probability",
            "phase_III_success_probability",
            "regulatory_success_probability",
        ),
        "patient_match": ("patient_match_score", "patient_match_probability"),
        "cns": (
            "cns_predicted_potential",
            "cns_penetration_potential",
            "cns_clinical_efficacy_probability",
        ),
        "resistance": (
            "resistance_mechanism_probability",
            "resistance_risk_probability",
            "predicted_resistance_probability",
        ),
        "safety": (
            "safety_risk_probability",
            "grade_ge_3_ae_probability",
            "dlt_probability",
            "discontinuation_probability",
            "organ_toxicity_probability",
            "therapeutic_index_risk",
        ),
        "differentiation": (
            "differentiation_score",
            "biomarker_stratification_precision",
            "biomarker_strength",
        ),
        "competition": ("competition_intensity", "competition_score"),
        "commercial_opportunity": ("commercial_opportunity_score",),
        "licensing_signals": ("licensing_availability_signal", "licensing_signal"),
        "evidence_confidence": ("evidence_confidence",),
    }
    OPPORTUNITY_EPISTEMIC_CLASSES = frozenset(
        {
            "FACT",
            "DERIVED_FEATURE",
            "ML_PREDICTION",
            "AI_INFERENCE",
            "HYPOTHESIS",
            "UNKNOWN",
        }
    )

    def __init__(self, feature_store: Optional[FeatureStore] = None) -> None:
        self.feature_store = feature_store or FeatureStore()

    def _resolve_cutoff(self, cutoff_date: Optional[date], default: date) -> date:
        return cutoff_date or default

    def _select_feature_records(self, asset_id: str, cutoff: date, tenant_id: Optional[str] = None) -> Dict[str, Optional[float]]:
        feature_rows = self.feature_store.get_feature_records_for_asset(asset_id, tenant_id=tenant_id)
        selected: Dict[str, Optional[float]] = {}
        for row in feature_rows:
            if row.prediction_cutoff and row.prediction_cutoff <= cutoff:
                selected[row.feature_name] = row.value
        return selected or {}

    def _select_label_records(self, asset_id: str, cutoff: date, tenant_id: Optional[str] = None) -> Dict[str, Optional[float]]:
        labels = self.feature_store.get_feature_records_for_asset(asset_id, tenant_id=tenant_id, feature_name_prefix="label_")
        selected: Dict[str, Optional[float]] = {}
        for row in labels:
            if row.prediction_cutoff and row.prediction_cutoff <= cutoff:
                selected[row.feature_name] = row.value
        return selected or {}

    @staticmethod
    def _has_explicit_observed_label(record: FeatureRecord, target_name: str) -> bool:
        provenance = record.provenance
        return (
            record.feature_name == f"label_{target_name}"
            and provenance.get("target_name") == target_name
            and provenance.get("record_type") == "observed_outcome_label"
            and provenance.get("test_only") is not True
            and provenance.get("scientific_evidence") is not False
            and record.value in (0, 1, 0.0, 1.0)
            and bool(record.evidence_references)
        )

    def _select_historical_features(
        self,
        entity_id: str,
        feature_names: tuple[str, ...],
        prediction_cutoff: date,
        tenant_id: Optional[str],
    ) -> tuple[Dict[str, Optional[float]], Dict[str, Dict[str, Any]]]:
        selected: Dict[str, Optional[float]] = {name: None for name in feature_names}
        selected_records: Dict[str, FeatureRecord] = {}
        for record in self.feature_store.get_feature_records_for_asset(
            entity_id,
            tenant_id=tenant_id,
        ):
            if record.feature_name not in feature_names:
                continue
            if record.observation_date > prediction_cutoff:
                continue
            if record.prediction_cutoff > prediction_cutoff:
                continue
            if record.feature_version != "v1":
                continue
            if (
                record.provenance.get("test_only") is True
                or record.provenance.get("scientific_evidence") is False
            ):
                continue
            previous = selected_records.get(record.feature_name)
            if previous is None or (
                record.prediction_cutoff,
                record.observation_date,
            ) > (previous.prediction_cutoff, previous.observation_date):
                selected_records[record.feature_name] = record

        provenance: Dict[str, Dict[str, Any]] = {}
        for name, record in selected_records.items():
            value = record.value
            selected[name] = (
                float(value)
                if isinstance(value, (int, float)) and not isinstance(value, bool)
                else None
            )
            provenance[name] = record.model_dump(mode="json")
        return selected, provenance

    def _select_observed_label(
        self,
        entity_id: str,
        target_name: str,
        prediction_cutoff: date,
        dataset_cutoff: date,
        tenant_id: Optional[str],
    ) -> Optional[FeatureRecord]:
        eligible = [
            record
            for record in self.feature_store.get_feature_records_for_asset(
                entity_id,
                tenant_id=tenant_id,
                feature_name_prefix=f"label_{target_name}",
            )
            if self._has_explicit_observed_label(record, target_name)
            and record.observation_date > prediction_cutoff
            and record.observation_date <= dataset_cutoff
            and record.prediction_cutoff <= dataset_cutoff
        ]
        return max(
            eligible,
            key=lambda record: (record.observation_date, record.prediction_cutoff),
            default=None,
        )

    @classmethod
    def _binary_labels_are_sufficient(cls, values: List[Optional[float]]) -> bool:
        known = [value for value in values if value in (0.0, 1.0)]
        return (
            len(known) >= cls.MINIMUM_LABELLED_ROWS
            and known.count(0.0) >= cls.MINIMUM_ROWS_PER_CLASS
            and known.count(1.0) >= cls.MINIMUM_ROWS_PER_CLASS
        )

    def build_cns_dataset(
        self,
        name: str = "cns_v1",
        version: str = "1.0.0",
        cutoff_date: Optional[date] = None,
        tenant_id: Optional[str] = None,
        *,
        prediction_cutoff: Optional[date] = None,
    ) -> MLDataset:
        """Build a cutoff-safe CNS dataset; measured activity is never relabeled as predicted potential."""
        cutoff = self._resolve_cutoff(cutoff_date, date.today())
        feature_cutoff = prediction_cutoff or cutoff
        if feature_cutoff > cutoff:
            raise ValueError("CNS prediction cutoff cannot be later than the dataset cutoff.")

        assets = list_fixture_assets()
        unknown_labels = LabelGenerator.generate_cns_labels(
            assets,
            prediction_cutoff=feature_cutoff,
            tenant_id=tenant_id,
        )
        from app.opportunity_engine.cns.engine import CNSIntelligenceEngine

        cns_engine = CNSIntelligenceEngine()
        records: List[DatasetRecord] = []
        label_versions: set[str] = set()
        for asset in assets:
            feature_values, feature_provenance = self._select_historical_features(
                asset.id,
                self.CNS_FEATURES,
                feature_cutoff,
                tenant_id,
            )
            label_record = self._select_observed_label(
                asset.id,
                "cns_clinical_efficacy",
                feature_cutoff,
                cutoff,
                tenant_id,
            )
            if label_record is not None:
                label_versions.add(label_record.feature_version)
            measured_evidence = {
                name: row
                for name, row in feature_provenance.items()
                if name in self.CNS_MEASURED_EVIDENCE_FEATURES
                and row.get("provenance", {}).get("evidence_kind")
                in {"measured", "observed"}
            }
            predicted_potential = {
                name: row
                for name, row in self._select_historical_features(
                    asset.id,
                    tuple(self.CNS_PREDICTED_EVIDENCE_FEATURES),
                    feature_cutoff,
                    tenant_id,
                )[1].items()
            }
            raw_observations = cns_engine.get_raw_observations_for_asset(asset.id.lower())
            undated_observations = [
                {
                    "parameter_type": observation.parameter_type.value,
                    "evidence_level": observation.evidence_level.value,
                    "species": observation.species.value,
                    "normalized_value": observation.normalized_value,
                    "normalized_unit": observation.normalized_unit,
                    "source_citation": observation.source_citation,
                    "pmid": observation.pmid,
                    "nct_id": observation.nct_id,
                    "observation_date": None,
                    "time_admissible": False,
                }
                for observation in raw_observations
                if observation.observation_date is None
            ]
            dated_observations = [
                {
                    "parameter_type": observation.parameter_type.value,
                    "evidence_level": observation.evidence_level.value,
                    "species": observation.species.value,
                    "normalized_value": observation.normalized_value,
                    "normalized_unit": observation.normalized_unit,
                    "source_citation": observation.source_citation,
                    "pmid": observation.pmid,
                    "nct_id": observation.nct_id,
                    "observation_date": observation.observation_date.isoformat(),
                    "time_admissible": True,
                }
                for observation in raw_observations
                if observation.observation_date is not None
                and observation.observation_date <= feature_cutoff
            ]
            labels = unknown_labels[f"{asset.id.lower()}:cns_clinical_efficacy"]
            measured_evidence.update(
                {
                    f"raw_observation_{index}": observation
                    for index, observation in enumerate(dated_observations)
                }
            )
            records.append(
                DatasetRecord(
                    entity_id=asset.id,
                    as_of_date=feature_cutoff,
                    features=feature_values,
                    label=float(label_record.value) if label_record is not None else None,
                    metadata={
                        "tenant_id": tenant_id,
                        "feature_cutoff": feature_cutoff.isoformat(),
                        "dataset_cutoff": cutoff.isoformat(),
                        "label_status": (
                            "observed_outcome"
                            if label_record is not None
                            else labels.provenance["label_status"]
                        ),
                        "label_observation_date": (
                            label_record.observation_date.isoformat()
                            if label_record is not None
                            else None
                        ),
                        "label_evidence_references": (
                            label_record.evidence_references if label_record is not None else []
                        ),
                        "feature_provenance": feature_provenance,
                        "measured_cns_evidence": measured_evidence,
                        "undated_cns_evidence_excluded": undated_observations,
                        "predicted_cns_potential": predicted_potential,
                        "cns_evidence_state": (
                            "measured_and_predicted"
                            if measured_evidence and predicted_potential
                            else "measured"
                            if measured_evidence
                            else "predicted_potential_only"
                            if predicted_potential
                            else "undated_measured"
                            if undated_observations
                            else "unknown"
                        ),
                        "test_only": False,
                    },
                )
            )

        labels = [record.label for record in records]
        training_available = self._binary_labels_are_sufficient(labels)
        return MLDataset(
            name=name,
            version=version,
            feature_names=list(self.CNS_FEATURES),
            target_name="cns_clinical_efficacy",
            train_records=records,
            cutoff_date=cutoff,
            feature_versions=["v1"],
            label_versions=sorted(label_versions),
            prediction_cutoffs={"training": feature_cutoff, "validation": cutoff, "test": cutoff},
            asset_scope=[asset.id for asset in assets],
            metadata={
                "dataset_family": "prompt_41_cns",
                "model_name": "cns",
                "tenant_scope": tenant_id or "global",
                "temporal_guardrail": (
                    "feature observation_date and prediction_cutoff <= prediction_cutoff; "
                    "observed label observation_date > prediction_cutoff and <= dataset cutoff"
                ),
                "prediction_cutoff": feature_cutoff.isoformat(),
                "dataset_cutoff": cutoff.isoformat(),
                "measured_predicted_unknown_distinguished": True,
                "undated_raw_clinical_outcomes_excluded": True,
                "undated_raw_observation_count": sum(
                    len(record.metadata["undated_cns_evidence_excluded"])
                    for record in records
                ),
                "model_status": "development_unavailable" if not training_available else "trainable",
                "training_available": training_available,
                "labelled_rows": sum(value is not None for value in labels),
                "class_counts": {
                    "0": labels.count(0.0),
                    "1": labels.count(1.0),
                },
                "minimum_labelled_rows": self.MINIMUM_LABELLED_ROWS,
                "minimum_rows_per_class": self.MINIMUM_ROWS_PER_CLASS,
                "unavailable_reason": (
                    None
                    if training_available
                    else "Insufficient dated, tenant-scoped observed CNS efficacy outcomes."
                ),
                "synthetic_data_used": False,
            },
        )

    def build_resistance_dataset(
        self,
        name: str = "resistance_v1",
        version: str = "1.0.0",
        cutoff_date: Optional[date] = None,
        tenant_id: Optional[str] = None,
        *,
        prediction_cutoff: Optional[date] = None,
    ) -> MLDataset:
        """Build a point-in-time resistance dataset from explicit observed mechanism labels only."""
        cutoff = self._resolve_cutoff(cutoff_date, date.today())
        feature_cutoff = prediction_cutoff or cutoff
        if feature_cutoff > cutoff:
            raise ValueError("Resistance prediction cutoff cannot be later than the dataset cutoff.")

        assets = list_fixture_assets()
        from app.opportunity_engine.resistance.engine import ResistanceIntelligenceEngine

        resistance_engine = ResistanceIntelligenceEngine()
        canonical_profiles = {
            profile.asset_id.lower(): profile
            for profile in resistance_engine.list_benchmark_profiles()
        }
        unknown_labels = LabelGenerator.generate_resistance_labels(
            assets,
            prediction_cutoff=feature_cutoff,
            tenant_id=tenant_id,
        )
        records: List[DatasetRecord] = []
        target_counts: Dict[str, Dict[str, int]] = {
            target: {"0": 0, "1": 0} for target in LabelGenerator.RESISTANCE_TARGETS
        }
        label_versions: set[str] = set()
        for asset in assets:
            feature_values, feature_provenance = self._select_historical_features(
                asset.id,
                self.RESISTANCE_FEATURES,
                feature_cutoff,
                tenant_id,
            )
            resistance_labels: Dict[str, Optional[float]] = {}
            label_provenance: Dict[str, Dict[str, Any]] = {}
            for target_name in LabelGenerator.RESISTANCE_TARGETS:
                label_record = self._select_observed_label(
                    asset.id,
                    f"resistance_{target_name}",
                    feature_cutoff,
                    cutoff,
                    tenant_id,
                )
                if label_record is None:
                    resistance_labels[target_name] = None
                    label_provenance[target_name] = unknown_labels[asset.id.lower()][
                        target_name
                    ].provenance
                    continue
                outcome = float(label_record.value)
                resistance_labels[target_name] = outcome
                target_counts[target_name][str(int(outcome))] += 1
                label_versions.add(label_record.feature_version)
                label_provenance[target_name] = label_record.model_dump(mode="json")
            profile = canonical_profiles.get(asset.id.lower())
            records.append(
                DatasetRecord(
                    entity_id=asset.id,
                    as_of_date=feature_cutoff,
                    features=feature_values,
                    label=None,
                    metadata={
                        "tenant_id": tenant_id,
                        "feature_cutoff": feature_cutoff.isoformat(),
                        "dataset_cutoff": cutoff.isoformat(),
                        "resistance_labels": resistance_labels,
                        "label_provenance": label_provenance,
                        "feature_provenance": feature_provenance,
                        "unknown_targets": [
                            target
                            for target, outcome in resistance_labels.items()
                            if outcome is None
                        ],
                        "supporting_evidence": {
                            name: row.get("evidence_references", [])
                            for name, row in feature_provenance.items()
                            if row.get("evidence_references")
                        },
                        "undated_canonical_resistance_evidence": (
                            [
                                {
                                    "mechanism_name": mechanism.mechanism_name,
                                    "classification": mechanism.classification.value,
                                    "is_experimentally_proven": mechanism.is_experimentally_proven,
                                    "evidence_citations": mechanism.evidence_citations,
                                    "time_admissible": False,
                                }
                                for mechanism in profile.top_escape_mechanisms
                            ]
                            if profile is not None
                            else []
                        ),
                    },
                )
            )

        target_training_status = {
            target: (
                count["0"] + count["1"] >= self.MINIMUM_LABELLED_ROWS
                and count["0"] >= self.MINIMUM_ROWS_PER_CLASS
                and count["1"] >= self.MINIMUM_ROWS_PER_CLASS
            )
            for target, count in target_counts.items()
        }
        training_available = bool(target_training_status) and all(
            target_training_status.values()
        )
        return MLDataset(
            name=name,
            version=version,
            feature_names=list(self.RESISTANCE_FEATURES),
            target_name="resistance_mechanisms",
            train_records=records,
            cutoff_date=cutoff,
            feature_versions=["v1"],
            label_versions=sorted(label_versions),
            prediction_cutoffs={"training": feature_cutoff, "validation": cutoff, "test": cutoff},
            asset_scope=[asset.id for asset in assets],
            metadata={
                "dataset_family": "prompt_42_resistance",
                "model_name": "resistance",
                "tenant_scope": tenant_id or "global",
                "temporal_guardrail": (
                    "feature observation_date and prediction_cutoff <= prediction_cutoff; "
                    "observed outcome observation_date > prediction_cutoff and <= dataset cutoff"
                ),
                "prediction_cutoff": feature_cutoff.isoformat(),
                "dataset_cutoff": cutoff.isoformat(),
                "resistance_targets": list(LabelGenerator.RESISTANCE_TARGETS),
                "target_class_counts": target_counts,
                "target_training_status": target_training_status,
                "undated_canonical_resistance_profiles_excluded": True,
                "undated_canonical_mechanism_count": sum(
                    len(record.metadata["undated_canonical_resistance_evidence"])
                    for record in records
                ),
                "model_status": "development_unavailable" if not training_available else "trainable",
                "training_available": training_available,
                "minimum_labelled_rows": self.MINIMUM_LABELLED_ROWS,
                "minimum_rows_per_class": self.MINIMUM_ROWS_PER_CLASS,
                "unavailable_reason": (
                    None
                    if training_available
                    else "Insufficient dated, tenant-scoped observed resistance mechanism outcomes."
                ),
                "synthetic_data_used": False,
            },
        )

    def build_opportunity_ranking_dataset(
        self,
        name: str = "opportunity_ranking_v1",
        version: str = "1.0.0",
        cutoff_date: Optional[date] = None,
        tenant_id: Optional[str] = None,
        *,
        prediction_cutoff: Optional[date] = None,
    ) -> MLDataset:
        """Build a point-in-time ranking dataset without deriving labels or imputing unknown signals."""
        cutoff = self._resolve_cutoff(cutoff_date, date.today())
        feature_cutoff = prediction_cutoff or cutoff
        if feature_cutoff > cutoff:
            raise ValueError("Opportunity prediction cutoff cannot be later than the dataset cutoff.")

        assets = list_fixture_assets()
        unknown_labels = LabelGenerator.generate_opportunity_labels(
            assets,
            prediction_cutoff=feature_cutoff,
            tenant_id=tenant_id,
        )
        feature_names = [
            feature_name
            for names in self.OPPORTUNITY_SIGNAL_FEATURES.values()
            for feature_name in names
        ]
        records: List[DatasetRecord] = []
        label_versions: set[str] = set()
        for asset in assets:
            selected_records: Dict[str, FeatureRecord] = {}
            for feature_record in self.feature_store.get_feature_records_for_asset(
                asset.id,
                tenant_id=tenant_id,
            ):
                if feature_record.feature_name not in feature_names:
                    continue
                if feature_record.observation_date > feature_cutoff:
                    continue
                if feature_record.prediction_cutoff > feature_cutoff:
                    continue
                if (
                    feature_record.provenance.get("test_only") is True
                    or feature_record.provenance.get("scientific_evidence") is False
                ):
                    continue
                current = selected_records.get(feature_record.feature_name)
                if current is None or (
                    feature_record.prediction_cutoff,
                    feature_record.observation_date,
                ) > (current.prediction_cutoff, current.observation_date):
                    selected_records[feature_record.feature_name] = feature_record

            feature_values: Dict[str, Optional[float]] = {
                feature_name: None for feature_name in feature_names
            }
            feature_provenance: Dict[str, Dict[str, Any]] = {}
            upstream_signals: Dict[str, Dict[str, Dict[str, Any]]] = {}
            for signal_name, signal_feature_names in self.OPPORTUNITY_SIGNAL_FEATURES.items():
                upstream_signals[signal_name] = {}
                for feature_name in signal_feature_names:
                    source = selected_records.get(feature_name)
                    if source is None:
                        upstream_signals[signal_name][feature_name] = {
                            "epistemic_class": "UNKNOWN",
                            "available": False,
                            "value": None,
                            "reason": "No tenant-visible feature record at the prediction cutoff.",
                        }
                        continue

                    provenance = source.provenance
                    declared_class = provenance.get("epistemic_class")
                    epistemic_class = (
                        declared_class.upper()
                        if isinstance(declared_class, str)
                        and declared_class.upper() in self.OPPORTUNITY_EPISTEMIC_CLASSES
                        else "UNKNOWN"
                    )
                    numeric_value = (
                        float(source.value)
                        if isinstance(source.value, (int, float))
                        and not isinstance(source.value, bool)
                        else None
                    )
                    available = numeric_value is not None and epistemic_class != "UNKNOWN"
                    feature_values[feature_name] = numeric_value if available else None
                    serialized_record = source.model_dump(mode="json")
                    feature_provenance[feature_name] = serialized_record
                    upstream_signals[signal_name][feature_name] = {
                        "epistemic_class": epistemic_class,
                        "available": available,
                        "value": numeric_value if available else None,
                        "unclassified_value": (
                            numeric_value if numeric_value is not None and not available else None
                        ),
                        "unavailable_reason": (
                            None
                            if available
                            else "Missing value or no declared epistemic class; excluded from numeric inputs."
                        ),
                        "feature_version": source.feature_version,
                        "observation_date": source.observation_date.isoformat(),
                        "prediction_cutoff": source.prediction_cutoff.isoformat(),
                        "evidence_references": source.evidence_references,
                        "provenance": provenance,
                    }

            label = self._select_observed_label(
                asset.id,
                LabelGenerator.OPPORTUNITY_SUCCESS_TARGET,
                feature_cutoff,
                cutoff,
                tenant_id,
            )
            if label is not None:
                label_versions.add(label.feature_version)
            label_record = unknown_labels[
                f"{asset.id.lower()}:{LabelGenerator.OPPORTUNITY_SUCCESS_TARGET}"
            ]
            records.append(
                DatasetRecord(
                    entity_id=asset.id,
                    as_of_date=feature_cutoff,
                    features=feature_values,
                    label=float(label.value) if label is not None else None,
                    metadata={
                        "tenant_id": tenant_id,
                        "feature_cutoff": feature_cutoff.isoformat(),
                        "dataset_cutoff": cutoff.isoformat(),
                        "upstream_signals": upstream_signals,
                        "feature_provenance": feature_provenance,
                        "label_status": (
                            "observed_opportunity_success"
                            if label is not None
                            else label_record.provenance["label_status"]
                        ),
                        "label_observation_date": (
                            label.observation_date.isoformat() if label is not None else None
                        ),
                        "label_evidence_references": (
                            label.evidence_references if label is not None else []
                        ),
                    },
                )
            )

        labels = [record.label for record in records]
        training_available = self._binary_labels_are_sufficient(labels)
        return MLDataset(
            name=name,
            version=version,
            feature_names=feature_names,
            target_name=LabelGenerator.OPPORTUNITY_SUCCESS_TARGET,
            train_records=records,
            cutoff_date=cutoff,
            feature_versions=["v1"],
            label_versions=sorted(label_versions),
            prediction_cutoffs={
                "training": feature_cutoff,
                "validation": cutoff,
                "test": cutoff,
            },
            asset_scope=[asset.id for asset in assets],
            metadata={
                "dataset_family": "prompt_43_opportunity_ranking",
                "model_name": "opportunity_ranking",
                "tenant_scope": tenant_id or "global",
                "prediction_cutoff": feature_cutoff.isoformat(),
                "dataset_cutoff": cutoff.isoformat(),
                "temporal_guardrail": (
                    "feature observation_date and prediction_cutoff <= prediction_cutoff; "
                    "observed outcome observation_date > prediction_cutoff and <= dataset cutoff"
                ),
                "upstream_signal_groups": list(self.OPPORTUNITY_SIGNAL_FEATURES),
                "epistemic_classes": sorted(self.OPPORTUNITY_EPISTEMIC_CLASSES),
                "training_available": training_available,
                "model_status": (
                    "historical_labels_available"
                    if training_available
                    else "insufficient_historical_labels"
                ),
                "labelled_rows": sum(value is not None for value in labels),
                "class_counts": {
                    "0": labels.count(0.0),
                    "1": labels.count(1.0),
                },
                "minimum_labelled_rows": self.MINIMUM_LABELLED_ROWS,
                "minimum_rows_per_class": self.MINIMUM_ROWS_PER_CLASS,
                "unavailable_reason": (
                    None
                    if training_available
                    else "Insufficient explicit, dated, tenant-scoped opportunity success labels."
                ),
                "synthetic_data_used": False,
                "legacy_synthetic_opportunity_cohort_used": False,
            },
        )

    def build_dataset(
        self,
        name: str = "oncology_opportunity_v1",
        version: str = "1.0.0",
        target_name: str = "opportunity_pursuit_success",
        cutoff_date: Optional[date] = None,
        train_ratio: float = 0.6,
        val_ratio: float = 0.2,
        test_ratio: float = 0.2,
    ) -> MLDataset:
        cutoff = self._resolve_cutoff(cutoff_date, date.today())
        assets = list_fixture_assets()
        labels = LabelGenerator.generate_labels(assets, prediction_cutoff=cutoff)
        records: List[DatasetRecord] = []

        feature_names = [f.name for f in self.feature_store.CANONICAL_FEATURES]
        for asset in assets:
            feat_vec = self.feature_store.compute_features_for_asset(asset, as_of=cutoff)
            feature_values = feat_vec.features
            key = asset.id.lower()
            label_record = labels.get(f"{key}:{target_name}") or labels.get(f"{key}:IND_achieved")
            outcome = label_record.outcome_value if label_record and label_record.outcome_value is not None else 0.0

            records.append(
                DatasetRecord(
                    entity_id=asset.id,
                    as_of_date=cutoff,
                    features=feature_values,
                    label=outcome,
                    metadata={
                        "asset_name": asset.name,
                        "stage": asset.stage.value,
                        "owner": asset.owner,
                        "cutoff": cutoff.isoformat(),
                        "label_target": label_record.target_name if label_record else target_name,
                    },
                )
            )

        synthetic_cohort = [
            ("hist_asset_001", {"target_selectivity_score": 90.0, "biochemical_potency_score": 85.0, "safety_therapeutic_index": 80.0, "cns_penetration_potential": 75.0, "biomarker_stratification_precision": 85.0, "clinical_readiness_score": 70.0, "trial_sample_power": 75.0, "licensing_availability_signal": 80.0}, 1.0),
            ("hist_asset_002", {"target_selectivity_score": 45.0, "biochemical_potency_score": 50.0, "safety_therapeutic_index": 35.0, "cns_penetration_potential": 20.0, "biomarker_stratification_precision": 40.0, "clinical_readiness_score": 30.0, "trial_sample_power": 40.0, "licensing_availability_signal": 20.0}, 0.0),
            ("hist_asset_003", {"target_selectivity_score": 88.0, "biochemical_potency_score": 92.0, "safety_therapeutic_index": 78.0, "cns_penetration_potential": 85.0, "biomarker_stratification_precision": 90.0, "clinical_readiness_score": 80.0, "trial_sample_power": 85.0, "licensing_availability_signal": 50.0}, 1.0),
            ("hist_asset_004", {"target_selectivity_score": 30.0, "biochemical_potency_score": 40.0, "safety_therapeutic_index": 20.0, "cns_penetration_potential": 15.0, "biomarker_stratification_precision": 30.0, "clinical_readiness_score": 25.0, "trial_sample_power": 30.0, "licensing_availability_signal": 90.0}, 0.0),
            ("hist_asset_005", {"target_selectivity_score": 75.0, "biochemical_potency_score": 70.0, "safety_therapeutic_index": 68.0, "cns_penetration_potential": 60.0, "biomarker_stratification_precision": 75.0, "clinical_readiness_score": 60.0, "trial_sample_power": 65.0, "licensing_availability_signal": 40.0}, 1.0),
            ("hist_asset_006", {"target_selectivity_score": 40.0, "biochemical_potency_score": 45.0, "safety_therapeutic_index": 30.0, "cns_penetration_potential": 25.0, "biomarker_stratification_precision": 35.0, "clinical_readiness_score": 35.0, "trial_sample_power": 35.0, "licensing_availability_signal": 10.0}, 0.0),
        ]

        for s_id, s_feats, s_lbl in synthetic_cohort:
            records.append(
                DatasetRecord(
                    entity_id=s_id,
                    as_of_date=self._resolve_cutoff(cutoff_date, date.today()),
                    features=s_feats,
                    label=s_lbl,
                    metadata={"synthetic": True, "cutoff": self._resolve_cutoff(cutoff_date, date.today()).isoformat()},
                )
            )

        n = len(records)
        train_idx = int(n * train_ratio)
        val_idx = int(n * (train_ratio + val_ratio))
        train = records[:train_idx]
        val = records[train_idx:val_idx]
        test = records[val_idx:]

        dataset = MLDataset(
            name=name,
            version=version,
            feature_names=feature_names,
            target_name=target_name,
            train_records=train,
            val_records=val,
            test_records=test,
            cutoff_date=cutoff,
            feature_versions=["v1"],
            label_versions=["v1"],
            prediction_cutoffs={
                "training": cutoff,
                "validation": cutoff,
                "test": cutoff,
            },
            asset_scope=[asset.id for asset in assets],
            metadata={
                "dataset_family": "prompt_30_31",
                "generated_from": "feature_store_and_label_generator",
                "feature_store": "versioned_feature_store",
                "temporal_guardrail": "prediction_cutoff_enforced",
                "tenant_scope": "global",
                "cutoff_date": cutoff.isoformat(),
                "train_ratio": train_ratio,
                "val_ratio": val_ratio,
                "test_ratio": test_ratio,
            },
        )
        return dataset

    def build_translational_dataset(
        self,
        name: str = "biology_translational_v1",
        version: str = "1.0.0",
        cutoff_date: Optional[date] = None,
        tenant_id: Optional[str] = None,
        *,
        prediction_cutoff: Optional[date] = None,
    ) -> MLDataset:
        """Build a point-in-time translational dataset from observed, tenant-scoped records."""
        cutoff = self._resolve_cutoff(cutoff_date, date.today())
        feature_cutoff = prediction_cutoff or cutoff
        if feature_cutoff > cutoff:
            raise ValueError("Translational prediction cutoff cannot be later than the dataset cutoff.")
        assets = list_fixture_assets()
        labels = LabelGenerator.generate_translational_labels(
            assets,
            prediction_cutoff=feature_cutoff,
            tenant_id=tenant_id,
        )
        feature_names = [definition.name for definition in self.feature_store.TRANSLATIONAL_FEATURES]
        records: List[DatasetRecord] = []
        label_versions: set[str] = set()
        for asset in assets:
            feature_values, feature_provenance = self._select_historical_features(
                asset.id, tuple(feature_names), feature_cutoff, tenant_id
            )
            outcome_record = self._select_observed_label(
                asset.id, "translational_potential", feature_cutoff, cutoff, tenant_id
            )
            outcome = float(outcome_record.value) if outcome_record is not None else None
            if outcome_record is not None:
                label_versions.add(outcome_record.feature_version)
            unknown_label = labels[f"{asset.id.lower()}:translational_potential"]
            records.append(
                DatasetRecord(
                    entity_id=asset.id,
                    as_of_date=feature_cutoff,
                    features={name: feature_values.get(name) for name in feature_names},
                    label=outcome,
                    metadata={
                        "tenant_id": tenant_id,
                        "feature_cutoff": feature_cutoff.isoformat(),
                        "dataset_cutoff": cutoff.isoformat(),
                        "target_name": "translational_potential",
                        "label_status": (
                            "observed_outcome"
                            if outcome_record is not None
                            else unknown_label.provenance["label_status"]
                        ),
                        "label_provenance": (
                            outcome_record.model_dump(mode="json")
                            if outcome_record is not None
                            else unknown_label.provenance
                        ),
                        "feature_provenance": feature_provenance,
                    },
                )
            )

        labels_for_training = [record.label for record in records]
        training_available = self._binary_labels_are_sufficient(labels_for_training)
        dataset = MLDataset(
            name=name,
            version=version,
            feature_names=feature_names,
            target_name="translational_potential",
            train_records=records,
            val_records=[],
            test_records=[],
            cutoff_date=cutoff,
            feature_versions=["v1"],
            label_versions=sorted(label_versions),
            prediction_cutoffs={"training": feature_cutoff, "validation": cutoff, "test": cutoff},
            asset_scope=[asset.id for asset in assets],
            metadata={
                "dataset_family": "prompt_37_biology_translational",
                "feature_family": "prompt_37",
                "model_family": "biology_translational",
                "tenant_scope": tenant_id or "global",
                "temporal_guardrail": "features_available_at_prediction_cutoff_and_outcomes_observed_after_cutoff",
                "prediction_cutoff": feature_cutoff.isoformat(),
                "dataset_cutoff": cutoff.isoformat(),
                "training_available": training_available,
                "model_status": "trainable" if training_available else "insufficient_historical_labels",
                "labelled_rows": sum(value is not None for value in labels_for_training),
                "class_counts": {
                    "0": labels_for_training.count(0.0),
                    "1": labels_for_training.count(1.0),
                },
                "minimum_labelled_rows": self.MINIMUM_LABELLED_ROWS,
                "minimum_rows_per_class": self.MINIMUM_ROWS_PER_CLASS,
                "synthetic_data_used": False,
            },
        )
        return dataset

    def build_clinical_success_dataset(
        self,
        name: str = "clinical_success_v1",
        version: str = "1.0.0",
        cutoff_date: Optional[date] = None,
        tenant_id: Optional[str] = None,
        *,
        prediction_cutoff: Optional[date] = None,
    ) -> MLDataset:
        """Build multi-outcome clinical data from point-in-time features and observed outcomes."""
        cutoff = self._resolve_cutoff(cutoff_date, date.today())
        feature_cutoff = prediction_cutoff or cutoff
        if feature_cutoff > cutoff:
            raise ValueError("Clinical prediction cutoff cannot be later than the dataset cutoff.")
        assets = list_fixture_assets()
        labels = LabelGenerator.generate_clinical_success_labels(
            assets,
            prediction_cutoff=feature_cutoff,
            tenant_id=tenant_id,
        )
        feature_names = [definition.name for definition in self.feature_store.CANONICAL_FEATURES]
        clinical_targets = [
            "phase_II_success",
            "phase_III_success",
            "regulatory_success",
            "failure_probability",
        ]
        records: List[DatasetRecord] = []
        target_labels: Dict[str, List[Optional[float]]] = {target: [] for target in clinical_targets}
        label_versions: set[str] = set()
        for asset in assets:
            feature_values, feature_provenance = self._select_historical_features(
                asset.id, tuple(feature_names), feature_cutoff, tenant_id
            )
            observed_labels: Dict[str, Optional[float]] = {}
            label_provenance: Dict[str, Dict[str, Any]] = {}
            for target in clinical_targets:
                label_record = self._select_observed_label(
                    asset.id, target, feature_cutoff, cutoff, tenant_id
                )
                outcome = float(label_record.value) if label_record is not None else None
                observed_labels[target] = outcome
                target_labels[target].append(outcome)
                label_provenance[target] = (
                    label_record.model_dump(mode="json")
                    if label_record is not None
                    else labels[f"{asset.id.lower()}:{target}"].provenance
                )
                if label_record is not None:
                    label_versions.add(label_record.feature_version)
            records.append(
                DatasetRecord(
                    entity_id=asset.id,
                    as_of_date=feature_cutoff,
                    features={name: feature_values.get(name) for name in feature_names},
                    label=observed_labels["phase_II_success"],
                    metadata={
                        "tenant_id": tenant_id,
                        "feature_cutoff": feature_cutoff.isoformat(),
                        "dataset_cutoff": cutoff.isoformat(),
                        "target_name": "phase_II_success",
                        "clinical_targets": clinical_targets,
                        "clinical_labels": observed_labels,
                        "label_provenance": label_provenance,
                        "feature_provenance": feature_provenance,
                    },
                )
            )

        dataset = MLDataset(
            name=name,
            version=version,
            feature_names=feature_names,
            target_name="phase_II_success",
            train_records=records,
            val_records=[],
            test_records=[],
            cutoff_date=cutoff,
            feature_versions=["v1"],
            label_versions=sorted(label_versions),
            prediction_cutoffs={"training": feature_cutoff, "validation": cutoff, "test": cutoff},
            asset_scope=[asset.id for asset in assets],
            metadata={
                "dataset_family": "prompt_38_clinical_success",
                "feature_family": "prompt_29",
                "model_family": "clinical_success",
                "tenant_scope": tenant_id or "global",
                "temporal_guardrail": "features_available_at_prediction_cutoff_and_outcomes_observed_after_cutoff",
                "prediction_cutoff": feature_cutoff.isoformat(),
                "dataset_cutoff": cutoff.isoformat(),
                "clinical_targets": clinical_targets,
                "target_training_status": {
                    target: {
                        "training_available": self._binary_labels_are_sufficient(values),
                        "labelled_rows": sum(value is not None for value in values),
                        "class_counts": {
                            "0": values.count(0.0),
                            "1": values.count(1.0),
                        },
                    }
                    for target, values in target_labels.items()
                },
                "training_available": self._binary_labels_are_sufficient(
                    target_labels["phase_II_success"]
                ),
                "model_status": (
                    "trainable"
                    if self._binary_labels_are_sufficient(target_labels["phase_II_success"])
                    else "insufficient_historical_labels"
                ),
                "synthetic_data_used": False,
            },
        )
        return dataset

    def build_patient_response_dataset(
        self,
        name: str = "patient_response_v1",
        version: str = "1.0.0",
        cutoff_date: Optional[date] = None,
        tenant_id: Optional[str] = None,
        *,
        test_only_fixture: bool = False,
    ) -> MLDataset:
        """Build a point-in-time patient-response dataset.

        Domain assets have unknown response labels until patient-level outcomes are
        available. The optional deterministic cohort is explicitly test-only.
        """
        cutoff = self._resolve_cutoff(cutoff_date, date.today())
        feature_names = [definition.name for definition in self.feature_store.PATIENT_RESPONSE_FEATURES]
        records: List[DatasetRecord] = []

        if test_only_fixture:
            labels = LabelGenerator.generate_patient_response_test_labels(cutoff, tenant_id=tenant_id)
            for index in range(len(labels)):
                entity_id = f"patient_response_test_{index + 1:02d}"
                label = labels[entity_id.lower()]
                feature_values = {
                    feature_name: (
                        None
                        if index < 12 and index % 4 == 0 and feature_index in (2, 7)
                        else float(((index + 2) * (feature_index + 3) * 7) % 101)
                    )
                    for feature_index, feature_name in enumerate(feature_names)
                }
                for feature_name in feature_names:
                    record = FeatureRecord(
                        feature_name=feature_name,
                        value=feature_values[feature_name],
                        unit="test_fixture_value",
                        asset=entity_id,
                        asset_id=entity_id,
                        tenant_id=tenant_id,
                        evidence_references=[f"test-only:{entity_id}:{feature_name}"],
                        observation_date=cutoff,
                        prediction_cutoff=cutoff,
                        feature_version="v1",
                        extraction_method="prompt_39_test_only_fixture",
                        confidence=1.0,
                        provenance={
                            "test_only": True,
                            "scientific_evidence": False,
                            "feature_family": "prompt_39",
                            "prediction_cutoff": cutoff.isoformat(),
                        },
                    )
                    self.feature_store.record_feature(record)
                records.append(
                    DatasetRecord(
                        entity_id=entity_id,
                        as_of_date=cutoff,
                        features=feature_values,
                        label=label.outcome_value,
                        metadata={
                            "tenant_id": tenant_id,
                            "cutoff": cutoff.isoformat(),
                            "target_name": "patient_response",
                            "test_only": True,
                            "scientific_evidence": False,
                            "label_version": label.label_version,
                            "label_provenance": label.provenance,
                        },
                    )
                )
            train_records, val_records = records[:12], records[12:]
            assets_scope = [record.entity_id for record in records]
            label_versions = ["test-v1"]
        else:
            assets = list_fixture_assets()
            labels = LabelGenerator.generate_patient_response_labels(
                assets, prediction_cutoff=cutoff, tenant_id=tenant_id
            )
            for asset in assets:
                feature_records = self.feature_store.create_prompt_39_feature_records(
                    asset,
                    observation_date=cutoff,
                    prediction_cutoff=cutoff,
                    feature_version="v1",
                    tenant_id=tenant_id,
                )
                feature_values = {
                    record.feature_name: record.value
                    for record in feature_records
                    if record.observation_date <= cutoff and record.prediction_cutoff <= cutoff
                }
                label = labels[f"{asset.id.lower()}:patient_response"]
                records.append(
                    DatasetRecord(
                        entity_id=asset.id,
                        as_of_date=cutoff,
                        features={name: feature_values.get(name) for name in feature_names},
                        label=label.outcome_value,
                        metadata={
                            "asset_name": asset.name,
                            "tenant_id": tenant_id,
                            "cutoff": cutoff.isoformat(),
                            "target_name": "patient_response",
                            "prompt_family": "patient_response",
                            "label_status": label.provenance["label_status"],
                            "feature_versions": ["v1"],
                        },
                    )
                )
            train_records, val_records = records, []
            assets_scope = [asset.id for asset in assets]
            label_versions = ["v1"]

        dataset = MLDataset(
            name=name,
            version=version,
            feature_names=feature_names,
            target_name="patient_response",
            train_records=train_records,
            val_records=val_records,
            test_records=[],
            cutoff_date=cutoff,
            feature_versions=["v1"],
            label_versions=label_versions,
            prediction_cutoffs={"training": cutoff, "validation": cutoff, "test": cutoff},
            asset_scope=assets_scope,
            metadata={
                "dataset_family": "prompt_39_patient_response",
                "feature_family": "patient_response",
                "model_family": "patient_response",
                "tenant_scope": tenant_id or "global",
                "temporal_guardrail": "prediction_cutoff_enforced",
                "response_targets": ["patient_response"],
                "test_only": test_only_fixture,
                "test_fixture_scientific_evidence": False,
                "label_status": (
                    "deterministic_test_only_fixture"
                    if test_only_fixture
                    else "unknown_without_patient_level_response_outcomes"
                ),
            },
        )
        return dataset

    def build_safety_dataset(
        self,
        name: str = "safety_v1",
        version: str = "1.0.0",
        cutoff_date: Optional[date] = None,
        tenant_id: Optional[str] = None,
        *,
        test_only_fixture: bool = False,
    ) -> MLDataset:
        """Build a point-in-time safety dataset; synthetic labels are test-only."""
        cutoff = self._resolve_cutoff(cutoff_date, date.today())
        feature_names = [definition.name for definition in self.feature_store.SAFETY_FEATURES]
        records: List[DatasetRecord] = []

        if test_only_fixture:
            labels = LabelGenerator.generate_safety_test_labels(cutoff, tenant_id=tenant_id)
            for index in range(len(labels)):
                entity_id = f"safety_test_{index + 1:02d}"
                feature_values: Dict[str, Optional[float]] = {
                    feature_name: (
                        None
                        if index < 12 and (index + feature_index) % 7 == 0
                        else float(((index + 3) * (feature_index + 5) * 11) % 101)
                    )
                    for feature_index, feature_name in enumerate(feature_names)
                }
                for feature_name in feature_names:
                    self.feature_store.record_feature(
                        FeatureRecord(
                            feature_name=feature_name,
                            value=feature_values[feature_name],
                            unit="test_fixture_value",
                            asset=entity_id,
                            asset_id=entity_id,
                            tenant_id=tenant_id,
                            evidence_references=[f"test-only:{entity_id}:{feature_name}"],
                            observation_date=cutoff,
                            prediction_cutoff=cutoff,
                            feature_version="v1",
                            extraction_method="prompt_40_test_only_fixture",
                            confidence=1.0,
                            provenance={
                                "test_only": True,
                                "scientific_evidence": False,
                                "feature_family": "prompt_40",
                                "prediction_cutoff": cutoff.isoformat(),
                            },
                        )
                    )
                outcome_labels = labels[entity_id.lower()]
                outcome_values = {
                    target: label.outcome_value
                    for target, label in outcome_labels.items()
                }
                records.append(
                    DatasetRecord(
                        entity_id=entity_id,
                        as_of_date=cutoff,
                        features=feature_values,
                        label=outcome_values["grade_ge_3_ae"],
                        metadata={
                            "tenant_id": tenant_id,
                            "cutoff": cutoff.isoformat(),
                            "target_name": "safety",
                            "safety_labels": outcome_values,
                            "safety_label_provenance": {
                                target: label.provenance
                                for target, label in outcome_labels.items()
                            },
                            "test_only": True,
                            "scientific_evidence": False,
                            "label_version": "test-v1",
                        },
                    )
                )
            train_records, val_records = records[:12], records[12:]
            asset_scope = [record.entity_id for record in records]
            label_versions = ["test-v1"]
        else:
            assets = list_fixture_assets()
            labels = LabelGenerator.generate_safety_outcome_labels(
                assets, prediction_cutoff=cutoff, tenant_id=tenant_id
            )
            for asset in assets:
                feature_records = self.feature_store.create_prompt_40_feature_records(
                    asset,
                    observation_date=cutoff,
                    prediction_cutoff=cutoff,
                    feature_version="v1",
                    tenant_id=tenant_id,
                )
                feature_values = {
                    row.feature_name: row.value
                    for row in feature_records
                    if row.observation_date <= cutoff and row.prediction_cutoff <= cutoff
                }
                outcome_labels = {
                    target: labels[f"{asset.id.lower()}:{target}"]
                    for target in LabelGenerator.SAFETY_TARGETS
                }
                outcome_values = {
                    target: label.outcome_value
                    for target, label in outcome_labels.items()
                }
                records.append(
                    DatasetRecord(
                        entity_id=asset.id,
                        as_of_date=cutoff,
                        features={name: feature_values.get(name) for name in feature_names},
                        label=None,
                        metadata={
                            "asset_name": asset.name,
                            "tenant_id": tenant_id,
                            "cutoff": cutoff.isoformat(),
                            "target_name": "safety",
                            "safety_labels": outcome_values,
                            "safety_label_status": "unknown_no_observed_safety_outcome",
                            "feature_versions": ["v1"],
                        },
                    )
                )
            train_records, val_records = records, []
            asset_scope = [asset.id for asset in assets]
            label_versions = ["v1"]

        dataset = MLDataset(
            name=name,
            version=version,
            feature_names=feature_names,
            target_name="safety",
            train_records=train_records,
            val_records=val_records,
            test_records=[],
            cutoff_date=cutoff,
            feature_versions=["v1"],
            label_versions=label_versions,
            prediction_cutoffs={"training": cutoff, "validation": cutoff, "test": cutoff},
            asset_scope=asset_scope,
            metadata={
                "dataset_family": "prompt_40_safety",
                "feature_family": "safety",
                "model_family": "safety",
                "tenant_scope": tenant_id or "global",
                "temporal_guardrail": "prediction_cutoff_enforced",
                "safety_targets": list(LabelGenerator.SAFETY_TARGETS),
                "safety_target_definitions": {
                    "grade_ge_3_ae": "Grade >=3 adverse event",
                    "dlt": "Dose-limiting toxicity",
                    "discontinuation": "Treatment discontinuation",
                    "organ_toxicity": "Organ toxicity",
                    "therapeutic_index_risk": "Therapeutic-index risk",
                },
                "test_only": test_only_fixture,
                "test_fixture_scientific_evidence": False,
                "label_status": (
                    "deterministic_test_only_fixture"
                    if test_only_fixture
                    else "unknown_without_observed_safety_outcomes"
                ),
            },
        )
        return dataset
