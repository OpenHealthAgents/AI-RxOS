from __future__ import annotations

from fastapi import HTTPException, Request, status


def _trusted_tenant_id(request: Request) -> str | None:
    """Read tenant scope only from trusted request context, never from query input."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        return None
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid tenant context.",
        )
    return tenant_id.strip()
