from __future__ import annotations

import jwt
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import trusted_identity_middleware


def _app(environment: str = "production") -> tuple[FastAPI, str]:
    secret = "synthetic-security-test-key-with-32-bytes"
    settings = Settings(
        environment=environment,
        jwt_secret=secret,
        kg_canonical_database_url="postgresql://test:test@localhost/test",
    )
    app = FastAPI()
    app.state.security_settings = settings
    app.middleware("http")(trusted_identity_middleware)

    @app.get("/api/v1/scope")
    async def scope(request: Request):
        return {
            "tenant_id": getattr(request.state, "tenant_id", None),
            "user_id": getattr(request.state, "user_id", None),
            "roles": sorted(getattr(request.state, "roles", set())),
        }

    return app, secret


def _token(secret: str, **claims: object) -> str:
    return jwt.encode(claims, secret, algorithm="HS256")


def test_production_api_rejects_missing_and_invalid_bearer_tokens() -> None:
    app, secret = _app()
    client = TestClient(app)
    assert client.get("/api/v1/scope").status_code == 401
    assert client.get(
        "/api/v1/scope",
        headers={"Authorization": f"Bearer {_token(secret, sub='user-1', organizationId='tenant-a', exp=1)}"},
    ).status_code == 401


def test_tenant_scope_is_derived_from_verified_claim_not_header() -> None:
    app, secret = _app()
    client = TestClient(app)
    token = _token(
        secret,
        sub="user-1",
        organizationId="tenant-a",
        roles=["Reviewer"],
        exp=4_102_444_800,
    )
    response = client.get(
        "/api/v1/scope",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Authenticated-Organization-ID": "tenant-b",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": "tenant-a",
        "user_id": "user-1",
        "roles": ["reviewer"],
    }


def test_production_api_rejects_missing_tenant_claim() -> None:
    app, secret = _app()
    token = _token(secret, sub="user-1", roles=["analyst"], exp=4_102_444_800)
    response = TestClient(app).get("/api/v1/scope", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_production_settings_reject_default_or_missing_security_secrets() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(
            environment="production",
            kg_canonical_database_url="postgresql://test:test@localhost/test",
        )
    with pytest.raises(ValidationError, match="KG_CANONICAL_DATABASE_URL"):
        Settings(
            environment="production",
            jwt_secret="synthetic-security-test-key-with-32-bytes",
        )
