from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


MonitoringCategory = Literal[
    "publications",
    "clinical_trials",
    "regulatory",
    "patents",
    "company_events",
    "licensing",
    "competition",
    "resistance",
    "cns",
]


class MonitoringEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: str
    source_category: MonitoringCategory
    source_id: str
    change_type: Literal["new_source_record", "material_change"]
    previous_content_hash: str | None
    current_content_hash: str
    previous_material_hash: str | None
    current_material_hash: str
    previous_snapshot_id: UUID | None
    current_snapshot_id: UUID
    source_event_at: AwareDatetime | None
    detected_at: AwareDatetime
    changed_fields: list[str]
    evidence_refs: list[dict[str, Any]]
    materiality_rationale: str
    canonical_entity_id: UUID | None
    canonical_resolution_status: str
    recalculation_status: str
    decision_change_state: str
    previous_decision_version: dict[str, Any] | None = None
    current_decision_version: dict[str, Any] | None = None
    previous_decision_state: str | None = None
    current_decision_state: str | None = None
    evidence_caused_change: list[dict[str, Any]] = []
    created_at: AwareDatetime


class MonitoringEventPage(BaseModel):
    items: list[MonitoringEvent]
    count: int
    limit: int
    source_category: MonitoringCategory | None = None
