from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from app.model_registry.registry import ModelRegistry
from app.model_registry.schemas import ModelRequest, ModelResponse
from app.memory.llm_wiki import AgentMemory, create_agent_memory
from app.core.security import TenantContext
from app.prompt_registry.registry import PromptRegistry
from app.tool_registry.registry import ToolRegistry
from app.tool_registry.schemas import ToolExecutionResult


class AgentRuntime:
    """Explicit dependency bundle for graph nodes; no provider is hardcoded."""

    def __init__(
        self,
        *,
        models: ModelRegistry,
        prompts: PromptRegistry,
        tools: ToolRegistry,
        memory: AgentMemory | None = None,
        event_sink: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        telemetry_hook: Callable[[dict[str, Any]], None] | None = None,
        tenant: TenantContext | None = None,
    ) -> None:
        self.models = models
        self.prompts = prompts
        self.tools = tools
        self._memory: ContextVar[AgentMemory | None] = ContextVar(f"agent_memory_{id(self)}", default=None)
        self._event_sink: ContextVar[Callable[[dict[str, Any]], Awaitable[None]] | None] = ContextVar(f"agent_event_sink_{id(self)}", default=None)
        self._construction_memory = memory
        self._construction_event_sink = event_sink
        self.telemetry_hook = telemetry_hook
        self.tenant = tenant

    @property
    def memory(self) -> AgentMemory | None:
        return self._memory.get()

    @memory.setter
    def memory(self, value: AgentMemory | None) -> None:
        self._memory.set(value)

    @property
    def event_sink(self) -> Callable[[dict[str, Any]], Awaitable[None]] | None:
        return self._event_sink.get()

    @event_sink.setter
    def event_sink(self, value: Callable[[dict[str, Any]], Awaitable[None]] | None) -> None:
        self._event_sink.set(value)

    def attach_run_memory(self, run_id: str) -> AgentMemory:
        configured_adapter = self._construction_memory.long_term if self._construction_memory is not None else None
        current = AgentMemory(
            run_id,
            self.tenant or TenantContext(),
            long_term=configured_adapter,
        )
        self.memory = current
        return current

    async def emit(self, event: dict[str, Any]) -> None:
        if self.telemetry_hook is not None:
            self.telemetry_hook(event)
        if self.event_sink is not None:
            await self.event_sink(event)

    async def render_prompt(
        self, name: str, variables: dict[str, Any] | None = None, *, version: int | None = None
    ) -> str:
        return await self.prompts.render(name, variables, version=version)

    async def call_model(self, request: ModelRequest) -> ModelResponse:
        response = await self.models.complete(request)
        await self.emit({"type": "model_output", "model": response.model, "content": response.content})
        return response

    async def stream_model(self, request: ModelRequest) -> AsyncIterator[str]:
        async for token in self.models.stream(request):
            await self.emit({"type": "token", "content": token})
            yield token

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        await self.emit({"type": "tool_call", "name": name, "arguments": arguments})
        result = await self.tools.execute(name, arguments)
        await self.emit({"type": "tool_result", "name": name, "result": result.result})
        return result