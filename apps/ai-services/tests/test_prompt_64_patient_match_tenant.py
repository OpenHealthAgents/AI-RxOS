import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ml import router as ml_router
from app.opportunity_engine import patient_match
from app.opportunity_engine.core_api import _trusted_tenant_id

client = TestClient(app)


class EmptyDomainEngine:
    def evaluate_intelligence(self, *_args, **_kwargs) -> None:
        return None


def test_patient_match_intelligence_uses_trusted_tenant_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ml_router, "get_shared_ml_services", lambda: (None, None))
    monkeypatch.setattr(
        patient_match.router, "get_biology_engine", EmptyDomainEngine
    )
    monkeypatch.setattr(
        patient_match.router, "get_clinical_engine", EmptyDomainEngine
    )
    app.dependency_overrides[_trusted_tenant_id] = lambda: "trusted-tenant"
    try:
        response = client.get(
            "/api/v1/patient-match/intelligence/zongertinib",
            params={"tenant_id": "caller-controlled"},
        )
    finally:
        app.dependency_overrides.pop(_trusted_tenant_id, None)

    assert response.status_code == 200, response.text
    assert response.json()["tenant_id"] == "trusted-tenant"
