from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

MODE_CONFIG = {
    "expert_only": {
        "decision": "expert_only_decision",
        "confidence": "expert_only_confidence",
        "time": "expert_only_time_sec",
        "evidence": "expert_only_evidence_count",
    },
    "ai_only": {
        "decision": "ai_only_decision",
        "confidence": "ai_only_confidence",
        "time": "ai_only_time_sec",
        "evidence": "ai_only_evidence_count",
    },
    "expert_plus_ai": {
        "decision": "expert_plus_ai_decision",
        "confidence": "expert_plus_ai_confidence",
        "time": "expert_plus_ai_time_sec",
        "evidence": "expert_plus_ai_evidence_count",
    },
}


class ExpertBenchmarkError(ValueError):
    """Raised when benchmark records are malformed or incomplete."""


def _coerce_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExpertBenchmarkError(f"{context} must be an object")
    return value


def _safe_float(value: Any, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive validation
        raise ExpertBenchmarkError(f"{context} must be numeric") from exc
    if result != result:
        raise ExpertBenchmarkError(f"{context} must not be NaN")
    return result


def _accuracy(predictions: Sequence[int], labels: Sequence[int]) -> float:
    if not predictions or not labels:
        return 0.0
    return sum(int(pred == label) for pred, label in zip(predictions, labels)) / len(predictions)


def _false_positive_rate(predictions: Sequence[int], labels: Sequence[int]) -> float:
    if not predictions:
        return 0.0
    fp = sum(1 for pred, label in zip(predictions, labels) if pred == 1 and label == 0)
    negative_count = sum(1 for label in labels if label == 0)
    return fp / negative_count if negative_count else 0.0


def _false_negative_rate(predictions: Sequence[int], labels: Sequence[int]) -> float:
    if not predictions:
        return 0.0
    fn = sum(1 for pred, label in zip(predictions, labels) if pred == 0 and label == 1)
    positive_count = sum(1 for label in labels if label == 1)
    return fn / positive_count if positive_count else 0.0


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _summarize_mode(records: Sequence[Mapping[str, Any]], mode: str) -> dict[str, float | int]:
    config = MODE_CONFIG[mode]
    decisions = []
    confidences = []
    times = []
    evidence = []
    labels = []

    for record in records:
        label = int(record["ground_truth"])
        labels.append(label)

        decision_field = config["decision"]
        if decision_field not in record:
            raise ExpertBenchmarkError(f"records are missing {decision_field!r} for mode {mode!r}")
        decision = int(record[decision_field])
        decisions.append(decision)

        if config["confidence"] in record:
            confidences.append(_safe_float(record[config["confidence"]], f"{mode}.confidence"))
        if config["time"] in record:
            times.append(_safe_float(record[config["time"]], f"{mode}.time"))
        if config["evidence"] in record:
            evidence.append(int(record[config["evidence"]]))

    if not labels:
        raise ExpertBenchmarkError(f"No records were provided for benchmark mode {mode!r}")

    return {
        "decision_accuracy": _accuracy(decisions, labels),
        "confidence": _mean(confidences) if confidences else 0.0,
        "avg_time_sec": _mean(times) if times else 0.0,
        "avg_evidence_count": _mean(evidence) if evidence else 0.0,
        "false_positive_rate": _false_positive_rate(decisions, labels),
        "false_negative_rate": _false_negative_rate(decisions, labels),
    }


def evaluate_expert_benchmark(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Evaluate benchmark records comparing expert-only, AI-only, and expert+AI decisions.

    The design is intentionally fail-closed: without a real benchmark dataset, the result is a
    documentation-limited status rather than a claim that AI materially improved expert outcomes.
    """
    if not isinstance(records, Sequence):
        raise ExpertBenchmarkError("records must be a list")

    if not records:
        return {
            "status": "documentation_limited",
            "reason": "No benchmark records were supplied.",
            "metrics": {},
            "comparison": {},
            "material_improvement": False,
        }

    normalized_records: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        record_map = _coerce_mapping(record, f"records[{index}]")
        if "ground_truth" not in record_map:
            raise ExpertBenchmarkError(f"records[{index}].ground_truth is required")

        label = int(record_map["ground_truth"])
        if label not in (0, 1):
            raise ExpertBenchmarkError(f"records[{index}].ground_truth must be 0 or 1")

        normalized_record = {"ground_truth": label}
        for mode, config in MODE_CONFIG.items():
            for field_name in (config["decision"], config["confidence"], config["time"], config["evidence"]):
                if field_name in record_map:
                    normalized_record[field_name] = record_map[field_name]
        normalized_records.append(normalized_record)

    mode_metrics = {mode: _summarize_mode(normalized_records, mode) for mode in MODE_CONFIG.keys()}
    expert = mode_metrics["expert_only"]
    ai = mode_metrics["ai_only"]
    combo = mode_metrics["expert_plus_ai"]

    material_improvement = (
        combo["decision_accuracy"] > expert["decision_accuracy"]
        and combo["false_positive_rate"] <= expert["false_positive_rate"]
        and combo["false_negative_rate"] <= expert["false_negative_rate"]
    )

    status = "ready_for_expert_benchmark"
    if not any(
        mode_metrics[mode]["decision_accuracy"] > 0.0 for mode in MODE_CONFIG.keys()
    ):
        status = "documentation_limited"

    summary = {
        "status": status,
        "objective": "Determine whether AI materially improves expert decision-making without replacing the scientist.",
        "metrics": mode_metrics,
        "comparison": {
            "accuracy_delta_expert_plus_ai_vs_expert_only": combo["decision_accuracy"] - expert["decision_accuracy"],
            "false_positive_delta_expert_plus_ai_vs_expert_only": combo["false_positive_rate"] - expert["false_positive_rate"],
            "false_negative_delta_expert_plus_ai_vs_expert_only": combo["false_negative_rate"] - expert["false_negative_rate"],
            "confidence_delta_expert_plus_ai_vs_expert_only": combo["confidence"] - expert["confidence"],
            "time_delta_expert_plus_ai_vs_expert_only": combo["avg_time_sec"] - expert["avg_time_sec"],
            "evidence_delta_expert_plus_ai_vs_expert_only": combo["avg_evidence_count"] - expert["avg_evidence_count"],
        },
        "material_improvement": material_improvement,
    }

    if summary["comparison"]["accuracy_delta_expert_plus_ai_vs_expert_only"] < 0:
        summary["status"] = "documentation_limited"
        summary["reason"] = "The benchmark does not support a positive performance claim for expert+AI over expert-only decisions."
    return summary
