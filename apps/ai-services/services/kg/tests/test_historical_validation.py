from __future__ import annotations

import pytest

from app.services.historical_validation import HistoricalValidationError, evaluate_historical_validation


VALID_HISTORY = [
    {"asset_id": "A-001", "label": 1, "score": 0.92, "winner": True, "biomarker_population": "HER2+"},
    {"asset_id": "A-002", "label": 1, "score": 0.85, "winner": True, "biomarker_population": "HER2+"},
    {"asset_id": "A-003", "label": 0, "score": 0.32, "failure_avoided": True, "predicted_resistance": False},
    {"asset_id": "A-004", "label": 0, "score": 0.28, "failure_avoided": True, "predicted_resistance": False},
    {"asset_id": "A-005", "label": 1, "score": 0.78, "successful_asset_ranked_high": True, "competitive_differentiation": True},
    {"asset_id": "A-006", "label": 0, "score": 0.41, "predicted_resistance": True},
]


def test_evaluate_historical_validation_accepts_valid_retrospective_dataset():
    report = evaluate_historical_validation(VALID_HISTORY)
    assert report["status"] == "ready_for_historical_validation"
    assert report["metrics"]["auroc"] > 0.5
    assert report["metrics"]["precision"] >= 0.0
    assert len(report["visual_report"]["charts"]) >= 3


def test_evaluate_historical_validation_rejects_invalid_scores():
    with pytest.raises(HistoricalValidationError, match="score"):
        evaluate_historical_validation([
            {"asset_id": "A-001", "label": 1, "score": "not-a-number"},
            {"asset_id": "A-002", "label": 0, "score": 0.2},
        ])


def test_evaluate_historical_validation_returns_documentation_limited_for_unbalanced_or_missing_data():
    report = evaluate_historical_validation([
        {"asset_id": "A-001", "label": 1, "score": 0.8},
        {"asset_id": "A-002", "label": 1, "score": 0.7},
    ])
    assert report["status"] == "documentation_limited"
    assert "both positive and negative" in report["reason"]


def test_evaluate_historical_validation_metrics_are_bounded():
    report = evaluate_historical_validation(VALID_HISTORY)
    for metric_name in ("auroc", "auprc", "precision", "recall", "sensitivity", "specificity", "brier_score"):
        assert 0.0 <= report["metrics"][metric_name] <= 1.0
