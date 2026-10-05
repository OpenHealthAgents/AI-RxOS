from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import httpx
from neo4j import AsyncTransaction

from app.core.config import Settings
from app.database.canonical_store import CanonicalStore
from app.database.neo4j import Neo4jManager
from app.utils.logging import get_logger

logger = get_logger(__name__)


class CanonicalProjectionWorker:
    def __init__(self, store: CanonicalStore, neo4j: Neo4jManager, settings: Settings):
        self.store = store
        self.neo4j = neo4j
        self.settings = settings

    async def run_once(self, limit: int = 25, organization_id: UUID | None = None) -> int:
        events = await self.store.claim_projection_events(organization_id, limit)
        delivered = 0
        for event in events:
            payload = event["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            try:
                projection_version = int(payload.get("projection_version", event["id"]))
                await self._project_graph(event["event_type"], payload, projection_version)
                if event["event_type"] == "entity.upserted":
                    await self._project_search(payload, projection_version, organization_id)
                await self.store.mark_projection_delivered(event["id"])
                delivered += 1
            except Exception as exc:
                logger.exception(
                    "Canonical projection delivery failed",
                    extra={"event_id": event["id"], "event_type": event["event_type"]},
                )
                await self.store.mark_projection_failed(event["id"], event["attempts"], str(exc))
        return delivered

    async def _project_graph(self, event_type: str, payload: dict[str, Any], projection_version: int) -> None:
        if self.neo4j.driver is None:
            raise RuntimeError("Neo4j projection is unavailable")
        if event_type == "entity.upserted":
            query = """MERGE (n:CanonicalEntity {id: $id})
                WITH n
                     WHERE (n.organization_id = $organization_id
                         OR ($organization_id IS NULL AND n.organization_id IS NULL)
                         OR (n.organization_id IS NULL AND n.visibility IS NULL))
                        AND coalesce(n.projection_version, 0) <= $projection_version
                SET n.entity_type = $entity_type,
                    n.name = $preferred_name,
                    n.description = $description,
                    n.modality = $modality,
                    n.lifecycle_status = $lifecycle_status,
                    n.visibility = $visibility,
                    n.organization_id = $organization_id,
                    n.attributes_json = $attributes_json,
                    n.created_at = $created_at,
                    n.updated_at = $updated_at,
                    n.projection_version = $projection_version
                RETURN n.id AS id"""
            parameters = {
                "id": payload["id"],
                "entity_type": payload["entity_type"],
                "preferred_name": payload["preferred_name"],
                "description": payload.get("description"),
                "modality": payload.get("modality"),
                "lifecycle_status": payload.get("lifecycle_status"),
                "visibility": payload.get("visibility", "global"),
                "organization_id": payload.get("organization_id"),
                "attributes_json": json.dumps(payload.get("attributes", {}), ensure_ascii=True),
                "projection_version": projection_version,
                "created_at": payload.get("created_at"),
                "updated_at": payload.get("updated_at", payload.get("created_at")),
            }
        elif event_type == "relationship.upserted":
            query = """MATCH (subject:CanonicalEntity {id: $subject_id})
                WHERE subject.organization_id IS NULL
                   OR subject.organization_id = $organization_id
                   OR ($organization_id IS NULL AND coalesce(subject.visibility, 'global') = 'global')
                MATCH (object:CanonicalEntity {id: $object_id})
                WHERE object.organization_id IS NULL
                   OR object.organization_id = $organization_id
                   OR ($organization_id IS NULL AND coalesce(object.visibility, 'global') = 'global')
                MERGE (subject)-[r:CANONICAL_RELATIONSHIP {id: $id}]->(object)
                WITH r
                WHERE coalesce(r.projection_version, 0) <= $projection_version
                SET r.predicate = $predicate,
                    r.visibility = $visibility,
                    r.organization_id = $organization_id,
                    r.attributes_json = $attributes_json,
                    r.created_at = $created_at,
                    r.updated_at = $updated_at,
                    r.projection_version = $projection_version
                RETURN r.id AS id"""
            parameters = {
                "id": payload["id"],
                "subject_id": payload["subject_entity_id"],
                "object_id": payload["object_entity_id"],
                "predicate": payload["predicate"],
                "visibility": payload.get("visibility", "global"),
                "organization_id": payload.get("organization_id"),
                "attributes_json": json.dumps(payload.get("attributes", {}), ensure_ascii=True),
                "projection_version": projection_version,
                "created_at": payload.get("created_at"),
                "updated_at": payload.get("updated_at", payload.get("created_at")),
            }
        else:
            raise ValueError(f"unsupported canonical projection event: {event_type}")

        async with self.neo4j.get_session() as session:
            if event_type == "relationship.upserted":
                endpoint_record = await session.execute_read(
                    self._run_graph_query,
                    """MATCH (subject:CanonicalEntity {id: $subject_id})
                    MATCH (object:CanonicalEntity {id: $object_id})
                    RETURN count(*) AS endpoint_count""",
                    {
                        "subject_id": payload["subject_entity_id"],
                        "object_id": payload["object_entity_id"],
                    },
                )
                if endpoint_record is None or endpoint_record["endpoint_count"] != 1:
                    raise RuntimeError("canonical relationship projection endpoints are unavailable")
            record = await session.execute_write(self._run_graph_query, query, parameters)
        if record is None and event_type == "relationship.upserted":
            raise RuntimeError("canonical graph projection endpoint was not present")

    @staticmethod
    async def _run_graph_query(
        transaction: AsyncTransaction,
        query: str,
        parameters: dict[str, Any],
    ) -> Any:
        result = await transaction.run(query, **parameters)
        return await result.single()

    async def _project_search(
        self, payload: dict[str, Any], projection_version: int, organization_id: UUID | None
    ) -> None:
        entity_id = payload["id"]
        available_at = payload.get("updated_at", payload.get("created_at"))
        search_context = await self.store.load_search_projection_metadata(
            UUID(str(entity_id)), organization_id, available_at
        )
        attributes = payload.get("attributes")
        if attributes is None:
            attributes = {}
        source_record = search_context.get("source_record") if isinstance(search_context, dict) else {}
        if not isinstance(source_record, dict):
            source_record = {}
        aliases = search_context.get("aliases", []) if isinstance(search_context, dict) else []
        identifiers = search_context.get("identifiers", []) if isinstance(search_context, dict) else []
        document = {
            "id": f"{entity_id}:{projection_version}",
            "document_id": entity_id,
            "canonical_id": entity_id,
            "projection_key": entity_id,
            "entity_type": payload["entity_type"],
            "title": payload["preferred_name"],
            "content": json.dumps({
                "entity_type": payload["entity_type"],
                "description": payload.get("description"),
                "modality": payload.get("modality"),
                "lifecycle_status": payload.get("lifecycle_status"),
                "attributes": attributes,
                "source_metadata": search_context,
            }, ensure_ascii=True),
            "source": "canonical_entity",
            "tenant_id": payload.get("organization_id"),
            "visibility": payload.get("visibility", "global"),
            "aliases": [
                item.get("value")
                for item in aliases
                if isinstance(item, dict) and item.get("value")
            ],
            "identifiers": [
                f"{item.get('namespace')}:{item.get('value')}"
                for item in identifiers
                if isinstance(item, dict) and item.get("namespace") and item.get("value")
            ],
            "projection_version": projection_version,
            "knowledge_available_at": available_at,
            "source_record_id": source_record.get("id") or payload.get("source_record_id"),
            "source_url": source_record.get("source_url"),
            "published_at": source_record.get("published_at"),
            "metadata": search_context,
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            headers = {}
            if self.settings.search_internal_token:
                headers["X-Search-Internal-Token"] = self.settings.search_internal_token
            elif organization_id is not None:
                headers["X-Authenticated-Organization-ID"] = str(organization_id)
            else:
                raise RuntimeError("SEARCH_INTERNAL_TOKEN is required for global Search projection")
            response = await client.post(
                f"{self.settings.search_service_url.rstrip('/')}/api/v1/search/index",
                json={"documents": [document]},
                headers=headers,
            )
            response.raise_for_status()
