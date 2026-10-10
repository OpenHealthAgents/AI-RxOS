from __future__ import annotations

from datetime import date

from app.ml.dataset import DatasetBuilder, LabelGenerator
from app.ml.features import FeatureStore
from app.ml.models import InferenceRequest, ModelArchitecture, ModelStage
from app.ml.pipeline import TrainingPipeline
from app.ml.registry import ModelRegistry
from app.ml.serving import ModelServingEngine
from app.opportunity_engine.data.fixtures import list_fixture_assets


def test_prompt_39_patient_response_dataset_and_training_lifecycle():
    builder = DatasetBuilder(feature_store=FeatureStore())
    cutoff = date(2024, 6, 1)
    dataset = builder.build_patient_response_dataset(
        cutoff_date=cutoff,
        tenant_id="tenant-39",
        test_only_fixture=True,
    )

    assert dataset.name == "patient_response_v1"
    assert dataset.target_name == "patient_response"
    assert dataset.cutoff_date == cutoff
    assert dataset.feature_versions == ["v1"]
    assert dataset.label_versions == ["test-v1"]
    assert len(dataset.train_records) > 0
    assert any(record.features.get(feature) is None for record in dataset.train_records for feature in dataset.feature_names)

    labels = LabelGenerator.generate_patient_response_labels(list_fixture_assets(), prediction_cutoff=cutoff, tenant_id="tenant-39")
    assert all(label.outcome_value is None for label in labels.values())

    pipeline = TrainingPipeline()
    artifact = pipeline.train(
        dataset=dataset,
        architecture=ModelArchitecture.LOGISTIC_REGRESSION,
        stage=ModelStage.DEVELOPMENT,
        model_name="patient_response",
        model_version="v1.0.0",
        training_cutoff=cutoff,
        validation_cutoff=cutoff,
        test_cutoff=cutoff,
        tenant_id="tenant-39",
    )

    assert artifact.name == "patient_response"
    assert artifact.version == "v1.0.0"
    assert artifact.fitted_model is not None
    assert artifact.metrics.roc_auc is not None
    assert artifact.metrics.auprc is not None
    assert artifact.metrics.brier_score is not None
    assert artifact.metrics.precision is not None
    assert artifact.metrics.recall is not None

    registry = ModelRegistry()
    registry.register(artifact)
    retrieved = registry.get_model_by_version("patient_response", "v1.0.0")
    assert retrieved is not None
    assert retrieved.model_id == artifact.model_id

    serving = ModelServingEngine(registry=registry, feature_store=FeatureStore())
    request = InferenceRequest(
        entity_id=list_fixture_assets()[0].id,
        asset_id=list_fixture_assets()[0].id,
        model_name="patient_response",
        model_version="v1.0.0",
        feature_version="v1",
        prediction_cutoff=cutoff,
        tenant_id="tenant-39",
    )
    prediction = serving.predict(request)
    assert prediction.model_name == "patient_response"
    assert prediction.model_version == "v1.0.0"
    assert isinstance(prediction.probability, float)
    assert 0.0 <= prediction.probability <= 1.0
    assert prediction.input_snapshot["prediction_cutoff"] == cutoff.isoformat()
    assert prediction.tenant_id == "tenant-39"


def test_prompt_40_safety_dataset_and_training_lifecycle():
    feature_store = FeatureStore()
    builder = DatasetBuilder(feature_store=feature_store)
    cutoff = date(2024, 7, 1)
    dataset = builder.build_safety_dataset(
        cutoff_date=cutoff,
        tenant_id="tenant-40",
        test_only_fixture=True,
    )

    assert dataset.name == "safety_v1"
    assert dataset.target_name == "safety"
    assert dataset.cutoff_date == cutoff
    assert dataset.feature_versions == ["v1"]
    assert dataset.label_versions == ["test-v1"]
    assert len(dataset.train_records) > 0
    assert any(record.features.get(feature) is None for record in dataset.train_records for feature in dataset.feature_names)

    labels = LabelGenerator.generate_safety_labels(list_fixture_assets(), prediction_cutoff=cutoff, tenant_id="tenant-40")
    assert labels
    assert all(label.outcome_value is None for label in labels.values())

    pipeline = TrainingPipeline()
    artifact = pipeline.train(
        dataset=dataset,
        architecture=ModelArchitecture.LOGISTIC_REGRESSION,
        stage=ModelStage.DEVELOPMENT,
        model_name="safety",
        model_version="v1.0.0",
        training_cutoff=cutoff,
        validation_cutoff=cutoff,
        test_cutoff=cutoff,
        tenant_id="tenant-40",
    )

    assert artifact.name == "safety"
    assert artifact.version == "v1.0.0"
    assert artifact.fitted_model is not None
    assert artifact.metrics.roc_auc is not None
    assert artifact.metrics.auprc is not None
    assert artifact.metrics.brier_score is not None
    assert artifact.metrics.precision is not None
    assert artifact.metrics.recall is not None

    registry = ModelRegistry()
    registry.register(artifact)
    retrieved = registry.get_model_by_version("safety", "v1.0.0")
    assert retrieved is not None
    assert retrieved.model_id == artifact.model_id

    serving = ModelServingEngine(registry=registry, feature_store=feature_store)
    request = InferenceRequest(
        entity_id="safety_test_13",
        asset_id="safety_test_13",
        model_name="safety",
        model_version="v1.0.0",
        feature_version="v1",
        prediction_cutoff=cutoff,
        tenant_id="tenant-40",
    )
    prediction = serving.predict(request)
    assert prediction.model_name == "safety"
    assert prediction.model_version == "v1.0.0"
    assert prediction.outcome_probabilities
    assert isinstance(prediction.probability, float)
    assert 0.0 <= prediction.probability <= 1.0
    assert prediction.input_snapshot["prediction_cutoff"] == cutoff.isoformat()
    assert prediction.tenant_id == "tenant-40"
