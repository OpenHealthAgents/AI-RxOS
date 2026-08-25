from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ProviderName = Literal["openai", "anthropic", "google", "open_source"]


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    provider: ProviderName
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=1024, gt=0)
    timeout_seconds: float = Field(default=30, gt=0)
    max_retries: int = Field(default=2, ge=0, le=5)


class ModelRegistryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_model: str
    fallback_models: list[str] = Field(default_factory=list)
    models: dict[str, ModelConfig]

    @model_validator(mode="after")
    def validate_model_references(self) -> ModelRegistryConfig:
        references = [self.primary_model, *self.fallback_models]
        missing = [name for name in references if name not in self.models]
        if missing:
            raise ValueError(
                f"model references are not configured: {', '.join(missing)}"
            )
        if len(set(references)) != len(references):
            raise ValueError("primary_model and fallback_models must be unique")
        return self

    @classmethod
    def from_json(cls, value: str) -> ModelRegistryConfig:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("model registry configuration must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise TypeError("model registry configuration must be a JSON object")
        return cls.model_validate(payload)


class ModelRequest(BaseModel):
    messages: list[dict[str, Any]]
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)


class ModelResponse(BaseModel):
    model: str
    provider: ProviderName
    content: str
    raw: dict[str, Any] = Field(default_factory=dict)
