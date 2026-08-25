from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ToolHandler = Callable[[dict[str, Any]], Any | Awaitable[Any]]
current_execution_id: ContextVar[str | None] = ContextVar(
    "tool_execution_id", default=None
)


class ToolDefinition(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    handler: ToolHandler
    source: str = "local"
    timeout_seconds: float = Field(default=30, gt=0)
    allowed_agents: frozenset[str] = Field(default_factory=frozenset)
    required_permissions: frozenset[str] = Field(default_factory=frozenset)
    allowed_organizations: frozenset[str] = Field(default_factory=frozenset)
    allowed_workspaces: frozenset[str] = Field(default_factory=frozenset)
    retry_mode: Literal["idempotent", "non_idempotent", "requires_idempotency_key"] = (
        "non_idempotent"
    )


class ToolExecutionResult(BaseModel):
    name: str
    result: Any
    source: str
