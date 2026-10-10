from __future__ import annotations

import pytest

from app.services.expert_benchmark import ExpertBenchmarkError, evaluate_expert_benchmark


VALID_BENCHMARK = [
    {
        "ground_truth": 1,
        "expert_only_decision": 1,
        "ai_only_decision": 1,
        "expert_plus_ai_decision": 1,
        "expert_only_confidence": 0.72,
        "ai_only_confidence": 0.81,
        "expert_plus_ai_confidence": 0.9,
        "expert_only_time_sec": 28.0,
        "ai_only_time_sec": 12.0,
        "expert_plus_ai_time_sec": 18.0,
        "expert_only_evidence_count": 5,
        "ai_only_evidence_count": 7,
        "expert_plus_ai_evidence_count": 9,
    },
    {
        "ground_truth": 0,
        "expert_only_decision": 0,
        "ai_only_decision": 1,
        "expert_plus_ai_decision": 0,
        "expert_only_confidence": 0.66,
        "ai_only_confidence": 0.58,
        "expert_plus_ai_confidence": 0.78,
        "expert_only_time_sec": 31.0,
        "ai_only_time_sec": 10.0,
        "expert_plus_ai_time_sec": 16.5,
        "expert_only_evidence_count": 4,
        "ai_only_evidence_count": 6,
        "expert_plus_ai_evidence_count": 8,
    },
    {
        "ground_truth": 1,
        "expert_only_decision": 0,
        "ai_only_decision": 1,
        "expert_plus_ai_decision": 1,
        "expert_only_confidence": 0.55,
        "ai_only_confidence": 0.79,
        "expert_plus_ai_confidence": 0.88,
        "expert_only_time_sec": 25.0,
        "ai_only_time_sec": 9.0,
        "expert_plus_ai_time_sec": 15.0,
        "expert_only_evidence_count": 3,
        "ai_only_evidence_count": 7,
        "expert_plus_ai_evidence_count": 9,
    },
    {
        "ground_truth": 0,
        "expert_only_decision": 0,
        "ai_only_decision": 0,
        "expert_plus_ai_decision": 0,
        "expert_only_confidence": 0.71,
        "ai_only_confidence": 0.67,
        "expert_plus_ai_confidence": 0.85,
        "expert_only_time_sec": 30.0,
        "ai_only_time_sec": 8.5,
        "expert_plus_ai_time_sec": 17.0,
        "expert_only_evidence_count": 5,
        "ai_only_evidence_count": 6,
        "expert_plus_ai_evidence_count": 8,
    },
]


def test_evaluate_expert_benchmark_accepts_valid_records():
    report = evaluate_expert_benchmark(VALID_BENCHMARK)
    assert report["status"] == "ready_for_expert_benchmark"
    assert set(report["metrics"]) == {"expert_only", "ai_only", "expert_plus_ai"}
    assert report["comparison"]["accuracy_delta_expert_plus_ai_vs_expert_only"] >= 0


def test_evaluate_expert_benchmark_rejects_missing_ground_truth():
    with pytest.raises(ExpertBenchmarkError, match="ground_truth"):
        evaluate_expert_benchmark([
            {
                "expert_only_decision": 1,
                "ai_only_decision": 1,
                "expert_plus_ai_decision": 1,
            }
        ])


def test_evaluate_expert_benchmark_no_dataset_is_documentation_limited():
    report = evaluate_expert_benchmark([])
    assert report["status"] == "documentation_limited"
    assert "No benchmark records" in report["reason"]


def test_evaluate_expert_benchmark_rejects_invalid_label_values():
    with pytest.raises(ExpertBenchmarkError, match="ground_truth"):
        evaluate_expert_benchmark([
            {"ground_truth": 2, "expert_only_decision": 1, "ai_only_decision": 1, "expert_plus_ai_decision": 1}
        ])
