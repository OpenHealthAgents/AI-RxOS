"""
Model Registry for Interpretable Oncology ML.

Manages model versioning, lifecycle stages (development, staging, production, archived),
model metadata, and champion/challenger promotions.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID

from .models import ModelArtifact, ModelStage


class ModelRegistry:
    """In-memory catalog for model lineage, lifecycle, and artifact traceability."""

    def __init__(self) -> None:
        self._models: Dict[str, ModelArtifact] = {}

    def register(self, model: ModelArtifact) -> ModelArtifact:
        """Registers a trained model artifact and preserves version immutability."""
        existing = self.get_model_by_version(model.name, model.version)
        if existing is not None and str(existing.model_id) != str(model.model_id):
            raise ValueError(
                f"Model version '{model.name}:{model.version}' already exists in the registry."
            )

        key = str(model.model_id)
        self._models[key] = model
        return model

    def get_model(self, model_id: UUID | str) -> Optional[ModelArtifact]:
        return self._models.get(str(model_id))

    def get_model_by_version(self, name: str, version: str) -> Optional[ModelArtifact]:
        for m in self._models.values():
            if m.name == name and m.version == version:
                return m
        return None

    def list_models(self, stage: Optional[ModelStage] = None) -> List[ModelArtifact]:
        models = list(self._models.values())
        if stage is not None:
            models = [m for m in models if m.stage == stage]
        return sorted(models, key=lambda m: m.registered_at, reverse=True)

    def get_production_model(self, name_contains: Optional[str] = None) -> Optional[ModelArtifact]:
        candidates = [m for m in self._models.values() if m.stage == ModelStage.PRODUCTION and m.is_active]
        if name_contains:
            candidates = [m for m in candidates if name_contains in m.name]
        if not candidates:
            candidates = [m for m in self._models.values() if m.is_active]
        return candidates[0] if candidates else None

    def promote_model(self, model_id: UUID | str, target_stage: ModelStage) -> ModelArtifact:
        key = str(model_id)
        if key not in self._models:
            raise KeyError(f"Model ID '{model_id}' not found in registry.")

        target_model = self._models[key]
        if target_stage == ModelStage.PRODUCTION:
            for other_id, other in self._models.items():
                if other_id != key and other.name == target_model.name and other.stage == ModelStage.PRODUCTION:
                    self._models[other_id] = other.model_copy(update={"stage": ModelStage.ARCHIVED})
        updated = target_model.model_copy(update={"stage": target_stage})
        self._models[key] = updated
        return updated
