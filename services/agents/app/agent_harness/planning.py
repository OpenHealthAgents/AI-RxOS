from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

from app.agent_harness.graph import END, AgentGraph, StateGraph
from app.agent_harness.runtime import AgentRuntime
from app.agent_harness.schemas import AgentState, RetryPolicy
from app.model_registry.schemas import ModelRequest
from app.security.redaction import sanitize_exception


class PlanStep(BaseModel):
    id: str
    description: str
    status: str = "pending"
    result: Any = None
    error: str | None = None


class ExecutionPlan(BaseModel):
    task: str
    steps: list[PlanStep] = Field(min_length=1)
    revision: int = 0


PlanBuilder = Callable[
    [AgentState, AgentRuntime], list[PlanStep] | Awaitable[list[PlanStep]]
]
StepExecutor = Callable[[AgentState, PlanStep, AgentRuntime], Any | Awaitable[Any]]
Reflector = Callable[
    [AgentState, AgentRuntime], dict[str, Any] | Awaitable[dict[str, Any]]
]


class PlanExecuteNodes:
    """Reusable planning, execution, and reflection nodes for StateGraph."""

    def __init__(
        self,
        *,
        planner: PlanBuilder | None = None,
        executor: StepExecutor | None = None,
        reflector: Reflector | None = None,
        plan_prompt: str = "agent.plan",
        reflection_prompt: str = "agent.reflect",
        retry: RetryPolicy | None = None,
    ) -> None:
        self.planner = planner
        self.executor = executor
        self.reflector = reflector
        self.plan_prompt = plan_prompt
        self.reflection_prompt = reflection_prompt
        self.retry = retry or RetryPolicy()

    async def plan(self, state: AgentState, runtime: AgentRuntime) -> AgentState:
        steps = await self._build_plan(state, runtime)
        current = (
            ExecutionPlan.model_validate(state.data["plan"])
            if state.data.get("plan")
            else None
        )
        completed = (
            {step.id: step for step in current.steps if step.status == "completed"}
            if current
            else {}
        )
        revision = current.revision + 1 if current else 0
        for step in steps:
            if step.id in completed:
                step.status = "completed"
                step.result = completed[step.id].result
        plan = ExecutionPlan(
            task=state.data.get("original_task", ""), steps=steps, revision=revision
        )
        state.data["plan"] = plan.model_dump()
        state.data["current_step_index"] = self._next_pending(plan)
        state.data.pop("plan_revision_required", None)
        return state

    async def execute_step(
        self, state: AgentState, runtime: AgentRuntime
    ) -> AgentState:
        plan = ExecutionPlan.model_validate(state.data["plan"])
        index = state.data.get("current_step_index", self._next_pending(plan))
        if index >= len(plan.steps):
            return state
        step = plan.steps[index]
        if step.status == "completed":
            state.data["current_step_index"] = self._next_pending(plan)
            state.data["plan"] = plan.model_dump()
            return state
        step.status = "in_progress"
        try:
            if self.executor is None:
                raise RuntimeError("a step executor is required")
            result = self.executor(state, step, runtime)
            if hasattr(result, "__await__"):
                result = await result
            step.result = result
            step.status = "completed"
            step.error = None
            state.data["current_step_index"] = self._next_pending(plan)
        except Exception as exc:  # noqa: BLE001
            step.status = "failed"
            step.error = sanitize_exception(exc)["error"]
            state.data["plan_revision_required"] = True
            state.data["current_step_index"] = index
        state.data["plan"] = plan.model_dump()
        return state

    async def reflect(self, state: AgentState, runtime: AgentRuntime) -> AgentState:
        if self.reflector is not None:
            result = self.reflector(state, runtime)
            if hasattr(result, "__await__"):
                result = await result
        else:
            prompt = await runtime.render_prompt(
                self.reflection_prompt,
                {
                    "task": state.data.get("original_task", ""),
                    "result": json.dumps(state.data.get("plan", {})),
                },
            )
            response = await runtime.call_model(
                ModelRequest(messages=[{"role": "user", "content": prompt}])
            )
            result = self._parse_reflection(response.content)
        state.data["reflection"] = result
        return state

    def build_graph(self, checkpoint_store) -> AgentGraph:
        graph = StateGraph()
        graph.add_node("plan", self.plan, retry=self.retry)
        graph.add_node("execute", self.execute_step, retry=self.retry)
        graph.add_node("reflect", self.reflect, retry=self.retry)
        graph.set_entry_point("plan")
        graph.add_edge("plan", "execute")
        graph.add_conditional_edges(
            "execute",
            lambda state: (
                "plan"
                if state.data.get("plan_revision_required")
                else "reflect"
                if self._is_complete(state)
                else "execute"
            ),
            {"plan": "plan", "execute": "execute", "reflect": "reflect"},
        )
        graph.add_edge("reflect", END)
        return graph.compile(checkpoint_store)

    async def _build_plan(
        self, state: AgentState, runtime: AgentRuntime
    ) -> list[PlanStep]:
        if self.planner is not None:
            result = self.planner(state, runtime)
            if hasattr(result, "__await__"):
                result = await result
            return result
        prompt = await runtime.render_prompt(
            self.plan_prompt,
            {
                "task": state.data.get("original_task", ""),
                "feedback": json.dumps(state.data.get("plan", {})),
            },
        )
        response = await runtime.call_model(
            ModelRequest(messages=[{"role": "user", "content": prompt}])
        )
        payload = json.loads(response.content)
        return [PlanStep.model_validate(step) for step in payload["steps"]]

    @staticmethod
    def _next_pending(plan: ExecutionPlan) -> int:
        return next(
            (
                index
                for index, step in enumerate(plan.steps)
                if step.status != "completed"
            ),
            len(plan.steps),
        )

    @staticmethod
    def _is_complete(state: AgentState) -> bool:
        plan = ExecutionPlan.model_validate(state.data["plan"])
        return all(step.status == "completed" for step in plan.steps)

    @staticmethod
    def _parse_reflection(content: str) -> dict[str, Any]:
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            return {"satisfied": False, "assessment": content, "parse_error": True}
        if not isinstance(result, dict) or not isinstance(
            result.get("satisfied"), bool
        ):
            return {"satisfied": False, "assessment": content, "parse_error": True}
        return result
