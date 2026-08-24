from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.agent_harness.checkpoints import CheckpointStore
from app.agent_harness.runtime import AgentRuntime
from app.agent_harness.schemas import AgentState, RetryPolicy
from app.core.errors import AIPlatformError
from app.core.security import TenantContext
from app.memory.llm_wiki import AgentMemory

logger = logging.getLogger(__name__)

END = "__end__"
NodeHandler = Callable[[AgentState, AgentRuntime], AgentState | dict[str, Any] | Awaitable[AgentState | dict[str, Any]]]
RouteHandler = Callable[[AgentState], str | Awaitable[str]]


class GraphConfigurationError(ValueError):
    pass


class AgentExecutionError(AIPlatformError):
    def __init__(self, message: str, *, node: str | None = None) -> None:
        super().__init__(message, code="AGENT_EXECUTION_ERROR", operation="agent_run", retriable=True, details={"node": node})


class StateGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, tuple[NodeHandler, RetryPolicy]] = {}
        self._edges: dict[str, str] = {}
        self._conditional: dict[str, tuple[RouteHandler, dict[str, str]]] = {}
        self._entry: str | None = None

    def add_node(self, name: str, handler: NodeHandler, *, retry: RetryPolicy | None = None) -> "StateGraph":
        if name in self._nodes or name == END:
            raise GraphConfigurationError(f"node already exists or is reserved: {name}")
        self._nodes[name] = (handler, retry or RetryPolicy())
        return self

    def set_entry_point(self, name: str) -> "StateGraph":
        self._entry = name
        return self

    def add_edge(self, source: str, target: str) -> "StateGraph":
        self._edges[source] = target
        return self

    def add_conditional_edges(self, source: str, router: RouteHandler, mapping: dict[str, str]) -> "StateGraph":
        self._conditional[source] = (router, mapping)
        return self

    def compile(self, checkpoint_store: CheckpointStore) -> "AgentGraph":
        if self._entry is None or self._entry not in self._nodes:
            raise GraphConfigurationError("entry point must reference a registered node")
        for source, target in {**self._edges, **{s: t for s, (_, m) in self._conditional.items() for t in m.values()}}.items():
            if source not in self._nodes or target != END and target not in self._nodes:
                raise GraphConfigurationError(f"invalid edge: {source} -> {target}")
        return AgentGraph(self._nodes, self._edges, self._conditional, self._entry, checkpoint_store)


class AgentGraph:
    def __init__(self, nodes, edges, conditional, entry, checkpoint_store) -> None:
        self._nodes = nodes
        self._edges = edges
        self._conditional = conditional
        self._entry = entry
        self._checkpoints = checkpoint_store

    async def run(
        self,
        runtime: AgentRuntime,
        *,
        state: AgentState | None = None,
        resume_run_id: str | None = None,
        event_sink=None,
    ) -> AgentState:
        if resume_run_id:
            state = await self._checkpoints.load(resume_run_id)
            if state is None:
                raise AgentExecutionError(f"checkpoint not found: {resume_run_id}")
        state = state or AgentState()
        if state.status == "completed":
            return state
        if isinstance(runtime, AgentRuntime):
            runtime.attach_run_memory(state.run_id)
            if event_sink is not None:
                runtime.event_sink = event_sink
        state.current_node = state.current_node or self._entry
        state.status = "running"
        state.error = None
        await self._checkpoints.save(state)
        await self._emit(runtime, {"type": "run_started", "run_id": state.run_id})
        logger.info("agent_run_started", extra={"event": "agent_run_started", "run_id": state.run_id})

        while state.current_node != END:
            node_name = state.current_node
            handler, policy = self._nodes[node_name]
            last_error: Exception | None = None
            await self._emit(runtime, {"type": "node_started", "node": node_name})
            logger.info("agent_node_started", extra={"event": "agent_node_started", "run_id": state.run_id, "node": node_name})
            for attempt in range(1, policy.max_attempts + 1):
                state.node_attempts[node_name] = state.node_attempts.get(node_name, 0) + 1
                try:
                    result = handler(state, runtime)
                    if inspect.isawaitable(result):
                        result = await result
                    if isinstance(result, AgentState):
                        state = result
                    else:
                        state.data.update(result)
                    last_error = None
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    state.error = str(exc)
                    await self._checkpoints.save(state)
                    await self._emit(runtime, {"type": "node_error", "node": node_name, "attempt": attempt, "error": str(exc)})
                    logger.warning("agent_node_failed", extra={"event": "agent_node_failed", "run_id": state.run_id, "node": node_name, "attempt": attempt, "error": str(exc)})
                    if attempt < policy.max_attempts and policy.delay_seconds:
                        await asyncio.sleep(policy.delay_seconds)
            if last_error is not None:
                state.status = "failed"
                state.current_node = node_name
                await self._checkpoints.save(state)
                raise AgentExecutionError(f"node {node_name} failed after {policy.max_attempts} attempts") from last_error

            state.error = None
            state.current_node = await self._next_node(node_name, state)
            await self._checkpoints.save(state)
            await self._emit(runtime, {"type": "node_completed", "node": node_name, "next_node": state.current_node})

        state.status = "completed"
        await self._checkpoints.save(state)
        await self._emit(runtime, {"type": "run_completed", "run_id": state.run_id})
        logger.info("agent_run_completed", extra={"event": "agent_run_completed", "run_id": state.run_id})
        return state

    @staticmethod
    async def _emit(runtime: AgentRuntime, event: dict[str, Any]) -> None:
        emitter = getattr(runtime, "emit", None)
        if emitter is not None:
            await emitter(event)

    async def _next_node(self, source: str, state: AgentState) -> str:
        if source in self._conditional:
            router, mapping = self._conditional[source]
            route = router(state)
            if inspect.isawaitable(route):
                route = await route
            try:
                return mapping[route]
            except KeyError as exc:
                raise AgentExecutionError(f"route {route!r} is not mapped for node {source}") from exc
        return self._edges.get(source, END)