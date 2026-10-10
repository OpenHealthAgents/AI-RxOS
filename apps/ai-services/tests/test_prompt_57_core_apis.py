from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.opportunity_engine.biology.models import BiologyIntelligence
from app.opportunity_engine.clinical.models import ClinicalIntelligence
from app.opportunity_engine.cns.models import CNSIntelligence
from app.opportunity_engine.commercial.models import CommercialOpportunityProfile
from app.opportunity_engine.competitive.models import CompetitiveIntelligenceProfile
from app.opportunity_engine.core_api import (
    AssetCatalogResponse,
    AssetDomainResponse,
    AssetEvaluationResponse,
    AssetEvidenceResponse,
    AssetHistoryResponse,
    AssetResource,
    _trusted_tenant_id,
)
from app.opportunity_engine.intelligence import IntelligenceValueStatus
from app.opportunity_engine.intelligence_47_49 import (
    CombinationIntelligence,
    PatientMatchIntelligence,
    ResistanceIntelligence,
)
from app.opportunity_engine.licensing.models import AssetOwnershipProfile
from app.opportunity_engine.safety.models import SafetyIntelligenceProfile

client = TestClient(app)
TODAY = datetime.now(timezone.utc).date()


def test_core_asset_listing_and_retrieval_are_typed() -> None:
    response = client.get("/api/assets")
    assert response.status_code == 200
    result = AssetCatalogResponse.model_validate(response.json())
    assert result.tenant_id is None
    assert any(asset.id == "zongertinib" for asset in result.assets)

    asset_response = client.get("/api/assets/zongertinib")
    assert asset_response.status_code == 200
    asset = AssetResource.model_validate(asset_response.json())
    assert asset.asset_id == "zongertinib"
    assert asset.tenant_id is None
    assert asset.asset.id == asset.asset_id


def test_domain_endpoints_use_typed_existing_intelligence_outputs() -> None:
    domain_models = {
        "biology": BiologyIntelligence,
        "clinical": ClinicalIntelligence,
        "cns": CNSIntelligence,
        "patients": PatientMatchIntelligence,
        "safety": SafetyIntelligenceProfile,
        "resistance": ResistanceIntelligence,
        "combinations": CombinationIntelligence,
        "competitive": CompetitiveIntelligenceProfile,
        "licensing": AssetOwnershipProfile,
        "commercial": CommercialOpportunityProfile,
    }
    for domain, profile_model in domain_models.items():
        response = client.get(
            f"/api/assets/zongertinib/{domain}",
            params={"cutoff": TODAY.isoformat()},
        )
        assert response.status_code == 200, (domain, response.text)
        result = AssetDomainResponse[profile_model].model_validate(response.json())
        assert result.asset_id == "zongertinib"
        assert result.tenant_id is None
        assert result.evaluation_cutoff is None or str(result.evaluation_cutoff) == TODAY.isoformat()
        assert result.data is not None


def test_evaluate_reuses_decision_and_why_with_typed_responses() -> None:
    response = client.get(
        "/api/assets/zongertinib/evaluate",
        params={"cutoff": "2024-01-01"},
    )
    assert response.status_code == 200, response.text
    result = AssetEvaluationResponse.model_validate(response.json())
    assert result.asset_id == "zongertinib"
    assert result.tenant_id is None
    assert result.evaluation_cutoff.isoformat() == "2024-01-01"
    assert result.decision.evaluation_cutoff.isoformat() == "2024-01-01"
    assert result.why.decision == result.decision.decision
    assert result.action_intelligence.decision == result.decision.decision
    assert result.action_intelligence.asset_id == result.asset_id
    assert result.biology.data is not None
    assert result.clinical.data is not None
    assert result.cns.data is not None


def test_evaluate_action_intelligence_uses_trusted_tenant_context() -> None:
    app.dependency_overrides[_trusted_tenant_id] = lambda: "tenant-trusted"
    try:
        response = client.get(
            "/api/assets/zongertinib/evaluate",
            params={"tenant_id": "tenant-attacker"},
        )
    finally:
        app.dependency_overrides.pop(_trusted_tenant_id, None)
    assert response.status_code == 200, response.text
    result = AssetEvaluationResponse.model_validate(response.json())
    assert result.tenant_id == "tenant-trusted"
    assert result.decision.tenant_id == "tenant-trusted"
    assert result.action_intelligence.tenant_id == "tenant-trusted"
    assert result.action_intelligence.recommended_actions


def test_historical_evaluation_does_not_claim_as_of_support_from_current_only_engines() -> None:
    cutoff = TODAY - timedelta(days=1)
    response = client.get(
        "/api/assets/zongertinib/evaluate",
        params={"cutoff": cutoff.isoformat()},
    )
    assert response.status_code == 200, response.text
    result = AssetEvaluationResponse.model_validate(response.json())
    for profile in (result.safety, result.competitive, result.commercial):
        assert profile.status == IntelligenceValueStatus.UNAVAILABLE
        assert profile.data is None
        assert profile.reason


def test_why_endpoint_uses_existing_why_engine() -> None:
    app.dependency_overrides[_trusted_tenant_id] = lambda: "tenant-b"
    try:
        response = client.get(
            "/api/assets/zongertinib/why",
            params={"cutoff": "2024-01-01"},
        )
    finally:
        app.dependency_overrides.pop(_trusted_tenant_id, None)
    assert response.status_code == 200, response.text
    assert response.json()["tenant_id"] == "tenant-b"
    assert response.json()["evaluation_cutoff"] == "2024-01-01"
    assert response.json()["decision"]
    assert "explanation" in response.json()


def test_evidence_and_history_preserve_cutoff_and_provenance() -> None:
    evidence_response = client.get(
        "/api/assets/zongertinib/evidence",
        params={"cutoff": "2024-01-01"},
    )
    assert evidence_response.status_code == 200
    evidence = AssetEvidenceResponse.model_validate(evidence_response.json())
    assert evidence.tenant_id is None
    assert evidence.cutoff.isoformat() == "2024-01-01"
    assert evidence.status in {
        IntelligenceValueStatus.AVAILABLE,
        IntelligenceValueStatus.UNKNOWN,
    }
    assert all(item.source_id and item.temporal_validity for item in evidence.evidence)

    history_response = client.get(
        "/api/assets/zongertinib/history",
        params={"as_of": "2020-01-01"},
    )
    assert history_response.status_code == 200
    history = AssetHistoryResponse.model_validate(history_response.json())
    assert history.as_of.isoformat() == "2020-01-01"
    assert all(item.publication_date <= history.as_of for item in history.evidence)
    assert all(item.prediction_cutoff <= history.as_of for item in history.milestones)


def test_unknown_asset_and_malformed_path_are_rejected() -> None:
    assert client.get("/api/assets/not-registered").status_code == 404
    assert client.get("/api/assets/bad%40id").status_code == 422
    assert client.get("/api/assets/zongertinib/biology?cutoff=not-a-date").status_code == 422


def test_missing_profile_data_remains_unknown() -> None:
    response = client.get("/api/assets/neratinib/licensing")
    assert response.status_code == 200
    result = AssetDomainResponse[dict].model_validate(response.json())
    assert result.status == IntelligenceValueStatus.UNKNOWN
    assert result.data is None
    assert result.reason


def test_tenant_context_is_preserved_and_public_catalog_is_consistent() -> None:
    app.dependency_overrides[_trusted_tenant_id] = lambda: "tenant-a"
    try:
        tenant_a = client.get("/api/assets")
    finally:
        app.dependency_overrides.pop(_trusted_tenant_id, None)
    assert tenant_a.status_code == 200
    result_a = AssetCatalogResponse.model_validate(tenant_a.json())
    assert result_a.tenant_id == "tenant-a"

    app.dependency_overrides[_trusted_tenant_id] = lambda: "tenant-b"
    try:
        tenant_b = client.get("/api/assets")
    finally:
        app.dependency_overrides.pop(_trusted_tenant_id, None)
    assert tenant_b.status_code == 200
    result_b = AssetCatalogResponse.model_validate(tenant_b.json())
    assert result_b.tenant_id == "tenant-b"
    assert {asset.id for asset in result_a.assets} == {asset.id for asset in result_b.assets}


def test_trusted_tenant_context_is_forwarded_to_domain_engines() -> None:
    app.dependency_overrides[_trusted_tenant_id] = lambda: "tenant-a"
    try:
        tenant_a = client.get("/api/assets/zongertinib/biology")
    finally:
        app.dependency_overrides.pop(_trusted_tenant_id, None)
    assert tenant_a.status_code == 200
    result_a = AssetDomainResponse[BiologyIntelligence].model_validate(tenant_a.json())
    assert result_a.tenant_id == "tenant-a"
    assert result_a.data is not None
    assert result_a.data.tenant_id == "tenant-a"

    app.dependency_overrides[_trusted_tenant_id] = lambda: "tenant-b"
    try:
        tenant_b = client.get("/api/assets/zongertinib/biology")
    finally:
        app.dependency_overrides.pop(_trusted_tenant_id, None)
    assert tenant_b.status_code == 200
    result_b = AssetDomainResponse[BiologyIntelligence].model_validate(tenant_b.json())
    assert result_b.tenant_id == "tenant-b"
    assert result_b.data is not None
    assert result_b.data.tenant_id == "tenant-b"
