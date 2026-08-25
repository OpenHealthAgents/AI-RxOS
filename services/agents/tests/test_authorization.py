from __future__ import annotations

import pytest

from app.core.errors import AIPlatformError
from app.core.security import AuthorizationService, TenantContext
from app.tool_registry import ToolRegistry


@pytest.mark.parametrize(
    "tenant, expected",
    [
        (TenantContext(organization_id="org-a", user_id="user-a"), True),
        (TenantContext(organization_id="org-a"), False),
        (TenantContext(organization_id="org-b", user_id="user-a"), True),
    ],
)
def test_agent_authorization_defaults_to_deny(tenant, expected):
    service = AuthorizationService()
    assert service.can_execute_agent(tenant, "research", {"research"}) is expected


def test_tool_permission_and_workspace_scope_are_enforced():
    registry = ToolRegistry()
    registry.register(
        "private-search",
        {},
        lambda _arguments: "ok",
        allowed_agents={"research"},
        required_permissions={"knowledge:read"},
        allowed_organizations={"org-a"},
        allowed_workspaces={"ws-a"},
    )
    authorized = TenantContext(
        organization_id="org-a",
        workspace_id="ws-a",
        user_id="user-a",
        permissions=frozenset({"knowledge:read"}),
    )

    async def execute() -> None:
        result = await registry.execute(
            "private-search",
            {},
            agent_name="research",
            tenant=authorized,
        )
        assert result.result == "ok"
        with pytest.raises(AIPlatformError, match="not authorized"):
            await registry.execute(
                "private-search",
                {},
                agent_name="writer",
                tenant=authorized,
            )
        with pytest.raises(AIPlatformError, match="not authorized"):
            await registry.execute(
                "private-search",
                {},
                agent_name="research",
                tenant=TenantContext(
                    organization_id="org-a", workspace_id="ws-a", user_id="user-a"
                ),
            )
        with pytest.raises(AIPlatformError, match="not authorized"):
            await registry.execute(
                "private-search",
                {},
                agent_name="research",
                tenant=TenantContext(
                    organization_id="org-b",
                    workspace_id="ws-a",
                    user_id="user-a",
                    permissions=frozenset({"knowledge:read"}),
                ),
            )

    import asyncio

    asyncio.run(execute())


def test_missing_tool_authorization_context_is_denied():
    registry = ToolRegistry()
    registry.register(
        "restricted", {}, lambda _arguments: "ok", allowed_agents={"default"}
    )

    async def execute() -> None:
        with pytest.raises(AIPlatformError, match="not authorized"):
            await registry.execute("restricted", {}, agent_name="default")

    import asyncio

    asyncio.run(execute())
