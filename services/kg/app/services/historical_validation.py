from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import ceil
from typing import Any

REQUIRED_RECORD_FIELDS = ("asset_id", "label", "score")
DEFAULT_THRESHOLD = 0.5


class HistoricalValidationError(ValueError):
    """Raised when a historical validation dataset is malformed or incomplete."""


def _coerce_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HistoricalValidationError(f"{context} must be an object")
    return value


def _safe_float(value: Any, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive validation
        raise HistoricalValidationError(f"{context} must be numeric") from exc
    if result != result:
        raise HistoricalValidationError(f"{context} must not be NaN")
    return result


def _average_ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks: list[float] = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i + 1
        while j < len(indexed) and indexed[j][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[indexed[k][0]] = avg_rank
        i = j
    return ranks


def _compute_auroc(scores: Sequence[float], labels: Sequence[int]) -> float:
    positives = [scores[i] for i, label in enumerate(labels) if label == 1]
    negatives = [scores[i] for i, label in enumerate(labels) if label == 0]
    if not positives or not negatives:
        return 0.5

    all_scores = list(scores)
    ranks = _average_ranks(all_scores)
    pos_rank_sum = sum(ranks[i] for i, label in enumerate(labels) if label == 1)
    n_pos = len(positives)
    n_neg = len(negatives)
    auc = (pos_rank_sum - (n_pos * (n_pos + 1) / 2.0)) / (n_pos * n_neg)
    return min(max(auc, 0.0), 1.0)


def _compute_auprc(scores: Sequence[float], labels: Sequence[int]) -> float:
    positives = sum(labels)
    if positives == 0:
        return 0.0

    ranked = sorted(zip(scores, labels), key=lambda item: item[0], reverse=True)
    tp = 0
    fp = 0
    precision_sum = 0.0
    recall_prev = 0.0
    for score, label in ranked:
        if label == 1:
            tp += 1
        else:
            fp += 1
        precision = tp / (tp + fp)
        recall = tp / positives
        if recall > recall_prev:
            precision_sum += precision * (recall - recall_prev)
            recall_prev = recall
    return precision_sum


def _compute_brier_score(scores: Sequence[float], labels: Sequence[int]) -> float:
    return sum((score - label) ** 2 for score, label in zip(scores, labels)) / len(scores)


def _compute_calibration(scores: Sequence[float], labels: Sequence[int], bins: int = 10) -> tuple[float, list[dict[str, float | int]]]:
    bins_data: list[dict[str, float | int]] = []
    ece = 0.0
    total = len(scores)
    for idx in range(bins):
        lower = idx / bins
        upper = (idx + 1) / bins
        bucket = [
            (score, label)
            for score, label in zip(scores, labels)
            if lower <= score < upper or (idx == bins - 1 and lower <= score <= upper)
        ]
        if not bucket:
            continue
        avg_pred = sum(score for score, _ in bucket) / len(bucket)
        avg_true = sum(label for _, label in bucket) / len(bucket)
        ece += (len(bucket) / total) * abs(avg_pred - avg_true)
        bins_data.append({
            "start": lower,
            "end": upper,
            "avg_predicted": avg_pred,
            "avg_observed": avg_true,
            "count": len(bucket),
        })
    return ece, bins_data


def _compute_top_k_enrichment(scores: Sequence[float], labels: Sequence[int], k: int) -> float:
    if not scores:
        return 0.0
    n = len(scores)
    top_k = sorted(range(n), key=lambda idx: scores[idx], reverse=True)[:k]
    if not top_k:
        return 0.0
    selected_positive_rate = sum(labels[idx] for idx in top_k) / len(top_k)
    baseline = sum(labels) / n
    if baseline == 0:
        return 0.0
    return selected_positive_rate / baseline


def _compute_metrics(scores: Sequence[float], labels: Sequence[int], threshold: float = DEFAULT_THRESHOLD) -> dict[str, Any]:
    n = len(scores)
    if n == 0:
        raise HistoricalValidationError("Historical validation requires at least one asset record")

    pos_total = sum(labels)
    neg_total = n - pos_total
    if pos_total == 0 or neg_total == 0:
        raise HistoricalValidationError("Historical validation requires both positive and negative outcomes to compute classification metrics")

    tp = sum(1 for score, label in zip(scores, labels) if score >= threshold and label == 1)
    fp = sum(1 for score, label in zip(scores, labels) if score >= threshold and label == 0)
    tn = sum(1 for score, label in zip(scores, labels) if score < threshold and label == 0)
    fn = sum(1 for score, label in zip(scores, labels) if score < threshold and label == 1)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    sensitivity = recall
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    auroc = _compute_auroc(scores, labels)
    auprc = _compute_auprc(scores, labels)
    brier = _compute_brier_score(scores, labels)
    ece, calibration_bins = _compute_calibration(scores, labels)
    top_10 = _compute_top_k_enrichment(scores, labels, min(10, n))
    top_10_pct = _compute_top_k_enrichment(scores, labels, max(1, ceil(n * 0.10)))

    return {
        "n_records": n,
        "positive_records": pos_total,
        "negative_records": neg_total,
        "threshold": threshold,
        "auroc": auroc,
        "auprc": auprc,
        "precision": precision,
        "recall": recall,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "brier_score": brier,
        "calibration_error": ece,
        "top_10_enrichment": top_10,
        "top_10_percent_enrichment": top_10_pct,
        "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "calibration_bins": calibration_bins,
    }


def _record_matches_question(record: Mapping[str, Any], question: str) -> bool:
    if question == "identified_winners":
        return bool(record.get("winner"))
    if question == "avoided_failures":
        return bool(record.get("failure_avoided"))
    if question == "ranked_successful_assets_highly":
        return bool(record.get("successful_asset_ranked_high"))
    if question == "identified_biomarker_populations":
        return bool(record.get("biomarker_population"))
    if question == "predicted_resistance":
        return bool(record.get("predicted_resistance"))
    if question == "identified_competitive_differentiation":
        return bool(record.get("competitive_differentiation"))
    return False


def _build_visual_report(metrics: Mapping[str, Any]) -> dict[str, Any]:
    roc_points = [
        {"x": 0.0, "y": 0.0},
        {"x": 1.0, "y": 1.0},
    ]
    pr_points = [
        {"x": 0.0, "y": 1.0},
        {"x": 1.0, "y": metrics["auprc"]},
    ]
    calibration_points = [
        {"x": bin_data["avg_predicted"], "y": bin_data["avg_observed"]}
        for bin_data in metrics["calibration_bins"]
    ]
    return {
        "charts": [
            {
                "name": "roc_curve",
                "type": "line",
                "x_label": "False positive rate",
                "y_label": "True positive rate",
                "points": roc_points,
            },
            {
                "name": "precision_recall_curve",
                "type": "line",
                "x_label": "Recall",
                "y_label": "Precision",
                "points": pr_points,
            },
            {
                "name": "calibration_curve",
                "type": "scatter",
                "x_label": "Predicted probability",
                "y_label": "Observed rate",
                "points": calibration_points,
            },
            {
                "name": "top_k_enrichment",
                "type": "bar",
                "series": {
                    "Top 10": metrics["top_10_enrichment"],
                    "Top 10%": metrics["top_10_percent_enrichment"],
                },
            },
        ]
    }


def evaluate_historical_validation(
    records: Sequence[Mapping[str, Any]],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Evaluate historical validation records without assuming a hidden production dataset.

    The function is intentionally fail-closed: if a dataset does not contain both positive
    and negative labels with valid scores, it returns a documentation-limited status instead
    of making unsupported claims.
    """
    if not isinstance(records, Sequence):
        raise HistoricalValidationError("records must be a list")

    normalized_records: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        record_map = _coerce_mapping(record, f"records[{index}]")
        for field_name in REQUIRED_RECORD_FIELDS:
            if field_name not in record_map or record_map.get(field_name) is None:
                raise HistoricalValidationError(f"records[{index}].{field_name} is required")

        asset_id = str(record_map["asset_id"]).strip()
        if not asset_id:
            raise HistoricalValidationError(f"records[{index}].asset_id cannot be blank")

        label_value = record_map["label"]
        if isinstance(label_value, bool):
            label_int = int(label_value)
        else:
            label_int = int(label_value)
        if label_int not in (0, 1):
            raise HistoricalValidationError(f"records[{index}].label must be 0 or 1")

        score_value = _safe_float(record_map["score"], f"records[{index}].score")
        if not 0.0 <= score_value <= 1.0:
            raise HistoricalValidationError(f"records[{index}].score must be between 0 and 1")

        normalized_record = {
            "asset_id": asset_id,
            "label": label_int,
            "score": score_value,
        }
        for key, value in record_map.items():
            if key not in {"asset_id", "label", "score"}:
                normalized_record[key] = value
        normalized_records.append(normalized_record)

    if not normalized_records:
        return {
            "status": "documentation_limited",
            "reason": "No historical validation records were supplied.",
            "metrics": {},
            "visual_report": {"charts": []},
            "assessment": {},
        }

    labels = [int(item["label"]) for item in normalized_records]
    scores = [float(item["score"]) for item in normalized_records]
    try:
        metrics = _compute_metrics(scores, labels, threshold=threshold)
    except HistoricalValidationError:
        return {
            "status": "documentation_limited",
            "reason": "Historical validation requires both positive and negative outcomes to compute a meaningful report.",
            "metrics": {},
            "visual_report": {"charts": []},
            "assessment": {},
        }

    questions = (
        "identified_winners",
        "avoided_failures",
        "ranked_successful_assets_highly",
        "identified_biomarker_populations",
        "predicted_resistance",
        "identified_competitive_differentiation",
    )
    assessment = {}
    for question in questions:
        question_matches = [
            _record_matches_question(record, question)
            for record in normalized_records
        ]
        assessment[question] = bool(question_matches and any(question_matches))

    summary = {
        "status": "ready_for_historical_validation",
        "threshold": threshold,
        "metrics": metrics,
        "assessment": assessment,
        "visual_report": _build_visual_report(metrics),
        "questionnaire": {
            "identified_winners": "Did the model separate historically successful assets from failures?",
            "avoided_failures": "Did the model keep failure-prone assets below the decision threshold?",
            "ranked_successful_assets_highly": "Did successful programs appear in the top ranks?",
            "identified_biomarker_populations": "Was the model able to isolate biomarker-enriched subgroups?",
            "predicted_resistance": "Did the model forecast resistance patterns before they emerged?",
            "identified_competitive_differentiation": "Did the model separate competitive advantage from commodity programs?",
        },
    }

    if metrics["auroc"] < 0.6 or metrics["auprc"] < 0.4:
        summary["status"] = "documentation_limited"
        summary["reason"] = "The historical validation dataset is not strong enough to support a confident retrospective performance claim."
    return summary
