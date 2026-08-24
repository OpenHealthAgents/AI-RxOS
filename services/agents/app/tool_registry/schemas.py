from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

ToolHandler = Callable[[dict[str, Any]], Any | Awaitable[Any]]


class ToolDefinition(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    handler: ToolHandler
    source: str = "local"
    timeout_seconds: float = Field(default=30, gt=0)


class ToolExecutionResult(BaseModel):
    name: str
    result: Any
    source: str