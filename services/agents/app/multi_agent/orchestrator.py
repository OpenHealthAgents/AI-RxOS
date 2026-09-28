from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.agent_harness.checkpoints import CheckpointStore
from app.agent_harness.graph import END, AgentGraph, StateGraph
from app.agent_harness.runtime import AgentRuntime
from app.agent_harness.schemas import AgentState, RetryPolicy
from app.multi_agent.schemas import AgentOutcome, SupervisorDecision

AgentHandler = Callable[[AgentState, AgentRuntime], Any | Awaitable[Any]]
SupervisorHandler = Callable[
    [AgentState], SupervisorDecision | str | Awaitable[SupervisorDecision | str]
]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentSpec:
    name: str
    handler: AgentHandler
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    allowed_parents: frozenset[str] | None = None
    description: str | None = None


class MultiAgentOrchestrator:
    """Supervisor-driven multi-agent execution built on StateGraph."""

    def __init__(
        self,
        agents: Sequence[AgentSpec],
        supervisor: SupervisorHandler,
        checkpoint_store: CheckpointStore,
    ) -> None:
        if not agents:
            raise ValueError("at least one agent is required")
        self._agents = {agent.name: agent for agent in agents}
        if len(self._agents) != len(agents):
            raise ValueError("agent names must be unique")
        self._supervisor = supervisor
        self._checkpoints = checkpoint_store

    def register_agent(
        self,
        name: str,
        handler: AgentHandler,
        *,
        retry: RetryPolicy | None = None,
        allowed_parents: Sequence[str] | None = None,
        description: str | None = None,
    ) -> AgentSpec:
        if name in self._agents:
            raise ValueError(f"agent already registered: {name}")
        spec = AgentSpec(
            name=name,
            handler=handler,
            retry=retry or RetryPolicy(),
            allowed_parents=(
                frozenset(allowed_parents) if allowed_parents is not None else None
            ),
            description=description,
        )
        self._agents[name] = spec
        return spec

    def resolve_agent(self, name: str) -> AgentSpec:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise KeyError(f"agent not registered: {name}") from exc

    def get_agent(self, name: str) -> AgentSpec:
        return self.resolve_agent(name)

    async def invoke_agent(
        self,
        runtime: AgentRuntime,
        name: str,
        *,
        state: AgentState | None = None,
        parent_agent_name: str | None = None,
        parent_execution_id: str | None = None,
        execution_id: str | None = None,
        **metadata: Any,
    ) -> Any:
        spec = self.resolve_agent(name)
        parent_name = parent_agent_name or runtime.agent_name
        if (
            spec.allowed_parents is not None
            and parent_name is not None
            and parent_name not in spec.allowed_parents
        ):
            raise PermissionError(
                f"agent '{name}' is not allowed to be invoked by '{parent_name}'"
            )

        if state is None:
            state = AgentState(run_id=f"agent-{uuid.uuid4().hex[:8]}")

        previous_agent_name = runtime.agent_name
        previous_execution_id = runtime.execution_id
        previous_parent_execution_id = runtime.parent_execution_id
        previous_request_id = runtime.request_id
        previous_correlation_id = runtime.correlation_id
        previous_conversation_id = runtime.conversation_id
        previous_tenant = runtime.current_tenant

        child_execution_id = execution_id or f"{runtime.execution_id or 'exec'}-{name}-{uuid.uuid4().hex[:8]}"
        child_parent_execution_id = parent_execution_id or runtime.execution_id
        runtime.set_agent_name(name)
        runtime.bind_execution_context(
            execution_id=child_execution_id,
            request_id=runtime.request_id,
            correlation_id=runtime.correlation_id,
            conversation_id=runtime.conversation_id,
            parent_execution_id=child_parent_execution_id,
            tenant=runtime.current_tenant,
            parent_agent_name=parent_name,
            **metadata,
        )
        try:
            result = spec.handler(state, runtime)
            if inspect.isawaitable(result):
                result = await result
            return result
        finally:
            runtime.set_agent_name(previous_agent_name)
            runtime.set_execution_id(previous_execution_id)
            runtime.set_parent_execution_id(previous_parent_execution_id)
            runtime.set_request_id(previous_request_id)
            runtime.set_correlation_id(previous_correlation_id)
            runtime.set_conversation_id(previous_conversation_id)
            if previous_tenant is not None:
                runtime._tenant.set(previous_tenant)

    def _build_graph(self) -> AgentGraph:
        graph = StateGraph()

        async def supervisor_node(
            state: AgentState, _runtime: AgentRuntime
        ) -> AgentState:
            decision = self._supervisor(state)
            if inspect.isawaitable(decision):
                decision = await decision
            if isinstance(decision, str):
                decision = SupervisorDecision(next_agent=decision)
            state.data.update(decision.context)
            state.data["next_agent"] = decision.next_agent
            return state

        graph.add_node("supervisor", supervisor_node)
        for agent in self._agents.values():
            graph.add_node(agent.name, self._agent_node(agent), retry=agent.retry)
            graph.add_edge(agent.name, "supervisor")
        graph.set_entry_point("supervisor")
        graph.add_conditional_edges(
            "supervisor",
            lambda state: state.data["next_agent"],
            {**{name: name for name in self._agents}, END: END},
        )
        return graph.compile(self._checkpoints)

    def _agent_node(self, agent: AgentSpec):
        async def execute(state: AgentState, runtime: AgentRuntime) -> AgentState:
            runtime.set_agent_name(agent.name)
            result = agent.handler(state, runtime)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, AgentOutcome):
                state.data.update(result.updates)
                if result.handoff:
                    state.data["pending_handoff"] = result.handoff.model_dump()
                else:
                    state.data.pop("pending_handoff", None)
            elif isinstance(result, AgentState):
                state = result
            elif isinstance(result, dict):
                state.data.update(result)
            else:
                raise TypeError(
                    f"agent {agent.name} must return AgentOutcome, AgentState, or dict"
                )
            return state

        return execute

    async def run(
        self,
        runtime: AgentRuntime,
        *,
        state: AgentState | None = None,
        resume_run_id: str | None = None,
        event_sink=None,
    ) -> AgentState:
        isolated_state = (
            state.model_copy(deep=True)
            if state is not None and resume_run_id is None
            else state
        )
        if isolated_state is not None:
            isolated_state.current_node = None
        return await self._build_graph().run(
            runtime,
            state=isolated_state,
            resume_run_id=resume_run_id,
            event_sink=event_sink,
        )

    async def run_parallel(
        self,
        runtime: AgentRuntime,
        *,
        state: AgentState,
        agent_names: Sequence[str],
    ) -> AgentState:
        """Run independent agents concurrently and merge their update maps."""
        logger.info(
            "agent_parallel_run_started",
            extra={
                "event": "agent_parallel_run_started",
                "run_id": state.run_id,
                "agents": list(agent_names),
            },
        )
        if not agent_names or len(set(agent_names)) != len(agent_names):
            raise ValueError("agent_names must contain one or more unique agents")
        missing = [name for name in agent_names if name not in self._agents]
        if missing:
            raise ValueError(f"agents are not registered: {', '.join(missing)}")

        async def run_one(name: str) -> tuple[str, AgentOutcome]:
            agent_state = state.model_copy(deep=True)
            result = self._agents[name].handler(agent_state, runtime)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, dict):
                result = AgentOutcome(updates=result)
            if not isinstance(result, AgentOutcome):
                raise TypeError(
                    f"parallel agent {name} must return AgentOutcome or dict"
                )
            return name, result

        results = await asyncio.gather(*(run_one(name) for name in agent_names))
        for name, result in results:
            state.data.update(result.updates)
            if result.handoff:
                raise ValueError(
                    f"parallel agent {name} returned a handoff; use sequential orchestration"
                )
        logger.info(
            "agent_parallel_run_completed",
            extra={
                "event": "agent_parallel_run_completed",
                "run_id": state.run_id,
                "agents": list(agent_names),
            },
        )
        return state
