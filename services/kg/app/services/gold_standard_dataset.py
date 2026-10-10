from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

REQUIRED_TARGETS = ("HER2", "ESR1")
EXPLICIT_UNKNOWN_OUTCOMES = {
    "unknown",
    "unresolved",
    "not_available",
    "not available",
    "unavailable",
}
REQUIRED_RECORD_FIELDS = (
    "canonical_identity",
    "aliases",
    "target",
    "modality",
    "development_stage",
    "indication",
    "owner_or_sponsor",
    "evidence_references",
    "outcome",
    "temporal_history",
)


class DatasetValidationError(ValueError):
    """Raised when a manifest does not satisfy the evidence-backed gold-standard constraints."""


def _coerce_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DatasetValidationError(f"{context} must be an object")
    return value


def _coerce_list(value: Any, context: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    raise DatasetValidationError(f"{context} must be a list")


def validate_gold_standard_dataset(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a gold-standard asset manifest without allowing fabricated outcomes.

    The dataset cannot be treated as complete unless the manifest explicitly reports
    actual counts and evidence-backed identity information for each record. Missing or
    ambiguous evidence remains an explicit unknown state rather than a defaulted value.
    """
    if not isinstance(manifest, Mapping):
        raise DatasetValidationError("Manifest must be an object")

    dataset_name = str(manifest.get("dataset_name") or "").strip()
    if not dataset_name:
        raise DatasetValidationError("dataset_name is required")

    version = str(manifest.get("version") or "").strip()
    if not version:
        raise DatasetValidationError("version is required")

    actual_counts = manifest.get("actual_counts")
    if not isinstance(actual_counts, Mapping):
        raise DatasetValidationError("actual_counts must be an object with HER2 and ESR1 counts")

    counts_by_target = {}
    for target in REQUIRED_TARGETS:
        value = actual_counts.get(target)
        if not isinstance(value, int) or value < 0:
            raise DatasetValidationError(f"actual_counts.{target} must be a non-negative integer")
        counts_by_target[target] = value

    records = _coerce_list(manifest.get("records"), "records")
    seen_ids: set[str] = set()
    counted_records = {"HER2": 0, "ESR1": 0}

    for index, record in enumerate(records):
        record_map = _coerce_mapping(record, f"records[{index}]")
        canonical_identity = str(record_map.get("canonical_identity") or "").strip()
        if not canonical_identity:
            raise DatasetValidationError(f"records[{index}].canonical_identity is required")
        if canonical_identity in seen_ids:
            raise DatasetValidationError(f"Duplicate canonical_identity: {canonical_identity}")
        seen_ids.add(canonical_identity)

        for field_name in REQUIRED_RECORD_FIELDS:
            value = record_map.get(field_name)
            if field_name in {"aliases", "evidence_references", "temporal_history"}:
                if value is None:
                    raise DatasetValidationError(f"records[{index}].{field_name} is required")
                _coerce_list(value, f"records[{index}].{field_name}")
                continue
            if value is None or (isinstance(value, str) and not value.strip()):
                raise DatasetValidationError(f"records[{index}].{field_name} cannot be blank")

        target_value = str(record_map.get("target") or "").strip().upper()
        if target_value not in REQUIRED_TARGETS:
            raise DatasetValidationError(
                f"records[{index}].target must be one of {REQUIRED_TARGETS}; got {target_value!r}"
            )
        counted_records[target_value] += 1

        outcome = str(record_map.get("outcome") or "").strip()
        if not outcome:
            raise DatasetValidationError(f"records[{index}].outcome is required; unknown outcomes must be explicit")

        normalized_outcome = outcome.casefold()
        if normalized_outcome in EXPLICIT_UNKNOWN_OUTCOMES:
            continue

        evidence_refs = _coerce_list(record_map.get("evidence_references"), f"records[{index}].evidence_references")
        if not evidence_refs:
            raise DatasetValidationError(
                f"records[{index}] declares outcome {outcome!r} without evidence references; "
                "fabricated or defaulted outcomes are not allowed"
            )

        failure_reason = record_map.get("failure_reason")
        if failure_reason is not None:
            failure_reason_text = str(failure_reason).strip()
            if failure_reason_text and failure_reason_text.casefold() not in EXPLICIT_UNKNOWN_OUTCOMES:
                if len(evidence_refs) == 0:
                    raise DatasetValidationError(
                        f"records[{index}].failure_reason requires evidence references" 
                        " when it is not explicitly unknown"
                    )

    for target in REQUIRED_TARGETS:
        if counted_records[target] != counts_by_target[target]:
            raise DatasetValidationError(
                f"actual_counts.{target}={counts_by_target[target]} does not match "
                f"the manifest records count={counted_records[target]}"
            )

    report = {
        "dataset_name": dataset_name,
        "version": version,
        "status": "ready_for_source_backed_load",
        "actual_counts": counts_by_target,
        "record_count": len(records),
        "count_by_target": counted_records,
    }
    return report


def dataset_manifest_report(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return a summary for a manifest without mutating the manifest itself."""
    return validate_gold_standard_dataset(manifest)
