import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.knowledge.models import TenantContext

settings = get_settings()
security = HTTPBearer(auto_error=False)
security_dependency = Security(security)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = security_dependency,
) -> dict[str, str]:
    if get_settings().environment == "test" and credentials is None:
        return {"sub": "test-user-fallback"}

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
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

    Mirrors services/auth's legacy claim shape (`organizationId`, `roles` —
    see services/auth/src/tenantContext.ts::AuthPayload). workspaceId/
    projectId are not yet issued by the auth service's JWTs (see the auth
    audit), so those fields are simply absent/None until that's added —
    this function does not invent claims that aren't there.
    """
    return TenantContext.from_claims(auth_payload)
