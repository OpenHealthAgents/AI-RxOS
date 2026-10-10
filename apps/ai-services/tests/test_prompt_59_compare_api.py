from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine import compare_api
from app.opportunity_engine.core_api import _trusted_tenant_id
from app.opportunity_engine.intelligence import (
    EpistemicClass,
    IntelligenceEvidence,
    IntelligenceValue,
    IntelligenceValueStatus,
)

client = TestClient(app)


def test_comparison_for_two_assets_returns_all_typed_dimensions() -> None:
    response = client.post(
        "/api/compare",
        json={"asset_ids": ["zongertinib", "tucatinib"]},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["evaluation_cutoff"] == date.today().isoformat()
    assert result["asset_ids"] == ["zongertinib", "tucatinib"]
    assert [dimension["dimension"] for dimension in result["dimensions"]] == [
        "biology",
        "clinical",
        "cns",
        "patient",
        "safety",
        "resistance",
        "competition",
        "licensing",
        "commercial",
    ]
    assert all(
        len(dimension["normalized_comparison"]) == 2
        for dimension in result["dimensions"]
    )
    assert all(
        "confidence" in dimension
        and "contradictory_evidence_status" in dimension
        and dimension["contradictory_evidence_status"] == "NOT_CLASSIFIED"
        for dimension in result["dimensions"]
    )
    biology = next(
        item for item in result["dimensions"] if item["dimension"] == "biology"
    )
    assert biology["normalized_comparison"][0]["metrics"][0]["metric"] == (
        "biology_validation"
    )
    assert (
        biology["normalized_comparison"][0]["metrics"][0]["source_output"][
            "prediction_cutoff"
        ]
        == result["evaluation_cutoff"]
    )
    cns = next(item for item in result["dimensions"] if item["dimension"] == "cns")
    assert {
        metric["metric"]
        for metric in cns["normalized_comparison"][0]["metrics"]
    } == {
        "cns_exposure_signal",
        "measured_cns_activity",
        "predicted_cns_potential",
        "predicted_cns_activity",
        "brain_metastasis_relevance",
    }
    expected_metrics = {
        "biology": {"biology_validation"},
        "clinical": {
            "clinical_readiness",
            "clinical_success_probability",
        },
        "cns": {
            "cns_exposure_signal",
            "measured_cns_activity",
            "predicted_cns_potential",
            "predicted_cns_activity",
            "brain_metastasis_relevance",
        },
        "patient": {"patient_match_score"},
        "safety": {"safety_score"},
        "resistance": {"resistance_risk", "evidenced_escape_mechanisms"},
        "competition": {
            "differentiation_score",
            "competitive_risk_score",
        },
        "licensing": {"licensing_status"},
        "commercial": {"commercial_opportunity_score"},
    }
    for dimension_name, metric_names in expected_metrics.items():
        dimension = next(
            item
            for item in result["dimensions"]
            if item["dimension"] == dimension_name
        )
        actual_metrics = {
            metric["metric"]
            for metric in dimension["normalized_comparison"][0]["metrics"]
        }
        assert actual_metrics == metric_names


def test_multiple_assets_are_compared_without_forcing_winners() -> None:
    response = client.post(
        "/api/compare",
        json={
            "asset_ids": [
                "zongertinib",
                "tucatinib",
                "neratinib",
                "poziotinib",
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["asset_ids"]) == 4
    assert all(
        dimension["winner_status"] != "WINNER_IDENTIFIED"
        or dimension["winner_asset_id"] is not None
        for dimension in response.json()["dimensions"]
    )


def test_twenty_asset_limit_is_supported_when_repository_resolves_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical_assets = [
        SimpleNamespace(id=f"asset-{index:02d}")
        for index in range(20)
    ]
    monkeypatch.setattr(
        compare_api,
        "list_fixture_assets",
        lambda: canonical_assets,
    )
    monkeypatch.setattr(
        compare_api,
        "_require_asset",
        lambda asset_id: SimpleNamespace(id=asset_id),
    )
    monkeypatch.setattr(
        compare_api,
        "_evaluate_components",
        lambda _asset_id, _tenant_id, _cutoff: {
            "biology": SimpleNamespace(
                biology_validation=IntelligenceValue(
                    name="biology_validation",
                    status=IntelligenceValueStatus.UNKNOWN,
                ),
                unknowns=["No comparison test evidence."],
            ),
            **{
                key: None
                for key in (
                    "clinical",
                    "cns",
                    "patients",
                    "safety",
                    "resistance",
                    "competitive",
                    "licensing",
                    "commercial",
                )
            },
        },
    )
    response = client.post(
        "/api/compare",
        json={"asset_ids": [asset.id for asset in canonical_assets]},
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["asset_ids"]) == 20


@pytest.mark.parametrize(
    "asset_ids",
    [
        [],
        ["zongertinib"],
        [f"asset-{index:02d}" for index in range(21)],
    ],
)
def test_asset_count_outside_two_to_twenty_is_rejected(
    asset_ids: list[str],
) -> None:
    response = client.post("/api/compare", json={"asset_ids": asset_ids})
    assert response.status_code == 422


def test_unknown_or_malformed_asset_ids_are_rejected() -> None:
    unknown = client.post(
        "/api/compare",
        json={"asset_ids": ["zongertinib", "unknown-asset"]},
    )
    assert unknown.status_code == 404
    assert "unknown-asset" in unknown.text

    malformed = client.post(
        "/api/compare",
        json={"asset_ids": ["zongertinib", "invalid@asset"]},
    )
    assert malformed.status_code == 422


def test_duplicate_asset_ids_are_rejected_case_insensitively() -> None:
    response = client.post(
        "/api/compare",
        json={"asset_ids": ["zongertinib", "ZONGERTINIB"]},
    )
    assert response.status_code == 422


def test_as_of_cutoff_is_preserved_and_future_cutoff_rejected() -> None:
    historical = client.post(
        "/api/compare",
        json={
            "asset_ids": ["zongertinib", "tucatinib"],
            "cutoff": "2020-01-01",
        },
    )
    assert historical.status_code == 200, historical.text
    result = historical.json()
    assert result["evaluation_cutoff"] == "2020-01-01"
    safety = next(
        item for item in result["dimensions"] if item["dimension"] == "safety"
    )
    assert all(
        row["metrics"][0]["status"] == "UNAVAILABLE"
        for row in safety["normalized_comparison"]
    )

    future = client.post(
        "/api/compare",
        json={
            "asset_ids": ["zongertinib", "tucatinib"],
            "cutoff": "2999-01-01",
        },
    )
    assert future.status_code == 422


def test_trusted_tenant_is_forwarded_to_existing_domain_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received_tenants: list[str | None] = []
    original = compare_api._evaluate_components

    def capture_tenant(
        asset_id: str,
        tenant_id: str | None,
        cutoff: date,
    ) -> dict[str, object]:
        received_tenants.append(tenant_id)
        return original(asset_id, tenant_id, cutoff)

    monkeypatch.setattr(compare_api, "_evaluate_components", capture_tenant)
    app.dependency_overrides[_trusted_tenant_id] = lambda: "tenant-a"
    try:
        response = client.post(
            "/api/compare",
            json={"asset_ids": ["zongertinib", "tucatinib"]},
        )
    finally:
        app.dependency_overrides.pop(_trusted_tenant_id, None)
        monkeypatch.undo()

    assert response.status_code == 200, response.text
    assert response.json()["tenant_id"] == "tenant-a"
    assert received_tenants == ["tenant-a", "tenant-a"]
    biology = next(
        item
        for item in response.json()["dimensions"]
        if item["dimension"] == "biology"
    )
    assert (
        biology["normalized_comparison"][0]["metrics"][0]["source_output"][
            "tenant_id"
        ]
        == "tenant-a"
    )


def test_partial_evidence_remains_asymmetric_and_does_not_produce_winner() -> None:
    evidence = IntelligenceEvidence(
        evidence_id="evidence-a",
        source_type="publication",
        source_reference="PMID:123456",
        citation="Observed evidence reference",
        confidence=0.9,
        epistemic_class=EpistemicClass.FACT,
    )
    supported = SimpleNamespace(
        biology_validation=IntelligenceValue(
            name="biology_validation",
            value=80.0,
            status=IntelligenceValueStatus.AVAILABLE,
            epistemic_class=EpistemicClass.FACT,
            confidence=0.9,
            supporting_evidence=[evidence],
            provenance={"source": "biology-engine"},
        ),
        unknowns=[],
        evidence=[evidence],
    )
    unavailable = SimpleNamespace(
        biology_validation=IntelligenceValue(
            name="biology_validation",
            status=IntelligenceValueStatus.UNKNOWN,
            reason="Evidence unavailable.",
        ),
        unknowns=["No biology evidence."],
        evidence=[],
    )
    comparison = compare_api._make_dimension_comparison(
        "biology",
        ["asset-a", "asset-b"],
        {"asset-a": supported, "asset-b": unavailable},
    )
    assert comparison.winner_asset_id is None
    assert comparison.winner_status == "INSUFFICIENT_EVIDENCE"
    assert comparison.normalized_comparison[0].metrics[0].supporting_evidence
    assert comparison.normalized_comparison[1].metrics[0].supporting_evidence == []
    assert comparison.normalized_comparison[1].metrics[0].raw_value is None


def test_evidence_backed_comparable_metric_identifies_winner_with_confidence() -> None:
    evidence_a = IntelligenceEvidence(
        evidence_id="bio-a",
        source_type="publication",
        source_reference="PMID:100",
        confidence=0.9,
        epistemic_class=EpistemicClass.FACT,
    )
    evidence_b = IntelligenceEvidence(
        evidence_id="bio-b",
        source_type="publication",
        source_reference="PMID:200",
        confidence=0.8,
        epistemic_class=EpistemicClass.FACT,
    )
    profiles = {
        "asset-a": SimpleNamespace(
            biology_validation=IntelligenceValue(
                name="biology_validation",
                value=75,
                status=IntelligenceValueStatus.AVAILABLE,
                epistemic_class=EpistemicClass.FACT,
                confidence=0.9,
                supporting_evidence=[evidence_a],
                provenance={"model_version": None},
            ),
            unknowns=[],
        ),
        "asset-b": SimpleNamespace(
            biology_validation=IntelligenceValue(
                name="biology_validation",
                value=55,
                status=IntelligenceValueStatus.AVAILABLE,
                epistemic_class=EpistemicClass.FACT,
                confidence=0.8,
                supporting_evidence=[evidence_b],
                provenance={"model_version": None},
            ),
            unknowns=[],
        ),
    }
    comparison = compare_api._make_dimension_comparison(
        "biology",
        list(profiles),
        profiles,
    )
    assert comparison.winner_asset_id == "asset-a"
    assert comparison.winner_status == "WINNER_IDENTIFIED"
    assert comparison.confidence == 0.8
    assert len(comparison.supporting_evidence) == 2
    assert [
        row.metrics[0].normalized_value
        for row in comparison.normalized_comparison
    ] == [0.75, 0.55]
    assert (
        comparison.normalized_comparison[0].metrics[0].provenance[
            "model_version"
        ]
        is None
    )


def test_tied_metrics_and_categorical_licensing_do_not_force_winner() -> None:
    profile = SimpleNamespace(
        biology_validation=IntelligenceValue(
            name="biology_validation",
            value=75,
            status=IntelligenceValueStatus.AVAILABLE,
            epistemic_class=EpistemicClass.FACT,
            confidence=0.8,
            supporting_evidence=[
                IntelligenceEvidence(
                    evidence_id="evidence",
                    source_type="paper",
                    source_reference="PMID:300",
                )
            ],
        ),
        unknowns=[],
    )
    tie = compare_api._make_dimension_comparison(
        "biology",
        ["asset-a", "asset-b"],
        {"asset-a": profile, "asset-b": profile},
    )
    assert tie.winner_asset_id is None
    assert tie.winner_status == "NOT_DISTINGUISHABLE"

    license_profile = SimpleNamespace(
        licensing_status=SimpleNamespace(value="VERIFIED_AVAILABLE"),
        licensing_status_verified=True,
        licensing_verification_source="Verified source record",
    )
    licensing = compare_api._make_dimension_comparison(
        "licensing",
        ["asset-a", "asset-b"],
        {"asset-a": license_profile, "asset-b": license_profile},
    )
    assert licensing.winner_asset_id is None
    assert licensing.winner_status == "NOT_COMPARABLE"
    assert all(
        row.metrics[0].raw_value == "VERIFIED_AVAILABLE"
        and row.metrics[0].supporting_evidence
        for row in licensing.normalized_comparison
    )


def test_missing_safety_data_is_not_normalized_or_ranked() -> None:
    profile = SimpleNamespace(
        safety_score=10.0,
        safety_confidence=0.8,
        has_missing_evidence=True,
        missing_evidence_details=["Human safety evidence is unavailable."],
        evidence_citations=[],
    )
    metric = compare_api._dimension_metrics("safety", profile)[0]
    assert metric.status == IntelligenceValueStatus.INSUFFICIENT_EVIDENCE
    assert metric.raw_value == 10.0
    assert metric.normalized_value is None
    assert metric.confidence == 0.8
    assert metric.supporting_evidence == []


def test_strict_request_schema_rejects_unknown_fields() -> None:
    response = client.post(
        "/api/compare",
        json={
            "asset_ids": ["zongertinib", "tucatinib"],
            "tenant_id": "caller-controlled",
        },
    )
    assert response.status_code == 422
