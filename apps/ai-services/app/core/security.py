from __future__ import annotations

from typing import Any

import jwt
from fastapi import Request
from jwt import PyJWTError

from app.core.config import Settings


def _claims_set(value: Any) -> set[str]:
    if isinstance(value, str):
        return {item.strip().lower() for item in value.split(",") if item.strip()}
    if isinstance(value, list):
        return {item.strip().lower() for item in value if isinstance(item, str) and item.strip()}
    return set()


async def trusted_identity_middleware(request: Request, call_next):
    settings: Settings = request.app.state.security_settings
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        try:
            claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
            user_id = claims.get("sub") or claims.get("user_id") or claims.get("userId")
            tenant_id = claims.get("organization_id") or claims.get("organizationId")
            scope = _claims_set(claims.get("scope"))
            roles = _claims_set(claims.get("roles"))
            permissions = _claims_set(claims.get("permissions"))

            trusted_user_id = user_id.strip() if isinstance(user_id, str) and user_id.strip() else None
            trusted_tenant_id = tenant_id.strip() if isinstance(tenant_id, str) and tenant_id.strip() else None
            if trusted_user_id:
                request.state.user_id = trusted_user_id
            if trusted_tenant_id:
                request.state.tenant_id = trusted_tenant_id
            request.state.roles = roles
            request.state.permissions = permissions
            request.state.authenticated = trusted_user_id is not None
            request.state.system_scope = "system" in scope and "ai-services:system" in permissions
        except PyJWTError:
            return _unauthorized()

    if request.url.path.startswith("/api/") and settings.environment.lower() in {"production", "prod"}:
        if not getattr(request.state, "authenticated", False):
            return _unauthorized()
        if not getattr(request.state, "tenant_id", None) and not getattr(request.state, "system_scope", False):
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=403,
                content={"detail": "authenticated tenant context is required"},
            )

    return await call_next(request)


def _unauthorized():
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=401, content={"detail": "valid bearer authentication is required"})


def require_review_permission(request: Request) -> tuple[str, str]:
    from fastapi import HTTPException, status

    if not getattr(request.state, "authenticated", False):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    tenant_id = getattr(request.state, "tenant_id", None)
    user_id = getattr(request.state, "user_id", None)
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="trusted tenant context is required")
    if not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="trusted user context is required")

    roles = getattr(request.state, "roles", set())
    permissions = getattr(request.state, "permissions", set())
    normalized_roles = {role.replace("-", "_").replace(" ", "_") for role in roles}
    if not ({"reviewer", "admin", "owner"} & normalized_roles or "evidence:review" in permissions):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="review permission required")
    return tenant_id.strip(), user_id.strip()
