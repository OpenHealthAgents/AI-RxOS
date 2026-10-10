from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.security import TenantContext

ToolHandler = Callable[[dict[str, Any]], Any | Awaitable[Any]]
current_execution_id: ContextVar[str | None] = ContextVar(
    "tool_execution_id", default=None
)


@dataclass(frozen=True)
class ToolExecutionContext:
    """Reusable framework context for tool execution within a runtime.

    This keeps the execution boundary explicit without forcing the rest of the
    agent platform to change its public API or production behaviors.
    """

    tool_name: str
    agent_name: str | None = None
    tenant: TenantContext | None = None
    execution_key: str | None = None
    execution_id: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


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
