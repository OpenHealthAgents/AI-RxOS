"""JWT verification and tenant-scope extraction for the agents service.

services/agents had no auth wiring at all prior to this (every endpoint was
unauthenticated). This mirrors services/literature's app/core/security.py
pattern (same JWT secret convention, same claim names) rather than inventing
a third auth shape — see services/auth/src/tenantContext.ts::AuthPayload for
the canonical {sub, organizationId, roles} claim shape this aligns with.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

security = HTTPBearer(auto_error=False)
security_dependency = Security(security)


@dataclass(frozen=True)
class TenantContext:
    organization_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    user_id: str | None = None

    def as_dict(self) -> dict[str, str]:
        return {
            k: v
            for k, v in {
                "organization_id": self.organization_id,
                "workspace_id": self.workspace_id,
                "project_id": self.project_id,
                "user_id": self.user_id,
            }.items()
            if v
        }


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = security_dependency,
) -> dict[str, str]:
    settings = get_settings()
    if settings.environment == "test" and credentials is None:
        return {"sub": "test-user-fallback"}

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )

    try:
        payload = jwt.decode(
            credentials.credentials, settings.jwt_secret, algorithms=["HS256"]
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid authentication token",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid authentication payload",
        )
    return payload


current_user_dependency = Depends(get_current_user)


def get_tenant_context(
    auth_payload: dict[str, str] = current_user_dependency,
) -> TenantContext:
    """Derive the caller's organization/workspace/project scope from the JWT.

    This is the only source of truth for scoping memory/conversation reads
    and writes — callers must never be able to pass an organization_id/
    workspace_id in a request body and have it override this, or one
    tenant could read another's agent/conversation memory.
    """
    return TenantContext(
        organization_id=auth_payload.get("organization_id")
        or auth_payload.get("organizationId"),
        workspace_id=auth_payload.get("workspace_id")
        or auth_payload.get("workspaceId"),
        project_id=auth_payload.get("project_id") or auth_payload.get("projectId"),
        user_id=auth_payload.get("user_id") or auth_payload.get("sub"),
    )
