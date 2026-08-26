from __future__ import annotations

import asyncio
import inspect
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError
from langgraph.graph import END as LANGGRAPH_END
from langgraph.graph import StateGraph as OfficialStateGraph

from app.agent_harness.checkpoints import CheckpointStore
from app.agent_harness.runtime import AgentRuntime
from app.agent_harness.schemas import AgentState, RetryPolicy
from app.core.errors import AIPlatformError
from app.core.observability import metrics, span
from app.core.security import TenantContext
from app.security.redaction import sanitize_exception

logger = logging.getLogger(__name__)

END = LANGGRAPH_END
NodeHandler = Callable[
    [AgentState, AgentRuntime],
    AgentState | dict[str, Any] | Awaitable[AgentState | dict[str, Any]],
]
RouteHandler = Callable[[AgentState], str | Awaitable[str]]


class LangGraphState(TypedDict):
    agent_state: AgentState


class GraphConfigurationError(ValueError):
    pass


class AgentExecutionError(AIPlatformError):
    def __init__(self, message: str, *, node: str | None = None) -> None:
        super().__init__(
            message,
            code="AGENT_EXECUTION_ERROR",
            operation="agent_run",
            retriable=True,
            details={"node": node},
        )


class StateGraph:
    def __init__(self) -> None: 
        self._graph = OfficialStateGraph(LangGraphState)
        self._nodes: dict[str, tuple[NodeHandler, RetryPolicy]] = {}
        self._edges: dict[str, str] = {}
        self._conditional: dict[str, tuple[RouteHandler, dict[str, str]]] = {}
        self._entry: str | None = None

    def add_node(
        self, name: str, handler: NodeHandler, *, retry: RetryPolicy | None = None
    ) -> StateGraph:
        if name in self._nodes or name == END:
            raise GraphConfigurationError(f"node already exists or is reserved: {name}")
        policy = retry or RetryPolicy()
        self._nodes[name] = (handler, policy)
        self._graph.add_node(name, self._node_adapter(name, handler, policy))
        return self

    def set_entry_point(self, name: str) -> StateGraph:
        self._entry = name
        return self

    def add_edge(self, source: str, target: str) -> StateGraph:
        self._edges[source] = target
        self._graph.add_edge(source, target)
        return self

    def add_conditional_edges(
        self, source: str, router: RouteHandler, mapping: dict[str, str]
    ) -> StateGraph:
        self._conditional[source] = (router, mapping)
        async def route(state: LangGraphState) -> str:
            result = router(state["agent_state"])
            if inspect.isawaitable(result):
                result = await result
            return result

        self._graph.add_conditional_edges(
            source, route, {key: value for key, value in mapping.items()}
        )
        return self

    def _node_adapter(
        self, name: str, handler: NodeHandler, policy: RetryPolicy
    ) -> Callable[..., Awaitable[dict[str, AgentState]]]:
        async def execute(
            state: LangGraphState, config: RunnableConfig
        ) -> dict[str, AgentState]:
            agent_state = state["agent_state"]
            runtime = config.get("configurable", {}).get("runtime")
            checkpoints = config.get("configurable", {}).get("checkpoints")
            if not isinstance(agent_state, AgentState) or runtime is None:
                raise GraphConfigurationError("LangGraph execution context is missing")
            if isinstance(runtime, AgentRuntime):
                runtime.set_agent_name(name)
            agent_state.current_node = name
            agent_state.status = "running"
            if checkpoints is not None:
                await checkpoints.save(agent_state)
            await AgentGraph._emit(runtime, {"type": "node_started", "node": name})
            last_error: Exception | None = None
            for attempt in range(1, policy.max_attempts + 1):
                agent_state.node_attempts[name] = (
                    agent_state.node_attempts.get(name, 0) + 1
                )
                try:
                    result = handler(agent_state, runtime)
                    if inspect.isawaitable(result):
                        result = await result
                    if isinstance(result, AgentState):
                        agent_state = result
                    elif isinstance(result, dict):
                        agent_state.data.update(result)
                    else:
                        raise TypeError(
                            f"node {name} must return AgentState or dict"
                        )
                    last_error = None
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    agent_state.error = sanitize_exception(exc)["error"]
                    if checkpoints is not None:
                        await checkpoints.save(agent_state)
                    await AgentGraph._emit(
                        runtime,
                        {
                            "type": "node_error",
                            "node": name,
                            "attempt": attempt,
                            **sanitize_exception(exc),
                        },
                    )
                    if isinstance(exc, AIPlatformError) and not exc.retriable:
                        break
                    if attempt < policy.max_attempts and policy.delay_seconds:
                        await asyncio.sleep(policy.delay_seconds)
            if last_error is not None:
                agent_state.status = "failed"
                if checkpoints is not None:
                    await checkpoints.save(agent_state)
                if isinstance(last_error, AIPlatformError) and not last_error.retriable:
                    raise last_error
                raise AgentExecutionError(
                    f"node {name} failed after {policy.max_attempts} attempts",
                    node=name,
                ) from last_error
            agent_state.error = None
            if checkpoints is not None:
                await checkpoints.save(agent_state)
            await AgentGraph._emit(
                runtime,
                {"type": "node_completed", "node": name, "next_node": None},
            )
            return {"agent_state": agent_state}

        return execute

    def compile(
        self,
        checkpoint_store: CheckpointStore,
        *,
        max_transitions: int = 100,
        max_execution_seconds: float | None = None,
    ) -> AgentGraph:
        if self._entry is None or self._entry not in self._nodes:
            raise GraphConfigurationError(
                "entry point must reference a registered node"
            )
        for source, target in {
            **self._edges,
            **{s: t for s, (_, m) in self._conditional.items() for t in m.values()},
        }.items():
            if source not in self._nodes or target != END and target not in self._nodes:
                raise GraphConfigurationError(f"invalid edge: {source} -> {target}")
        if max_transitions < 1:
            raise GraphConfigurationError("max_transitions must be at least 1")
        resume_node = "__langgraph_resume__"
        self._graph.add_node(resume_node, lambda state: state)
        self._graph.add_conditional_edges(
            resume_node,
            lambda state: state["agent_state"].current_node or self._entry,
            {**{name: name for name in self._nodes}, END: END},
        )
        self._graph.set_entry_point(resume_node)
        official_graph = self._graph.compile()
        return AgentGraph(
            checkpoint_store,
            max_transitions=max_transitions,
            official_graph=official_graph,
            max_execution_seconds=max_execution_seconds
            if max_execution_seconds is not None
            else float(os.getenv("AGENT_MAX_EXECUTION_SECONDS", "300")),
        )


class AgentGraph:
    def __init__(
        self,
        checkpoint_store,
        *,
        max_transitions: int,
        official_graph,
        max_execution_seconds: float,
    ) -> None:
        self._checkpoints = checkpoint_store
        self._max_transitions = max_transitions
        self._official_graph = official_graph
        if max_execution_seconds <= 0:
            raise GraphConfigurationError(
                "max_execution_seconds must be greater than zero"
            )
        self._max_execution_seconds = max_execution_seconds

    async def run(
        self,
        runtime: AgentRuntime,
        *,
        state: AgentState | None = None,
        resume_run_id: str | None = None,
        event_sink=None,
    ) -> AgentState:
        if resume_run_id:
            tenant_data = state.data.get("tenant") if state is not None else None
            tenant = (
                TenantContext(**tenant_data)
                if isinstance(tenant_data, dict)
                else runtime.current_tenant
                if isinstance(runtime, AgentRuntime)
                else None
            )
            state = await self._checkpoints.load(resume_run_id, tenant=tenant)
            if state is None:
                raise AgentExecutionError(f"checkpoint not found: {resume_run_id}")
        state = state or AgentState()
        if state.status == "completed":
            return state
        if isinstance(runtime, AgentRuntime):
            tenant_data = state.data.get("tenant")
            tenant = (
                TenantContext(**tenant_data) if isinstance(tenant_data, dict) else None
            )
            runtime.attach_run_memory(state.run_id, tenant=tenant)
            runtime.set_execution_id(state.data.get("execution_id"))
            if event_sink is not None:
                runtime.event_sink = event_sink
        state.status = "running"
        state.error = None
        await self._checkpoints.save(state)
        await self._emit(runtime, {"type": "run_started", "run_id": state.run_id})
        logger.info(
            "agent_run_started",
            extra={"event": "agent_run_started", "run_id": state.run_id},
        )

        graph_started = time.perf_counter()
        with span("agent.graph", job_id=state.run_id):
            metrics.inc("agent_graph_runs_total", status="started")
        try:
            result = await asyncio.wait_for(
                self._official_graph.ainvoke(
                    {"agent_state": state},
                    config={
                        "recursion_limit": self._max_transitions + 1,
                        "configurable": {
                            "runtime": runtime,
                            "checkpoints": self._checkpoints,
                        },
                    },
                ),
                timeout=self._max_execution_seconds,
            )
            state = result["agent_state"]
            state.current_node = END
            state.status = "completed"
        except GraphRecursionError as exc:
            state.status = "failed"
            state.error = f"graph exceeded maximum transitions: {self._max_transitions}"
            await self._checkpoints.save(state)
            await self._emit(
                runtime,
                {"type": "run_error", "run_id": state.run_id, "error": state.error},
            )
            raise AgentExecutionError(state.error, node=state.current_node) from exc
        except asyncio.TimeoutError as exc:
            state.status = "failed"
            state.error = "graph execution timed out"
            await self._checkpoints.save(state)
            await self._emit(
                runtime,
                {"type": "run_error", "run_id": state.run_id, "error": state.error},
            )
            raise AgentExecutionError(state.error, node=state.current_node) from exc
        except Exception as exc:
            state.status = "failed"
            state.error = sanitize_exception(exc)["error"]
            await self._checkpoints.save(state)
            await self._emit(
                runtime,
                {"type": "run_error", "run_id": state.run_id, "error": state.error},
            )
            raise
        metrics.observe(
            "agent_execution_duration_seconds",
            time.perf_counter() - graph_started,
            status="completed",
        )
        await self._checkpoints.save(state)
        await self._emit(runtime, {"type": "run_completed", "run_id": state.run_id})
        logger.info(
            "agent_run_completed",
            extra={"event": "agent_run_completed", "run_id": state.run_id},
        )
        return state

    @staticmethod
    async def _emit(runtime: AgentRuntime, event: dict[str, Any]) -> None:
        emitter = getattr(runtime, "emit", None)
        if emitter is not None:
            await emitter(event)
