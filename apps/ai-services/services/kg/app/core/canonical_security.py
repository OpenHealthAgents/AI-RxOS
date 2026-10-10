from __future__ import annotations

from typing import Any
from uuid import UUID

import jwt
from fastapi import HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

_bearer = HTTPBearer(auto_error=False)


class CanonicalPrincipal:
    def __init__(self, user_id: UUID | None, organization_id: UUID | None, roles: frozenset[str], permissions: frozenset[str]):
        self.user_id = user_id
        self.organization_id = organization_id
        self.roles = roles
        self.permissions = permissions

    @property
    def can_write_global(self) -> bool:
        return bool({"admin", "operator"} & self.roles) or "canonical:write:global" in self.permissions

    @property
    def can_review(self) -> bool:
        return bool({"admin", "operator", "reviewer"} & self.roles) or "canonical:review" in self.permissions

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles

    @property
    def is_scientist(self) -> bool:
        return "scientist" in self.roles

    @property
    def is_clinical_researcher(self) -> bool:
        return "clinical_researcher" in self.roles

    @property
    def is_bd(self) -> bool:
        return "bd" in self.roles

    @property
    def is_licensing(self) -> bool:
        return "licensing" in self.roles

    @property
    def is_executive(self) -> bool:
        return "executive" in self.roles

    @property
    def is_analyst(self) -> bool:
        return "analyst" in self.roles

    @property
    def is_reviewer(self) -> bool:
        return "reviewer" in self.roles


def _claim_set(value: Any) -> frozenset[str]:
    if isinstance(value, str):
        return frozenset(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, (list, tuple, set)):
        return frozenset(item for item in value if isinstance(item, str))
    return frozenset()


def get_canonical_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> CanonicalPrincipal:
    if isinstance(request, HTTPAuthorizationCredentials):
        credentials = request
        request = None
    settings = get_settings()
    internal_token = settings.search_internal_token
    headers = getattr(request, "headers", None)
    request_token = None if headers is None else headers.get("x-search-internal-token") or headers.get("X-Search-Internal-Token")
    auth_token = credentials.credentials if credentials is not None else None
    if internal_token and (request_token == internal_token or auth_token == internal_token):
        return CanonicalPrincipal(
            None,
            None,
            frozenset({"operator", "system"}),
            frozenset({"graph:system"}),
        )
    if settings.environment.lower() == "test" and credentials is None:
        # Allow local test harnesses using tenant headers to behave like a valid internal principal.
        org_id = None if headers is None else headers.get("x-authenticated-organization-id")
        return CanonicalPrincipal(
            None,
            UUID(str(org_id)) if org_id else None,
            frozenset({"operator"}),
            frozenset(),
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")

    try:
        production = settings.environment.lower() in {"production", "prod"}
        if production and (not settings.jwt_issuer or not settings.jwt_audience):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="canonical JWT issuer and audience must be configured in production",
            )
        decode_options = {"require": ["exp", "iss", "aud"]} if production else {}
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer if production else None,
            audience=settings.jwt_audience if production else None,
            options=decode_options,
        )
    except HTTPException:
        raise
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid authentication token") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid authentication payload")

    user_claim = payload.get("sub") or payload.get("user_id") or payload.get("userId")
    organization_claim = payload.get("organization_id") or payload.get("organizationId")
    try:
        user_id = UUID(str(user_claim)) if user_claim else None
        organization_id = UUID(str(organization_claim)) if organization_claim else None
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid identity claim") from exc

    return CanonicalPrincipal(
        user_id=user_id,
        organization_id=organization_id,
        roles=_claim_set(payload.get("roles")),
        permissions=_claim_set(payload.get("permissions")),
    )
