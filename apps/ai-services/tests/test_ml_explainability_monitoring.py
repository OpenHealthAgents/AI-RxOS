from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from app.main import app
from app.ml.dataset import DatasetBuilder
from app.ml.explainability import ExplainabilityEngine
from app.ml.models import (
    DriftStatus,
    InferenceRequest,
    ModelArchitecture,
    ModelArtifact,
    ModelEvaluationMetrics,
    MonitoringStatus,
    PredictionFailure,
    StoredPrediction,
)
from app.ml.monitoring import DriftDetectionEngine
from app.ml.pipeline import TrainingPipeline
from app.ml.prediction_store import PredictionStore
from app.ml.registry import ModelRegistry
from app.ml.serving import ModelServingEngine
from app.opportunity_engine.data.fixtures import list_fixture_assets
from fastapi.testclient import TestClient


def _tree_model(*, tenant_id: str | None = None, weights: dict | None = None) -> ModelArtifact:
    return ModelArtifact(
        name="tree-model",
        version="tree-v1",
        architecture=ModelArchitecture.RANDOM_FOREST,
        feature_names=["x", "y"],
        coefficients_or_weights=weights or {
            "n_estimators": 1,
            "trees": [{
                "feature_idx": 0,
                "threshold": 5.0,
                "left": {"value": 0.2},
                "right": {
                    "feature_idx": 1,
                    "threshold": 5.0,
                    "left": {"value": 0.9},
                    "right": {"value": 0.4},
                },
            }],
            "feature_importances": {"0": 0.6, "1": 0.4},
        },
        metrics=ModelEvaluationMetrics(
            accuracy=1.0,
            brier_score=0.05,
            roc_auc=0.9,
        ),
        dataset_version="dataset-v3",
        feature_versions=["feature-v4"],
        tenant_id=tenant_id,
        monitoring_reference={
            "feature_distributions": {
                "x": [0.0, 1.0, 2.0, 3.0, 4.0],
                "y": [0.0, 1.0, 2.0, 3.0, 4.0],
            },
            "feature_missing_rates": {"x": 0.0, "y": 0.0},
        },
    )


def _prediction(
    model: ModelArtifact,
    *,
    tenant_id: str | None,
    observed_features: dict | None = None,
    timestamp: datetime | None = None,
    outcome: float | None = None,
    outcome_date: date | None = None,
) -> StoredPrediction:
    values = observed_features or {"x": 9.0, "y": 9.0}
    probability = 0.4
    return StoredPrediction(
        entity_id="asset-1",
        asset_id="asset-1",
        tenant_id=tenant_id,
        model_name=model.name,
        model_id=model.model_id,
        model_version=model.version,
        model_type=model.architecture.value,
        architecture=model.architecture,
        feature_version="feature-v4",
        feature_versions=["feature-v4"],
        input_snapshot={
            "asset_id": "asset-1",
            "feature_version": "feature-v4",
            "feature_values": values,
            "feature_names": model.feature_names,
            "feature_units": {"x": "%", "y": "%"},
            "prediction_cutoff": "2026-10-01",
            "observation_dates": {},
        },
        prediction=0,
        probability=probability,
        predicted_probability=probability,
        confidence=None,
        prediction_cutoff=date(2026, 10, 1),
        prediction_timestamp=timestamp or datetime(2026, 10, 2, tzinfo=timezone.utc),
        features_used={key: float(value) for key, value in values.items()},
        actual_outcome=outcome,
        outcome_observed_date=outcome_date,
        latency_ms=12.0,
    )


def test_tree_explanation_uses_instance_contributions_and_preserves_snapshot_context():
    model = _tree_model()
    snapshot = {
        "asset_id": "asset-1",
        "feature_version": "feature-v4",
        "feature_values": {"x": 9.0, "y": 9.0},
        "observation_dates": {
            "x": {"evidence_references": ["ev-x"], "confidence": 0.9},
            "y": {"evidence_references": ["ev-y"], "confidence": 0.3},
        },
    }
    explanation = ExplainabilityEngine.explain_prediction(
        model=model,
        features=snapshot["feature_values"],
        predicted_probability=0.4,
        entity_id="asset-1",
        prediction_id=uuid4(),
        feature_version="feature-v4",
        input_snapshot=snapshot,
    )
    repeated = ExplainabilityEngine.explain_prediction(
        model=model,
        features=snapshot["feature_values"],
        predicted_probability=0.4,
        entity_id="asset-1",
        prediction_id=explanation.prediction_id,
        feature_version="feature-v4",
        input_snapshot=snapshot,
    )

    assert explanation.explanation_available
    assert explanation.model_name == model.name
    assert explanation.model_version == model.version
    assert explanation.feature_version == "feature-v4"
    assert explanation.input_snapshot == snapshot
    assert explanation.explanation_type == "MODEL_EXPLANATION"
    assert "not scientific evidence" in explanation.evidence_scope
    assert explanation.feature_evidence_references == {"x": ["ev-x"], "y": ["ev-y"]}
    assert explanation.scientific_evidence_citations == []
    assert [item.feature_name for item in explanation.positive_contributors] == ["x"]
    assert [item.feature_name for item in explanation.negative_contributors] == ["y"]
    assert explanation.uncertain_features[0].feature_name == "y"
    assert "scientific evidence" not in explanation.summary_narrative.lower() or "not scientific evidence" in explanation.summary_narrative.lower()
    assert [
        (item.feature_name, item.attribution_score, item.directional_impact)
        for item in explanation.top_drivers
    ] == [
        (item.feature_name, item.attribution_score, item.directional_impact)
        for item in repeated.top_drivers
    ]


def test_explanation_reports_missing_features_and_does_not_assign_them_contributions():
    model = _tree_model()
    explanation = ExplainabilityEngine.explain_prediction(
        model=model,
        features={"x": 8.0},
        predicted_probability=0.8,
        entity_id="asset-1",
        prediction_id=uuid4(),
        feature_version="feature-v4",
        input_snapshot={"feature_values": {"x": 8.0}},
    )

    assert not explanation.explanation_available
    assert explanation.missing_features == ["y"]
    assert explanation.positive_contributors == []
    assert explanation.negative_contributors == []
    assert any(item.feature_name == "y" for item in explanation.uncertain_features)


def test_explanation_does_not_expose_synthetic_feature_evidence_references():
    model = _tree_model()
    explanation = ExplainabilityEngine.explain_prediction(
        model=model,
        features={"x": 8.0, "y": 2.0},
        predicted_probability=0.7,
        entity_id="asset-1",
        prediction_id=uuid4(),
        feature_version="feature-v4",
        input_snapshot={
            "feature_values": {"x": 8.0, "y": 2.0},
            "observation_dates": {
                "x": {
                    "evidence_references": ["evidence-asset-1-feature-v4"],
                    "provenance": {"source_count": 0},
                },
                "y": {"evidence_references": ["ev-real"]},
            },
        },
    )

    assert explanation.feature_evidence_references["x"] == []
    assert explanation.feature_evidence_references["y"] == ["ev-real"]


def test_tree_explanation_is_unavailable_for_artifact_without_tree_structure():
    model = _tree_model(weights={"feature_importances": {"0": 1.0}})
    explanation = ExplainabilityEngine.explain_prediction(
        model=model,
        features={"x": 8.0, "y": 2.0},
        predicted_probability=0.7,
        entity_id="asset-1",
        prediction_id=uuid4(),
        feature_version="feature-v4",
    )

    assert not explanation.explanation_available
    assert "does not contain tree structures" in (explanation.unavailable_reason or "")
    assert explanation.top_drivers == []


def test_gradient_boosting_explanation_uses_instance_stump_contributions():
    model = _tree_model(
        weights={
            "learning_rate": 0.1,
            "base_log_odds": 0.0,
            "stumps": [
                {"feature_idx": 0, "threshold": 5.0, "left_value": -0.5, "right_value": 0.5},
                {"feature_idx": 1, "threshold": 5.0, "left_value": 0.4, "right_value": -0.4},
            ],
            "feature_importances": {"0": 0.5, "1": 0.5},
        }
    ).model_copy(update={"architecture": ModelArchitecture.GRADIENT_BOOSTING})
    explanation = ExplainabilityEngine.explain_prediction(
        model=model,
        features={"x": 9.0, "y": 9.0},
        predicted_probability=0.5,
        entity_id="asset-1",
        prediction_id=uuid4(),
        feature_version="feature-v4",
    )

    assert explanation.explanation_available
    assert [item.feature_name for item in explanation.positive_contributors] == ["x"]
    assert [item.feature_name for item in explanation.negative_contributors] == ["y"]
    assert {item.contribution_unit for item in explanation.top_drivers} == {"log_odds"}


def test_prediction_store_scopes_predictions_and_failures_to_exact_tenant():
    model = _tree_model(tenant_id="tenant-a")
    store = PredictionStore()
    tenant_prediction = _prediction(model, tenant_id="tenant-a")
    store.save_prediction(tenant_prediction)
    store.save_prediction(_prediction(model, tenant_id="tenant-b"))
    store.record_failure(
        PredictionFailure(
            tenant_id="tenant-a",
            asset_id="asset-1",
            model_name=model.name,
            model_version=model.version,
            feature_version="feature-v4",
            error_type="ValueError",
            message="input unavailable",
        )
    )

    assert store.get_prediction(tenant_prediction.prediction_id) is None
    assert store.get_prediction(tenant_prediction.prediction_id, tenant_id="tenant-a") == tenant_prediction
    assert len(store.list_predictions(tenant_id="tenant-a")) == 1
    assert len(store.list_failures(tenant_id="tenant-a")) == 1
    assert store.list_predictions(tenant_id="tenant-c") == []


def test_prediction_failure_is_recorded_with_model_version_and_missing_features():
    model = _tree_model(tenant_id="tenant-a").model_copy(
        update={
            "architecture": ModelArchitecture.LOGISTIC_REGRESSION,
            "coefficients_or_weights": {"weights": [0.2, -0.1]},
            "feature_names": ["x", "y"],
        }
    )
    registry = ModelRegistry()
    registry.register(model)
    store = PredictionStore()
    serving = ModelServingEngine(
        registry=registry,
        prediction_store=store,
    )

    try:
        serving.predict(
            InferenceRequest(
                entity_id="asset-1",
                tenant_id="tenant-a",
                model_version=model.version,
                feature_version="feature-v4",
                features={"x": 1.0},
            )
        )
    except ValueError as error:
        assert "Required features missing" in str(error)
    else:
        raise AssertionError("Missing required features should reject prediction.")

    failures = store.list_failures(tenant_id="tenant-a", model_version=model.version)
    assert len(failures) == 1
    assert failures[0].feature_version == "feature-v4"
    assert failures[0].missing_features == ["y"]


def test_training_captures_internal_reference_without_exposing_raw_distribution():
    dataset = DatasetBuilder().build_dataset(name="monitoring-reference-test")
    model = TrainingPipeline().train(dataset, model_name="monitoring-reference", model_version="ref-v1")

    assert model.monitoring_reference["feature_distributions"]
    assert model.monitoring_reference["sample_count"] > 0
    assert "monitoring_reference" not in model.model_dump()


def test_monitoring_reports_versioned_drift_missingness_alerts_and_prediction_usage():
    model = _tree_model()
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 10, tzinfo=timezone.utc)
    predictions = [
        _prediction(model, tenant_id=None, observed_features={"x": 100.0, "y": 2.0}),
        _prediction(model, tenant_id=None, observed_features={"x": 100.0, "y": 3.0}),
        _prediction(model, tenant_id="tenant-other", observed_features={"x": 100.0, "y": 4.0}),
    ]
    failures = [
        PredictionFailure(
            tenant_id=None,
            asset_id="asset-1",
            model_name=model.name,
            model_version=model.version,
            feature_version="feature-v4",
            error_type="MissingRequiredFeaturesError",
            message="Required feature y missing",
            missing_features=["y"],
        )
    ]

    report = DriftDetectionEngine.evaluate_model(
        model,
        predictions,
        failures,
        window_start=start,
        window_end=end,
        tenant_id=None,
        feature_version="feature-v4",
    )

    assert report.model_version == "tree-v1"
    assert report.feature_versions == ["feature-v4"]
    assert report.dataset_version == "dataset-v3"
    assert report.prediction_count == 2
    assert report.failure_count == 1
    assert report.prediction_class_counts == {"0": 2}
    assert report.mean_latency_ms == 12.0
    assert report.feature_drifts["x"].drift_status in {
        DriftStatus.MODERATE_DRIFT,
        DriftStatus.SEVERE_DRIFT,
    }
    assert report.feature_drifts["y"].current_missing_rate == 1 / 3
    assert any(alert.metric == "feature_psi:x" for alert in report.alerts)
    assert any(alert.metric == "missing_rate_delta:y" for alert in report.alerts)
    assert all(alert.model_version == model.version for alert in report.alerts)
    assert report.status in {MonitoringStatus.DRIFT_DETECTED, MonitoringStatus.WARNING}


def test_monitoring_keeps_performance_unavailable_without_sufficient_observed_outcomes():
    model = _tree_model()
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 10, tzinfo=timezone.utc)
    prediction = _prediction(model, tenant_id=None)
    before = prediction.input_snapshot.copy()

    store = PredictionStore()
    store.save_prediction(prediction)
    store.record_outcome(
        prediction.prediction_id,
        actual_outcome=1.0,
        observed_date=date(2026, 10, 20),
    )
    report = DriftDetectionEngine.evaluate_model(
        model,
        [store.get_prediction(prediction.prediction_id)],
        [ ],
        window_start=start,
        window_end=end,
        tenant_id=None,
        feature_version="feature-v4",
        min_outcomes=1,
    )

    assert store.get_prediction(prediction.prediction_id).input_snapshot == before
    assert report.outcome_count == 0
    assert report.performance_metrics == {}
    assert report.calibration_metrics["production_brier_score"] is None
    assert report.status != MonitoringStatus.DEGRADED


def test_monitoring_measures_performance_and_calibration_only_after_valid_outcomes():
    model = _tree_model()
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 10, tzinfo=timezone.utc)
    predictions = [
        _prediction(
            model,
            tenant_id=None,
            timestamp=datetime(2026, 10, 2, index, tzinfo=timezone.utc),
            outcome=1.0,
            outcome_date=date(2026, 10, 3),
        )
        for index in (1, 2)
    ]

    report = DriftDetectionEngine.evaluate_model(
        model,
        predictions,
        window_start=start,
        window_end=end,
        tenant_id=None,
        feature_version="feature-v4",
        min_outcomes=2,
    )

    assert report.outcome_count == 2
    assert report.performance_metrics["accuracy"] == 0.0
    assert report.calibration_metrics["production_brier_score"] == 0.36
    assert report.status == MonitoringStatus.DEGRADED
    assert any(alert.metric == "accuracy_drop" for alert in report.alerts)
    assert any(alert.metric == "calibration_brier_score_delta" for alert in report.alerts)


def test_explanation_and_monitoring_routes_use_prediction_scope_and_version():
    client = TestClient(app)
    asset = list_fixture_assets()[0]
    prediction_response = client.post(
        "/api/v1/ml/predict",
        json={"entity_id": asset.id, "model_version": "v1.0.0", "model_name": "opportunity_pursuit_logistic_regression"},
    )
    assert prediction_response.status_code == 200
    prediction = prediction_response.json()
    prediction_id = prediction["prediction_id"]

    explanation_response = client.get(
        f"/api/v1/ml/predictions/{prediction_id}/explanation"
    )
    assert explanation_response.status_code == 200
    explanation = explanation_response.json()
    assert explanation["prediction_id"] == prediction_id
    assert explanation["model_version"] == prediction["model_version"]
    assert explanation["feature_version"] == prediction["feature_version"]
    assert explanation["explanation_type"] == "MODEL_EXPLANATION"
    assert explanation["evidence_scope"]

    now = datetime.now(timezone.utc)
    monitoring_response = client.post(
        "/api/v1/ml/monitoring/evaluate",
        json={
            "model_version": prediction["model_version"],
            "feature_version": prediction["feature_version"],
            "window_start": (now - timedelta(days=1)).isoformat(),
            "window_end": (now + timedelta(seconds=1)).isoformat(),
        },
    )
    assert monitoring_response.status_code == 200
    monitoring = monitoring_response.json()
    assert monitoring["model_version"] == prediction["model_version"]
    assert monitoring["feature_versions"] == [prediction["feature_version"]]
    assert monitoring["prediction_count"] >= 1
    report_id = monitoring["report_id"]
    assert client.get(f"/api/v1/ml/monitoring/reports/{report_id}").status_code == 200
    assert client.get(
        f"/api/v1/ml/monitoring/reports/{report_id}?tenant_id=another-tenant"
    ).status_code == 404
    assert client.get(
        f"/api/v1/ml/predictions/{prediction_id}?tenant_id=another-tenant"
    ).status_code == 404


def test_psi_and_legacy_drift_report_mark_missing_comparison_insufficient():
    assert DriftDetectionEngine.calculate_psi([], [1.0]) is None
    report = DriftDetectionEngine.evaluate_drift(
        model_version="tree-v1",
        baseline_features={"x": [1.0, 2.0]},
        current_features={"x": []},
    )
    assert report.feature_drifts["x"].drift_status == DriftStatus.INSUFFICIENT_DATA
    assert report.feature_drifts["x"].psi is None


def test_monitoring_accepts_an_alternative_drift_detector():
    class FixedDriftDetector:
        name = "test_statistic"

        def calculate(self, baseline: list[float], current: list[float]) -> float:
            assert baseline and current
            return 0.3

    model = _tree_model()
    report = DriftDetectionEngine.evaluate_model(
        model,
        [_prediction(model, tenant_id=None)],
        window_start=datetime(2026, 10, 1, tzinfo=timezone.utc),
        window_end=datetime(2026, 10, 10, tzinfo=timezone.utc),
        tenant_id=None,
        feature_version="feature-v4",
        drift_detector=FixedDriftDetector(),
    )

    assert report.feature_drifts["x"].psi == 0.3
    assert any(alert.metric == "feature_test_statistic:x" for alert in report.alerts)
