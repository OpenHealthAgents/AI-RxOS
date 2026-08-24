from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.tool_registry.registry import ToolRegistry


class MCPProtocolError(RuntimeError):
    pass


class MCPClient:
    """Minimal MCP JSON-RPC client for initialize, tools/list, and tools/call."""

    def __init__(self, url: str, *, headers: dict[str, str] | None = None, timeout_seconds: float = 30.0, client: httpx.AsyncClient | None = None, event_sink=None) -> None:
        self.url = url
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.timeout_seconds = timeout_seconds
        self.client = client
        self.event_sink = event_sink
        self._request_id = 0
        self._session_id: str | None = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._owned_client: httpx.AsyncClient | None = None

    async def _http_client(self) -> httpx.AsyncClient:
        if self.client is not None:
            return self.client
        if self._owned_client is None:
            self._owned_client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._owned_client

    async def _request_once(self, method: str, params: dict[str, Any] | None = None, *, stream: bool = False) -> httpx.Response:
        self._request_id += 1
        payload = {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params or {}}
        request_headers = dict(self.headers)
        if self._session_id:
            request_headers["Mcp-Session-Id"] = self._session_id
        http_client = await self._http_client()
        response = await http_client.post(self.url, headers=request_headers, json=payload)
        response.raise_for_status()
        if method == "initialize":
            self._session_id = response.headers.get("Mcp-Session-Id")
        return response

    async def _initialize(self) -> None:
        async with self._init_lock:
            if self._initialized:
                return
            try:
                response = await self._request_once(
                    "initialize",
                    {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "ai-rxos-agents", "version": "0.1.0"}},
                )
                body = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise MCPProtocolError("MCP initialize failed") from exc
            if "error" in body or not isinstance(body.get("result"), dict):
                raise MCPProtocolError(f"MCP initialize error: {body.get('error', 'invalid result')}")
            self._initialized = True

    async def _reset_session(self) -> None:
        self._initialized = False
        self._session_id = None

    async def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        await self._initialize()
        try:
            response = await self._request_once(method, params)
            body = response.json()
        except (httpx.HTTPError, ValueError) as first_error:
            await self._reset_session()
            try:
                await self._initialize()
                response = await self._request_once(method, params)
                body = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise MCPProtocolError(f"MCP request {method} failed after reconnect: {exc}") from first_error
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
        await self._initialize()
        params = {"name": name, "arguments": arguments}
        try:
            response = await self._request_once("tools/call", params, stream=True)
            if "text/event-stream" in response.headers.get("content-type", ""):
                return await self._consume_stream(name, response)
            body = response.json()
        except (httpx.HTTPError, ValueError) as first_error:
            await self._reset_session()
            try:
                await self._initialize()
                response = await self._request_once("tools/call", params, stream=True)
                if "text/event-stream" in response.headers.get("content-type", ""):
                    return await self._consume_stream(name, response)
                body = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise MCPProtocolError(f"MCP tool {name} failed after reconnect: {exc}") from first_error
        if "error" in body:
            raise MCPProtocolError(f"MCP tools/call error: {body['error']}")
        result = body.get("result")
        if not isinstance(result, dict):
            raise MCPProtocolError(f"MCP tools/call returned no result for {name}")
        if result.get("isError"):
            raise MCPProtocolError(f"MCP tool {name} returned an error")
        content = result.get("structuredContent")
        if content is not None:
            return content
        items = result.get("content", [])
        texts = [item.get("text", "") for item in items if item.get("type") == "text"]
        return texts[0] if len(texts) == 1 else texts

    async def _consume_stream(self, name: str, response: httpx.Response) -> Any:
        chunks: list[str] = []
        structured: Any = None
        for line in response.text.splitlines():
            if not line.startswith("data:"):
                continue
            try:
                event = json.loads(line[5:].strip())
            except json.JSONDecodeError as exc:
                raise MCPProtocolError(f"invalid MCP stream event for {name}") from exc
            result = event.get("result", event)
            if result.get("structuredContent") is not None:
                structured = result["structuredContent"]
            for item in result.get("content", []):
                text = item.get("text") if isinstance(item, dict) else None
                if text:
                    chunks.append(text)
                    if self.event_sink is not None:
                        await self.event_sink({"type": "mcp_tool_chunk", "name": name, "content": text})
            text = result.get("text") or result.get("delta")
            if text:
                chunks.append(text)
                if self.event_sink is not None:
                    await self.event_sink({"type": "mcp_tool_chunk", "name": name, "content": text})
        return structured if structured is not None else "".join(chunks)

    async def import_tools(self, registry: ToolRegistry, *, namespace: str | None = None) -> list[str]:
        await self._initialize()
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

    async def aclose(self) -> None:
        if self._owned_client is not None:
            await self._owned_client.aclose()
            self._owned_client = None