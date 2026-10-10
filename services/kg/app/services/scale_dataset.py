from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REQUIRED_TARGETS = (
    "HER2",
    "ESR1",
    "HER3",
    "TROP2",
    "B7-H4",
    "CDK4/6",
    "PI3K",
    "AKT",
    "mTOR",
    "FGFR",
    "PARP",
    "ATR",
    "WEE1",
    "POLQ",
    "GPX4",
    "FSP1",
    "FTL",
    "xCT/SLC7A11",
    "PD-1",
    "PD-L1",
    "TIGIT",
    "LAG3",
    "NK-cell targets",
    "TAM targets",
)

CATEGORY_KEYS = (
    "approved_known_positive_controls",
    "successful_phase_ii_iii",
    "failed_phase_ii_iii",
    "phase_i",
    "preclinical_biotech",
    "academic",
)

EXPLICIT_UNKNOWN_OUTCOMES = {
    "unknown",
    "unresolved",
    "not_available",
    "not available",
    "unavailable",
}


class ScaleDatasetValidationError(ValueError):
    """Raised when a scale dataset manifest violates the evidence-backed contract."""


def _coerce_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ScaleDatasetValidationError(f"{context} must be an object")
    return value


def _coerce_list(value: Any, context: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    raise ScaleDatasetValidationError(f"{context} must be a list")


def validate_scale_dataset_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a scale-dataset manifest without permitting fabricated counts.

    A manifest may legitimately report zero or incomplete coverage when the repository
    does not yet contain a source-backed asset inventory. In that case the status is
    explicitly documented as limited rather than claiming the 500-asset scale target.
    """
    if not isinstance(manifest, Mapping):
        raise ScaleDatasetValidationError("Manifest must be an object")

    dataset_name = str(manifest.get("dataset_name") or "").strip()
    if not dataset_name:
        raise ScaleDatasetValidationError("dataset_name is required")

    version = str(manifest.get("version") or "").strip()
    if not version:
        raise ScaleDatasetValidationError("version is required")

    actual_counts = _coerce_mapping(manifest.get("actual_counts"), "actual_counts")
    total_unique_assets = actual_counts.get("total_unique_assets")
    if not isinstance(total_unique_assets, int) or total_unique_assets < 0:
        raise ScaleDatasetValidationError("actual_counts.total_unique_assets must be a non-negative integer")

    category_distribution = _coerce_mapping(
        manifest.get("category_distribution", {}),
        "category_distribution",
    )
    category_summary: dict[str, int] = {}
    for key in CATEGORY_KEYS:
        value = category_distribution.get(key)
        if value is None:
            category_summary[key] = 0
        elif not isinstance(value, int) or value < 0:
            raise ScaleDatasetValidationError(f"category_distribution.{key} must be a non-negative integer")
        else:
            category_summary[key] = value

    target_coverage = _coerce_mapping(manifest.get("target_coverage", {}), "target_coverage")
    target_summary: dict[str, int] = {}
    for target in REQUIRED_TARGETS:
        value = target_coverage.get(target)
        if value is None:
            target_summary[target] = 0
        elif not isinstance(value, int) or value < 0:
            raise ScaleDatasetValidationError(f"target_coverage.{target} must be a non-negative integer")
        else:
            target_summary[target] = value

    records = _coerce_list(manifest.get("records", []), "records")
    seen_ids: set[str] = set()
    counted_assets = 0
    for index, record in enumerate(records):
        record_map = _coerce_mapping(record, f"records[{index}]")
        canonical_identity = str(record_map.get("canonical_identity") or "").strip()
        if not canonical_identity:
            raise ScaleDatasetValidationError(f"records[{index}].canonical_identity is required")
        if canonical_identity in seen_ids:
            raise ScaleDatasetValidationError(f"Duplicate canonical_identity: {canonical_identity}")
        seen_ids.add(canonical_identity)

        for field_name in (
            "canonical_identity",
            "source_identifiers",
            "target",
            "modality",
            "development_stage",
            "indication",
            "owner_or_sponsor",
            "supporting_evidence",
            "outcome",
            "temporal_history",
        ):
            value = record_map.get(field_name)
            if field_name in {"source_identifiers", "supporting_evidence", "temporal_history"}:
                if value is None:
                    raise ScaleDatasetValidationError(f"records[{index}].{field_name} is required")
                _coerce_list(value, f"records[{index}].{field_name}")
                continue
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ScaleDatasetValidationError(f"records[{index}].{field_name} cannot be blank")

        target_name = str(record_map.get("target") or "").strip()
        if target_name not in REQUIRED_TARGETS:
            raise ScaleDatasetValidationError(
                f"records[{index}].target must be one of {REQUIRED_TARGETS}; got {target_name!r}"
            )
        counted_assets += 1

        outcome = str(record_map.get("outcome") or "").strip()
        if not outcome:
            raise ScaleDatasetValidationError(
                f"records[{index}].outcome is required; unknown outcomes must be explicit"
            )
        if outcome.casefold() not in EXPLICIT_UNKNOWN_OUTCOMES:
            evidence = _coerce_list(
                record_map.get("supporting_evidence"),
                f"records[{index}].supporting_evidence",
            )
            if not evidence:
                raise ScaleDatasetValidationError(
                    f"records[{index}] declares outcome {outcome!r} without supporting evidence"
                )

    if records and total_unique_assets != counted_assets:
        raise ScaleDatasetValidationError(
            f"actual_counts.total_unique_assets={total_unique_assets} does not match "
            f"record_count={counted_assets}"
        )

    total_category = sum(category_summary.values())
    if records and total_category and total_category != counted_assets:
        raise ScaleDatasetValidationError(
            "category_distribution total does not match the manifest record count; "
            "duplicate counting is not allowed"
        )

    if target_summary and sum(target_summary.values()) > total_unique_assets:
        raise ScaleDatasetValidationError(
            "target_coverage total cannot exceed total_unique_assets without evidence"
        )

    target_misses = {target: count for target, count in target_summary.items() if count > 0 and count > total_unique_assets}
    if target_misses:
        raise ScaleDatasetValidationError(
            f"target_coverage contains impossible counts: {target_misses}"
        )

    report = {
        "dataset_name": dataset_name,
        "version": version,
        "actual_counts": {
            "total_unique_assets": total_unique_assets,
            "total_records": len(records),
        },
        "category_distribution": category_summary,
        "target_coverage": target_summary,
        "status": "documentation_limited" if total_unique_assets < 500 else "ready_for_source_backed_scale",
        "dataset_target": 500,
        "target_gap": max(0, 500 - total_unique_assets),
        "coverage_gaps": [
            target for target, count in target_summary.items() if count == 0
        ],
    }
    return report
