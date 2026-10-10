from __future__ import annotations

from datetime import date, timedelta

import pytest
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

from app.ml.dataset import DatasetBuilder, LabelGenerator
from app.ml.features import FeatureStore
from app.ml.models import (
    FeatureRecord,
    InferenceRequest,
    ModelArchitecture,
    ModelStage,
)
from app.ml.monitoring import DriftDetectionEngine
from app.ml.pipeline import TrainingPipeline
from app.ml.registry import ModelRegistry
from app.ml.serving import MissingRequiredFeaturesError, ModelServingEngine
from app.opportunity_engine.data.fixtures import list_fixture_assets


EXPECTED_FEATURES = {
    "mutation",
    "expression",
    "amplification",
    "biomarker",
    "subtype",
    "prior_treatment",
    "line_of_therapy",
    "resistance",
    "CNS",
    "mechanism",
}


def _train_prompt_39(feature_store: FeatureStore, tenant_id: str = "tenant-39"):
    cutoff = date(2024, 6, 1)
    dataset = DatasetBuilder(feature_store).build_patient_response_dataset(
        cutoff_date=cutoff,
        tenant_id=tenant_id,
        test_only_fixture=True,
    )
    artifact = TrainingPipeline().train(
        dataset=dataset,
        architecture=ModelArchitecture.LOGISTIC_REGRESSION,
        stage=ModelStage.DEVELOPMENT,
        model_name="patient_response",
        model_version="v1.0.0",
        training_cutoff=cutoff,
        validation_cutoff=cutoff,
        test_cutoff=cutoff,
        random_seed=19,
        tenant_id=tenant_id,
    )
    return dataset, artifact


def test_prompt_39_real_training_registration_serving_explanation_and_monitoring():
    feature_store = FeatureStore()
    dataset, artifact = _train_prompt_39(feature_store)

    assert dataset.metadata["test_only"] is True
    assert dataset.metadata["test_fixture_scientific_evidence"] is False
    assert set(dataset.feature_names) == EXPECTED_FEATURES
    assert len(dataset.train_records) == 12
    assert len(dataset.val_records) == 4
    assert {row.label for row in dataset.train_records} == {0.0, 1.0}
    assert {row.label for row in dataset.val_records} == {0.0, 1.0}
    assert any(value is None for row in dataset.train_records for value in row.features.values())
    assert all(value is not None for row in dataset.val_records for value in row.features.values())
    assert all(row.as_of_date == dataset.cutoff_date for row in dataset.train_records + dataset.val_records)
    feature_records = [
        feature_store.get_feature_record(entity_id, feature_name, "v1", "tenant-39")
        for entity_id in dataset.asset_scope
        for feature_name in EXPECTED_FEATURES
    ]
    assert all(record is not None for record in feature_records)
    assert all(
        record.prediction_cutoff <= dataset.cutoff_date
        and record.observation_date <= record.prediction_cutoff
        and record.tenant_id == "tenant-39"
        and record.feature_name in EXPECTED_FEATURES
        and record.provenance["test_only"] is True
        for record in feature_records
        if record is not None
    )

    assert artifact.name == "patient_response"
    assert artifact.fitted_model is not None
    assert hasattr(artifact.fitted_model, "predict_proba")
    assert list(artifact.fitted_model.classes_) == [0.0, 1.0]
    assert artifact.fitted_model.n_iter_.size > 0
    assert artifact.metrics.roc_auc is not None
    assert artifact.metrics.auprc is not None
    assert artifact.metrics.brier_score is not None
    assert artifact.metrics.precision is not None
    assert artifact.metrics.recall is not None
    assert artifact.lineage["dataset_metadata"]["test_only"] is True

    validation_X = [
        [float(row.features[name]) for name in artifact.feature_names]
        for row in dataset.val_records
    ]
    validation_y = [int(row.label) for row in dataset.val_records]
    validation_probabilities = artifact.fitted_model.predict_proba(validation_X)[:, 1]
    assert artifact.metrics.roc_auc == pytest.approx(roc_auc_score(validation_y, validation_probabilities), abs=1e-4)
    assert artifact.metrics.auprc == pytest.approx(
        average_precision_score(validation_y, validation_probabilities), abs=1e-4
    )
    assert artifact.metrics.brier_score == pytest.approx(
        brier_score_loss(validation_y, validation_probabilities), abs=1e-4
    )
    assert artifact.metrics.precision == pytest.approx(
        precision_score(validation_y, validation_probabilities >= 0.5), abs=1e-4
    )
    assert artifact.metrics.recall == pytest.approx(
        recall_score(validation_y, validation_probabilities >= 0.5), abs=1e-4
    )

    registry = ModelRegistry()
    registry.register(artifact)
    retrieved = registry.get_model_by_version("patient_response", "v1.0.0")
    assert retrieved is artifact
    assert retrieved.fitted_model is artifact.fitted_model

    serving = ModelServingEngine(registry=registry, feature_store=feature_store)
    request = InferenceRequest(
        entity_id="patient_response_test_13",
        asset_id="patient_response_test_13",
        model_name="patient_response",
        model_version="v1.0.0",
        feature_version="v1",
        prediction_cutoff=dataset.cutoff_date,
        tenant_id="tenant-39",
    )
    prediction = serving.predict(request)

    assert prediction.patient_segment in {"likely_responder", "unlikely_responder"}
    assert 0.0 <= prediction.probability <= 1.0
    assert prediction.confidence is not None
    assert prediction.model_version == "v1.0.0"
    assert prediction.feature_version == "v1"
    assert prediction.prediction_cutoff == dataset.cutoff_date
    assert prediction.prediction_timestamp.tzinfo is not None
    assert prediction.tenant_id == "tenant-39"
    assert prediction.input_snapshot["feature_names"] == artifact.feature_names
    assert prediction.input_snapshot["prediction_cutoff"] == dataset.cutoff_date.isoformat()
    assert set(prediction.input_snapshot["observation_dates"]) == EXPECTED_FEATURES
    assert all(
        item["feature_version"] == "v1"
        and item["extraction_method"] == "prompt_39_test_only_fixture"
        and item["evidence_references"]
        and item["provenance"]["test_only"] is True
        for item in prediction.input_snapshot["observation_dates"].values()
    )
    assert prediction.explanation is not None
    assert prediction.explanation.explanation_available is True
    assert {item.feature_name for item in prediction.explanation.top_drivers} == EXPECTED_FEATURES
    assert all(item.contribution_unit == "log_odds" for item in prediction.explanation.top_drivers)
    assert serving.explain_prediction(str(prediction.prediction_id), tenant_id="tenant-39") is not None

    report = DriftDetectionEngine.evaluate_model(
        retrieved,
        [prediction],
        window_start=prediction.prediction_timestamp - timedelta(seconds=1),
        window_end=prediction.prediction_timestamp + timedelta(seconds=1),
        tenant_id="tenant-39",
        feature_version="v1",
    )
    assert report.model_name == "patient_response"
    assert report.model_version == "v1.0.0"
    assert report.dataset_version == dataset.version
    assert report.prediction_count == 1


def test_prompt_39_fixture_training_is_reproducible_and_metrics_are_evaluated():
    first_dataset, first_artifact = _train_prompt_39(FeatureStore())
    second_dataset, second_artifact = _train_prompt_39(FeatureStore())

    assert [row.features for row in first_dataset.train_records] == [
        row.features for row in second_dataset.train_records
    ]
    assert [row.label for row in first_dataset.val_records] == [
        row.label for row in second_dataset.val_records
    ]
    assert first_artifact.fitted_model.coef_.tolist() == second_artifact.fitted_model.coef_.tolist()
    assert first_artifact.metrics.model_dump() == second_artifact.metrics.model_dump()


def test_prompt_39_domain_labels_and_missing_features_remain_unknown():
    cutoff = date(2024, 6, 1)
    labels = LabelGenerator.generate_patient_response_labels(
        list_fixture_assets(),
        prediction_cutoff=cutoff,
        tenant_id="tenant-39",
    )
    assert labels
    assert all(label.outcome_value is None for label in labels.values())
    assert all(label.is_known_at_cutoff is False for label in labels.values())

    feature_store = FeatureStore()
    historical = DatasetBuilder(feature_store).build_patient_response_dataset(
        cutoff_date=cutoff,
        tenant_id="tenant-39",
    )
    assert historical.train_records
    assert all(row.label is None for row in historical.train_records)

    asset = list_fixture_assets()[0]
    missing = FeatureRecord(
        feature_name="mutation",
        value=None,
        asset=asset.id,
        tenant_id="tenant-missing",
        observation_date=cutoff,
        prediction_cutoff=cutoff,
        feature_version="v1",
        extraction_method="observed_missing_value",
        confidence=0.0,
        provenance={"missing_values_preserved": True},
    )
    feature_store.record_feature(missing)
    stored = feature_store.get_feature_record(asset.id, "mutation", "v1", "tenant-missing")
    assert stored is not None
    assert stored.value is None
    assert stored.is_missing is True


def test_prompt_39_future_feature_rows_are_excluded_from_historical_dataset(monkeypatch):
    cutoff = date(2024, 6, 1)
    feature_store = FeatureStore()
    original = feature_store.create_prompt_39_feature_records

    def future_only(*args, **kwargs):
        return [
            row.model_copy(
                update={
                    "observation_date": cutoff + timedelta(days=1),
                    "prediction_cutoff": cutoff + timedelta(days=1),
                }
            )
            for row in original(*args, **kwargs)
        ]

    monkeypatch.setattr(feature_store, "create_prompt_39_feature_records", future_only)
    dataset = DatasetBuilder(feature_store).build_patient_response_dataset(
        cutoff_date=cutoff,
        tenant_id="tenant-39",
    )

    assert dataset.train_records
    assert all(row.label is None for row in dataset.train_records)
    assert all(all(value is None for value in row.features.values()) for row in dataset.train_records)
    assert all(row.as_of_date == cutoff for row in dataset.train_records)


def test_prompt_39_tenant_isolation_and_missing_prediction_rejection():
    feature_store = FeatureStore()
    dataset, artifact = _train_prompt_39(feature_store)
    registry = ModelRegistry()
    registry.register(artifact)
    serving = ModelServingEngine(registry=registry, feature_store=feature_store)

    request = InferenceRequest(
        entity_id="patient_response_test_13",
        model_name="patient_response",
        model_version="v1.0.0",
        feature_version="v1",
        prediction_cutoff=dataset.cutoff_date,
        tenant_id="other-tenant",
    )
    with pytest.raises(ValueError, match="tenant-visible"):
        serving.predict(request)

    successful = serving.predict(
        InferenceRequest(
            entity_id="patient_response_test_13",
            model_name="patient_response",
            model_version="v1.0.0",
            feature_version="v1",
            prediction_cutoff=dataset.cutoff_date,
            tenant_id="tenant-39",
        )
    )
    incomplete = {name: 1.0 for name in artifact.feature_names}
    incomplete["mutation"] = None
    bad_request = InferenceRequest(
        entity_id="patient_response_test_13",
        features=incomplete,
        model_name="patient_response",
        model_version="v1.0.0",
        feature_version="v1",
        prediction_cutoff=dataset.cutoff_date,
        tenant_id="tenant-39",
    )
    with pytest.raises(MissingRequiredFeaturesError, match="mutation"):
        serving.predict(bad_request)
    assert serving.prediction_store.get_prediction(
        str(successful.prediction_id),
        tenant_id="other-tenant",
    ) is None
