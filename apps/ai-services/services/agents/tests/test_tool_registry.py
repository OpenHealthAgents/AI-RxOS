from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest

from app.agent_harness import (
    AgentRuntime,
    AgentState,
    InMemoryCheckpointStore,
    StateGraph,
)
from app.core.security import TenantContext
from app.tool_registry import (
    MCPClient,
    SchemaValidationError,
    ToolExecutionContext,
    ToolRegistry,
)

TEST_TENANT = TenantContext(organization_id="org-test", user_id="user-test")

OBJECT_SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": "integer"}},
    "required": ["value"],
    "additionalProperties": False,
}


@pytest.mark.asyncio
async def test_register_executes_async_handler_and_validates_input_output():
    registry = ToolRegistry()

    async def double(arguments):
        return {"result": arguments["value"] * 2}

    registry.register(
        "double",
        OBJECT_SCHEMA,
        double,
        output_schema={
            "type": "object",
            "properties": {"result": {"type": "integer"}},
            "required": ["result"],
        },
    )

    execution = await registry.execute(
        "double", {"value": 4}, agent_name="default", tenant=TEST_TENANT
    )

    assert execution.result == {"result": 8}
    with pytest.raises(SchemaValidationError):
        await registry.execute(
            "double", {"value": "4"}, agent_name="default", tenant=TEST_TENANT
        )


@pytest.mark.asyncio
async def test_tool_executor_accepts_reusable_execution_context():
    registry = ToolRegistry()
    registry.register(
        "echo",
        OBJECT_SCHEMA,
        lambda arguments: {"reply": arguments["value"]},
        output_schema={"type": "object", "properties": {"reply": {"type": "integer"}}, "required": ["reply"]},
    )

    result = await registry.execute(
        "echo",
        {"value": 7},
        context=ToolExecutionContext(
            tool_name="echo",
            agent_name="default",
            tenant=TEST_TENANT,
            execution_id="exec-123",
            correlation_id="corr-456",
            request_id="req-789",
        ),
    )

    assert result.result == {"reply": 7}


@pytest.mark.asyncio
async def test_output_schema_rejects_invalid_handler_result():
    registry = ToolRegistry()
    registry.register(
        "bad", {}, lambda _: "not-an-object", output_schema={"type": "object"}
    )

    with pytest.raises(SchemaValidationError):
        await registry.execute("bad", {}, agent_name="default", tenant=TEST_TENANT)


@pytest.mark.asyncio
async def test_restricted_tool_denies_wrong_agent():
    registry = ToolRegistry()
    registry.register("restricted", {}, lambda _: "ok", allowed_agents={"writer"})

    with pytest.raises(Exception) as error:
        await registry.execute("restricted", {}, agent_name="researcher")
    assert getattr(error.value, "code", None) == "TOOL_NOT_AUTHORIZED"


@pytest.mark.asyncio
async def test_sync_tool_timeout_is_enforced():
    registry = ToolRegistry()

    def slow(_arguments):
        import time

        time.sleep(0.2)
        return "done"

    registry.register("slow", {}, slow, timeout_seconds=0.01)

    with pytest.raises(Exception) as error:
        await registry.execute("slow", {}, agent_name="default", tenant=TEST_TENANT)
    assert getattr(error.value, "code", None) == "TIMEOUT"


@pytest.mark.asyncio
async def test_tool_retry_mode_requires_stable_execution_key_when_declared():
    registry = ToolRegistry()
    registry.register(
        "side-effect",
        {},
        lambda _: "ok",
        retry_mode="requires_idempotency_key",
    )

    with pytest.raises(Exception) as error:
        await registry.execute(
            "side-effect", {}, agent_name="default", tenant=TEST_TENANT
        )
    assert getattr(error.value, "code", None) == "TOOL_NOT_AUTHORIZED"
    result = await registry.execute(
        "side-effect",
        {},
        agent_name="default",
        tenant=TEST_TENANT,
        execution_key="org-test:job-1:tool-1",
    )
    assert result.result == "ok"


@pytest.mark.asyncio
async def test_mcp_client_imports_and_calls_exposed_tool():
    requests: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.content
        import json

        payload = json.loads(body)
        requests.append(payload)
        if payload["method"] == "initialize":
            result = {"protocolVersion": "2024-11-05"}
        elif payload["method"] == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "echo",
                        "description": "Echo text",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"],
                        },
                    }
                ]
            }
        else:
            result = {
                "structuredContent": {"echo": payload["params"]["arguments"]["text"]}
            }
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": result},
            request=request,
        )

    client = MCPClient(
        "https://mcp.test",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    registry = ToolRegistry()

    assert await client.import_tools(registry) == ["echo"]
    execution = await registry.execute(
        "echo", {"text": "hello"}, agent_name="default", tenant=TEST_TENANT
    )

    assert execution.result == {"echo": "hello"}
    assert [request["method"] for request in requests] == [
        "initialize",
        "tools/list",
        "tools/call",
    ]


@pytest.mark.asyncio
async def test_agent_runtime_uses_registry_authorization_before_mcp():
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["method"] == "initialize":
            result = {"protocolVersion": "2024-11-05"}
        elif payload["method"] == "tools/list":
            result = {"tools": [{"name": "secure", "inputSchema": {"type": "object"}}]}
        else:
            result = {"structuredContent": {"ok": True}}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result}, request=request)

    client = MCPClient(
        "https://mcp.test",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    registry = ToolRegistry()
    await client.import_tools(
        registry,
        allowed_agents={"agent"},
        allowed_organizations={"org-test"},
    )
    runtime = AgentRuntime(models=object(), prompts=object(), tools=registry)

    async def node(_state, dependencies):
        result = await dependencies.call_tool("secure", {},)
        return {"result": result.result}

    graph = StateGraph().add_node("agent", node).set_entry_point("agent").compile(InMemoryCheckpointStore())
    result = await graph.run(
        runtime,
        state=AgentState(
            data={"tenant": TEST_TENANT.as_dict()},
        ),
    )

    assert result.data["result"] == {"ok": True}

    with pytest.raises(Exception) as error:
        await registry.execute(
            "secure", {}, agent_name="default", tenant=TenantContext(organization_id="other", user_id="user-test")
        )
    assert getattr(error.value, "code", None) == "TOOL_NOT_AUTHORIZED"


@pytest.mark.asyncio
async def test_mcp_malformed_response_is_safe():
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": []},
            request=request,
        )

    client = MCPClient(
        "https://mcp.test",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(Exception, match="invalid result"):
        await client.list_tools()


@pytest.mark.asyncio
async def test_mcp_timeout_is_bounded_and_does_not_expose_payload():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret response payload", request=request)

    client = MCPClient(
        "https://mcp.test",
        timeout_seconds=0.01,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(Exception) as error:
        await client.list_tools()
    assert "secret response payload" not in str(error.value)


@pytest.mark.asyncio
async def test_mcp_client_local_http_smoke_path():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            request = json.loads(self.rfile.read(length))
            if request["method"] == "initialize":
                result = {"protocolVersion": "2024-11-05"}
            elif request["method"] == "tools/list":
                result = {
                    "tools": [
                        {
                            "name": "add",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"value": {"type": "integer"}},
                                "required": ["value"],
                            },
                        }
                    ]
                }
            else:
                result = {
                    "structuredContent": {
                        "value": request["params"]["arguments"]["value"] + 1
                    }
                }
            body = json.dumps(
                {"jsonrpc": "2.0", "id": request["id"], "result": result}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = MCPClient(f"http://127.0.0.1:{server.server_port}")
        registry = ToolRegistry()
        assert await client.import_tools(registry) == ["add"]
        result = await registry.execute(
            "add", {"value": 2}, agent_name="default", tenant=TEST_TENANT
        )
        assert result.result == {"value": 3}
    finally:
        server.shutdown()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_mcp_session_is_reused_across_list_and_call_requests():
    methods: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        methods.append(payload["method"])
        if payload["method"] == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "session-1"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2024-11-05"},
                },
                request=request,
            )
        if payload["method"] == "tools/list":
            result = {"tools": [{"name": "echo", "inputSchema": {"type": "object"}}]}
        else:
            result = {
                "structuredContent": {"echo": payload["params"]["arguments"]["value"]}
            }
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": result},
            request=request,
        )

    client = MCPClient(
        "https://mcp.test",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    registry = ToolRegistry()
    await client.import_tools(registry)
    await registry.execute(
        "echo", {"value": "one"}, agent_name="default", tenant=TEST_TENANT
    )
    await registry.execute(
        "echo", {"value": "two"}, agent_name="default", tenant=TEST_TENANT
    )

    assert methods == ["initialize", "tools/list", "tools/call", "tools/call"]


@pytest.mark.asyncio
async def test_mcp_session_reconnects_after_transport_failure():
    methods: list[str] = []
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        payload = json.loads(request.content)
        methods.append(payload["method"])
        if payload["method"] == "initialize":
            session = f"session-{methods.count('initialize')}"
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": session},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2024-11-05"},
                },
                request=request,
            )
        if payload["method"] == "tools/list":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": payload["id"], "result": {"tools": []}},
                request=request,
            )
        call_count += 1
        if call_count == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"structuredContent": {"ok": True}},
            },
            request=request,
        )

    client = MCPClient(
        "https://mcp.test",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    result = await client.call_tool("recover", {})

    assert result == {"ok": True}
    assert methods == ["initialize", "tools/call", "initialize", "tools/call"]


@pytest.mark.asyncio
async def test_mcp_streaming_tool_result_is_forwarded_to_event_sink():
    events: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["method"] == "initialize":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2024-11-05"},
                },
                request=request,
            )
        stream = (
            'data: {"content":[{"type":"text","text":"hello"}]}\n\n'
            'data: {"content":[{"type":"text","text":" world"}]}\n\n'
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=stream,
            request=request,
        )

    async def sink(event):
        events.append(event)

    client = MCPClient(
        "https://mcp.test",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        event_sink=sink,
    )
    result = await client.call_tool("streaming", {})

    assert result == "hello world"
    assert events == [
        {"type": "mcp_tool_chunk", "name": "streaming", "status": "completed"},
        {"type": "mcp_tool_chunk", "name": "streaming", "status": "completed"},
    ]
