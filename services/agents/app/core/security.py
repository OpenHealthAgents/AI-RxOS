"""JWT verification and tenant-scope extraction for the agents service.

services/agents had no auth wiring at all prior to this (every endpoint was
unauthenticated). This mirrors services/literature's app/core/security.py
pattern (same JWT secret convention, same claim names) rather than inventing
a third auth shape — see services/auth/src/tenantContext.ts::AuthPayload for
the canonical {sub, organizationId, roles} claim shape this aligns with.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    roles: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()

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

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = security_dependency,
) -> dict[str, Any]:
    settings = get_settings()
    production = settings.environment.lower() in {"production", "prod"}
    if settings.environment == "test" and credentials is None:
        return {"sub": "test-user-fallback"}

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer if production else None,
            audience=settings.jwt_audience if production else None,
            options={
                "require": ["exp", "iss", "aud"]
                if production
                else []
            },
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
    auth_payload: dict[str, Any] = current_user_dependency,
) -> TenantContext:
    """Derive the caller's organization/workspace/project scope from the JWT.

    This is the only source of truth for scoping memory/conversation reads
    and writes — callers must never be able to pass an organization_id/
    workspace_id in a request body and have it override this, or one
    tenant could read another's agent/conversation memory.
    """

    def claim_set(name: str) -> frozenset[str]:
        value: Any = auth_payload.get(name, [])
        if isinstance(value, str):
            return frozenset(item.strip() for item in value.split(",") if item.strip())
        return frozenset(value)

    return TenantContext(
        organization_id=auth_payload.get("organization_id")
        or auth_payload.get("organizationId"),
        workspace_id=auth_payload.get("workspace_id")
        or auth_payload.get("workspaceId"),
        project_id=auth_payload.get("project_id") or auth_payload.get("projectId"),
        user_id=auth_payload.get("user_id") or auth_payload.get("sub"),
        roles=claim_set("roles"),
        permissions=claim_set("permissions"),
    )


class AuthorizationService:
    """Central authorization policy for agent, tool, and tenant resources."""

    def can_execute_agent(
        self,
        tenant: TenantContext,
        agent_name: str,
        allowed_agents: set[str] | frozenset[str],
    ) -> bool:
        return bool(
            tenant.user_id and tenant.organization_id and agent_name in allowed_agents
        )

    def can_execute_tool(
        self,
        tenant: TenantContext,
        agent_name: str | None,
        allowed_agents: frozenset[str],
        required_permissions: frozenset[str],
    ) -> bool:
        return bool(
            tenant.user_id
            and tenant.organization_id
            and agent_name
            and (not allowed_agents or agent_name in allowed_agents)
            and required_permissions.issubset(tenant.permissions)
        )

    def can_access_job(self, tenant: TenantContext, job_tenant: dict[str, str]) -> bool:
        return bool(tenant.user_id and tenant.as_dict() == job_tenant)

    def can_access_conversation(
        self, tenant: TenantContext, owner: dict[str, str]
    ) -> bool:
        return bool(tenant.user_id and tenant.as_dict() == owner)

    def can_access_memory(self, tenant: TenantContext, owner: dict[str, str]) -> bool:
        return bool(tenant.user_id and tenant.as_dict() == owner)

    def can_replay_job(self, tenant: TenantContext, owner: dict[str, str]) -> bool:
        return bool(
            tenant.user_id
            and tenant.as_dict() == owner
            and (
                "agents:dlq:replay" in tenant.permissions
                or "operator" in tenant.roles
                or "admin" in tenant.roles
            )
        )
