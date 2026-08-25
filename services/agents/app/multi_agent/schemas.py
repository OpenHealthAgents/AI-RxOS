from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Handoff(BaseModel):
    target_agent: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None


class AgentOutcome(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    updates: dict[str, Any] = Field(default_factory=dict)
    handoff: Handoff | None = None


class SupervisorDecision(BaseModel):
    next_agent: str
    context: dict[str, Any] = Field(default_factory=dict)
