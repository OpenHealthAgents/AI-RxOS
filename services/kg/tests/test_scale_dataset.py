from __future__ import annotations

import pytest

from app.services.scale_dataset import ScaleDatasetValidationError, validate_scale_dataset_manifest

VALID_MANIFEST = {
    "dataset_name": "oncology_scale_dataset",
    "version": "2026.10.10",
    "actual_counts": {"total_unique_assets": 2},
    "category_distribution": {
        "approved_known_positive_controls": 1,
        "successful_phase_ii_iii": 1,
        "failed_phase_ii_iii": 0,
        "phase_i": 0,
        "preclinical_biotech": 0,
        "academic": 0,
    },
    "target_coverage": {
        "HER2": 1,
        "ESR1": 1,
        "HER3": 0,
        "TROP2": 0,
        "B7-H4": 0,
        "CDK4/6": 0,
        "PI3K": 0,
        "AKT": 0,
        "mTOR": 0,
        "FGFR": 0,
        "PARP": 0,
        "ATR": 0,
        "WEE1": 0,
        "POLQ": 0,
        "GPX4": 0,
        "FSP1": 0,
        "FTL": 0,
        "xCT/SLC7A11": 0,
        "PD-1": 0,
        "PD-L1": 0,
        "TIGIT": 0,
        "LAG3": 0,
        "NK-cell targets": 0,
        "TAM targets": 0,
    },
    "records": [
        {
            "canonical_identity": "scale-her2-001",
            "source_identifiers": ["NCT00001"],
            "target": "HER2",
            "modality": "ANTIBODY",
            "development_stage": "Approved",
            "indication": "HER2-positive breast cancer",
            "owner_or_sponsor": "Genentech",
            "supporting_evidence": [{"source": "example-data", "url": "https://example.invalid/1"}],
            "outcome": "approved",
            "temporal_history": [{"stage": "Approved", "effective_date": "2010-01-01"}],
        },
        {
            "canonical_identity": "scale-esr1-001",
            "source_identifiers": ["NCT00002"],
            "target": "ESR1",
            "modality": "SMALL_MOLECULE",
            "development_stage": "Phase III",
            "indication": "ER-positive breast cancer",
            "owner_or_sponsor": "AstraZeneca",
            "supporting_evidence": [{"source": "example-data", "url": "https://example.invalid/2"}],
            "outcome": "unknown",
            "temporal_history": [{"stage": "Phase III", "effective_date": "2015-01-01"}],
        },
    ],
}


def test_validate_scale_dataset_manifest_accepts_documented_limitations():
    report = validate_scale_dataset_manifest(VALID_MANIFEST)
    assert report["status"] == "documentation_limited"
    assert report["actual_counts"]["total_unique_assets"] == 2
    assert report["target_gap"] == 498


def test_validate_scale_dataset_manifest_rejects_fabricated_default_values():
    manifest = {
        **VALID_MANIFEST,
        "records": [{
            **VALID_MANIFEST["records"][0],
            "outcome": "approved",
            "supporting_evidence": [],
        }],
    }
    with pytest.raises(ScaleDatasetValidationError, match="supporting evidence"):
        validate_scale_dataset_manifest(manifest)

    manifest = {
        **VALID_MANIFEST,
        "actual_counts": {"total_unique_assets": 3},
    }
    with pytest.raises(ScaleDatasetValidationError, match="total_unique_assets"):
        validate_scale_dataset_manifest(manifest)


def test_validate_scale_dataset_manifest_rejects_duplicate_identity_and_target_gap():
    manifest = {
        **VALID_MANIFEST,
        "records": [
            VALID_MANIFEST["records"][0],
            VALID_MANIFEST["records"][0],
        ],
    }
    with pytest.raises(ScaleDatasetValidationError, match="Duplicate canonical_identity"):
        validate_scale_dataset_manifest(manifest)
