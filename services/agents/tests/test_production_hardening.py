from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.config import Settings
from app.core.security import get_current_user

VALID_KEY = "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTI="


def production_settings(**overrides):
    values = {
        "environment": "production",
        "execution_payload_key": VALID_KEY,
        "jwt_secret": "a-real-production-secret-value",
        "jwt_issuer": "ai-rxos",
        "jwt_audience": "ai-rxos-agents",
        "redis_url": "rediss://redis.example:6379/0",
        "redis_tls_required": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_production_settings_require_real_secrets_and_claim_config():
    production_settings()
    with pytest.raises(ValueError):
        production_settings(execution_payload_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    with pytest.raises(ValueError):
        production_settings(jwt_secret="change_this_dev_secret_before_deploying")
    with pytest.raises(ValueError):
        production_settings(jwt_issuer=None)
    with pytest.raises(ValueError):
        production_settings(redis_url="redis://redis.example:6379/0")


def test_production_jwt_requires_issuer_audience_expiry_and_hs256():
    settings = production_settings()
    token = jwt.encode(
        {
            "sub": "user-1",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    original = __import__("app.core.security", fromlist=["get_settings"]).get_settings
    __import__("app.core.security", fromlist=["get_settings"]).get_settings = lambda: settings
    try:
        assert get_current_user(credentials)["sub"] == "user-1"
        for changes in (
            {"iss": "wrong"},
            {"aud": "wrong"},
            {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        ):
            claims = {
                "sub": "user-1",
                "iss": settings.jwt_issuer,
                "aud": settings.jwt_audience,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            }
            claims.update(changes)
            bad = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")
            with pytest.raises(HTTPException):
                get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=bad))
    finally:
        __import__("app.core.security", fromlist=["get_settings"]).get_settings = original
