from __future__ import annotations

from typing import Any

import httpx

from app.tool_registry.registry import ToolRegistry


class MCPProtocolError(RuntimeError):
    pass


class MCPClient:
    """Minimal MCP JSON-RPC client for initialize, tools/list, and tools/call."""

    def __init__(self, url: str, *, headers: dict[str, str] | None = None, timeout_seconds: float = 30.0, client: httpx.AsyncClient | None = None) -> None:
        self.url = url
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.timeout_seconds = timeout_seconds
        self.client = client
        self._request_id = 0

    async def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._request_id += 1
        payload = {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params or {}}
        http_client = self.client or httpx.AsyncClient(timeout=self.timeout_seconds)
        close_client = self.client is None
        try:
            response = await http_client.post(self.url, headers=self.headers, json=payload)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MCPProtocolError(f"MCP request {method} failed: {exc}") from exc
        finally:
            if close_client:
                await http_client.aclose()
        if "error" in body:
            raise MCPProtocolError(f"MCP {method} error: {body['error']}")
        if not isinstance(body.get("result"), dict):
            raise MCPProtocolError(f"MCP {method} returned no result")
        return body["result"]

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._request("tools/list")
        tools = result.get("tools", [])
        if not isinstance(tools, list):
            raise MCPProtocolError("MCP tools/list returned invalid tools")
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = await self._request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise MCPProtocolError(f"MCP tool {name} returned an error")
        content = result.get("structuredContent")
        if content is not None:
            return content
        items = result.get("content", [])
        texts = [item.get("text", "") for item in items if item.get("type") == "text"]
        return texts[0] if len(texts) == 1 else texts

    async def import_tools(self, registry: ToolRegistry, *, namespace: str | None = None) -> list[str]:
        await self._request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "ai-rxos-agents", "version": "0.1.0"}})
        imported: list[str] = []
        for tool in await self.list_tools():
            remote_name = tool.get("name")
            if not isinstance(remote_name, str) or not remote_name:
                raise MCPProtocolError("MCP tool is missing a name")
            name = f"{namespace}.{remote_name}" if namespace else remote_name
            registry.register(
                name,
                tool.get("inputSchema") or {},
                lambda arguments, remote_name=remote_name: self.call_tool(remote_name, arguments),
                output_schema=tool.get("outputSchema"),
                description=tool.get("description", ""),
                source=f"mcp:{self.url}",
            )
            imported.append(name)
        return imported