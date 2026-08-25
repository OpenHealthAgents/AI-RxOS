from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    data: dict[str, Any] = Field(default_factory=dict)
    current_node: str | None = None
    status: Literal["pending", "running", "failed", "completed"] = "pending"
    error: str | None = None
    node_attempts: dict[str, int] = Field(default_factory=dict)


class RetryPolicy(BaseModel):
    max_attempts: int = Field(default=3, ge=1)
    delay_seconds: float = Field(default=0, ge=0)
