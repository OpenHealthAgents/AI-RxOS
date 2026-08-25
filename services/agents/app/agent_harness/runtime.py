from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from app.core.observability import CostCalculator, ModelUsage, metrics, span
from app.core.security import TenantContext
from app.memory.llm_wiki import AgentMemory
from app.model_registry.registry import ModelRegistry
from app.model_registry.schemas import ModelRequest, ModelResponse
from app.prompt_registry.registry import PromptRegistry
from app.security.redaction import redact_event
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
        cost_calculator: CostCalculator | None = None,
    ) -> None:
        self.models = models
        self.prompts = prompts
        self.tools = tools
        self._memory: ContextVar[AgentMemory | None] = ContextVar(
            f"agent_memory_{id(self)}", default=None
        )
        self._event_sink: ContextVar[
            Callable[[dict[str, Any]], Awaitable[None]] | None
        ] = ContextVar(f"agent_event_sink_{id(self)}", default=None)
        self._construction_memory = memory
        self._construction_event_sink = event_sink
        self.telemetry_hook = telemetry_hook
        self.tenant = tenant
        self.cost_calculator = cost_calculator or CostCalculator(
            os.getenv("MODEL_PRICING_JSON")
        )
        self._agent_name: ContextVar[str | None] = ContextVar(
            f"agent_name_{id(self)}", default=None
        )
        self._tenant: ContextVar[TenantContext | None] = ContextVar(
            f"agent_tenant_{id(self)}", default=tenant
        )
        self._tool_call_number: ContextVar[int] = ContextVar(
            f"tool_call_number_{id(self)}", default=0
        )
        self._execution_id: ContextVar[str | None] = ContextVar(
            f"execution_id_{id(self)}", default=None
        )

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
    def event_sink(
        self, value: Callable[[dict[str, Any]], Awaitable[None]] | None
    ) -> None:
        self._event_sink.set(value)

    @property
    def agent_name(self) -> str | None:
        return self._agent_name.get()

    def set_agent_name(self, name: str | None) -> None:
        self._agent_name.set(name)

    @property
    def execution_id(self) -> str | None:
        return self._execution_id.get()

    def set_execution_id(self, execution_id: str | None) -> None:
        self._execution_id.set(execution_id)

    @property
    def current_tenant(self) -> TenantContext | None:
        return self._tenant.get()

    def attach_run_memory(
        self, run_id: str, *, tenant: TenantContext | None = None
    ) -> AgentMemory:
        configured_adapter = (
            self._construction_memory.long_term
            if self._construction_memory is not None
            else None
        )
        current = AgentMemory(
            run_id,
            tenant or self.tenant or TenantContext(),
            long_term=configured_adapter,
        )
        self._tenant.set(tenant or self.tenant or TenantContext())
        self.memory = current
        return current

    async def emit(self, event: dict[str, Any]) -> None:
        safe_event = redact_event(event)
        if self.telemetry_hook is not None:
            self.telemetry_hook(safe_event)
        if self.event_sink is not None:
            await self.event_sink(safe_event)

    @staticmethod
    def format_retrieved_context(context: Any) -> str:
        """Wrap untrusted retrieved context (e.g. from LLM Wiki) in structural XML tags.

        Note: Wrapping untrusted content in delimiters reduces but does not eliminate
        prompt injection risk — it is one defense-in-depth mitigation layer, not a complete solution.
        """
        if context is None:
            return ""
        if isinstance(context, (dict, list)):
            content_str = json.dumps(context)
        else:
            content_str = str(context)
        return f"<retrieved_context>\n{content_str}\n</retrieved_context>"

    def build_structured_messages(
        self,
        system_instruction: str,
        user_input: str | None = None,
        retrieved_context: Any | None = None,
        extra_messages: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Construct structured model messages separating system instructions into a dedicated 'system' role
        and wrapping untrusted retrieved data in structural XML delimiters.

        Note: Structural role separation and XML delimiting reduce prompt injection vulnerability
        by establishing explicit role boundaries for the model. This is one mitigation layer, not a complete solution.
        """
        messages: list[dict[str, Any]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction.strip()})

        user_content_parts: list[str] = []
        if user_input:
            user_content_parts.append(str(user_input).strip())
        if retrieved_context is not None:
            formatted_context = self.format_retrieved_context(retrieved_context)
            if formatted_context:
                user_content_parts.append(formatted_context)

        if user_content_parts:
            messages.append(
                {"role": "user", "content": "\n\n".join(user_content_parts)}
            )

        if extra_messages:
            messages.extend(extra_messages)

        return messages

    async def render_prompt(
        self,
        name: str,
        variables: dict[str, Any] | None = None,
        *,
        version: int | None = None,
    ) -> str:
        return await self.prompts.render(name, variables, version=version)

    async def call_model(self, request: ModelRequest) -> ModelResponse:
        started = time.perf_counter()
        try:
            with span("model.provider", model="configured"):
                response = await self.models.complete(request)
            metrics.inc(
                "agent_model_requests_total",
                provider=response.provider,
                model=response.model,
                status="success",
            )
        except Exception:
            metrics.inc("agent_model_failures_total", status="error")
            raise
        metrics.observe(
            "agent_model_duration_seconds",
            time.perf_counter() - started,
            status="success",
        )
        usage = ModelUsage.from_raw(response.raw)
        if usage is not None:
            estimated_cost = self.cost_calculator.estimate(
                response.provider, response.model, usage
            )
            if estimated_cost is not None:
                metrics.observe(
                    "agent_model_estimated_cost",
                    estimated_cost,
                    provider=response.provider,
                    model=response.model,
                )
            await self.emit(
                {
                    "type": "model_usage",
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                }
            )
        await self.emit(
            {
                "type": "model_output",
                "model": response.model,
                "content": response.content,
            }
        )
        return response

    async def stream_model(self, request: ModelRequest) -> AsyncIterator[str]:
        async for token in self.models.stream(request):
            await self.emit({"type": "token", "content": token})
            yield token

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> ToolExecutionResult:
        definition = self.tools.get(name)
        call_number = self._tool_call_number.get() + 1
        self._tool_call_number.set(call_number)
        argument_fingerprint = hashlib.sha256(
            json.dumps(arguments, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        tool_call_id = f"{name}:{argument_fingerprint}"
        await self.emit(
            {
                "type": "tool_call",
                "name": name,
                "tool_call_id": tool_call_id,
                "retry_mode": definition.retry_mode,
            }
        )
        tenant = self.current_tenant
        execution_key = (
            f"{tenant.organization_id if tenant else '_none'}:{tool_call_id}:{name}"
        )
        started = time.perf_counter()
        try:
            with span(
                "agent.tool", tool_name=name, agent_type=self.agent_name or "unknown"
            ):
                result = await self.tools.execute(
                    name,
                    arguments,
                    agent_name=self.agent_name,
                    tenant=tenant,
                    execution_key=execution_key,
                    execution_id=self.execution_id,
                )
            metrics.inc("agent_tool_calls_total", tool_name=name, status="success")
        except Exception:
            metrics.inc("agent_tool_failures_total", tool_name=name, status="error")
            raise
        metrics.observe(
            "agent_tool_duration_seconds",
            time.perf_counter() - started,
            tool_name=name,
            status="success",
        )
        await self.emit({"type": "tool_result", "name": name, "result": result.result})
        return result
