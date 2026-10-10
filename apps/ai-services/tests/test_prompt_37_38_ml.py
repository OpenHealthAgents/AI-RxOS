from __future__ import annotations

from datetime import date

from app.ml.dataset import DatasetBuilder, LabelGenerator
from app.ml.features import FeatureStore
from app.ml.models import FeatureRecord
from app.opportunity_engine.data.fixtures import list_fixture_assets


def _first_asset_id() -> str:
    return list_fixture_assets()[0].id.lower()


def _observed_label(
    asset_id: str,
    target_name: str,
    value: float,
    *,
    tenant_id: str,
    observation_date: date,
    prediction_cutoff: date,
    record_type: str = "observed_outcome_label",
    test_only: bool = False,
) -> FeatureRecord:
    return FeatureRecord(
        feature_name=f"label_{target_name}",
        value=value,
        asset=asset_id,
        asset_id=asset_id,
        tenant_id=tenant_id,
        evidence_references=["verified-outcome-evidence"],
        observation_date=observation_date,
        prediction_cutoff=prediction_cutoff,
        feature_version="observed-v1",
        provenance={
            "target_name": target_name,
            "record_type": record_type,
            "test_only": test_only,
        },
    )


def test_prompt_37_translational_features_preserve_missingness_and_versioned_cutoff():
    store = FeatureStore()
    asset = list_fixture_assets()[0]
    cutoff = date(2024, 3, 1)
    records = store.create_prompt_37_feature_records(
        asset,
        observation_date=date(2024, 2, 1),
        prediction_cutoff=cutoff,
        feature_version="v1",
        tenant_id="tenant-37",
    )

    names = {r.feature_name for r in records}
    assert {"potency", "selectivity", "mechanistic_evidence", "genetic_evidence", "functional_evidence", "model_diversity", "pdx_efficacy", "organoid_efficacy", "biomarker_strength", "human_evidence"}.issubset(names)
    missing = [r.feature_name for r in records if r.value is None]
    assert "functional_evidence" in missing
    assert "pdx_efficacy" in missing
    assert "organoid_efficacy" in missing
    assert "human_evidence" in missing
    for record in records:
        assert record.tenant_id == "tenant-37"
        assert record.prediction_cutoff == cutoff
        assert record.feature_version == "v1"


def test_prompt_37_translational_dataset_and_labels_are_time_safe():
    builder = DatasetBuilder(feature_store=FeatureStore())
    cutoff = date(2024, 4, 1)
    dataset = builder.build_translational_dataset(cutoff_date=cutoff, tenant_id="tenant-37")
    assert dataset.target_name == "translational_potential"
    assert dataset.feature_versions == ["v1"]
    assert dataset.label_versions == []
    assert dataset.cutoff_date == cutoff
    assert all(record.label is None for record in dataset.train_records)
    assert dataset.metadata["training_available"] is False
    assert dataset.metadata["synthetic_data_used"] is False
    assert all(
        record.metadata["label_status"] == "unknown_without_observed_translational_outcome"
        for record in dataset.train_records
    )

    asset_key = _first_asset_id()
    labels = LabelGenerator.generate_translational_labels(list_fixture_assets(), prediction_cutoff=cutoff, tenant_id="tenant-37")
    assert f"{asset_key}:translational_potential" in labels
    assert labels[f"{asset_key}:translational_potential"].tenant_id == "tenant-37"


def test_prompt_37_uses_only_observed_temporal_and_tenant_scoped_outcomes():
    feature_store = FeatureStore()
    builder = DatasetBuilder(feature_store=feature_store)
    asset_id = list_fixture_assets()[0].id
    prediction_cutoff = date(2024, 1, 1)
    dataset_cutoff = date(2024, 6, 1)
    feature_store.record_feature(
        _observed_label(
            asset_id,
            "translational_potential",
            1.0,
            tenant_id="tenant-37",
            observation_date=date(2024, 3, 1),
            prediction_cutoff=prediction_cutoff,
        )
    )
    feature_store.record_feature(
        _observed_label(
            asset_id,
            "translational_potential",
            0.0,
            tenant_id="tenant-other",
            observation_date=date(2024, 3, 1),
            prediction_cutoff=prediction_cutoff,
        )
    )
    feature_store.record_feature(
        _observed_label(
            asset_id,
            "translational_potential",
            0.0,
            tenant_id="tenant-37",
            observation_date=date(2024, 7, 1),
            prediction_cutoff=prediction_cutoff,
        )
    )
    feature_store.record_feature(
        _observed_label(
            asset_id,
            "translational_potential",
            0.0,
            tenant_id="tenant-37",
            observation_date=date(2024, 3, 1),
            prediction_cutoff=prediction_cutoff,
            record_type="derived_score",
        )
    )

    dataset = builder.build_translational_dataset(
        cutoff_date=dataset_cutoff,
        prediction_cutoff=prediction_cutoff,
        tenant_id="tenant-37",
    )
    record = next(row for row in dataset.train_records if row.entity_id == asset_id)
    assert record.label == 1.0
    assert record.metadata["label_provenance"]["tenant_id"] == "tenant-37"
    assert record.metadata["feature_cutoff"] == prediction_cutoff.isoformat()


def test_prompt_38_clinical_success_preserves_unknowns_and_all_observed_targets():
    builder = DatasetBuilder(feature_store=FeatureStore())
    cutoff = date(2024, 5, 1)
    dataset = builder.build_clinical_success_dataset(cutoff_date=cutoff, tenant_id="tenant-38")
    assert dataset.target_name == "phase_II_success"
    assert dataset.feature_versions == ["v1"]
    assert dataset.label_versions == []
    assert dataset.cutoff_date == cutoff
    assert dataset.metadata["training_available"] is False
    assert dataset.metadata["synthetic_data_used"] is False
    assert dataset.metadata["clinical_targets"] == [
        "phase_II_success",
        "phase_III_success",
        "regulatory_success",
        "failure_probability",
    ]
    assert all(row.label is None for row in dataset.train_records)
    assert all(
        all(value is None for value in row.metadata["clinical_labels"].values())
        for row in dataset.train_records
    )

    asset_key = _first_asset_id()
    labels = LabelGenerator.generate_clinical_success_labels(list_fixture_assets(), prediction_cutoff=cutoff, tenant_id="tenant-38")
    assert f"{asset_key}:phase_II_success" in labels
    assert labels[f"{asset_key}:phase_II_success"].prediction_cutoff == cutoff
    assert labels[f"{asset_key}:phase_II_success"].tenant_id == "tenant-38"

    phase_ii_values = {label.outcome_value for label in labels.values() if label.target_name == "phase_II_success"}
    assert phase_ii_values == {None}


def test_prompt_38_records_each_observed_clinical_endpoint_without_stage_labels():
    feature_store = FeatureStore()
    builder = DatasetBuilder(feature_store=feature_store)
    asset_id = list_fixture_assets()[0].id
    prediction_cutoff = date(2023, 1, 1)
    dataset_cutoff = date(2024, 1, 1)
    outcomes = {
        "phase_II_success": 1.0,
        "phase_III_success": 0.0,
        "regulatory_success": 1.0,
        "failure_probability": 0.0,
    }
    for target, value in outcomes.items():
        feature_store.record_feature(
            _observed_label(
                asset_id,
                target,
                value,
                tenant_id="tenant-38",
                observation_date=date(2023, 8, 1),
                prediction_cutoff=prediction_cutoff,
            )
        )

    dataset = builder.build_clinical_success_dataset(
        cutoff_date=dataset_cutoff,
        prediction_cutoff=prediction_cutoff,
        tenant_id="tenant-38",
    )
    record = next(row for row in dataset.train_records if row.entity_id == asset_id)
    assert record.label == 1.0
    assert record.metadata["clinical_labels"] == outcomes
    assert dataset.metadata["target_training_status"]["phase_II_success"]["labelled_rows"] == 1
    assert dataset.metadata["target_training_status"]["phase_II_success"]["training_available"] is False
