from __future__ import annotations

import pytest

from app.services.gold_standard_dataset import DatasetValidationError, validate_gold_standard_dataset


VALID_MANIFEST = {
    "dataset_name": "her2_esr1_gold_standard",
    "version": "2026.10.10",
    "actual_counts": {"HER2": 1, "ESR1": 1},
    "records": [
        {
            "canonical_identity": "asset-her2-001",
            "aliases": ["trastuzumab"],
            "target": "HER2",
            "modality": "ANTIBODY",
            "development_stage": "Approved",
            "indication": "HER2-positive breast cancer",
            "owner_or_sponsor": "Genentech",
            "evidence_references": [{"source": "example-data", "url": "https://example.invalid/1"}],
            "outcome": "approved",
            "failure_reason": "unknown",
            "temporal_history": [{"stage": "Approved", "effective_date": "2010-01-01"}],
        },
        {
            "canonical_identity": "asset-esr1-001",
            "aliases": ["fulvestrant"],
            "target": "ESR1",
            "modality": "SMALL_MOLECULE",
            "development_stage": "Approved",
            "indication": "ER-positive breast cancer",
            "owner_or_sponsor": "AstraZeneca",
            "evidence_references": [{"source": "example-data", "url": "https://example.invalid/2"}],
            "outcome": "unknown",
            "failure_reason": "unknown",
            "temporal_history": [{"stage": "Approved", "effective_date": "2015-01-01"}],
        },
    ],
}


def test_validate_gold_standard_dataset_accepts_explicit_unknowns_and_evidence():
    report = validate_gold_standard_dataset(VALID_MANIFEST)
    assert report["status"] == "ready_for_source_backed_load"
    assert report["actual_counts"] == {"HER2": 1, "ESR1": 1}


def test_validate_gold_standard_dataset_rejects_missing_outcome_or_fabricated_default():
    manifest = {
        **VALID_MANIFEST,
        "records": [
            {
                **VALID_MANIFEST["records"][0],
                "outcome": "",
            }
        ],
    }
    with pytest.raises(DatasetValidationError, match="outcome"):
        validate_gold_standard_dataset(manifest)

    manifest = {
        **VALID_MANIFEST,
        "records": [
            {
                **VALID_MANIFEST["records"][0],
                "outcome": "approved",
                "evidence_references": [],
            }
        ],
    }
    with pytest.raises(DatasetValidationError, match="evidence references"):
        validate_gold_standard_dataset(manifest)


def test_validate_gold_standard_dataset_rejects_count_mismatch():
    manifest = {
        **VALID_MANIFEST,
        "actual_counts": {"HER2": 2, "ESR1": 1},
    }
    with pytest.raises(DatasetValidationError, match="actual_counts"):
        validate_gold_standard_dataset(manifest)
