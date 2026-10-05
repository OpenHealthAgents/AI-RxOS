from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.canonical_security import CanonicalPrincipal


class Neo4jAuthorizationError(PermissionError):
    """Raised when a graph operation has no explicit authorized scope."""


@dataclass(frozen=True)
class Neo4jScope:
    organization_id: UUID | None
    system: bool = False

    @property
    def tenant_id(self) -> str | None:
        return str(self.organization_id) if self.organization_id else None


def tenant_scope(principal: CanonicalPrincipal) -> Neo4jScope:
    if principal.organization_id is None:
        if "graph:system" in principal.permissions or "system" in principal.roles:
            return Neo4jScope(None, system=True)
        raise Neo4jAuthorizationError("tenant context required")
    return Neo4jScope(principal.organization_id)


def system_scope(principal: CanonicalPrincipal) -> Neo4jScope:
    if "graph:system" not in principal.permissions and "system" not in principal.roles:
        raise Neo4jAuthorizationError("explicit graph system scope required")
    return Neo4jScope(principal.organization_id, system=True)


def visibility_predicate(variable: str, scope_parameter: str = "organization_id") -> str:
    return (
        f"(${scope_parameter} IS NOT NULL AND "
        f"(coalesce({variable}.visibility, 'global') = 'global' OR "
        f"coalesce({variable}.organization_id, {variable}.tenant_id) = ${scope_parameter}))"
    )


def require_scope(scope: Neo4jScope | None) -> Neo4jScope:
    if scope is None:
        raise Neo4jAuthorizationError("explicit graph scope required")
    if not scope.system and scope.organization_id is None:
        raise Neo4jAuthorizationError("tenant context required")
    return scope