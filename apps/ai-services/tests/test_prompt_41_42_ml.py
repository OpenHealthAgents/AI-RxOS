from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.ml.dataset import DatasetBuilder, LabelGenerator
from app.ml.features import FeatureStore
from app.ml.models import FeatureRecord
from app.ml.registry import ModelRegistry
from app.opportunity_engine.cns.engine import CNSIntelligenceEngine
from app.opportunity_engine.cns.models import CNSEvidenceLevel, CNSParameterType
from app.opportunity_engine.data.fixtures import list_fixture_assets
from app.opportunity_engine.resistance.engine import ResistanceIntelligenceEngine

PREDICTION_CUTOFF = date(2024, 1, 1)
DATASET_CUTOFF = date(2025, 1, 1)


def _feature(
    *,
    asset_id: str,
    feature_name: str,
    value: float | None,
    observation_date: date,
    prediction_cutoff: date,
    tenant_id: str,
    provenance: dict | None = None,
) -> FeatureRecord:
    return FeatureRecord(
        feature_name=feature_name,
        value=value,
        unit="test fixture only",
        asset=asset_id,
        tenant_id=tenant_id,
        evidence_references=[f"test-only:{asset_id}:{feature_name}"],
        observation_date=observation_date,
        prediction_cutoff=prediction_cutoff,
        feature_version="v1",
        extraction_method="prompt_41_42_test_fixture",
        confidence=1.0,
        provenance=provenance
        or {"test_only": True, "scientific_evidence": False, "test_fixture": True},
    )


def test_cns_dataset_refuses_undated_outcomes_and_distinguishes_evidence_types():
    store = FeatureStore()
    dataset = DatasetBuilder(store).build_cns_dataset(
        cutoff_date=DATASET_CUTOFF,
        prediction_cutoff=PREDICTION_CUTOFF,
        tenant_id="cns-tenant",
    )

    engine_observations = CNSIntelligenceEngine().get_raw_observations_for_asset("tucatinib")
    clinical_outcomes = [
        observation
        for observation in engine_observations
        if observation.parameter_type
        in {
            CNSParameterType.INTRACRANIAL_RESPONSE,
            CNSParameterType.CNS_PROGRESSION,
            CNSParameterType.BRAIN_METASTASIS_RESPONSE,
        }
        and observation.evidence_level == CNSEvidenceLevel.CLINICAL_CNS_EVIDENCE
    ]
    assert clinical_outcomes
    assert all(observation.observation_date is None for observation in clinical_outcomes)
    assert dataset.metadata["training_available"] is False
    assert dataset.metadata["model_status"] == "development_unavailable"
    assert dataset.metadata["undated_raw_clinical_outcomes_excluded"] is True
    assert dataset.metadata["labelled_rows"] == 0
    assert dataset.metadata["synthetic_data_used"] is False
    assert dataset.target_name == "cns_clinical_efficacy"
    assert all(record.label is None for record in dataset.train_records)
    assert dataset.metadata["undated_raw_observation_count"] > 0
    assert all(record.metadata["measured_cns_evidence"] == {} for record in dataset.train_records)
    assert all(record.metadata["predicted_cns_potential"] == {} for record in dataset.train_records)
    tucatinib = next(row for row in dataset.train_records if row.entity_id == "tucatinib")
    assert tucatinib.metadata["cns_evidence_state"] == "undated_measured"
    assert tucatinib.metadata["undated_cns_evidence_excluded"]
    assert any(
        row["parameter_type"] == CNSParameterType.INTRACRANIAL_RESPONSE.value
        and row["time_admissible"] is False
        for row in tucatinib.metadata["undated_cns_evidence_excluded"]
    )
    assert all(
        record.metadata["cns_evidence_state"] in {"undated_measured", "unknown"}
        for record in dataset.train_records
    )

    unknown_labels = LabelGenerator.generate_cns_labels(
        list_fixture_assets(),
        prediction_cutoff=PREDICTION_CUTOFF,
        tenant_id="cns-tenant",
    )
    assert unknown_labels
    assert all(label.outcome_value is None for label in unknown_labels.values())
    assert all(not label.is_known_at_cutoff for label in unknown_labels.values())
    assert all(not label.evidence_references for label in unknown_labels.values())


def test_cns_dataset_uses_only_tenant_scoped_features_available_at_cutoff():
    store = FeatureStore()
    asset_id = list_fixture_assets()[0].id
    store.record_feature(
        _feature(
            asset_id=asset_id,
            feature_name="kp_uu",
            value=0.42,
            observation_date=PREDICTION_CUTOFF - timedelta(days=5),
            prediction_cutoff=PREDICTION_CUTOFF,
            tenant_id="tenant-a",
        )
    )
    store.record_feature(
        _feature(
            asset_id=asset_id,
            feature_name="kp_uu",
            value=99.0,
            observation_date=PREDICTION_CUTOFF + timedelta(days=1),
            prediction_cutoff=PREDICTION_CUTOFF + timedelta(days=1),
            tenant_id="tenant-a",
        )
    )
    store.record_feature(
        _feature(
            asset_id=asset_id,
            feature_name="kp_uu",
            value=0.91,
            observation_date=PREDICTION_CUTOFF,
            prediction_cutoff=PREDICTION_CUTOFF,
            tenant_id="tenant-b",
        )
    )

    dataset = DatasetBuilder(store).build_cns_dataset(
        cutoff_date=DATASET_CUTOFF,
        prediction_cutoff=PREDICTION_CUTOFF,
        tenant_id="tenant-a",
    )
    record = next(row for row in dataset.train_records if row.entity_id == asset_id)
    assert record.features["kp_uu"] is None
    assert "kp_uu" not in record.metadata["feature_provenance"]
    tenant_a_records = store.list_feature_versions(asset_id, "kp_uu", "tenant-a")
    tenant_b_records = store.list_feature_versions(asset_id, "kp_uu", "tenant-b")
    assert {row.value for row in tenant_a_records} == {0.42, 99.0}
    assert [row.value for row in tenant_b_records] == [0.91]
    assert record.label is None
    assert dataset.metadata["training_available"] is False


def test_cns_predicted_potential_is_not_used_as_measured_efficacy_or_model_input():
    store = FeatureStore()
    asset_id = list_fixture_assets()[0].id
    store.record_feature(
        _feature(
            asset_id=asset_id,
            feature_name="cns_penetration_potential",
            value=80.0,
            observation_date=PREDICTION_CUTOFF,
            prediction_cutoff=PREDICTION_CUTOFF,
            tenant_id="tenant-cns",
        )
    )
    store.record_feature(
        _feature(
            asset_id=asset_id,
            feature_name="kp_uu",
            value=0.37,
            observation_date=PREDICTION_CUTOFF,
            prediction_cutoff=PREDICTION_CUTOFF,
            tenant_id="tenant-cns",
            provenance={
                "evidence_kind": "measured",
                "test_only": True,
                "scientific_evidence": False,
            },
        )
    )

    dataset = DatasetBuilder(store).build_cns_dataset(
        cutoff_date=DATASET_CUTOFF,
        prediction_cutoff=PREDICTION_CUTOFF,
        tenant_id="tenant-cns",
    )
    record = next(row for row in dataset.train_records if row.entity_id == asset_id)
    assert "cns_penetration_potential" not in dataset.feature_names
    assert record.features["kp_uu"] is None
    assert record.metadata["measured_cns_evidence"] == {}
    assert record.metadata["predicted_cns_potential"] == {}
    assert record.metadata["cns_evidence_state"] == "undated_measured"
    assert record.label is None


def test_resistance_dataset_keeps_mechanisms_and_labels_unknown_without_dated_outcomes():
    store = FeatureStore()
    dataset = DatasetBuilder(store).build_resistance_dataset(
        cutoff_date=DATASET_CUTOFF,
        prediction_cutoff=PREDICTION_CUTOFF,
        tenant_id="resistance-tenant",
    )

    profile = ResistanceIntelligenceEngine().list_benchmark_profiles()[0]
    assert profile.top_escape_mechanisms
    assert dataset.metadata["training_available"] is False
    assert dataset.metadata["model_status"] == "development_unavailable"
    assert dataset.metadata["undated_canonical_resistance_profiles_excluded"] is True
    assert "observation_date" not in type(profile.top_escape_mechanisms[0]).model_fields
    assert dataset.metadata["synthetic_data_used"] is False
    assert set(dataset.metadata["resistance_targets"]) == set(LabelGenerator.RESISTANCE_TARGETS)
    assert dataset.metadata["target_training_status"] == {
        target: False for target in LabelGenerator.RESISTANCE_TARGETS
    }
    assert all(record.label is None for record in dataset.train_records)
    assert all(
        all(value is None for value in record.metadata["resistance_labels"].values())
        and len(record.metadata["unknown_targets"]) == len(LabelGenerator.RESISTANCE_TARGETS)
        for record in dataset.train_records
    )
    assert dataset.metadata["undated_canonical_mechanism_count"] > 0
    assert all(
        evidence["time_admissible"] is False
        for record in dataset.train_records
        for evidence in record.metadata["undated_canonical_resistance_evidence"]
    )

    labels = LabelGenerator.generate_resistance_labels(
        list_fixture_assets(),
        prediction_cutoff=PREDICTION_CUTOFF,
        tenant_id="resistance-tenant",
    )
    assert labels
    assert all(
        label.outcome_value is None
        for target_labels in labels.values()
        for label in target_labels.values()
    )
    assert all(
        not label.is_known_at_cutoff
        for target_labels in labels.values()
        for label in target_labels.values()
    )


def test_resistance_features_respect_tenant_and_point_in_time_and_reject_test_labels():
    store = FeatureStore()
    asset_id = list_fixture_assets()[0].id
    store.record_feature(
        _feature(
            asset_id=asset_id,
            feature_name="mutation_evidence",
            value=2.0,
            observation_date=PREDICTION_CUTOFF,
            prediction_cutoff=PREDICTION_CUTOFF,
            tenant_id="tenant-a",
        )
    )
    store.record_feature(
        _feature(
            asset_id=asset_id,
            feature_name="mutation_evidence",
            value=99.0,
            observation_date=PREDICTION_CUTOFF,
            prediction_cutoff=PREDICTION_CUTOFF + timedelta(days=1),
            tenant_id="tenant-a",
        )
    )
    store.record_feature(
        _feature(
            asset_id=asset_id,
            feature_name="mutation_evidence",
            value=7.0,
            observation_date=PREDICTION_CUTOFF,
            prediction_cutoff=PREDICTION_CUTOFF,
            tenant_id="tenant-b",
        )
    )
    store.record_feature(
        _feature(
            asset_id=asset_id,
            feature_name="mutation_evidence",
            value=101.0,
            observation_date=PREDICTION_CUTOFF,
            prediction_cutoff=PREDICTION_CUTOFF,
            tenant_id="tenant-a",
            provenance={"test_only": True, "scientific_evidence": False},
        )
    )
    store.record_feature(
        _feature(
            asset_id=asset_id,
            feature_name="label_resistance_target_mutation",
            value=1.0,
            observation_date=DATASET_CUTOFF,
            prediction_cutoff=DATASET_CUTOFF,
            tenant_id="tenant-a",
            provenance={
                "record_type": "observed_outcome_label",
                "target_name": "resistance_target_mutation",
                "test_only": True,
                "scientific_evidence": False,
            },
        )
    )

    dataset = DatasetBuilder(store).build_resistance_dataset(
        cutoff_date=DATASET_CUTOFF,
        prediction_cutoff=PREDICTION_CUTOFF,
        tenant_id="tenant-a",
    )
    record = next(row for row in dataset.train_records if row.entity_id == asset_id)
    assert record.features["mutation_evidence"] is None
    assert "mutation_evidence" not in record.metadata["feature_provenance"]
    assert record.metadata["resistance_labels"]["target_mutation"] is None
    assert dataset.metadata["training_available"] is False
    assert dataset.label_versions == []


@pytest.mark.parametrize(
    "builder_name",
    ["build_cns_dataset", "build_resistance_dataset"],
)
def test_temporal_dataset_cutoff_cannot_precede_prediction_cutoff(builder_name):
    builder = DatasetBuilder(FeatureStore())
    with pytest.raises(ValueError, match="prediction cutoff cannot be later"):
        getattr(builder, builder_name)(
            cutoff_date=PREDICTION_CUTOFF,
            prediction_cutoff=DATASET_CUTOFF,
        )


def test_unavailable_models_are_not_registered_or_served():
    registry = ModelRegistry()
    assert registry.get_production_model() is None
    assert registry.get_model_by_version("cns", "unavailable") is None
    assert registry.get_model_by_version("resistance", "unavailable") is None
