from __future__ import annotations

import os

import pytest

from app.core.security import TenantContext
from app.tool_registry import MCPClient, ToolRegistry


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("AI_RXOS_LIVE_MCP_TESTS") != "1",
    reason="set AI_RXOS_LIVE_MCP_TESTS=1 to enable",
)
async def test_real_mcp_server_discovery_and_tool_invocation():
    url = os.getenv("AI_RXOS_MCP_URL")
    tool_name = os.getenv("AI_RXOS_MCP_TOOL")
    if not url or not tool_name:
        pytest.skip("AI_RXOS_MCP_URL and AI_RXOS_MCP_TOOL are required")

    client = MCPClient(url, headers={"Authorization": os.getenv("AI_RXOS_MCP_AUTH", "")})
    registry = ToolRegistry()
    await client.import_tools(
        registry,
        allowed_agents={"default"},
        allowed_organizations={os.getenv("AI_RXOS_MCP_ORGANIZATION", "live-org")},
        allowed_workspaces={os.getenv("AI_RXOS_MCP_WORKSPACE", "live-workspace")},
    )
    result = await registry.execute(
        tool_name,
        {},
        agent_name="default",
        tenant=TenantContext(
            organization_id=os.getenv("AI_RXOS_MCP_ORGANIZATION", "live-org"),
            workspace_id=os.getenv("AI_RXOS_MCP_WORKSPACE", "live-workspace"),
            user_id="live-test-user",
        ),
        execution_key="live-mcp-test",
    )
    assert result.name == tool_name
