from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid5


_EVENT_NAMESPACE = UUID("c09d9ea5-3a79-4577-9eb0-8870026623b7")
_TRANSPORT_KEYS = frozenset(
    {
        "api_endpoint",
        "content_hash",
        "fetched_at",
        "ingested_at",
        "next_page_token",
        "page_token",
        "parser",
        "query",
        "request_id",
        "request_metadata",
        "retrieval_date",
        "retrieved_at",
        "source_updated_at",
    }
)

_SOURCE_CATEGORIES = {
    "pubmed": "publications",
    "clinicaltrials": "clinical_trials",
    "clinical_trials": "clinical_trials",
    "regulatory": "regulatory",
    "regulatory_events": "regulatory",
    "patent": "patents",
    "patents": "patents",
    "company_websites": "company_events",
    "company_events": "company_events",
    "company": "company_events",
    "licensing": "licensing",
    "licensing_events": "licensing",
    "competitors": "competition",
    "competition": "competition",
    "competitive": "competition",
    "resistance": "resistance",
    "resistance_evidence": "resistance",
    "cns": "cns",
    "cns_evidence": "cns",
}


def source_category(source: str) -> str:
    """Return a supported monitoring category or fail for an unwired source."""
    try:
        return _SOURCE_CATEGORIES[source.lower().strip()]
    except KeyError as exc:
        raise ValueError(f"unsupported monitoring source: {source}") from exc


def _without_transport_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _without_transport_metadata(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key).casefold() not in _TRANSPORT_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_without_transport_metadata(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def material_payload(
    source: str,
    record: Mapping[str, Any],
    *,
    extracted_entities: list[dict[str, Any]] | None = None,
    extracted_relationships: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Select source-backed fields whose changes can affect evidence or decisions."""
    source_category(source)
    if source == "pubmed":
        selected = {
            key: record.get(key)
            for key in (
                "title",
                "abstract",
                "doi",
                "authors",
                "journal",
                "publication_date",
                "study_type",
                "keywords",
                "mesh_terms",
                "mesh",
                "entities",
                "references",
            )
        }
        selected["extracted_entities"] = extracted_entities or []
        selected["extracted_relationships"] = extracted_relationships or []
        return _without_transport_metadata(selected)

    raw_payload = record.get("raw_payload")
    if source in {"clinicaltrials", "regulatory", "regulatory_events"} and raw_payload is not None:
        return {"source_record": _without_transport_metadata(raw_payload)}

    if source in {"company_websites", "company_events", "company"}:
        selected = {
            key: record.get(key)
            for key in (
                "title",
                "abstract",
                "asset_id",
                "company_name",
                "event_type",
                "event_date",
                "published_date",
                "source_id",
                "url",
            )
        }
        selected["source_record"] = _without_transport_metadata(raw_payload or record.get("metadata") or {})
        selected["metadata"] = record.get("metadata") or {}
        return _without_transport_metadata(selected)

    if source in {"licensing", "licensing_events"}:
        selected = {
            key: record.get(key)
            for key in (
                "asset_id",
                "status",
                "licensee",
                "licensor",
                "deal_type",
                "effective_date",
                "termination_date",
                "verification_source",
            )
        }
        selected["source_record"] = _without_transport_metadata(raw_payload or record)
        selected["metadata"] = record.get("metadata") or {}
        return _without_transport_metadata(selected)

    if source in {"competitors", "competition", "competitive"}:
        selected = {
            key: record.get(key)
            for key in (
                "asset_id",
                "competitor_name",
                "competitor_asset_id",
                "therapeutic_area",
                "stage",
                "market_share",
                "differentiation_score",
                "source_id",
            )
        }
        selected["source_record"] = _without_transport_metadata(raw_payload or record)
        selected["metadata"] = record.get("metadata") or {}
        return _without_transport_metadata(selected)

    if source in {"resistance", "resistance_evidence"}:
        selected = {
            key: record.get(key)
            for key in (
                "asset_id",
                "mechanism",
                "risk_level",
                "evidence_level",
                "clinical_observation",
                "confidence",
                "source_id",
            )
        }
        selected["source_record"] = _without_transport_metadata(raw_payload or record)
        selected["metadata"] = record.get("metadata") or {}
        return _without_transport_metadata(selected)

    if source in {"cns", "cns_evidence"}:
        selected = {
            key: record.get(key)
            for key in (
                "asset_id",
                "brain_penetration",
                "intracranial_response",
                "cns_activity_score",
                "confidence",
                "source_id",
            )
        }
        selected["source_record"] = _without_transport_metadata(raw_payload or record)
        selected["metadata"] = record.get("metadata") or {}
        return _without_transport_metadata(selected)

    if source == "patent":
        selected = {
            key: record.get(key)
            for key in ("title", "abstract", "authors", "published_date")
        }
        selected["source_record"] = raw_payload
        selected["metadata"] = record.get("metadata") or {}
        return _without_transport_metadata(selected)

    return _without_transport_metadata(
        {key: record.get(key) for key in ("title", "abstract", "metadata")}
    )


def material_hash(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        _without_transport_metadata(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def changed_material_fields(
    previous: Mapping[str, Any], current: Mapping[str, Any]
) -> list[str]:
    """Return deterministic field paths that differ; arrays are compared as values."""
    changed: set[str] = set()

    def compare(old: Any, new: Any, path: str) -> None:
        if isinstance(old, Mapping) and isinstance(new, Mapping):
            for key in sorted(set(old) | set(new)):
                child_path = f"{path}.{key}" if path else str(key)
                if key not in old or key not in new:
                    changed.add(child_path)
                else:
                    compare(old[key], new[key], child_path)
            return
        if old != new:
            changed.add(path or "$")

    compare(previous, current, "")
    return sorted(changed)


def monitoring_event_id(
    source: str,
    source_id: str,
    previous_snapshot_id: UUID | None,
    current_snapshot_id: UUID,
    organization_id: UUID | None,
) -> UUID:
    scope = str(organization_id) if organization_id else "global"
    identity = "|".join(
        (
            scope,
            source,
            source_id.strip(),
            str(previous_snapshot_id) if previous_snapshot_id else "initial",
            str(current_snapshot_id),
        )
    )
    return uuid5(_EVENT_NAMESPACE, identity)
