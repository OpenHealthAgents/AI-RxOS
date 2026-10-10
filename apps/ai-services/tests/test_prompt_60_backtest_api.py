from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ml.models import (
    ModelArchitecture,
    ModelArtifact,
    ModelEvaluationMetrics,
    StoredPrediction,
)
from app.ml.prediction_store import PredictionStore
from app.ml.registry import ModelRegistry
from app.ml.router import get_shared_ml_backtest_services
from app.opportunity_engine import backtest_api
from app.opportunity_engine.core_api import _trusted_tenant_id

client = TestClient(app)
_CUTOFF = date(2020, 1, 1)
_WINDOW_END = date(2021, 1, 1)


def _model(*, tenant_id: str | None = None) -> ModelArtifact:
    return ModelArtifact(
        name="historical-response-model",
        version="1.2.0",
        architecture=ModelArchitecture.LOGISTIC_REGRESSION,
        feature_names=["response_feature"],
        metrics=ModelEvaluationMetrics(),
        dataset_version="dataset-v3",
        feature_versions=["feature-v3"],
        label_versions=["label-v2"],
        training_cutoff=date(2019, 11, 1),
        registered_at=datetime(2019, 12, 1, tzinfo=timezone.utc),
        tenant_id=tenant_id,
        lineage={"target_name": "response_within_12_months"},
    )


def _prediction(
    model: ModelArtifact,
    asset_id: str,
    *,
    tenant_id: str | None = None,
    outcome: float | None = 1.0,
    probability: float = 0.8,
    feature_observation_date: date = date(2019, 12, 20),
    outcome_references: list[str] | None = None,
) -> StoredPrediction:
    return StoredPrediction(
        entity_id=asset_id,
        asset_id=asset_id,
        tenant_id=tenant_id,
        model_name=model.name,
        model_id=model.model_id,
        model_version=model.version,
        feature_version="feature-v3",
        input_snapshot={
            "prediction_cutoff": _CUTOFF.isoformat(),
            "observation_dates": {
                "response_feature": {
                    "observation_date": feature_observation_date.isoformat(),
                    "prediction_cutoff": _CUTOFF.isoformat(),
                    "feature_version": "feature-v3",
                    "evidence_references": ["evidence:feature-1"],
                    "provenance_available": True,
                    "provenance": {"source": "versioned feature store"},
                }
            },
        },
        probability=probability,
        predicted_class=int(probability >= 0.5),
        confidence=0.91,
        prediction_cutoff=_CUTOFF,
        prediction_timestamp=datetime(2020, 1, 1, 12, tzinfo=timezone.utc),
        features_used={"response_feature": 0.7},
        actual_outcome=outcome,
        outcome_observed_date=date(2020, 6, 1) if outcome is not None else None,
        lineage={
            "outcome_target_name": "response_within_12_months",
            "label_version": "label-v2",
            "outcome_evidence_references": outcome_references
            if outcome_references is not None
            else (["evidence:outcome-1"] if outcome is not None else []),
        },
    )


def _install_services(
    monkeypatch: pytest.MonkeyPatch,
    models: list[ModelArtifact] | None = None,
    predictions: list[StoredPrediction] | None = None,
) -> tuple[ModelRegistry, PredictionStore]:
    registry = ModelRegistry()
    store = PredictionStore()
    for model in models or []:
        registry.register(model)
    for prediction in predictions or []:
        store.save_prediction(prediction)
    app.dependency_overrides[get_shared_ml_backtest_services] = lambda: (
        registry,
        store,
    )
    monkeypatch.setattr(backtest_api, "_temporal_engine", backtest_api.TemporalIntelligenceEngine())
    return registry, store


def _custom_assets(monkeypatch: pytest.MonkeyPatch, count: int) -> list[str]:
    assets = [
        SimpleNamespace(id=f"asset-{index:02d}", name=f"Asset {index:02d}")
        for index in range(count)
    ]
    monkeypatch.setattr(backtest_api, "list_fixture_assets", lambda: assets)
    return [asset.id for asset in assets]


def _post(request: dict[str, object]):
    return client.post("/api/backtest", json=request)


def test_endpoint_returns_unknown_when_no_historical_predictions_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backtest_api, "list_fixture_assets", lambda: [
        SimpleNamespace(id="tucatinib", name="Tucatinib")
    ])
    _install_services(monkeypatch)
    try:
        response = _post(
            {
                "asset_ids": ["tucatinib"],
                "cutoff": "2017-01-01",
                "evaluation_window_end": "2019-12-31",
            }
        )
    finally:
        app.dependency_overrides.pop(get_shared_ml_backtest_services, None)
    assert response.status_code == 200, response.text
    result = response.json()
    candidate = result["candidates"][0]
    assert any(
        "fixture-backed" in limitation
        for limitation in result["limitations"]
    )
    assert candidate["prediction"]["status"] == "INSUFFICIENT_HISTORY"
    assert candidate["prediction"]["prediction_type"] == "UNKNOWN"
    assert candidate["prediction"]["predicted_value"] is None
    assert candidate["prediction_outcome"]["status"] == "UNKNOWN"
    assert candidate["observed_outcomes"][0]["epistemic_class"] == "OBSERVED"
    assert candidate["prediction"]["evidence_references"] == []
    assert result["metrics"]["label_count"] == 0
    assert result["ranking"]["status"] == "INSUFFICIENT_HISTORY"


def test_historical_outcomes_respect_evaluation_window_and_preserve_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backtest_api, "list_fixture_assets", lambda: [
        SimpleNamespace(id="tucatinib", name="Tucatinib")
    ])
    _install_services(monkeypatch)
    try:
        response = _post(
            {
                "asset_ids": ["tucatinib"],
                "cutoff": "2018-01-01",
                "evaluation_window_end": "2019-12-31",
            }
        )
    finally:
        app.dependency_overrides.pop(get_shared_ml_backtest_services, None)
    assert response.status_code == 200, response.text
    outcomes = response.json()["candidates"][0]["observed_outcomes"]
    assert outcomes
    assert all(item["publicly_known_date"] <= "2019-12-31" for item in outcomes)
    assert all(item["evidence_references"] for item in outcomes)
    assert not any(item["outcome_type"] == "regulatory_approval" for item in outcomes)


def test_available_prediction_keeps_model_feature_and_outcome_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_ids = _custom_assets(monkeypatch, 1)
    model = _model(tenant_id="tenant-a")
    prediction = _prediction(model, asset_ids[0], tenant_id="tenant-a")
    _install_services(monkeypatch, [model], [prediction])
    app.dependency_overrides[_trusted_tenant_id] = lambda: "tenant-a"
    try:
        response = _post(
            {
                "asset_ids": asset_ids,
                "cutoff": _CUTOFF.isoformat(),
                "evaluation_window_end": _WINDOW_END.isoformat(),
                "model_name": model.name,
                "model_version": model.version,
                "feature_version": "feature-v3",
            }
        )
    finally:
        app.dependency_overrides.pop(get_shared_ml_backtest_services, None)
        app.dependency_overrides.pop(_trusted_tenant_id, None)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["tenant_id"] == "tenant-a"
    candidate = result["candidates"][0]
    assert candidate["prediction"]["status"] == "AVAILABLE"
    assert candidate["prediction"]["model_lineage"]["dataset_version"] == "dataset-v3"
    assert candidate["prediction"]["feature_lineage"][0]["feature_name"] == "response_feature"
    assert candidate["prediction"]["evidence_references"] == ["evidence:feature-1"]
    assert candidate["prediction_outcome"]["status"] == "COMPARABLE"
    assert candidate["prediction_outcome"]["outcome_evidence_references"] == [
        "evidence:outcome-1"
    ]
    assert candidate["sensitivity_analysis"]["analysis_type"] == (
        "HYPOTHETICAL_THRESHOLD_SENSITIVITY"
    )


def test_future_feature_observation_is_rejected_as_historical_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_ids = _custom_assets(monkeypatch, 1)
    model = _model()
    prediction = _prediction(
        model,
        asset_ids[0],
        feature_observation_date=date(2020, 1, 2),
    )
    _install_services(monkeypatch, [model], [prediction])
    try:
        response = _post(
            {
                "asset_ids": asset_ids,
                "cutoff": _CUTOFF.isoformat(),
                "evaluation_window_end": _WINDOW_END.isoformat(),
            }
        )
    finally:
        app.dependency_overrides.pop(get_shared_ml_backtest_services, None)
    assert response.status_code == 200, response.text
    candidate = response.json()["candidates"][0]
    assert candidate["prediction"]["status"] == "INSUFFICIENT_HISTORY"
    assert "post-prediction-cutoff" in " ".join(candidate["prediction"]["unknowns"])
    assert candidate["prediction_outcome"]["status"] == "UNKNOWN"


def test_unreferenced_or_test_only_actual_outcomes_remain_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_ids = _custom_assets(monkeypatch, 2)
    model = _model()
    predictions = [
        _prediction(model, asset_ids[0], outcome_references=[]),
        _prediction(model, asset_ids[1], outcome_references=["test-only:label"]),
    ]
    _install_services(monkeypatch, [model], predictions)
    try:
        response = _post(
            {
                "asset_ids": asset_ids,
                "cutoff": _CUTOFF.isoformat(),
                "evaluation_window_end": _WINDOW_END.isoformat(),
            }
        )
    finally:
        app.dependency_overrides.pop(get_shared_ml_backtest_services, None)
    assert response.status_code == 200, response.text
    candidates = response.json()["candidates"]
    assert all(item["prediction_outcome"]["status"] == "UNKNOWN" for item in candidates)
    assert response.json()["metrics"]["label_count"] == 0


def test_metrics_ranking_and_calibration_require_sufficient_aligned_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_ids = _custom_assets(monkeypatch, 10)
    model = _model()
    predictions = [
        _prediction(
            model,
            asset_id,
            outcome=float(index in {0, 1, 2, 5, 6}),
            probability=0.99 - index * 0.01,
        )
        for index, asset_id in enumerate(asset_ids)
    ]
    _install_services(monkeypatch, [model], predictions)
    app.dependency_overrides[_trusted_tenant_id] = lambda: None
    try:
        response = _post(
            {
                "asset_ids": asset_ids,
                "cutoff": _CUTOFF.isoformat(),
                "evaluation_window_end": _WINDOW_END.isoformat(),
                "top_k": 5,
            }
        )
    finally:
        app.dependency_overrides.pop(get_shared_ml_backtest_services, None)
        app.dependency_overrides.pop(_trusted_tenant_id, None)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["metrics"]["label_status"] == "AVAILABLE"
    assert result["metrics"]["label_count"] == 10
    assert all(metric["status"] == "AVAILABLE" for metric in result["metrics"]["metrics"])
    assert result["ranking"]["status"] == "AVAILABLE"
    assert result["ranking"]["denominator"] == 5
    assert result["ranking"]["numerator"] == 3
    assert result["ranking"]["hit_rate"] == pytest.approx(0.6)
    assert result["enrichment"]["status"] == "AVAILABLE"
    assert result["enrichment"]["enrichment"] == pytest.approx(1.5)
    assert result["calibration"]["status"] == "AVAILABLE"
    assert result["calibration"]["sample_count"] == 10
    assert result["calibration"]["brier_score"] is not None
    assert result["calibration"]["expected_calibration_error"] is not None


def test_same_input_produces_deterministic_ranking_and_sensitivity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_ids = _custom_assets(monkeypatch, 2)
    model = _model()
    predictions = [
        _prediction(model, asset_ids[0], outcome=None, probability=0.8),
        _prediction(model, asset_ids[1], outcome=None, probability=0.4),
    ]
    _install_services(monkeypatch, [model], predictions)
    request = {
        "asset_ids": asset_ids,
        "cutoff": _CUTOFF.isoformat(),
        "evaluation_window_end": _WINDOW_END.isoformat(),
        "top_k": 2,
        "decision_threshold": 0.7,
    }
    try:
        first = _post(request)
        second = _post(request)
    finally:
        app.dependency_overrides.pop(get_shared_ml_backtest_services, None)
    assert first.status_code == second.status_code == 200
    assert first.json()["ranking"] == second.json()["ranking"]
    assert first.json()["candidates"] == second.json()["candidates"]
    assert first.json()["candidates"][0]["sensitivity_analysis"]["hypothetical_class"] == 1


def test_tenant_scope_excludes_other_tenant_predictions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_ids = _custom_assets(monkeypatch, 1)
    model = _model(tenant_id="tenant-a")
    predictions = [
        _prediction(model, asset_ids[0], tenant_id="tenant-a"),
        _prediction(model, asset_ids[0], tenant_id="tenant-b", probability=0.99),
    ]
    _install_services(monkeypatch, [model], predictions)
    app.dependency_overrides[_trusted_tenant_id] = lambda: "tenant-a"
    try:
        response = _post(
            {
                "asset_ids": asset_ids,
                "cutoff": _CUTOFF.isoformat(),
                "evaluation_window_end": _WINDOW_END.isoformat(),
            }
        )
    finally:
        app.dependency_overrides.pop(get_shared_ml_backtest_services, None)
        app.dependency_overrides.pop(_trusted_tenant_id, None)
    assert response.status_code == 200, response.text
    assert response.json()["tenant_id"] == "tenant-a"
    assert response.json()["candidates"][0]["prediction"]["predicted_value"] == 0.8


@pytest.mark.parametrize(
    ("model_updates", "prediction_updates"),
    [
        (
            {"registered_at": datetime(2020, 1, 2, tzinfo=timezone.utc)},
            {},
        ),
        ({"training_cutoff": date(2020, 1, 2)}, {}),
        (
            {},
            {"prediction_timestamp": datetime(2020, 1, 2, tzinfo=timezone.utc)},
        ),
    ],
)
def test_model_and_prediction_must_exist_by_the_historical_cutoff(
    monkeypatch: pytest.MonkeyPatch,
    model_updates: dict[str, object],
    prediction_updates: dict[str, object],
) -> None:
    asset_ids = _custom_assets(monkeypatch, 1)
    model = _model().model_copy(update=model_updates)
    prediction = _prediction(model, asset_ids[0]).model_copy(
        update=prediction_updates
    )
    _install_services(monkeypatch, [model], [prediction])
    try:
        response = _post(
            {
                "asset_ids": asset_ids,
                "cutoff": _CUTOFF.isoformat(),
                "evaluation_window_end": _WINDOW_END.isoformat(),
            }
        )
    finally:
        app.dependency_overrides.pop(get_shared_ml_backtest_services, None)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["candidates"][0]["prediction"]["status"] == "INSUFFICIENT_HISTORY"
    assert result["metrics"]["label_count"] == 0


def test_ranking_metrics_are_withheld_for_incomplete_prediction_cohort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_ids = _custom_assets(monkeypatch, 2)
    model = _model()
    prediction = _prediction(model, asset_ids[0], outcome=1.0)
    _install_services(monkeypatch, [model], [prediction])
    try:
        response = _post(
            {
                "asset_ids": asset_ids,
                "cutoff": _CUTOFF.isoformat(),
                "evaluation_window_end": _WINDOW_END.isoformat(),
            }
        )
    finally:
        app.dependency_overrides.pop(get_shared_ml_backtest_services, None)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["ranking"]["status"] == "INSUFFICIENT_HISTORY"
    assert result["ranking"]["hit_rate"] is None
    assert result["enrichment"]["status"] == "INSUFFICIENT_DATA"


@pytest.mark.parametrize(
    "payload",
    [
        {"asset_ids": [], "cutoff": "2020-01-01"},
        {"asset_ids": ["zongertinib", "ZONGERTINIB"], "cutoff": "2020-01-01"},
        {"asset_ids": ["invalid@asset"], "cutoff": "2020-01-01"},
        {"asset_ids": ["zongertinib"], "cutoff": "2099-01-01"},
        {"asset_ids": ["zongertinib"], "cutoff": "2020-01-01", "unsupported": True},
        {
            "asset_ids": ["zongertinib"],
            "cutoff": "2020-01-01",
            "feature_version": "feature-v3",
        },
    ],
)
def test_malformed_or_unsupported_backtest_requests_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
) -> None:
    _install_services(monkeypatch)
    try:
        response = _post(payload)
    finally:
        app.dependency_overrides.pop(get_shared_ml_backtest_services, None)
    assert response.status_code == 422


def test_unknown_asset_is_not_silently_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_services(monkeypatch)
    try:
        response = _post(
            {"asset_ids": ["unknown-asset"], "cutoff": "2020-01-01"}
        )
    finally:
        app.dependency_overrides.pop(get_shared_ml_backtest_services, None)
    assert response.status_code == 404
    assert "unknown-asset" in response.text
