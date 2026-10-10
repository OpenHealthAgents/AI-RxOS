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
from app.ml.models import FeatureRecord, InferenceRequest, ModelArchitecture, ModelStage
from app.ml.monitoring import DriftDetectionEngine
from app.ml.pipeline import TrainingPipeline, ValidationPipeline
from app.ml.registry import ModelRegistry
from app.ml.serving import ModelServingEngine
from app.opportunity_engine.data.fixtures import list_fixture_assets

SAFETY_TARGETS = {
    "grade_ge_3_ae",
    "dlt",
    "discontinuation",
    "organ_toxicity",
    "therapeutic_index_risk",
}


def _build_and_train(feature_store: FeatureStore, tenant_id: str = "tenant-40"):
    cutoff = date(2024, 7, 1)
    dataset = DatasetBuilder(feature_store).build_safety_dataset(
        cutoff_date=cutoff,
        tenant_id=tenant_id,
        test_only_fixture=True,
    )
    artifact = TrainingPipeline().train(
        dataset=dataset,
        architecture=ModelArchitecture.LOGISTIC_REGRESSION,
        stage=ModelStage.DEVELOPMENT,
        model_name="safety",
        model_version="v1.0.0",
        training_cutoff=cutoff,
        validation_cutoff=cutoff,
        test_cutoff=cutoff,
        random_seed=37,
        selected_labels=sorted(SAFETY_TARGETS),
        tenant_id=tenant_id,
    )
    return dataset, artifact


def test_prompt_40_real_multitarget_training_registry_serving_explanation_monitoring():
    feature_store = FeatureStore()
    dataset, artifact = _build_and_train(feature_store)

    assert dataset.metadata["test_only"] is True
    assert dataset.metadata["test_fixture_scientific_evidence"] is False
    assert set(dataset.metadata["safety_targets"]) == SAFETY_TARGETS
    assert dataset.metadata["safety_target_definitions"]["grade_ge_3_ae"] == "Grade >=3 adverse event"
    assert len(dataset.train_records) == 12
    assert len(dataset.val_records) == 4
    assert any(value is None for row in dataset.train_records for value in row.features.values())
    assert all(value is not None for row in dataset.val_records for value in row.features.values())
    for target_name in SAFETY_TARGETS:
        assert {row.metadata["safety_labels"][target_name] for row in dataset.train_records} == {0.0, 1.0}
        assert {row.metadata["safety_labels"][target_name] for row in dataset.val_records} == {0.0, 1.0}

    feature_records = [
        feature_store.get_feature_record(entity_id, feature_name, "v1", "tenant-40")
        for entity_id in dataset.asset_scope
        for feature_name in dataset.feature_names
    ]
    assert all(record is not None for record in feature_records)
    assert all(
        record.tenant_id == "tenant-40"
        and record.observation_date <= record.prediction_cutoff <= dataset.cutoff_date
        and record.extraction_method == "prompt_40_test_only_fixture"
        and record.provenance["test_only"] is True
        and record.provenance["scientific_evidence"] is False
        for record in feature_records
        if record is not None
    )

    assert artifact.name == "safety"
    assert artifact.fitted_model is not None
    assert set(artifact.fitted_model.target_names) == SAFETY_TARGETS
    assert set(artifact.fitted_model.estimators_) == SAFETY_TARGETS
    assert all(estimator.n_iter_.size > 0 for estimator in artifact.fitted_model.estimators_.values())
    assert artifact.metrics.roc_auc is not None
    assert artifact.metrics.auprc is not None
    assert artifact.metrics.brier_score is not None
    assert artifact.metrics.precision is not None
    assert artifact.metrics.recall is not None
    assert set(artifact.lineage["output_metrics"]) == SAFETY_TARGETS
    assert all(
        metrics["roc_auc"] is not None
        and metrics["auprc"] is not None
        and metrics["brier_score"] is not None
        and metrics["precision"] is not None
        and metrics["recall"] is not None
        and metrics["expected_calibration_error"] is not None
        for metrics in artifact.lineage["output_metrics"].values()
    )
    assert set(artifact.lineage["calibration_metrics"]) == SAFETY_TARGETS

    validation_X = [
        [float(row.features[name]) for name in artifact.feature_names]
        for row in dataset.val_records
    ]
    probabilities = artifact.fitted_model.predict_proba(validation_X)
    for target_name in SAFETY_TARGETS:
        truth = [int(row.metadata["safety_labels"][target_name]) for row in dataset.val_records]
        values = probabilities[target_name]
        metrics = artifact.lineage["output_metrics"][target_name]
        calibration = artifact.lineage["calibration_metrics"][target_name]
        assert metrics["roc_auc"] == pytest.approx(roc_auc_score(truth, values), abs=1e-4)
        assert metrics["auprc"] == pytest.approx(average_precision_score(truth, values), abs=1e-4)
        assert metrics["brier_score"] == pytest.approx(brier_score_loss(truth, values), abs=1e-4)
        assert metrics["precision"] == pytest.approx(
            precision_score(truth, [value >= 0.5 for value in values]), abs=1e-4
        )
        assert metrics["recall"] == pytest.approx(
            recall_score(truth, [value >= 0.5 for value in values]), abs=1e-4
        )
        assert calibration["expected_calibration_error"] == pytest.approx(
            ValidationPipeline.expected_calibration_error(truth, values), abs=1e-4
        )

    registry = ModelRegistry()
    registry.register(artifact)
    retrieved = registry.get_model_by_version("safety", "v1.0.0")
    assert retrieved is artifact
    assert retrieved.fitted_model is artifact.fitted_model

    serving = ModelServingEngine(registry=registry, feature_store=feature_store)
    prediction = serving.predict(
        InferenceRequest(
            entity_id="safety_test_13",
            asset_id="safety_test_13",
            model_name="safety",
            model_version="v1.0.0",
            feature_version="v1",
            prediction_cutoff=dataset.cutoff_date,
            tenant_id="tenant-40",
        )
    )
    assert prediction.outcome_probabilities.keys() == SAFETY_TARGETS
    assert prediction.outcome_predictions.keys() == SAFETY_TARGETS
    assert prediction.probability == pytest.approx(
        prediction.outcome_probabilities["grade_ge_3_ae"], abs=1e-4
    )
    assert all(0.0 <= value <= 1.0 for value in prediction.outcome_probabilities.values())
    assert prediction.confidence is not None
    assert prediction.model_version == "v1.0.0"
    assert prediction.feature_version == "v1"
    assert prediction.prediction_cutoff == dataset.cutoff_date
    assert prediction.prediction_timestamp.tzinfo is not None
    assert prediction.tenant_id == "tenant-40"
    assert prediction.input_snapshot["prediction_cutoff"] == dataset.cutoff_date.isoformat()
    assert prediction.input_snapshot["model_version"] == "v1.0.0"
    assert prediction.input_snapshot["tenant_id"] == "tenant-40"
    assert prediction.explanation is not None
    assert prediction.explanation.explanation_type == "MODEL_EXPLANATION"
    assert prediction.explanation.evidence_scope.startswith("Feature provenance only")
    assert prediction.explanation.explanation_available is True
    assert prediction.explanation.top_drivers
    assert {item.feature_name for item in prediction.explanation.top_drivers}.issubset(
        set(artifact.feature_names)
    )
    assert serving.explain_prediction(str(prediction.prediction_id), tenant_id="tenant-40") is not None

    report = DriftDetectionEngine.evaluate_model(
        retrieved,
        [prediction],
        window_start=prediction.prediction_timestamp - timedelta(seconds=1),
        window_end=prediction.prediction_timestamp + timedelta(seconds=1),
        tenant_id="tenant-40",
        feature_version="v1",
    )
    assert report.model_name == "safety"
    assert report.model_version == "v1.0.0"
    assert report.dataset_version == dataset.version
    assert report.prediction_count == 1


def test_prompt_40_unknown_domain_labels_and_missing_safety_features_are_not_negative():
    cutoff = date(2024, 7, 1)
    assets = list_fixture_assets()
    labels = LabelGenerator.generate_safety_outcome_labels(
        assets, prediction_cutoff=cutoff, tenant_id="tenant-40"
    )
    assert labels
    assert all(label.outcome_value is None for label in labels.values())
    assert all(not label.is_known_at_cutoff for label in labels.values())

    feature_store = FeatureStore()
    dataset = DatasetBuilder(feature_store).build_safety_dataset(
        cutoff_date=cutoff,
        tenant_id="tenant-40",
    )
    assert dataset.metadata["test_only"] is False
    assert all(row.label is None for row in dataset.train_records)
    assert all(
        value is None
        for row in dataset.train_records
        for feature_name, value in row.features.items()
        if feature_name in {
            "ae_rate",
            "dlt",
            "discontinuation",
            "organ_toxicity",
            "therapeutic_index_risk",
            "clinical_response",
            "development_stage",
            "human_evidence",
        }
    )

    asset = assets[0]
    feature = FeatureRecord(
        feature_name="ae_rate",
        value=None,
        asset=asset.id,
        tenant_id="tenant-missing",
        observation_date=cutoff,
        prediction_cutoff=cutoff,
        feature_version="v1",
        extraction_method="observed_missing_safety_evidence",
        confidence=0.0,
        provenance={"missing_values_preserved": True},
    )
    feature_store.record_feature(feature)
    stored = feature_store.get_feature_record(asset.id, "ae_rate", "v1", "tenant-missing")
    assert stored is not None and stored.value is None and stored.is_missing


def test_prompt_40_future_feature_information_is_excluded(monkeypatch):
    cutoff = date(2024, 7, 1)
    feature_store = FeatureStore()
    original = feature_store.create_prompt_40_feature_records

    def future_rows(*args, **kwargs):
        return [
            row.model_copy(
                update={
                    "observation_date": cutoff + timedelta(days=1),
                    "prediction_cutoff": cutoff + timedelta(days=1),
                    "value": 100.0,
                }
            )
            for row in original(*args, **kwargs)
        ]

    monkeypatch.setattr(feature_store, "create_prompt_40_feature_records", future_rows)
    dataset = DatasetBuilder(feature_store).build_safety_dataset(
        cutoff_date=cutoff,
        tenant_id="tenant-40",
    )
    assert all(row.label is None for row in dataset.train_records)
    assert all(all(value is None for value in row.features.values()) for row in dataset.train_records)
    assert all(row.as_of_date == cutoff for row in dataset.train_records)


def test_prompt_40_test_fixture_is_reproducible_and_isolated_by_tenant():
    first_dataset, first_model = _build_and_train(FeatureStore(), tenant_id="tenant-a")
    second_dataset, second_model = _build_and_train(FeatureStore(), tenant_id="tenant-a")
    assert [row.features for row in first_dataset.train_records] == [
        row.features for row in second_dataset.train_records
    ]
    assert [row.metadata["safety_labels"] for row in first_dataset.train_records] == [
        row.metadata["safety_labels"] for row in second_dataset.train_records
    ]
    for target in SAFETY_TARGETS:
        assert first_model.fitted_model.estimators_[target].coef_.tolist() == (
            second_model.fitted_model.estimators_[target].coef_.tolist()
        )
    assert first_model.metrics.model_dump() == second_model.metrics.model_dump()

    registry = ModelRegistry()
    registry.register(first_model)
    serving = ModelServingEngine(registry=registry, feature_store=FeatureStore())
    with pytest.raises(ValueError, match="tenant-visible"):
        serving.predict(
            InferenceRequest(
                entity_id="safety_test_13",
                model_name="safety",
                model_version=first_model.version,
                feature_version="v1",
                prediction_cutoff=first_dataset.cutoff_date,
                tenant_id="tenant-b",
            )
        )


def test_prompt_40_missing_prediction_evidence_is_imputed_with_explicit_uncertainty():
    feature_store = FeatureStore()
    dataset, artifact = _build_and_train(feature_store)
    registry = ModelRegistry()
    registry.register(artifact)
    serving = ModelServingEngine(registry=registry, feature_store=feature_store)

    asset = list_fixture_assets()[0]
    prediction = serving.predict(
        InferenceRequest(
            entity_id=asset.id,
            asset_id=asset.id,
            model_name="safety",
            model_version=artifact.version,
            feature_version="v1",
            prediction_cutoff=dataset.cutoff_date,
            tenant_id="tenant-40",
        )
    )
    assert prediction.uncertainty_reasons
    assert prediction.input_snapshot["missing_features"]
    assert prediction.confidence < 1.0
    assert all(
        prediction.input_snapshot["observed_feature_values"][name] is None
        for name in prediction.input_snapshot["missing_features"]
    )
    assert prediction.explanation is not None
    assert set(prediction.input_snapshot["missing_features"]).issubset(
        set(prediction.explanation.missing_features)
    )
    assert any(
        "median-imputed" in item.reason
        for item in prediction.explanation.uncertain_features
    )
