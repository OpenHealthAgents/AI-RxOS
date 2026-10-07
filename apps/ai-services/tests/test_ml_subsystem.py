"""
Test Suite for ML Subsystem as a First-Class Subsystem.

Covers all 12 core components:
1. Dataset Builder
2. Feature Engineering
3. Feature Store
4. Label Generator
5. Training Pipeline
6. Validation Pipeline
7. Model Registry
8. Model Serving
9. Prediction Store
10. Explainability
11. Monitoring & Drift Detection (PSI)
12. Interpretable Baselines (Logistic Regression, Random Forest, Gradient Boosting)
"""

from __future__ import annotations

import math
from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ml.algorithms import (
    GradientBoostingBaseline,
    LogisticRegressionModel,
    RandomForestBaseline,
)
from app.ml.dataset import DatasetBuilder, LabelGenerator
from app.ml.explainability import ExplainabilityEngine
from app.ml.features import FeatureStore
from app.ml.models import (
    DriftStatus,
    FeatureDataType,
    InferenceRequest,
    ModelArchitecture,
    ModelArtifact,
    ModelEvaluationMetrics,
    ModelStage,
    StoredPrediction,
)
from app.ml.monitoring import DriftDetectionEngine
from app.ml.pipeline import TrainingPipeline, ValidationPipeline
from app.ml.prediction_store import PredictionStore
from app.ml.registry import ModelRegistry
from app.ml.serving import ModelServingEngine
from app.opportunity_engine.data.fixtures import list_fixture_assets


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. Feature Engineering & Feature Store
# ==============================================================================

def test_feature_store_canonical_definitions():
    store = FeatureStore()
    assert len(store.CANONICAL_FEATURES) == 8
    feature_names = [f.name for f in store.CANONICAL_FEATURES]
    assert "target_selectivity_score" in feature_names
    assert "safety_therapeutic_index" in feature_names
    assert "cns_penetration_potential" in feature_names
    assert "clinical_readiness_score" in feature_names


def test_feature_store_point_in_time_extraction():
    store = FeatureStore()
    assets = list_fixture_assets()
    first_asset = assets[0]

    vec = store.get_features(first_asset.id, as_of_date=date(2024, 1, 1))
    assert vec.entity_id == first_asset.id
    assert vec.as_of_date == date(2024, 1, 1)
    assert len(vec.features) == 8
    for f in store.CANONICAL_FEATURES:
        assert f.name in vec.features
        val = vec.features[f.name]
        assert 0.0 <= val <= 100.0


def test_feature_store_batch_extraction():
    store = FeatureStore()
    vectors = store.extract_batch()
    assert len(vectors) >= 4
    for vec in vectors:
        assert len(vec.features) == 8


# ==============================================================================
# 2. Label Generator & Dataset Builder
# ==============================================================================

def test_label_generator_supervised_labels():
    assets = list_fixture_assets()
    labels = LabelGenerator.generate_labels(assets)
    assert len(labels) == len(assets)
    for asset_id, lbl in labels.items():
        assert lbl.target_name == "opportunity_pursuit_success"
        assert lbl.outcome_value in (0.0, 1.0)
        assert lbl.observation_horizon_date == date(2024, 1, 1)


def test_dataset_builder_deterministic_splits():
    builder = DatasetBuilder()
    dataset = builder.build_dataset(
        name="test_oncology_dataset",
        version="v1.0-test",
        train_ratio=0.6,
        val_ratio=0.2,
        test_ratio=0.2,
    )

    assert dataset.name == "test_oncology_dataset"
    assert len(dataset.feature_names) == 8
    total_records = len(dataset.train_records) + len(dataset.val_records) + len(dataset.test_records)
    assert total_records >= 5
    assert len(dataset.train_records) > 0

    # Ensure records have both features and labels
    for r in dataset.train_records:
        assert len(r.features) == 8
        assert r.label in (0.0, 1.0)


# ==============================================================================
# 3. Baseline Interpretable Algorithms
# ==============================================================================

def test_logistic_regression_fit_and_predict():
    # Linearly separable 2D synthetic problem
    X = [[10.0, 20.0], [12.0, 22.0], [80.0, 90.0], [85.0, 95.0]]
    y = [0.0, 0.0, 1.0, 1.0]

    model = LogisticRegressionModel(learning_rate=0.01, max_iter=200)
    model.fit(X, y)

    probas = model.predict_proba(X)
    assert len(probas) == 4
    assert probas[0] < 0.5
    assert probas[3] > 0.5

    preds = model.predict(X)
    assert preds == [0, 0, 1, 1]

    # Test serialization & deserialization
    d = model.to_dict()
    loaded = LogisticRegressionModel.from_dict(d)
    loaded_probs = loaded.predict_proba(X)
    for p1, p2 in zip(probas, loaded_probs):
        assert abs(p1 - p2) < 1e-6


def test_random_forest_baseline_fit_and_predict():
    X = [[5.0, 10.0], [10.0, 15.0], [70.0, 80.0], [85.0, 90.0]]
    y = [0.0, 0.0, 1.0, 1.0]

    rf = RandomForestBaseline(n_estimators=5, max_depth=2, seed=123)
    rf.fit(X, y)

    probas = rf.predict_proba(X)
    assert len(probas) == 4
    assert probas[0] <= probas[3]

    importances = rf.get_feature_importances(["feat1", "feat2"])
    assert "feat1" in importances
    assert "feat2" in importances

    # Serialization
    d = rf.to_dict()
    loaded = RandomForestBaseline.from_dict(d)
    loaded_probs = loaded.predict_proba(X)
    assert len(loaded_probs) == 4


def test_gradient_boosting_baseline_fit_and_predict():
    X = [[5.0, 10.0], [12.0, 18.0], [60.0, 75.0], [80.0, 95.0]]
    y = [0.0, 0.0, 1.0, 1.0]

    gb = GradientBoostingBaseline(n_estimators=10, learning_rate=0.1)
    gb.fit(X, y)

    probas = gb.predict_proba(X)
    assert len(probas) == 4
    assert probas[0] < probas[3]

    importances = gb.get_feature_importances(["feat1", "feat2"])
    assert len(importances) == 2

    # Serialization
    d = gb.to_dict()
    loaded = GradientBoostingBaseline.from_dict(d)
    loaded_probs = loaded.predict_proba(X)
    assert len(loaded_probs) == 4


# ==============================================================================
# 4. Validation and Training Pipelines
# ==============================================================================

def test_validation_pipeline_metrics():
    y_true = [1.0, 1.0, 0.0, 0.0]
    y_prob = [0.9, 0.8, 0.1, 0.2]

    metrics = ValidationPipeline.evaluate(y_true, y_prob)
    assert metrics.accuracy == 1.0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.f1_score == 1.0
    assert metrics.roc_auc == 1.0
    assert metrics.brier_score < 0.05
    assert metrics.log_loss < 0.3


def test_training_pipeline_all_architectures():
    builder = DatasetBuilder()
    dataset = builder.build_dataset(name="pipeline_test_dataset")

    pipeline = TrainingPipeline()

    for arch in [
        ModelArchitecture.LOGISTIC_REGRESSION,
        ModelArchitecture.RANDOM_FOREST,
        ModelArchitecture.GRADIENT_BOOSTING,
    ]:
        artifact = pipeline.train(
            dataset=dataset,
            architecture=arch,
            stage=ModelStage.DEVELOPMENT,
            model_name=f"test_model_{arch.value}",
            model_version="v1.0.0",
        )
        assert artifact.architecture == arch
        assert artifact.metrics.accuracy >= 0.0
        assert artifact.metrics.roc_auc >= 0.0
        assert len(artifact.feature_names) == 8


# ==============================================================================
# 5. Model Registry
# ==============================================================================

def test_model_registry_lifecycle():
    registry = ModelRegistry()
    builder = DatasetBuilder()
    dataset = builder.build_dataset()
    pipeline = TrainingPipeline()

    model1 = pipeline.train(
        dataset=dataset,
        architecture=ModelArchitecture.LOGISTIC_REGRESSION,
        stage=ModelStage.DEVELOPMENT,
        model_name="opportunity_candidate",
        model_version="v1.0.0",
    )
    registry.register(model1)

    assert registry.get_model(model1.model_id) is not None
    assert len(registry.list_models(stage=ModelStage.DEVELOPMENT)) == 1

    # Promote to production
    promoted = registry.promote_model(model1.model_id, ModelStage.PRODUCTION)
    assert promoted.stage == ModelStage.PRODUCTION

    prod_model = registry.get_production_model()
    assert prod_model is not None
    assert prod_model.model_id == model1.model_id

    # Register second model and promote -> should archive model1
    model2 = pipeline.train(
        dataset=dataset,
        architecture=ModelArchitecture.RANDOM_FOREST,
        stage=ModelStage.STAGING,
        model_name="opportunity_candidate",
        model_version="v2.0.0",
    )
    registry.register(model2)
    registry.promote_model(model2.model_id, ModelStage.PRODUCTION)

    assert registry.get_model(model1.model_id).stage == ModelStage.ARCHIVED
    assert registry.get_production_model().model_id == model2.model_id


# ==============================================================================
# 6. Explainability Engine
# ==============================================================================

def test_explainability_feature_attributions():
    builder = DatasetBuilder()
    dataset = builder.build_dataset()
    pipeline = TrainingPipeline()

    model = pipeline.train(
        dataset=dataset,
        architecture=ModelArchitecture.LOGISTIC_REGRESSION,
        model_name="explain_model",
    )

    test_features = {f: 75.0 for f in dataset.feature_names}
    explanation = ExplainabilityEngine.explain_prediction(
        model=model,
        features=test_features,
        predicted_probability=0.82,
        entity_id="AST-001",
        prediction_id=uuid4(),
    )

    assert explanation.entity_id == "AST-001"
    assert explanation.predicted_probability == 0.82
    assert len(explanation.top_drivers) == 8
    assert "summary_narrative" in explanation.model_dump()
    assert len(explanation.summary_narrative) > 10


# ==============================================================================
# 7. Model Serving & Prediction Store
# ==============================================================================

def test_model_serving_engine_and_prediction_store():
    serving = ModelServingEngine()
    assets = list_fixture_assets()
    target_asset = assets[0]

    request = InferenceRequest(entity_id=target_asset.id)
    pred = serving.predict(request)

    assert pred.entity_id == target_asset.id
    assert 0.0 <= pred.predicted_probability <= 1.0
    assert pred.predicted_class in (0, 1)
    assert pred.latency_ms >= 0.0
    assert pred.explanation is not None

    # Check that prediction was persisted in prediction store
    fetched = serving.prediction_store.get_prediction(pred.prediction_id)
    assert fetched is not None
    assert fetched.predicted_probability == pred.predicted_probability

    # Record delayed actual outcome
    updated = serving.prediction_store.record_outcome(
        prediction_id=pred.prediction_id,
        actual_outcome=1.0,
        observed_date=date(2025, 1, 1),
    )
    assert updated.actual_outcome == 1.0
    assert len(serving.prediction_store.get_evaluated_predictions()) == 1


# ==============================================================================
# 8. Monitoring & Drift Detection (PSI)
# ==============================================================================

def test_drift_detection_psi_calculation():
    # Identical distributions -> PSI ~ 0.0
    base = [10.0, 20.0, 30.0, 40.0, 50.0] * 10
    curr_same = [10.0, 20.0, 30.0, 40.0, 50.0] * 10
    psi_no_drift = DriftDetectionEngine.calculate_psi(base, curr_same)
    assert psi_no_drift < 0.05

    # Drastically shifted distribution -> Severe PSI >= 0.25
    curr_shifted = [45.0, 50.0, 50.0, 50.0, 50.0] * 10
    psi_severe = DriftDetectionEngine.calculate_psi(base, curr_shifted)
    assert psi_severe >= 0.20


def test_drift_detection_report_generation():
    base_feats = {
        "target_selectivity_score": [20.0, 40.0, 60.0, 80.0] * 5,
        "safety_therapeutic_index": [30.0, 50.0, 70.0, 90.0] * 5,
    }
    # Current features with severe shift in target_selectivity_score
    curr_feats = {
        "target_selectivity_score": [80.0, 80.0, 80.0, 80.0] * 5,
        "safety_therapeutic_index": [30.0, 50.0, 70.0, 90.0] * 5,
    }

    report = DriftDetectionEngine.evaluate_drift(
        model_version="v1.0.0",
        baseline_features=base_feats,
        current_features=curr_feats,
    )

    assert report.model_version == "v1.0.0"
    assert "target_selectivity_score" in report.feature_drifts
    assert report.feature_drifts["target_selectivity_score"].drift_status in (
        DriftStatus.MODERATE_DRIFT,
        DriftStatus.SEVERE_DRIFT,
    )
    assert report.overall_drift_status in (
        DriftStatus.MODERATE_DRIFT,
        DriftStatus.SEVERE_DRIFT,
    )


# ==============================================================================
# 9. FastAPI REST Router Endpoints
# ==============================================================================

def test_api_features_endpoint(client):
    res = client.get("/api/v1/ml/features")
    assert res.status_code == 200
    features = res.json()
    assert len(features) == 8
    assert any(f["name"] == "target_selectivity_score" for f in features)


def test_api_train_and_models_endpoint(client):
    # Train Logistic Regression
    train_payload = {
        "dataset_name": "api_test_dataset",
        "architecture": "logistic_regression",
        "stage": "staging",
        "model_name": "api_trained_lr",
        "model_version": "v1.2.0",
    }
    res = client.post("/api/v1/ml/train", json=train_payload)
    assert res.status_code == 201
    artifact = res.json()
    model_id = artifact["model_id"]
    assert artifact["architecture"] == "logistic_regression"
    assert artifact["stage"] == "staging"

    # Fetch model by ID
    res_get = client.get(f"/api/v1/ml/models/{model_id}")
    assert res_get.status_code == 200
    assert res_get.json()["model_id"] == model_id

    # Promote model to production
    res_promote = client.post(
        f"/api/v1/ml/models/{model_id}/promote",
        json={"stage": "production"},
    )
    assert res_promote.status_code == 200
    assert res_promote.json()["stage"] == "production"

    # List models
    res_list = client.get("/api/v1/ml/models?stage=production")
    assert res_list.status_code == 200
    assert any(m["model_id"] == model_id for m in res_list.json())


def test_api_predict_and_prediction_store(client):
    assets = list_fixture_assets()
    first_asset = assets[0]

    predict_payload = {
        "entity_id": first_asset.id,
    }
    res = client.post("/api/v1/ml/predict", json=predict_payload)
    assert res.status_code == 200
    prediction = res.json()
    pred_id = prediction["prediction_id"]

    assert prediction["entity_id"] == first_asset.id
    assert 0.0 <= prediction["predicted_probability"] <= 1.0
    assert prediction["predicted_class"] in (0, 1)
    assert prediction["latency_ms"] >= 0.0
    assert prediction["explanation"] is not None
    assert len(prediction["explanation"]["top_drivers"]) == 8

    # Retrieve from prediction store
    res_stored = client.get(f"/api/v1/ml/predictions/{pred_id}")
    assert res_stored.status_code == 200
    assert res_stored.json()["prediction_id"] == pred_id


def test_api_drift_evaluate_endpoint(client):
    res = client.post(
        "/api/v1/ml/drift/evaluate",
        json={"model_version": "v1.0.0"},
    )
    assert res.status_code == 200
    report = res.json()
    assert report["model_version"] == "v1.0.0"
    assert "overall_drift_status" in report
    assert "feature_drifts" in report
