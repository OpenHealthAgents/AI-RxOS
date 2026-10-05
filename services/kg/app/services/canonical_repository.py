from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from app.core.canonical_security import CanonicalPrincipal
from app.database.canonical_store import CanonicalStore
from app.schemas.canonical import (
    AliasInput,
    CanonicalEntityCreate,
    CanonicalRelationshipCreate,
    ClinicalTrialIngest,
    ClaimCreate,
    EntityType,
    EvidenceLinkCreate,
    IdentifierInput,
    LicensingEventIngest,
    ObservationCreate,
    ObservationKind,
    PatentRecordIngest,
    PubMedArticleIngest,
    RegulatoryEventIngest,
    RegulatoryEventType,
    SourceRecordInput,
    SourceType,
    Visibility,
)
from app.services.canonical_identity import normalize_identifier, normalize_name


class CanonicalConflictError(ValueError):
    pass


class CanonicalNotFoundError(LookupError):
    pass


class CanonicalAuthorizationError(PermissionError):
    pass


class CanonicalRepository:
    def __init__(self, store: CanonicalStore):
        self.store = store

    @staticmethod
    def _require_aware_as_of(as_of: datetime | None) -> None:
        if as_of is not None and (as_of.tzinfo is None or as_of.utcoffset() is None):
            raise ValueError("as_of must include a timezone")

    @staticmethod
    def _coerce_source_record(source_record: Any) -> SourceRecordInput:
        if isinstance(source_record, SourceRecordInput):
            return source_record
        if isinstance(source_record, dict):
            return SourceRecordInput.model_validate(source_record)
        raise TypeError("source_record must be a SourceRecordInput or mapping")

    @staticmethod
    def _coerce_uuid(value: Any, label: str) -> UUID | None:
        if value is None or value == "":
            return None
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise CanonicalAuthorizationError(f"invalid {label} UUID") from exc

    @staticmethod
    def _scope(visibility: Visibility, principal: CanonicalPrincipal) -> UUID | None:
        if visibility == Visibility.GLOBAL:
            if not principal.can_write_global:
                raise CanonicalAuthorizationError("global canonical writes require an operator role")
            return None
        if principal.organization_id is None or principal.user_id is None:
            raise CanonicalAuthorizationError("tenant-scoped writes require verified user and organization claims")
        return principal.organization_id

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    async def _source_record(
        self,
        connection: asyncpg.Connection,
        source: SourceRecordInput,
        organization_id: UUID | None,
    ) -> UUID:
        source_id = uuid4()
        await connection.execute(
            """INSERT INTO canonical.source_records (
                id, visibility, organization_id, namespace, external_id, source_type,
                source_url, published_at, source_updated_at, observed_at,
                raw_payload_ref, content_hash, provenance
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb)
            ON CONFLICT DO NOTHING""",
            source_id,
            "tenant" if organization_id else "global",
            organization_id,
            source.namespace.strip().casefold(),
            source.external_id.strip(),
            source.source_type.value,
            str(source.source_url) if source.source_url else None,
            source.published_at,
            source.source_updated_at,
            source.observed_at,
            source.raw_payload_ref,
            source.content_hash,
            json.dumps(source.provenance),
        )
        existing_id = await connection.fetchval(
            """SELECT id FROM canonical.source_records
            WHERE namespace = $1 AND external_id = $2
                            AND organization_id IS NOT DISTINCT FROM $3::uuid""",
            source.namespace.strip().casefold(),
            source.external_id.strip(),
            organization_id,
        )
        if existing_id is None:
            raise CanonicalConflictError("source record could not be persisted")
        return existing_id

    async def create_entity(
        self,
        payload: CanonicalEntityCreate,
        principal: CanonicalPrincipal,
    ) -> dict[str, Any]:
        organization_id = self._scope(payload.visibility, principal)
        entity_id = uuid4()
        normalized_name = normalize_name(payload.preferred_name)
        try:
            async with self.store.connection(organization_id) as connection:
                source_id = await self._source_record(connection, payload.source_record, organization_id)
                await connection.execute(
                    """INSERT INTO canonical.entities (
                        id, entity_type, preferred_name, normalized_name, description,
                        modality, lifecycle_status, attributes, visibility,
                        organization_id, created_by, created_source_record_id
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10, $11, $12)""",
                    entity_id,
                    payload.entity_type.value,
                    payload.preferred_name.strip(),
                    normalized_name,
                    payload.description,
                    payload.modality.value if payload.modality else None,
                    payload.lifecycle_status,
                    json.dumps(payload.attributes),
                    payload.visibility.value,
                    organization_id,
                    principal.user_id,
                    source_id,
                )
                if payload.lifecycle_status:
                    await connection.execute(
                        """INSERT INTO canonical.observations (
                            id, entity_id, property_name, observation_kind, value,
                            verification_state, source_record_id, published_at,
                            observed_at, source_updated_at, visibility, organization_id
                        ) VALUES ($1, $2, 'lifecycle_status', 'normalized_observation', $3::jsonb,
                            'unreviewed', $4, $5, $6, $7, $8, $9)""",
                        uuid4(), entity_id, json.dumps(payload.lifecycle_status), source_id,
                        payload.source_record.published_at, payload.source_record.observed_at,
                        payload.source_record.source_updated_at, payload.visibility.value, organization_id,
                    )
                timestamps = await connection.fetchrow(
                    "SELECT created_at, updated_at FROM canonical.entities WHERE id = $1",
                    entity_id,
                )
                for identifier in payload.identifiers:
                    identifier_source_id = await self._source_record(connection, identifier.source_record, organization_id)
                    await connection.execute(
                        """INSERT INTO canonical.identifiers (
                            id, entity_id, visibility, organization_id, namespace,
                            identifier_type, value, normalized_value, source_record_id
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                        uuid4(), entity_id, payload.visibility.value, organization_id,
                        identifier.namespace.strip().casefold(), identifier.identifier_type.strip().casefold(),
                        identifier.value.strip(), normalize_identifier(identifier.value), identifier_source_id,
                    )
                for alias in payload.aliases:
                    if alias.verification_state.value != "unreviewed" and (
                        not principal.can_review or principal.user_id is None
                    ):
                        raise CanonicalAuthorizationError("reviewed aliases require a reviewer role")
                    await self._insert_alias(
                        connection, entity_id, payload.visibility, organization_id, alias, principal.user_id
                    )
                await self._enqueue_entity_projection(connection, entity_id, organization_id)
                return await self._get_entity(connection, entity_id, organization_id)
        except asyncpg.UniqueViolationError as exc:
            raise CanonicalConflictError("canonical name or external identifier already exists in this scope") from exc

    async def _insert_alias(
        self,
        connection: asyncpg.Connection,
        entity_id: UUID,
        visibility: Visibility,
        organization_id: UUID | None,
        alias: AliasInput,
        verified_by: UUID | None,
    ) -> None:
        source_id = await self._source_record(connection, alias.source_record, organization_id)
        await connection.execute(
            """INSERT INTO canonical.aliases (
                id, entity_id, visibility, organization_id, value, normalized_value,
                alias_type, verification_state, source_record_id, verified_by, verified_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                CASE WHEN $8 = 'verified' THEN NOW() ELSE NULL END)""",
            uuid4(), entity_id, visibility.value, organization_id, alias.value.strip(),
            normalize_name(alias.value), alias.alias_type, alias.verification_state.value, source_id, verified_by,
        )

    async def _enqueue_entity_projection(
        self,
        connection: asyncpg.Connection,
        entity_id: UUID,
        organization_id: UUID | None,
    ) -> None:
        row = await connection.fetchrow(
            """UPDATE canonical.entities SET updated_at = NOW()
            WHERE id = $1 AND (organization_id IS NULL OR organization_id = $2)
            RETURNING id, entity_type, preferred_name, description, modality,
                lifecycle_status, visibility, organization_id, attributes,
                created_source_record_id, created_at, updated_at""",
            entity_id, organization_id,
        )
        if row is None:
            raise CanonicalNotFoundError("canonical entity not found")
        identifiers = await connection.fetch(
            """SELECT namespace, identifier_type, value
            FROM canonical.identifiers WHERE entity_id = $1
              AND (organization_id IS NULL OR organization_id = $2)
            ORDER BY namespace, identifier_type, value""",
            entity_id, organization_id,
        )
        aliases = await connection.fetch(
            """SELECT value, alias_type, verification_state
            FROM canonical.aliases WHERE entity_id = $1
              AND (organization_id IS NULL OR organization_id = $2)
            ORDER BY normalized_value, value""",
            entity_id, organization_id,
        )
        source_id = row["created_source_record_id"]
        projection_payload = {
            "id": str(row["id"]),
            "entity_type": row["entity_type"],
            "preferred_name": row["preferred_name"],
            "description": row["description"],
            "modality": row["modality"],
            "lifecycle_status": row["lifecycle_status"],
            "visibility": row["visibility"],
            "organization_id": str(row["organization_id"]) if row["organization_id"] else None,
            "source_record_id": str(source_id) if source_id else None,
            "attributes": self._json_value(row["attributes"]),
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
            "identifiers": [dict(item) for item in identifiers],
            "aliases": [dict(item) for item in aliases],
        }
        event_visibility = row["visibility"]
        event_organization_id = row["organization_id"]
        await connection.execute(
            """INSERT INTO canonical.projection_outbox (
                event_type, aggregate_id, visibility, organization_id, payload
            ) VALUES ('entity.upserted', $1, $2, $3, $4::jsonb)""",
            entity_id, event_visibility, event_organization_id, json.dumps(projection_payload),
        )

    async def _get_entity(
        self, connection: asyncpg.Connection, entity_id: UUID, organization_id: UUID | None
    ) -> dict[str, Any]:
        row = await connection.fetchrow(
            """SELECT id, entity_type, preferred_name, normalized_name, description,
                modality, lifecycle_status, visibility, organization_id, attributes,
                created_source_record_id, created_at, updated_at
            FROM canonical.entities
            WHERE id = $1 AND (organization_id IS NULL OR organization_id = $2)""",
            entity_id,
            organization_id,
        )
        if row is None:
            raise CanonicalNotFoundError("canonical entity not found")
        result = dict(row)
        result["attributes"] = self._json_value(result["attributes"])
        result["identifiers"] = [dict(item) for item in await connection.fetch(
            """SELECT namespace, identifier_type, value, source_record_id, created_at
            FROM canonical.identifiers WHERE entity_id = $1
              AND (organization_id IS NULL OR organization_id = $2)
            ORDER BY namespace, identifier_type, value""",
            entity_id, organization_id,
        )]
        result["aliases"] = [dict(item) for item in await connection.fetch(
            """SELECT value, alias_type, verification_state, source_record_id,
                verified_by, created_at, verified_at
            FROM canonical.aliases WHERE entity_id = $1
              AND (organization_id IS NULL OR organization_id = $2)
            ORDER BY normalized_value, value""",
            entity_id, organization_id,
        )]
        return result

    async def get_entity(self, entity_id: UUID, principal: CanonicalPrincipal) -> dict[str, Any]:
        async with self.store.connection(principal.organization_id) as connection:
            return await self._get_entity(connection, entity_id, principal.organization_id)

    async def list_entities(
        self,
        entity_type: str,
        principal: CanonicalPrincipal,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        offset = (page - 1) * page_size
        async with self.store.connection(principal.organization_id) as connection:
            ids = await connection.fetch(
                """SELECT id FROM canonical.entities
                WHERE entity_type = $1 AND (organization_id IS NULL OR organization_id = $2)
                ORDER BY normalized_name, id OFFSET $3 LIMIT $4""",
                entity_type, principal.organization_id, offset, page_size,
            )
            total = await connection.fetchval(
                """SELECT count(*) FROM canonical.entities
                WHERE entity_type = $1 AND (organization_id IS NULL OR organization_id = $2)""",
                entity_type, principal.organization_id,
            )
            return [await self._get_entity(connection, row["id"], principal.organization_id) for row in ids], total

    async def list_regulatory_events(
        self,
        principal: CanonicalPrincipal,
        *,
        event_id: str | None = None,
        regulator: str | None = None,
        jurisdiction: str | None = None,
        event_type: RegulatoryEventType | None = None,
        event_status: str | None = None,
        as_of: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        self._require_aware_as_of(as_of)
        async with self.store.connection(principal.organization_id) as connection:
            entities = await connection.fetch(
                """SELECT id, preferred_name, visibility, organization_id, attributes,
                    created_at, updated_at
                FROM canonical.entities
                WHERE entity_type = 'regulatory_event'
                  AND (organization_id IS NULL OR organization_id = $1::uuid)
                  AND ($2::timestamptz IS NULL OR created_at <= $2)
                ORDER BY created_at DESC, id""",
                principal.organization_id,
                as_of,
            )
            entity_ids = [row["id"] for row in entities]
            observations: dict[UUID, dict[str, dict[str, Any]]] = {
                entity_id: {} for entity_id in entity_ids
            }
            if entity_ids:
                fact_rows = await connection.fetch(
                    """SELECT entity_id, property_name, value, source_record_id, created_at
                    FROM canonical.observations
                    WHERE entity_id = ANY($1::uuid[])
                      AND observation_kind = 'source_fact'
                      AND (organization_id IS NULL OR organization_id = $2::uuid)
                      AND ($3::timestamptz IS NULL OR created_at <= $3)
                    ORDER BY created_at, id""",
                    entity_ids,
                    principal.organization_id,
                    as_of,
                )
                for fact in fact_rows:
                    observations[fact["entity_id"]][fact["property_name"]] = {
                        "value": self._json_value(fact["value"]),
                        "source_record_id": str(fact["source_record_id"]),
                        "available_at": fact["created_at"].isoformat(),
                    }

            items: list[dict[str, Any]] = []
            for entity in entities:
                facts = observations[entity["id"]]
                values = {
                    key: item["value"] for key, item in facts.items()
                }
                # Current attributes may include non-source defaults. Historical
                # responses are reconstructed only from facts available by cutoff.
                attrs = (
                    self._json_value(entity["attributes"])
                    if as_of is None
                    else values
                )
                selected_regulator = values.get("regulator", attrs.get("authority"))
                selected_jurisdiction = values.get("jurisdiction", attrs.get("jurisdiction"))
                selected_event_id = values.get("event_id", attrs.get("event_id"))
                selected_type = values.get("event_type", attrs.get("event_type"))
                selected_status = values.get("event_status", attrs.get("event_status"))
                if event_id and str(selected_event_id).casefold() != event_id.casefold():
                    continue
                if regulator and str(selected_regulator).casefold() != regulator.casefold():
                    continue
                if jurisdiction and str(selected_jurisdiction).casefold() != jurisdiction.casefold():
                    continue
                if event_type and selected_type != event_type.value:
                    continue
                if event_status and str(selected_status).casefold() != event_status.casefold():
                    continue
                items.append({
                    "id": entity["id"],
                    "title": entity["preferred_name"],
                    "visibility": entity["visibility"],
                    "organization_id": entity["organization_id"],
                    "attributes": attrs,
                    "facts": facts,
                    "created_at": entity["created_at"],
                    "updated_at": entity["updated_at"],
                })
            total = len(items)
            offset = (page - 1) * page_size
            return items[offset:offset + page_size], total

    async def create_relationship(
        self,
        payload: CanonicalRelationshipCreate,
        principal: CanonicalPrincipal,
    ) -> dict[str, Any]:
        relationship_id = uuid4()
        organization_id = self._scope(payload.visibility, principal)
        try:
            async with self.store.connection(principal.organization_id) as connection:
                endpoints = await connection.fetch(
                    """SELECT id, visibility, organization_id FROM canonical.entities
                    WHERE id = ANY($1::uuid[])
                      AND (organization_id IS NULL OR organization_id = $2)""",
                    [payload.subject_entity_id, payload.object_entity_id], principal.organization_id,
                )
                if len(endpoints) != 2:
                    raise CanonicalNotFoundError("one or both canonical relationship endpoints were not found")
                private_scopes = {
                    row["organization_id"] for row in endpoints if row["organization_id"] is not None
                }
                if private_scopes and private_scopes != {organization_id}:
                    raise CanonicalAuthorizationError("cross-organization relationships are not allowed")
                if payload.verification_state.value != "unreviewed" and (
                    not principal.can_review or principal.user_id is None
                ):
                    raise CanonicalAuthorizationError("reviewed observations require a reviewer role")
                source_id = await self._source_record(connection, payload.source_record, organization_id)
                await connection.execute(
                    """INSERT INTO canonical.relationships (
                        id, subject_entity_id, predicate, object_entity_id,
                        visibility, organization_id, attributes
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)""",
                    relationship_id, payload.subject_entity_id, payload.predicate,
                    payload.object_entity_id, payload.visibility.value, organization_id,
                    json.dumps(payload.attributes),
                )
                observation_id = uuid4()
                await connection.execute(
                    """INSERT INTO canonical.observations (
                        id, entity_id, relationship_id, property_name, observation_kind,
                        value, verification_state, confidence, source_record_id,
                        valid_from, valid_to, visibility, organization_id,
                        manually_verified_by, manually_verified_at
                    ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11,
                        $12, $13, $14, CASE WHEN $7 = 'verified' THEN NOW() ELSE NULL END)""",
                    observation_id, payload.subject_entity_id, relationship_id, payload.property_name,
                    payload.observation_kind.value, json.dumps(payload.observation_value),
                    payload.verification_state.value, payload.confidence, source_id,
                    payload.valid_from, payload.valid_to, payload.visibility.value, organization_id, principal.user_id,
                )
                created_at = await connection.fetchval(
                    "SELECT created_at FROM canonical.relationships WHERE id = $1", relationship_id
                )
                outbox_payload = {
                    "id": str(relationship_id),
                    "subject_entity_id": str(payload.subject_entity_id),
                    "predicate": payload.predicate,
                    "object_entity_id": str(payload.object_entity_id),
                    "visibility": payload.visibility.value,
                    "organization_id": str(organization_id) if organization_id else None,
                    "attributes": payload.attributes,
                    "created_at": created_at.isoformat(),
                    "updated_at": created_at.isoformat(),
                }
                await connection.execute(
                    """INSERT INTO canonical.projection_outbox (
                        event_type, aggregate_id, visibility, organization_id, payload
                    ) VALUES ('relationship.upserted', $1, $2, $3, $4::jsonb)""",
                    relationship_id, payload.visibility.value, organization_id, json.dumps(outbox_payload),
                )
                return {
                    **outbox_payload,
                    "observation_id": str(observation_id),
                    "source_record_id": str(source_id),
                    "created_at": created_at,
                }
        except asyncpg.UniqueViolationError as exc:
            raise CanonicalConflictError("canonical relationship conflicts with existing data") from exc

    async def create_observation(
        self,
        payload: ObservationCreate,
        principal: CanonicalPrincipal,
    ) -> dict[str, Any]:
        observation_id = uuid4()
        organization_id = self._scope(payload.visibility, principal)
        try:
            async with self.store.connection(principal.organization_id) as connection:
                entity = await connection.fetchrow(
                    """SELECT visibility, organization_id FROM canonical.entities
                    WHERE id = $1 AND (organization_id IS NULL OR organization_id = $2)""",
                    payload.entity_id, principal.organization_id,
                )
                if entity is None:
                    raise CanonicalNotFoundError("canonical entity not found")
                entity_organization_id = entity["organization_id"]
                if entity_organization_id is not None and entity_organization_id != organization_id:
                    raise CanonicalAuthorizationError("observation scope must match its private entity")
                if payload.relationship_id:
                    relationship = await connection.fetchrow(
                        """SELECT id, organization_id FROM canonical.relationships WHERE id = $1
                        AND subject_entity_id = $2
                        AND (organization_id IS NULL OR organization_id = $3)""",
                        payload.relationship_id, payload.entity_id, principal.organization_id,
                    )
                    if relationship is None:
                        raise CanonicalNotFoundError("canonical relationship not found")
                    if relationship["organization_id"] is not None and relationship["organization_id"] != organization_id:
                        raise CanonicalAuthorizationError("observation scope must match its private relationship")
                if payload.verification_state.value != "unreviewed" and (
                    not principal.can_review or principal.user_id is None
                ):
                    raise CanonicalAuthorizationError("reviewed observations require a reviewer role")
                if payload.observation_kind.value == "hypothesis" and payload.verification_state.value != "unreviewed":
                    raise CanonicalAuthorizationError("hypotheses must remain unreviewed")
                source_id = await self._source_record(connection, payload.source_record, organization_id)
                if payload.supersedes_observation_id:
                    superseded = await connection.fetchval(
                        """SELECT 1 FROM canonical.observations WHERE id = $1 AND entity_id = $2
                        AND (organization_id IS NULL OR organization_id = $3)""",
                        payload.supersedes_observation_id, payload.entity_id, principal.organization_id,
                    )
                    if not superseded:
                        raise CanonicalNotFoundError("superseded observation not found")
                row = await connection.fetchrow(
                    """INSERT INTO canonical.observations (
                        id, entity_id, relationship_id, property_name, observation_kind,
                        value, verification_state, confidence, source_record_id, valid_from,
                        valid_to, published_at, observed_at, source_updated_at, normalizer_version,
                        supersedes_observation_id, visibility, organization_id,
                        manually_verified_by, manually_verified_at
                    ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11,
                        $12, $13, $14, $15, $16, $17, $18, $19,
                        CASE WHEN $7 = 'verified' THEN NOW() ELSE NULL END) RETURNING *""",
                    observation_id, payload.entity_id, payload.relationship_id,
                    payload.property_name, payload.observation_kind.value, json.dumps(payload.value),
                    payload.verification_state.value, payload.confidence, source_id,
                    payload.valid_from, payload.valid_to, payload.source_record.published_at,
                    payload.source_record.observed_at, payload.source_record.source_updated_at,
                    payload.normalizer_version, payload.supersedes_observation_id,
                    payload.visibility.value, organization_id,
                    principal.user_id,
                )
                result = dict(row)
                result["value"] = self._json_value(result["value"])
                await self._enqueue_entity_projection(connection, payload.entity_id, organization_id)
                return result
        except asyncpg.UniqueViolationError as exc:
            raise CanonicalConflictError("observation conflicts with existing data") from exc

    async def create_claim(
        self,
        payload: ClaimCreate,
        principal: CanonicalPrincipal,
    ) -> dict[str, Any]:
        claim_id = uuid4()
        organization_id = self._scope(payload.visibility, principal)
        try:
            async with self.store.connection(principal.organization_id) as connection:
                entity = await connection.fetchrow(
                    """SELECT visibility, organization_id FROM canonical.entities
                    WHERE id = $1 AND (organization_id IS NULL OR organization_id = $2)""",
                    payload.entity_id, principal.organization_id,
                )
                if entity is None:
                    raise CanonicalNotFoundError("canonical entity not found")
                if entity["organization_id"] is not None and entity["organization_id"] != organization_id:
                    raise CanonicalAuthorizationError("claim scope must match the private entity")
                if payload.observation_id:
                    observation = await connection.fetchrow(
                        """SELECT id, entity_id, organization_id FROM canonical.observations
                        WHERE id = $1 AND entity_id = $2
                          AND (organization_id IS NULL OR organization_id = $3)""",
                        payload.observation_id, payload.entity_id, principal.organization_id,
                    )
                    if observation is None:
                        raise CanonicalNotFoundError("observation not found")
                source_id = await self._source_record(connection, payload.source_record, organization_id)
                row = await connection.fetchrow(
                    """INSERT INTO canonical.claims (
                        id, entity_id, claim_type, statement, visibility, organization_id,
                        confidence, source_record_id, observation_id, valid_from, valid_to
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING *""",
                    claim_id,
                    payload.entity_id,
                    payload.claim_type.value,
                    payload.statement.strip(),
                    payload.visibility.value,
                    organization_id,
                    payload.confidence,
                    source_id,
                    payload.observation_id,
                    payload.valid_from,
                    payload.valid_to,
                )
                await self._enqueue_entity_projection(connection, payload.entity_id, organization_id)
                return dict(row)
        except asyncpg.UniqueViolationError as exc:
            raise CanonicalConflictError("claim conflicts with existing data") from exc

    async def link_evidence(
        self,
        claim_id: UUID,
        payload: EvidenceLinkCreate,
        principal: CanonicalPrincipal,
    ) -> dict[str, Any]:
        organization_id = self._scope(payload.visibility, principal)
        async with self.store.connection(principal.organization_id) as connection:
            claim = await connection.fetchrow(
                """SELECT id, entity_id, organization_id, visibility FROM canonical.claims
                WHERE id = $1 AND (organization_id IS NULL OR organization_id = $2)""",
                claim_id, principal.organization_id,
            )
            if claim is None:
                raise CanonicalNotFoundError("claim not found")
            if claim["organization_id"] is not None and claim["organization_id"] != organization_id:
                raise CanonicalAuthorizationError("evidence scope must match the private claim")
            if payload.observation_id:
                observation = await connection.fetchrow(
                    """SELECT id, entity_id, organization_id FROM canonical.observations
                    WHERE id = $1 AND entity_id = $2
                      AND (organization_id IS NULL OR organization_id = $3)""",
                    payload.observation_id, claim["entity_id"], principal.organization_id,
                )
                if observation is None:
                    raise CanonicalNotFoundError("observation not found for this claim")
            if payload.source_record_id:
                source = await connection.fetchrow(
                    """SELECT id, organization_id FROM canonical.source_records
                    WHERE id = $1 AND (organization_id IS NULL OR organization_id = $2)""",
                    payload.source_record_id, principal.organization_id,
                )
                if source is None:
                    raise CanonicalNotFoundError("source record not found")
            row = await connection.fetchrow(
                """INSERT INTO canonical.evidence_links (
                    id, claim_id, observation_id, source_record_id, relation_type,
                    metadata, visibility, organization_id, valid_from, valid_to
                ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10) RETURNING *""",
                uuid4(), claim_id, payload.observation_id, payload.source_record_id,
                payload.relation_type.value, json.dumps(payload.metadata), payload.visibility.value,
                organization_id, payload.valid_from, payload.valid_to,
            )
            await self._enqueue_entity_projection(connection, claim["entity_id"], organization_id)
            return dict(row)

    async def list_claims(
        self,
        entity_id: UUID,
        principal: CanonicalPrincipal,
        page: int = 1,
        page_size: int = 20,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_aware_as_of(as_of)
        offset = (page - 1) * page_size
        async with self.store.connection(principal.organization_id) as connection:
            rows = await connection.fetch(
                """WITH cutoff AS (SELECT COALESCE($3::timestamptz, transaction_timestamp()) AS at)
                SELECT c.* FROM canonical.claims c CROSS JOIN cutoff t
                WHERE c.entity_id = $1 AND (c.organization_id IS NULL OR c.organization_id = $2)
                  AND (c.valid_from IS NULL OR c.valid_from <= t.at)
                  AND (c.valid_to IS NULL OR c.valid_to >= t.at)
                  AND c.created_at <= t.at
                  AND EXISTS (
                      SELECT 1 FROM canonical.source_records s
                      WHERE s.id = c.source_record_id AND s.ingested_at <= t.at
                  )
                  AND EXISTS (
                      SELECT 1 FROM canonical.entities e
                      JOIN canonical.source_records es ON es.id = e.created_source_record_id
                      WHERE e.id = c.entity_id AND e.created_at <= t.at AND es.ingested_at <= t.at
                  )
                  AND (c.observation_id IS NULL OR EXISTS (
                      SELECT 1 FROM canonical.observations o
                      JOIN canonical.source_records os ON os.id = o.source_record_id
                      WHERE o.id = c.observation_id AND o.ingested_at <= t.at AND os.ingested_at <= t.at
                        AND (o.valid_from IS NULL OR o.valid_from <= t.at)
                        AND (o.valid_to IS NULL OR o.valid_to >= t.at)
                  ))
                ORDER BY c.valid_from NULLS LAST, c.created_at DESC OFFSET $4 LIMIT $5""",
                entity_id, principal.organization_id, as_of, offset, page_size,
            )
            total = await connection.fetchval(
                """WITH cutoff AS (SELECT COALESCE($3::timestamptz, transaction_timestamp()) AS at)
                SELECT count(*) FROM canonical.claims c CROSS JOIN cutoff t
                WHERE c.entity_id = $1 AND (c.organization_id IS NULL OR c.organization_id = $2)
                  AND (c.valid_from IS NULL OR c.valid_from <= t.at)
                  AND (c.valid_to IS NULL OR c.valid_to >= t.at)
                  AND c.created_at <= t.at
                  AND EXISTS (
                      SELECT 1 FROM canonical.source_records s
                      WHERE s.id = c.source_record_id AND s.ingested_at <= t.at
                  )
                  AND EXISTS (
                      SELECT 1 FROM canonical.entities e
                      JOIN canonical.source_records es ON es.id = e.created_source_record_id
                      WHERE e.id = c.entity_id AND e.created_at <= t.at AND es.ingested_at <= t.at
                  )
                  AND (c.observation_id IS NULL OR EXISTS (
                      SELECT 1 FROM canonical.observations o
                      JOIN canonical.source_records os ON os.id = o.source_record_id
                      WHERE o.id = c.observation_id AND o.ingested_at <= t.at AND os.ingested_at <= t.at
                        AND (o.valid_from IS NULL OR o.valid_from <= t.at)
                        AND (o.valid_to IS NULL OR o.valid_to >= t.at)
                  ))""",
                entity_id, principal.organization_id, as_of,
            )
            items = [dict(row) for row in rows]
            return {"items": items, "total": total, "page": page, "page_size": page_size}

    async def get_claim_lineage(
        self,
        claim_id: UUID,
        principal: CanonicalPrincipal,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_aware_as_of(as_of)
        async with self.store.connection(principal.organization_id) as connection:
            claim = await connection.fetchrow(
                """WITH cutoff AS (SELECT COALESCE($3::timestamptz, transaction_timestamp()) AS at)
                SELECT c.*, to_jsonb(cs) AS source_record,
                    CASE WHEN o.id IS NULL THEN NULL ELSE to_jsonb(o) END AS observation,
                    CASE WHEN os.id IS NULL THEN NULL ELSE to_jsonb(os) END AS observation_source_record
                FROM canonical.claims c
                CROSS JOIN cutoff t
                JOIN canonical.source_records cs ON cs.id = c.source_record_id
                LEFT JOIN canonical.observations o ON o.id = c.observation_id
                    AND (o.organization_id IS NULL OR o.organization_id = $2)
                LEFT JOIN canonical.source_records os ON os.id = o.source_record_id
                WHERE c.id = $1 AND (c.organization_id IS NULL OR c.organization_id = $2)
                  AND c.created_at <= t.at AND cs.ingested_at <= t.at
                  AND (c.valid_from IS NULL OR c.valid_from <= t.at)
                  AND (c.valid_to IS NULL OR c.valid_to >= t.at)
                  AND EXISTS (
                      SELECT 1 FROM canonical.entities e
                      JOIN canonical.source_records es ON es.id = e.created_source_record_id
                      WHERE e.id = c.entity_id AND e.created_at <= t.at AND es.ingested_at <= t.at
                  )
                  AND (c.observation_id IS NULL OR (
                      o.id IS NOT NULL AND os.id IS NOT NULL AND o.ingested_at <= t.at AND os.ingested_at <= t.at
                      AND (o.valid_from IS NULL OR o.valid_from <= t.at)
                      AND (o.valid_to IS NULL OR o.valid_to >= t.at)
                  ))""",
                claim_id, principal.organization_id, as_of,
            )
            if claim is None:
                raise CanonicalNotFoundError("claim not found")
            evidence_rows = await connection.fetch(
                """WITH cutoff AS (SELECT COALESCE($3::timestamptz, transaction_timestamp()) AS at)
                SELECT el.*,
                    CASE WHEN o.id IS NULL THEN NULL ELSE to_jsonb(o) END AS observation,
                    CASE WHEN os.id IS NULL THEN NULL ELSE to_jsonb(os) END AS observation_source_record,
                    CASE WHEN s.id IS NULL THEN NULL ELSE to_jsonb(s) END AS source_record
                FROM canonical.evidence_links el
                CROSS JOIN cutoff t
                LEFT JOIN canonical.observations o ON o.id = el.observation_id
                    AND (o.organization_id IS NULL OR o.organization_id = $2)
                LEFT JOIN canonical.source_records os ON os.id = o.source_record_id
                LEFT JOIN canonical.source_records s ON s.id = el.source_record_id
                WHERE el.claim_id = $1 AND (el.organization_id IS NULL OR el.organization_id = $2)
                                    AND el.created_at <= t.at
                                    AND (el.valid_from IS NULL OR el.valid_from <= t.at)
                                    AND (el.valid_to IS NULL OR el.valid_to >= t.at)
                                    AND (el.source_record_id IS NULL OR (s.id IS NOT NULL AND s.ingested_at <= t.at))
                                    AND (el.observation_id IS NULL OR (
                                            o.id IS NOT NULL AND os.id IS NOT NULL AND o.ingested_at <= t.at AND os.ingested_at <= t.at
                                            AND (o.valid_from IS NULL OR o.valid_from <= t.at)
                                            AND (o.valid_to IS NULL OR o.valid_to >= t.at)
                  ))
                ORDER BY el.relation_type, el.created_at DESC""",
                claim_id, principal.organization_id, as_of,
            )
            evidence = [dict(row) for row in evidence_rows]
            claim_result = dict(claim)
            for key in ("source_record", "observation", "observation_source_record"):
                claim_result[key] = self._json_value(claim_result[key])
            if claim_result["observation"] is not None:
                claim_result["observation"]["value"] = self._json_value(claim_result["observation"]["value"])
            if claim_result["observation"] is not None:
                claim_result["observation"]["source_record"] = claim_result["observation_source_record"]
            claim_result.pop("observation_source_record")
            for row in evidence:
                row["metadata"] = self._json_value(row["metadata"])
                for key in ("observation", "observation_source_record", "source_record"):
                    row[key] = self._json_value(row[key])
                if row["observation"] is not None:
                    row["observation"]["value"] = self._json_value(row["observation"]["value"])
                    row["observation"]["source_record"] = row["observation_source_record"]
                row.pop("observation_source_record")
            claim_result["evidence"] = evidence
            claim_result["supporting_evidence"] = [row for row in evidence if row["relation_type"] == "supporting"]
            claim_result["contradicting_evidence"] = [row for row in evidence if row["relation_type"] == "contradicting"]
            return claim_result

    async def get_search_context(
        self,
        entity_ids: list[UUID],
        principal: CanonicalPrincipal,
        as_of: datetime | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Return tenant-scoped canonical identity and evidence for search hits."""
        self._require_aware_as_of(as_of)
        result: dict[str, dict[str, Any]] = {}
        for entity_id in dict.fromkeys(entity_ids):
            async with self.store.connection(principal.organization_id) as connection:
                entity = await connection.fetchrow(
                    """WITH cutoff AS (
                        SELECT COALESCE($3::timestamptz, transaction_timestamp()) AS at
                    )
                    SELECT e.id, to_jsonb(s) AS source_record
                    FROM canonical.entities e
                    JOIN canonical.source_records s ON s.id = e.created_source_record_id
                    CROSS JOIN cutoff t
                    WHERE e.id = $1 AND (e.organization_id IS NULL OR e.organization_id = $2)
                      AND e.created_at <= t.at AND s.ingested_at <= t.at""",
                    entity_id, principal.organization_id, as_of,
                )
                if entity is None:
                    continue
                identifiers = await connection.fetch(
                    """SELECT i.namespace, i.identifier_type, i.value, i.source_record_id, i.created_at
                    FROM canonical.identifiers i
                    JOIN canonical.source_records s ON s.id = i.source_record_id
                    WHERE i.entity_id = $1 AND (i.organization_id IS NULL OR i.organization_id = $2)
                      AND ($3::timestamptz IS NULL OR (i.created_at <= $3 AND s.ingested_at <= $3))
                    ORDER BY i.namespace, i.identifier_type, i.value""",
                    entity_id, principal.organization_id, as_of,
                )
                aliases = await connection.fetch(
                    """SELECT a.value, a.alias_type, a.verification_state, a.source_record_id,
                        a.created_at, a.verified_at
                    FROM canonical.aliases a
                    JOIN canonical.source_records s ON s.id = a.source_record_id
                    WHERE a.entity_id = $1 AND (a.organization_id IS NULL OR a.organization_id = $2)
                      AND ($3::timestamptz IS NULL OR (a.created_at <= $3 AND s.ingested_at <= $3))
                    ORDER BY a.normalized_value, a.value""",
                    entity_id, principal.organization_id, as_of,
                )
                source_record = self._json_value(entity["source_record"])

            observations, _ = await self.list_observations(
                entity_id, principal, page=1, page_size=100, as_of=as_of
            )
            claims_page = await self.list_claims(
                entity_id, principal, page=1, page_size=100, as_of=as_of
            )
            claim_lineage = [
                await self.get_claim_lineage(claim["id"], principal, as_of=as_of)
                for claim in claims_page["items"]
            ]
            result[str(entity_id)] = {
                "source_record": source_record,
                "identifiers": [dict(item) for item in identifiers],
                "aliases": [dict(item) for item in aliases],
                "observations": observations,
                "claims": claim_lineage,
                "contradictory": any(claim["contradicting_evidence"] for claim in claim_lineage),
            }
        return result

    async def ensure_identifier(
        self,
        entity_id: UUID,
        namespace: str,
        identifier_type: str,
        value: str,
        source_record: SourceRecordInput,
        visibility: Visibility,
        principal: CanonicalPrincipal,
    ) -> None:
        """Persist a source identifier once without changing B01 matching semantics."""
        organization_id = self._scope(visibility, principal)
        async with self.store.connection(principal.organization_id) as connection:
            existing = await connection.fetchval(
                """SELECT 1 FROM canonical.identifiers
                WHERE entity_id = $1 AND namespace = $2 AND identifier_type = $3
                  AND normalized_value = $4
                                    AND (organization_id IS NULL OR organization_id = $5::uuid)""",
                entity_id, namespace.strip().casefold(), identifier_type.strip().casefold(),
                normalize_identifier(value), principal.organization_id,
            )
            if existing:
                return
            source_id = await self._source_record(connection, source_record, organization_id)
            inserted_id = await connection.fetchval(
                """INSERT INTO canonical.identifiers (
                    id, entity_id, visibility, organization_id, namespace,
                    identifier_type, value, normalized_value, source_record_id
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT DO NOTHING RETURNING id""",
                uuid4(), entity_id, visibility.value, organization_id,
                namespace.strip().casefold(), identifier_type.strip().casefold(),
                value.strip(), normalize_identifier(value), source_id,
            )
            if inserted_id is not None:
                await self._enqueue_entity_projection(connection, entity_id, organization_id)

    async def ensure_observation(
        self,
        payload: ObservationCreate,
        principal: CanonicalPrincipal,
    ) -> dict[str, Any] | None:
        """Insert a factual observation once per entity/property/source tuple."""
        async with self.store.connection(principal.organization_id) as connection:
            source_id = await self._source_record(
                connection,
                payload.source_record,
                self._scope(payload.visibility, principal),
            )
            existing = await connection.fetchrow(
                """SELECT id, entity_id, value FROM canonical.observations
                WHERE entity_id = $1 AND property_name = $2 AND source_record_id = $3
                AND (organization_id IS NULL OR organization_id = $4::uuid)""",
                payload.entity_id, payload.property_name, source_id, principal.organization_id,
            )
            if existing:
                return dict(existing)
        return await self.create_observation(payload, principal)

    async def ingest_pubmed_article(
        self,
        payload: PubMedArticleIngest,
        principal: CanonicalPrincipal,
    ) -> dict[str, Any]:
        visibility = Visibility.TENANT if principal.organization_id else Visibility.GLOBAL
        organization_id = self._scope(visibility, principal)
        source_url = f"https://pubmed.ncbi.nlm.nih.gov/{payload.pmid}/"
        source_metadata = {
            key: value for key, value in payload.source_metadata.items() if key != "raw_xml"
        }
        source_record = SourceRecordInput(
            namespace="pubmed",
            external_id=f"{payload.pmid}:{payload.source_metadata.get('content_hash') or 'unversioned'}",
            source_type=SourceType.PUBLICATION,
            source_url=source_url,
            raw_payload_ref=(
                "literature_source_snapshots:pubmed:"
                f"{payload.pmid}:{payload.source_metadata.get('content_hash') or 'unversioned'}"
            ),
            content_hash=payload.source_metadata.get("content_hash"),
            provenance={
                "source": "NCBI PubMed",
                "pmid": payload.pmid,
                "pmcid": payload.pmcid,
                "doi": payload.doi,
                "retrieved_at": payload.retrieved_at.isoformat(),
                "publication_date_source": payload.publication_date_source,
                "query": payload.query,
                "parser": payload.source_metadata.get("parser"),
                "source_metadata": source_metadata,
            },
        )
        identifiers = [{
            "namespace": "pubmed",
            "identifier_type": "pmid",
            "value": payload.pmid,
        }]
        if payload.pmcid:
            identifiers.append({
                "namespace": "pmc",
                "identifier_type": "pmcid",
                "value": payload.pmcid,
            })
        if payload.doi:
            identifiers.append({
                "namespace": "doi",
                "identifier_type": "doi",
                "value": payload.doi,
            })

        reconciliation = await self.reconcile_legacy_record(
            {
                "source_type": "pubmed",
                "source_record_id": payload.pmid,
                "entity_type": EntityType.PUBLICATION.value,
                "names": [payload.title],
                "identifiers": identifiers,
                "tenant_id": str(organization_id) if organization_id else None,
                "metadata": {
                    "publication_date_source": payload.publication_date_source,
                    "source_metadata": source_metadata,
                },
                "source_record": source_record.model_dump(mode="json"),
            },
            principal,
            create_if_unresolved=True,
        )
        canonical_entity_id = reconciliation.get("canonical_entity_id")
        if canonical_entity_id is None:
            return {"reconciliation": reconciliation, "canonical_entity_id": None}

        entity_id = UUID(str(canonical_entity_id))
        for identifier in identifiers:
            await self.ensure_identifier(
                entity_id,
                identifier["namespace"],
                identifier["identifier_type"],
                identifier["value"],
                source_record,
                visibility,
                principal,
            )

        source_facts: dict[str, Any] = {"title": payload.title}
        for key, value in (
            ("abstract", payload.abstract),
            ("authors", payload.authors),
            ("journal", payload.journal),
            ("publication_date_source", payload.publication_date_source),
            ("pmid", payload.pmid),
            ("pmcid", payload.pmcid),
            ("doi", payload.doi),
            ("source_metadata", source_metadata),
        ):
            if value not in (None, [], {}):
                source_facts[key] = value

        observations: dict[str, dict[str, Any]] = {}
        for property_name, value in source_facts.items():
            observation = await self.ensure_observation(
                ObservationCreate(
                    entity_id=entity_id,
                    visibility=visibility,
                    property_name=property_name,
                    observation_kind=ObservationKind.SOURCE_FACT,
                    value=value,
                    source_record=source_record,
                ),
                principal,
            )
            observations[property_name] = observation

        if payload.extracted_entities:
            entity_type_by_label = {
                "drug": EntityType.THERAPEUTIC_ASSET.value,
                "drugs": EntityType.THERAPEUTIC_ASSET.value,
                "gene": EntityType.TARGET.value,
                "genes": EntityType.TARGET.value,
                "protein": EntityType.TARGET.value,
                "proteins": EntityType.TARGET.value,
                "target": EntityType.TARGET.value,
                "targets": EntityType.TARGET.value,
                "disease": EntityType.DISEASE.value,
                "diseases": EntityType.DISEASE.value,
                "clinical_trial": EntityType.CLINICAL_TRIAL.value,
                "clinical_trials": EntityType.CLINICAL_TRIAL.value,
                "company": EntityType.COMPANY.value,
                "companies": EntityType.COMPANY.value,
                "organization": EntityType.COMPANY.value,
                "organizations": EntityType.COMPANY.value,
                "biomarker": EntityType.BIOMARKER.value,
                "biomarkers": EntityType.BIOMARKER.value,
                "mutation": EntityType.RESISTANCE_MECHANISM.value,
                "mutations": EntityType.RESISTANCE_MECHANISM.value,
                "variant": EntityType.RESISTANCE_MECHANISM.value,
                "variants": EntityType.RESISTANCE_MECHANISM.value,
            }
            extraction_reconciliation = []
            for index, extracted in enumerate(payload.extracted_entities):
                mention = str(extracted.get("text") or "").strip()
                label = str(extracted.get("type") or extracted.get("category") or "").strip().casefold()
                entity_type = entity_type_by_label.get(label)
                if not mention or entity_type is None:
                    extraction_reconciliation.append({
                        "mention": mention,
                        "label": label,
                        "status": "UNRESOLVED",
                        "candidate_ids": [],
                        "reason": "unsupported or missing extracted entity type",
                    })
                    continue
                result = await self.reconcile_legacy_record(
                    {
                        "source_type": "pubmed_extraction",
                        "source_record_id": f"{payload.pmid}:{source_record.content_hash}:{index}",
                        "entity_type": entity_type,
                        "names": [mention],
                        "identifiers": extracted.get("identifiers", []),
                        "tenant_id": str(organization_id) if organization_id else None,
                        "metadata": {
                            "parent_pmid": payload.pmid,
                            "label": label,
                            "confidence": extracted.get("confidence_score", extracted.get("confidence")),
                            "origin": "literature_nlp",
                            "parser": source_metadata.get("parser"),
                        },
                        "source_record": source_record.model_dump(mode="json"),
                    },
                    principal,
                    create_if_unresolved=False,
                )
                extraction_reconciliation.append({
                    "mention": mention,
                    "label": label,
                    "status": result["status"],
                    "match_method": result.get("match_method"),
                    "candidate_ids": result.get("candidate_ids", []),
                })
            observations["extracted_entities"] = await self.ensure_observation(
                ObservationCreate(
                    entity_id=entity_id,
                    visibility=visibility,
                    property_name="extracted_entities",
                    observation_kind=ObservationKind.NORMALIZED_OBSERVATION,
                    value={
                        "items": payload.extracted_entities,
                        "origin": "literature_nlp",
                        "reconciliation": extraction_reconciliation,
                    },
                    source_record=source_record,
                ),
                principal,
            )
        if payload.extracted_relationships:
            observations["extracted_relationships"] = await self.ensure_observation(
                ObservationCreate(
                    entity_id=entity_id,
                    visibility=visibility,
                    property_name="extracted_relationships",
                    observation_kind=ObservationKind.NORMALIZED_OBSERVATION,
                    value={"items": payload.extracted_relationships, "origin": "literature_nlp"},
                    source_record=source_record,
                ),
                principal,
            )

        async with self.store.connection(principal.organization_id) as connection:
            source_record_id = await self._source_record(connection, source_record, organization_id)
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                f"pubmed-claim:{entity_id}:{payload.pmid}",
            )
            statement = f"PubMed indexed publication PMID:{payload.pmid}"
            claim = await connection.fetchrow(
                """SELECT * FROM canonical.claims
                WHERE entity_id = $1 AND source_record_id = $2
                  AND claim_type = 'source_fact' AND statement = $3
                  AND (organization_id IS NULL OR organization_id = $4)""",
                entity_id, source_record_id, statement, principal.organization_id,
            )
            if claim is None:
                claim = await connection.fetchrow(
                    """INSERT INTO canonical.claims (
                        id, entity_id, claim_type, statement, visibility, organization_id,
                        source_record_id, observation_id
                    ) VALUES ($1, $2, 'source_fact', $3, $4, $5, $6, $7)
                    RETURNING *""",
                    uuid4(), entity_id, statement, visibility.value, organization_id,
                    source_record_id, observations["title"]["id"],
                )
            claim_id = claim["id"]
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                f"pubmed-evidence:{claim_id}:{source_record_id}",
            )
            evidence_id = await connection.fetchval(
                """SELECT id FROM canonical.evidence_links
                WHERE claim_id = $1 AND source_record_id = $2 AND relation_type = 'supporting'
                  AND (organization_id IS NULL OR organization_id = $3) LIMIT 1""",
                claim_id, source_record_id, principal.organization_id,
            )
            if evidence_id is None:
                evidence_id = await connection.fetchval(
                    """INSERT INTO canonical.evidence_links (
                        id, claim_id, source_record_id, relation_type, metadata,
                        visibility, organization_id
                    ) VALUES ($1, $2, $3, 'supporting', $4::jsonb, $5, $6)
                    RETURNING id""",
                    uuid4(), claim_id, source_record_id,
                    json.dumps({"source": "pubmed", "pmid": payload.pmid}),
                    visibility.value, organization_id,
                )

        async with self.store.connection(principal.organization_id) as connection:
            await self._enqueue_entity_projection(connection, entity_id, organization_id)
        return {
            "reconciliation": reconciliation,
            "canonical_entity_id": str(entity_id),
            "source_record_id": str(source_record_id),
            "observation_ids": {key: str(row["id"]) for key, row in observations.items()},
            "claim_id": str(claim_id),
            "evidence_id": str(evidence_id),
            "visibility": visibility.value,
        }

    async def ingest_clinical_trial(
        self,
        payload: ClinicalTrialIngest,
        principal: CanonicalPrincipal,
    ) -> dict[str, Any]:
        nct_id = payload.nct_id
        visibility = Visibility.TENANT if principal.organization_id else Visibility.GLOBAL
        organization_id = self._scope(visibility, principal)
        source_record = SourceRecordInput(
            namespace="clinicaltrials",
            external_id=f"{nct_id}:{payload.content_hash}",
            source_type="trial_registry",
            source_url=f"https://clinicaltrials.gov/study/{nct_id}",
            raw_payload_ref=f"literature_source_snapshots:clinicaltrials:{nct_id}:{payload.content_hash}",
            content_hash=payload.content_hash,
            provenance={
                "source": "ClinicalTrials.gov",
                "nct_id": nct_id,
                "retrieved_at": payload.retrieved_at.isoformat(),
                "query": payload.query,
                **payload.source_metadata,
            },
        )
        identifiers = [{
            "namespace": "clinicaltrials",
            "identifier_type": "nct_id",
            "value": nct_id,
        }]
        sponsor = payload.study_data.get("lead_sponsor") or {}
        sponsor_name = sponsor.get("name") if isinstance(sponsor, dict) else None
        phases = payload.study_data.get("phases") or []
        interventions = payload.study_data.get("interventions") or []
        intervention_names = [
            item.get("name")
            for item in interventions
            if isinstance(item, dict) and item.get("name")
        ]
        attributes: dict[str, Any] = {
            "title": payload.title,
            "phase": ", ".join(str(value) for value in phases) if phases else None,
            "study_type": payload.study_data.get("study_type"),
            "status": payload.study_data.get("overall_status"),
            "sponsor": sponsor_name,
            "collaborators": [
                item.get("name") if isinstance(item, dict) else str(item)
                for item in payload.study_data.get("collaborators") or []
                if not isinstance(item, dict) or item.get("name")
            ],
            "interventions": intervention_names,
            "nct_id": nct_id,
        }
        if payload.study_data.get("enrollment") is not None:
            enrollment = payload.study_data["enrollment"]
            if isinstance(enrollment, dict):
                enrollment = enrollment.get("count")
            if enrollment is not None:
                attributes["enrollment"] = int(enrollment)

        reconciliation = await self.reconcile_legacy_record(
            {
                "source_type": "clinicaltrials",
                "source_record_id": f"{nct_id}:{payload.content_hash}",
                "entity_type": EntityType.CLINICAL_TRIAL.value,
                "names": [payload.title],
                "identifiers": identifiers,
                "tenant_id": str(organization_id) if organization_id else None,
                "metadata": {
                    "content_hash": payload.content_hash,
                    "query": payload.query,
                    "source_metadata": payload.source_metadata,
                },
                "attributes": attributes,
                "source_record": source_record.model_dump(mode="json"),
            },
            principal,
            create_if_unresolved=True,
        )
        canonical_entity_id = reconciliation.get("canonical_entity_id")
        if (
            canonical_entity_id is None
            or reconciliation.get("status") not in {"EXACT_MATCH", "NEW_ENTITY"}
        ):
            return {
                "reconciliation": reconciliation,
                "canonical_entity_id": None,
                "visibility": visibility.value,
            }

        entity_id = UUID(str(canonical_entity_id))
        await self.ensure_identifier(
            entity_id, "clinicaltrials", "nct_id", nct_id, source_record, visibility, principal
        )
        async with self.store.connection(principal.organization_id) as connection:
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                f"clinicaltrial-entity:{entity_id}",
            )
            updated_entity = await connection.fetchrow(
                """UPDATE canonical.entities
                SET attributes = COALESCE(attributes, '{}'::jsonb) || $2::jsonb,
                    updated_at = NOW()
                WHERE id = $1
                  AND organization_id IS NOT DISTINCT FROM $3::uuid
                  AND attributes IS DISTINCT FROM (
                      COALESCE(attributes, '{}'::jsonb) || $2::jsonb
                  )
                RETURNING id, entity_type, preferred_name, description, modality,
                    lifecycle_status, visibility, organization_id, attributes,
                    created_source_record_id, created_at, updated_at""",
                entity_id,
                json.dumps(attributes),
                organization_id,
            )
            if updated_entity is not None:
                projection_payload = dict(updated_entity)
                projection_payload["id"] = str(projection_payload["id"])
                projection_payload["organization_id"] = (
                    str(projection_payload["organization_id"])
                    if projection_payload["organization_id"] else None
                )
                created_source_record_id = projection_payload.pop("created_source_record_id")
                projection_payload["source_record_id"] = (
                    str(created_source_record_id) if created_source_record_id else None
                )
                projection_payload["attributes"] = self._json_value(
                    projection_payload["attributes"]
                )
                projection_payload["created_at"] = projection_payload["created_at"].isoformat()
                projection_payload["updated_at"] = projection_payload["updated_at"].isoformat()
                projection_payload["modality"] = (
                    projection_payload["modality"].value
                    if hasattr(projection_payload["modality"], "value")
                    else projection_payload["modality"]
                )
                await connection.execute(
                    """INSERT INTO canonical.projection_outbox (
                        event_type, aggregate_id, visibility, organization_id, payload
                    ) VALUES ('entity.upserted', $1, $2, $3, $4::jsonb)""",
                    entity_id,
                    visibility.value,
                    organization_id,
                    json.dumps(projection_payload),
                )
        source_facts: dict[str, Any] = {
            "nct_id": nct_id,
            "title": payload.title,
            "study_data": payload.study_data,
        }
        if payload.abstract:
            source_facts["brief_summary"] = payload.abstract
        for key in (
            "overall_status",
            "status_verified_date",
            "why_stopped",
            "study_type",
            "enrollment",
            "phases",
            "lead_sponsor",
            "collaborators",
            "conditions",
            "interventions",
            "arms",
            "primary_outcomes",
            "secondary_outcomes",
            "eligibility",
            "locations",
            "start_date",
            "primary_completion_date",
            "completion_date",
            "study_first_submitted_date",
            "study_first_posted_date",
            "results_first_submitted_date",
            "results_first_posted_date",
            "last_update_submitted_date",
            "last_update_posted_date",
            "references",
            "results",
        ):
            value = payload.study_data.get(key)
            if value not in (None, [], {}):
                source_facts[key] = value

        observations: dict[str, dict[str, Any]] = {}
        for property_name, value in source_facts.items():
            observation = await self.ensure_observation(
                ObservationCreate(
                    entity_id=entity_id,
                    visibility=visibility,
                    property_name=property_name,
                    observation_kind=ObservationKind.SOURCE_FACT,
                    value=value,
                    source_record=source_record,
                    normalizer_version="clinicaltrials-api-v2-v1",
                ),
                principal,
            )
            observations[property_name] = observation

        async with self.store.connection(principal.organization_id) as connection:
            source_record_id = await self._source_record(connection, source_record, organization_id)
            claim_ids: dict[str, str] = {}
            evidence_ids: dict[str, str] = {}
            for property_name, observation in observations.items():
                statement = f"ClinicalTrials.gov NCT:{nct_id} reports {property_name}"
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1))",
                    f"clinicaltrial-claim:{entity_id}:{source_record_id}:{property_name}",
                )
                claim = await connection.fetchrow(
                    """SELECT id FROM canonical.claims
                    WHERE entity_id = $1 AND source_record_id = $2
                      AND observation_id = $3 AND claim_type = 'source_fact'
                      AND statement = $4 AND (organization_id IS NULL OR organization_id = $5)""",
                    entity_id, source_record_id, observation["id"], statement,
                    principal.organization_id,
                )
                if claim is None:
                    claim = await connection.fetchrow(
                        """INSERT INTO canonical.claims (
                            id, entity_id, claim_type, statement, visibility,
                            organization_id, source_record_id, observation_id
                        ) VALUES ($1, $2, 'source_fact', $3, $4, $5, $6, $7)
                        RETURNING id""",
                        uuid4(), entity_id, statement, visibility.value,
                        organization_id, source_record_id, observation["id"],
                    )
                claim_id = claim["id"]
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1))",
                    f"clinicaltrial-evidence:{claim_id}:{observation['id']}",
                )
                evidence_id = await connection.fetchval(
                    """SELECT id FROM canonical.evidence_links
                    WHERE claim_id = $1 AND observation_id = $2
                      AND relation_type = 'supporting'
                      AND (organization_id IS NULL OR organization_id = $3)
                    LIMIT 1""",
                    claim_id, observation["id"], principal.organization_id,
                )
                if evidence_id is None:
                    evidence_id = await connection.fetchval(
                        """INSERT INTO canonical.evidence_links (
                            id, claim_id, observation_id, relation_type, metadata,
                            visibility, organization_id
                        ) VALUES ($1, $2, $3, 'supporting', $4::jsonb, $5, $6)
                        RETURNING id""",
                        uuid4(), claim_id, observation["id"],
                        json.dumps({
                            "source": "clinicaltrials",
                            "nct_id": nct_id,
                            "property_name": property_name,
                            "content_hash": payload.content_hash,
                        }),
                        visibility.value, organization_id,
                    )
                claim_ids[property_name] = str(claim_id)
                evidence_ids[property_name] = str(evidence_id)

        async with self.store.connection(principal.organization_id) as connection:
            await self._enqueue_entity_projection(connection, entity_id, organization_id)
        return {
            "reconciliation": reconciliation,
            "canonical_entity_id": str(entity_id),
            "source_record_id": str(source_record_id),
            "observation_ids": {key: str(row["id"]) for key, row in observations.items()},
            "claim_ids": claim_ids,
            "evidence_ids": evidence_ids,
            "visibility": visibility.value,
        }

    async def ingest_regulatory_event(
        self,
        payload: RegulatoryEventIngest,
        principal: CanonicalPrincipal,
    ) -> dict[str, Any]:
        visibility = Visibility.TENANT if principal.organization_id else Visibility.GLOBAL
        organization_id = self._scope(visibility, principal)
        normalized_event_type = getattr(payload.event_type, "value", payload.event_type)
        source_record = SourceRecordInput(
            namespace="fda_drugsfda",
            external_id=f"{payload.event_id}:{payload.content_hash}",
            source_type="regulatory_authority",
            source_url=payload.source_url,
            raw_payload_ref=payload.raw_payload_ref,
            content_hash=payload.content_hash,
            observed_at=payload.retrieved_at,
            provenance={
                **payload.source_metadata,
                "source": payload.regulator,
                "regulator": payload.regulator,
                "jurisdiction": payload.jurisdiction,
                "event_id": payload.event_id,
                "retrieved_at": payload.retrieved_at.isoformat(),
                "query": payload.query,
            },
        )
        attributes = {
            "authority": payload.regulator,
            "jurisdiction": payload.jurisdiction,
            "event_id": payload.event_id,
            "event_type": normalized_event_type,
            "event_status": payload.event_status,
            "application_number": payload.application_number,
            "application_type": payload.application_type,
            "submission_number": payload.submission_number,
            "submission_type": payload.submission_type,
            "submission_class_code": payload.submission_class_code,
            "event_date_source": payload.event_date_source,
            "product_names": payload.product_names,
            "product_identifiers": payload.product_identifiers,
            "active_ingredients": payload.active_ingredients,
            "sponsor_name": payload.sponsor_name,
        }
        reconciliation = await self.reconcile_legacy_record(
            {
                "source_type": "regulatory",
                "source_record_id": f"{payload.event_id}:{payload.content_hash}",
                "entity_type": EntityType.REGULATORY_EVENT.value,
                "names": [payload.title],
                "identifiers": [{
                    "namespace": "fda",
                    "identifier_type": "submission_event",
                    "value": payload.event_id,
                }],
                "tenant_id": str(organization_id) if organization_id else None,
                "metadata": {
                    "content_hash": payload.content_hash,
                    "regulator": payload.regulator,
                    "jurisdiction": payload.jurisdiction,
                    "source_metadata": payload.source_metadata,
                },
                "attributes": attributes,
                "source_record": source_record.model_dump(mode="json"),
            },
            principal,
            create_if_unresolved=True,
        )
        canonical_entity_id = reconciliation.get("canonical_entity_id")
        if (
            canonical_entity_id is None
            or reconciliation.get("status") not in {"EXACT_MATCH", "NEW_ENTITY"}
        ):
            return {
                "reconciliation": reconciliation,
                "canonical_entity_id": None,
                "visibility": visibility.value,
                "asset_reconciliation": [],
            }

        entity_id = UUID(str(canonical_entity_id))
        await self.ensure_identifier(
            entity_id,
            "fda",
            "submission_event",
            payload.event_id,
            source_record,
            visibility,
            principal,
        )
        async with self.store.connection(principal.organization_id) as connection:
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                f"regulatory-event-entity:{entity_id}",
            )
            updated_entity = await connection.fetchrow(
                """UPDATE canonical.entities
                SET attributes = COALESCE(attributes, '{}'::jsonb) || $2::jsonb,
                    updated_at = NOW()
                WHERE id = $1 AND organization_id IS NOT DISTINCT FROM $3::uuid
                  AND attributes IS DISTINCT FROM (
                      COALESCE(attributes, '{}'::jsonb) || $2::jsonb
                  )
                RETURNING id, entity_type, preferred_name, description, modality,
                    lifecycle_status, visibility, organization_id, attributes,
                    created_source_record_id, created_at, updated_at""",
                entity_id,
                json.dumps(attributes),
                organization_id,
            )
            if updated_entity is not None:
                projection_payload = dict(updated_entity)
                projection_payload["id"] = str(projection_payload["id"])
                projection_payload["organization_id"] = (
                    str(projection_payload["organization_id"])
                    if projection_payload["organization_id"] else None
                )
                created_source_id = projection_payload.pop("created_source_record_id")
                projection_payload["source_record_id"] = (
                    str(created_source_id) if created_source_id else None
                )
                projection_payload["attributes"] = self._json_value(
                    projection_payload["attributes"]
                )
                projection_payload["created_at"] = projection_payload["created_at"].isoformat()
                projection_payload["updated_at"] = projection_payload["updated_at"].isoformat()
                projection_payload["modality"] = (
                    projection_payload["modality"].value
                    if hasattr(projection_payload["modality"], "value")
                    else projection_payload["modality"]
                )
                await connection.execute(
                    """INSERT INTO canonical.projection_outbox (
                        event_type, aggregate_id, visibility, organization_id, payload
                    ) VALUES ('entity.upserted', $1, $2, $3, $4::jsonb)""",
                    entity_id,
                    visibility.value,
                    organization_id,
                    json.dumps(projection_payload),
                )

        source_facts: dict[str, Any] = {
            "regulator": payload.regulator,
            "jurisdiction": payload.jurisdiction,
            "event_id": payload.event_id,
            "event_type": normalized_event_type,
            "event_status": payload.event_status,
            "application_number": payload.application_number,
            "application_type": payload.application_type,
            "submission_number": payload.submission_number,
            "submission_type": payload.submission_type,
            "submission_class_code": payload.submission_class_code,
            "event_date_source": payload.event_date_source,
            "product_names": payload.product_names,
            "product_identifiers": payload.product_identifiers,
            "active_ingredients": payload.active_ingredients,
            "sponsor_name": payload.sponsor_name,
            "title": payload.title,
        }
        source_facts = {
            key: value for key, value in source_facts.items()
            if value not in (None, [], {})
        }
        observations: dict[str, dict[str, Any]] = {}
        for property_name, value in source_facts.items():
            observation = await self.ensure_observation(
                ObservationCreate(
                    entity_id=entity_id,
                    visibility=visibility,
                    property_name=property_name,
                    observation_kind=ObservationKind.SOURCE_FACT,
                    value=value,
                    source_record=source_record,
                    normalizer_version="openfda-drugsfda-v1",
                ),
                principal,
            )
            observations[property_name] = observation

        async with self.store.connection(principal.organization_id) as connection:
            source_record_id = await self._source_record(connection, source_record, organization_id)
            claim_ids: dict[str, str] = {}
            evidence_ids: dict[str, str] = {}
            for property_name, observation in observations.items():
                statement = (
                    f"{payload.regulator} reports {property_name} for "
                    f"{payload.application_number} submission {payload.submission_number}"
                )
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1))",
                    f"regulatory-claim:{entity_id}:{source_record_id}:{property_name}",
                )
                claim = await connection.fetchrow(
                    """SELECT id FROM canonical.claims
                    WHERE entity_id = $1 AND source_record_id = $2
                      AND observation_id = $3 AND claim_type = 'source_fact'
                      AND statement = $4
                      AND (organization_id IS NULL OR organization_id = $5::uuid)""",
                    entity_id, source_record_id, observation["id"], statement,
                    principal.organization_id,
                )
                if claim is None:
                    claim = await connection.fetchrow(
                        """INSERT INTO canonical.claims (
                            id, entity_id, claim_type, statement, visibility,
                            organization_id, source_record_id, observation_id
                        ) VALUES ($1, $2, 'source_fact', $3, $4, $5, $6, $7)
                        RETURNING id""",
                        uuid4(), entity_id, statement, visibility.value,
                        organization_id, source_record_id, observation["id"],
                    )
                claim_id = claim["id"]
                evidence_id = await connection.fetchval(
                    """SELECT id FROM canonical.evidence_links
                    WHERE claim_id = $1 AND observation_id = $2
                      AND relation_type = 'supporting'
                      AND (organization_id IS NULL OR organization_id = $3::uuid)
                    LIMIT 1""",
                    claim_id, observation["id"], principal.organization_id,
                )
                if evidence_id is None:
                    evidence_id = await connection.fetchval(
                        """INSERT INTO canonical.evidence_links (
                            id, claim_id, observation_id, relation_type, metadata,
                            visibility, organization_id
                        ) VALUES ($1, $2, $3, 'supporting', $4::jsonb, $5, $6)
                        RETURNING id""",
                        uuid4(), claim_id, observation["id"],
                        json.dumps({
                            "source": "openFDA Drugs@FDA",
                            "event_id": payload.event_id,
                            "jurisdiction": payload.jurisdiction,
                            "property_name": property_name,
                            "content_hash": payload.content_hash,
                        }),
                        visibility.value, organization_id,
                    )
                claim_ids[property_name] = str(claim_id)
                evidence_ids[property_name] = str(evidence_id)

        asset_reconciliation: list[dict[str, Any]] = []
        for product in payload.product_identifiers:
            product_number = str(product.get("product_number") or "").strip()
            if not product_number:
                continue
            async with self.store.connection(principal.organization_id) as connection:
                candidates = await connection.fetch(
                    """SELECT DISTINCT e.id
                    FROM canonical.identifiers i
                    JOIN canonical.entities e ON e.id = i.entity_id
                    WHERE i.namespace = 'fda' AND i.identifier_type = 'product_number'
                      AND i.normalized_value = $1 AND e.entity_type = 'therapeutic_asset'
                      AND (i.organization_id IS NULL OR i.organization_id = $2::uuid)
                      AND (e.organization_id IS NULL OR e.organization_id = $2::uuid)""",
                    normalize_identifier(product_number),
                    principal.organization_id,
                )
            candidate_ids = [row["id"] for row in candidates]
            if len(candidate_ids) != 1:
                asset_reconciliation.append({
                    "product_number": product_number,
                    "status": "UNRESOLVED" if not candidate_ids else "AMBIGUOUS",
                    "candidate_ids": [str(value) for value in candidate_ids],
                })
                continue
            relationship = await self.ensure_relationship(
                CanonicalRelationshipCreate(
                    subject_entity_id=entity_id,
                    predicate="REGULATORY_EVENT_FOR_ASSET",
                    object_entity_id=candidate_ids[0],
                    visibility=visibility,
                    attributes={
                        "regulator": payload.regulator,
                        "jurisdiction": payload.jurisdiction,
                        "product_number": product_number,
                        "identity_resolution": "exact_namespaced_identifier",
                    },
                    source_record=source_record,
                    property_name="product_identifier_relationship",
                    observation_value={
                        "product_number": product_number,
                        "brand_name": product.get("brand_name"),
                    },
                    observation_kind=ObservationKind.SOURCE_FACT,
                ),
                principal,
            )
            asset_reconciliation.append({
                "product_number": product_number,
                "status": "EXACT_MATCH",
                "canonical_entity_id": str(candidate_ids[0]),
                "relationship_id": str(relationship["id"]),
            })

        async with self.store.connection(principal.organization_id) as connection:
            await self._enqueue_entity_projection(connection, entity_id, organization_id)
        return {
            "reconciliation": reconciliation,
            "canonical_entity_id": str(entity_id),
            "source_record_id": str(source_record_id),
            "observation_ids": {key: str(row["id"]) for key, row in observations.items()},
            "claim_ids": claim_ids,
            "evidence_ids": evidence_ids,
            "asset_reconciliation": asset_reconciliation,
            "visibility": visibility.value,
        }

    async def _merge_ip_attributes(
        self,
        entity_id: UUID,
        attributes: dict[str, Any],
        visibility: Visibility,
        organization_id: UUID | None,
        principal: CanonicalPrincipal,
        lock_key: str,
    ) -> None:
        async with self.store.connection(principal.organization_id) as connection:
            await connection.execute("SELECT pg_advisory_xact_lock(hashtext($1))", lock_key)
            row = await connection.fetchrow(
                """UPDATE canonical.entities
                SET attributes = COALESCE(attributes, '{}'::jsonb) || $2::jsonb,
                    updated_at = NOW()
                WHERE id = $1 AND organization_id IS NOT DISTINCT FROM $3::uuid
                  AND attributes IS DISTINCT FROM (
                      COALESCE(attributes, '{}'::jsonb) || $2::jsonb
                  )
                RETURNING id, entity_type, preferred_name, description, modality,
                    lifecycle_status, visibility, organization_id, attributes,
                    created_source_record_id, created_at, updated_at""",
                entity_id,
                json.dumps(attributes),
                organization_id,
            )
            if row is None:
                return
            payload = dict(row)
            payload["id"] = str(payload["id"])
            payload["organization_id"] = (
                str(payload["organization_id"]) if payload["organization_id"] else None
            )
            source_id = payload.pop("created_source_record_id")
            payload["source_record_id"] = str(source_id) if source_id else None
            payload["attributes"] = self._json_value(payload["attributes"])
            payload["created_at"] = payload["created_at"].isoformat()
            payload["updated_at"] = payload["updated_at"].isoformat()
            payload["modality"] = (
                payload["modality"].value if hasattr(payload["modality"], "value")
                else payload["modality"]
            )
            await connection.execute(
                """INSERT INTO canonical.projection_outbox (
                    event_type, aggregate_id, visibility, organization_id, payload
                ) VALUES ('entity.upserted', $1, $2, $3, $4::jsonb)""",
                entity_id,
                visibility.value,
                organization_id,
                json.dumps(payload),
            )

    async def _ensure_ip_claims(
        self,
        entity_id: UUID,
        source_record: SourceRecordInput,
        visibility: Visibility,
        principal: CanonicalPrincipal,
        facts: dict[str, Any],
        source_label: str,
        subject_label: str,
    ) -> tuple[dict[str, str], dict[str, str]]:
        organization_id = self._scope(visibility, principal)
        claims: dict[str, str] = {}
        evidence_ids: dict[str, str] = {}
        async with self.store.connection(principal.organization_id) as connection:
            source_record_id = await self._source_record(
                connection, source_record, organization_id
            )
            for property_name, observation in facts.items():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1))",
                    f"ip-claim:{entity_id}:{source_record_id}:{property_name}",
                )
                statement = (
                    f"{source_label} reports {property_name} for {subject_label}"
                )
                claim = await connection.fetchrow(
                    """SELECT id FROM canonical.claims
                    WHERE entity_id = $1 AND source_record_id = $2
                      AND observation_id = $3 AND claim_type = 'source_fact'
                      AND statement = $4
                      AND (organization_id IS NULL OR organization_id = $5::uuid)""",
                    entity_id, source_record_id, observation["id"], statement,
                    principal.organization_id,
                )
                if claim is None:
                    claim = await connection.fetchrow(
                        """INSERT INTO canonical.claims (
                            id, entity_id, claim_type, statement, visibility,
                            organization_id, source_record_id, observation_id
                        ) VALUES ($1, $2, 'source_fact', $3, $4, $5, $6, $7)
                        RETURNING id""",
                        uuid4(), entity_id, statement, visibility.value,
                        organization_id, source_record_id, observation["id"],
                    )
                claim_id = claim["id"]
                evidence_id = await connection.fetchval(
                    """SELECT id FROM canonical.evidence_links
                    WHERE claim_id = $1 AND observation_id = $2
                      AND relation_type = 'supporting'
                      AND (organization_id IS NULL OR organization_id = $3::uuid)
                    LIMIT 1""",
                    claim_id, observation["id"], principal.organization_id,
                )
                if evidence_id is None:
                    evidence_id = await connection.fetchval(
                        """INSERT INTO canonical.evidence_links (
                            id, claim_id, observation_id, relation_type, metadata,
                            visibility, organization_id
                        ) VALUES ($1, $2, $3, 'supporting', $4::jsonb, $5, $6)
                        RETURNING id""",
                        uuid4(), claim_id, observation["id"],
                        json.dumps({
                            "source": source_label,
                            "property_name": property_name,
                            "source_record_id": str(source_record_id),
                        }),
                        visibility.value, organization_id,
                    )
                claims[property_name] = str(claim_id)
                evidence_ids[property_name] = str(evidence_id)
        return claims, evidence_ids

    async def ingest_patent_record(
        self,
        payload: PatentRecordIngest,
        principal: CanonicalPrincipal,
    ) -> dict[str, Any]:
        visibility = Visibility.TENANT if principal.organization_id else Visibility.GLOBAL
        organization_id = self._scope(visibility, principal)
        source_record = SourceRecordInput(
            namespace="google_patents",
            external_id=f"{payload.source_id}:{payload.content_hash}",
            source_type="patent_registry",
            source_url=payload.source_url,
            raw_payload_ref=payload.raw_payload_ref,
            content_hash=payload.content_hash,
            observed_at=payload.retrieved_at,
            provenance={
                **payload.source_metadata,
                "source": payload.source_name,
                "source_id": payload.source_id,
                "jurisdiction": payload.jurisdiction,
                "retrieved_at": payload.retrieved_at.isoformat(),
                "query": payload.query,
                "parser_version": payload.source_metadata.get("parser_version"),
            },
        )
        identifiers = []
        for identifier_type, value in (
            ("publication_number", payload.publication_number),
            ("application_number", payload.application_number),
            ("grant_number", payload.grant_number),
        ):
            if value:
                identifiers.append({
                    "namespace": f"patent:{payload.jurisdiction.casefold()}",
                    "identifier_type": identifier_type,
                    "value": value,
                })
        if not identifiers:
            identifiers.append({
                "namespace": "google_patents",
                "identifier_type": "source_id",
                "value": payload.source_id,
            })

        attributes = {
            "jurisdiction": payload.jurisdiction,
            "filing_date_source": payload.filing_date_source,
            "publication_date_source": payload.publication_date_source,
            "grant_date_source": payload.grant_date_source,
            "application_number": payload.application_number,
            "publication_number": payload.publication_number,
            "grant_number": payload.grant_number,
            "family_identifier": payload.family_identifier,
            "status": payload.status,
            "patent_type": payload.patent_type,
            "applicants": payload.applicants,
            "assignees": payload.assignees,
            "inventors": payload.inventors,
            "classifications": payload.classifications,
            "priority_numbers": payload.priority_numbers,
            "citations": payload.citations,
        }
        attributes = {key: value for key, value in attributes.items() if value not in (None, [], {})}
        reconciliation = await self.reconcile_legacy_record(
            {
                "source_type": "google_patents",
                "source_record_id": f"{payload.source_id}:{payload.content_hash}",
                "entity_type": EntityType.PATENT.value,
                "names": [payload.title],
                "identifiers": identifiers,
                "tenant_id": str(organization_id) if organization_id else None,
                "metadata": {
                    "content_hash": payload.content_hash,
                    "jurisdiction": payload.jurisdiction,
                    "source_metadata": payload.source_metadata,
                },
                "attributes": attributes,
                "source_record": source_record.model_dump(mode="json"),
            },
            principal,
            create_if_unresolved=True,
        )
        canonical_entity_id = reconciliation.get("canonical_entity_id")
        if canonical_entity_id is None or reconciliation.get("status") not in {
            "EXACT_MATCH", "NEW_ENTITY"
        }:
            return {
                "reconciliation": reconciliation,
                "canonical_entity_id": None,
                "visibility": visibility.value,
            }

        entity_id = UUID(str(canonical_entity_id))
        for identifier in identifiers:
            await self.ensure_identifier(
                entity_id,
                identifier["namespace"],
                identifier["identifier_type"],
                identifier["value"],
                source_record,
                visibility,
                principal,
            )
        await self._merge_ip_attributes(
            entity_id, attributes, visibility, organization_id, principal,
            f"patent-entity:{entity_id}",
        )

        source_facts = {
            "title": payload.title,
            "jurisdiction": payload.jurisdiction,
            "abstract": payload.abstract,
            "application_number": payload.application_number,
            "publication_number": payload.publication_number,
            "grant_number": payload.grant_number,
            "family_identifier": payload.family_identifier,
            "filing_date_source": payload.filing_date_source,
            "publication_date_source": payload.publication_date_source,
            "grant_date_source": payload.grant_date_source,
            "status": payload.status,
            "patent_type": payload.patent_type,
            "applicants": payload.applicants,
            "assignees": payload.assignees,
            "inventors": payload.inventors,
            "classifications": payload.classifications,
            "priority_numbers": payload.priority_numbers,
            "citations": payload.citations,
        }
        source_facts = {
            key: value for key, value in source_facts.items()
            if value not in (None, [], {})
        }
        observations = {}
        for property_name, value in source_facts.items():
            observations[property_name] = await self.ensure_observation(
                ObservationCreate(
                    entity_id=entity_id,
                    visibility=visibility,
                    property_name=property_name,
                    observation_kind=ObservationKind.SOURCE_FACT,
                    value=value,
                    source_record=source_record,
                ),
                principal,
            )
        claims, evidence = await self._ensure_ip_claims(
            entity_id, source_record, visibility, principal, observations,
            payload.source_name, f"patent {payload.source_id}",
        )

        family_reconciliation = None
        family_entity_id = None
        if payload.family_identifier:
            family_source = SourceRecordInput(
                namespace="google_patents",
                external_id=f"family:{payload.family_identifier}:{payload.content_hash}",
                source_type="patent_registry",
                source_url=payload.source_url,
                raw_payload_ref=payload.raw_payload_ref,
                content_hash=payload.content_hash,
                observed_at=payload.retrieved_at,
                provenance={
                    "source": payload.source_name,
                    "patent_source_id": payload.source_id,
                    "family_identifier": payload.family_identifier,
                },
            )
            family_reconciliation = await self.reconcile_legacy_record(
                {
                    "source_type": "google_patents_family",
                    "source_record_id": f"{payload.family_identifier}:{payload.content_hash}",
                    "entity_type": EntityType.PATENT_FAMILY.value,
                    "names": [f"Patent family {payload.family_identifier}"],
                    "identifiers": [{
                        "namespace": "google_patents",
                        "identifier_type": "family_id",
                        "value": payload.family_identifier,
                    }],
                    "tenant_id": str(organization_id) if organization_id else None,
                    "attributes": {"family_identifier": payload.family_identifier},
                    "source_record": family_source.model_dump(mode="json"),
                },
                principal,
                create_if_unresolved=True,
            )
            family_id = family_reconciliation.get("canonical_entity_id")
            if family_id and family_reconciliation.get("status") in {"EXACT_MATCH", "NEW_ENTITY"}:
                family_entity_id = UUID(str(family_id))
                await self.ensure_identifier(
                    family_entity_id, "google_patents", "family_id",
                    payload.family_identifier, family_source, visibility, principal,
                )
                family_observation = await self.ensure_observation(
                    ObservationCreate(
                        entity_id=family_entity_id,
                        visibility=visibility,
                        property_name="family_identifier",
                        observation_kind=ObservationKind.SOURCE_FACT,
                        value=payload.family_identifier,
                        source_record=family_source,
                    ),
                    principal,
                )
                await self._ensure_ip_claims(
                    family_entity_id,
                    family_source,
                    visibility,
                    principal,
                    {"family_identifier": family_observation},
                    payload.source_name,
                    f"patent family {payload.family_identifier}",
                )
                await self.ensure_relationship(
                    CanonicalRelationshipCreate(
                        subject_entity_id=entity_id,
                        predicate="MEMBER_OF_PATENT_FAMILY",
                        object_entity_id=family_entity_id,
                        visibility=visibility,
                        source_record=source_record,
                        property_name="patent_family_membership",
                        observation_value={"family_identifier": payload.family_identifier},
                        observation_kind=ObservationKind.SOURCE_FACT,
                        attributes={"identity_resolution": "exact_namespaced_identifier"},
                    ),
                    principal,
                )

        async with self.store.connection(principal.organization_id) as connection:
            await self._enqueue_entity_projection(connection, entity_id, organization_id)
            if family_entity_id is not None:
                await self._enqueue_entity_projection(connection, family_entity_id, organization_id)
        return {
            "reconciliation": reconciliation,
            "canonical_entity_id": str(entity_id),
            "source_record_id": str(await self._source_record_id(source_record, organization_id)),
            "observation_ids": {key: str(value["id"]) for key, value in observations.items()},
            "claim_ids": claims,
            "evidence_ids": evidence,
            "family_reconciliation": family_reconciliation,
            "family_entity_id": str(family_entity_id) if family_entity_id else None,
            "visibility": visibility.value,
        }

    async def _source_record_id(
        self, source_record: SourceRecordInput, organization_id: UUID | None
    ) -> UUID:
        async with self.store.connection(organization_id) as connection:
            return await self._source_record(connection, source_record, organization_id)

    async def ingest_licensing_event(
        self,
        payload: LicensingEventIngest,
        principal: CanonicalPrincipal,
    ) -> dict[str, Any]:
        visibility = Visibility.TENANT if principal.organization_id else Visibility.GLOBAL
        organization_id = self._scope(visibility, principal)
        source_record = SourceRecordInput(
            namespace="ip_licensing",
            external_id=(
                f"{hashlib.sha256(f'{payload.source_name}:{payload.event_id}'.encode()).hexdigest()}"
                f":{payload.content_hash}"
            ),
            source_type="database",
            source_url=payload.source_url,
            raw_payload_ref=payload.raw_payload_ref,
            content_hash=payload.content_hash,
            observed_at=payload.retrieved_at,
            provenance={
                **payload.source_metadata,
                "source": payload.source_name,
                "event_id": payload.event_id,
                "event_type": payload.event_type.value,
                "retrieved_at": payload.retrieved_at.isoformat(),
                "query": payload.query,
            },
        )
        attributes = {
            "event_id": payload.event_id,
            "source_name": payload.source_name,
            "event_type": payload.event_type.value,
            "event_date_source": payload.event_date_source,
            "effective_date_source": payload.effective_date_source,
            "expiration_date_source": payload.expiration_date_source,
            "licensor_names": payload.licensor_names,
            "licensee_names": payload.licensee_names,
            "asset_names": payload.asset_names,
            "patent_identifiers": payload.patent_identifiers,
            "territory": payload.territory,
            "exclusivity": payload.exclusivity.value,
            "field_of_use": payload.field_of_use,
            "rights_scope": payload.rights_scope,
        }
        attributes = {key: value for key, value in attributes.items() if value not in (None, [], {})}
        reconciliation = await self.reconcile_legacy_record(
            {
                "source_type": "ip_licensing",
                "source_record_id": f"{payload.source_name}:{payload.event_id}:{payload.content_hash}",
                "entity_type": EntityType.LICENSING_EVENT.value,
                "names": [payload.title],
                "identifiers": [{
                    "namespace": "ip_licensing",
                    "identifier_type": "event_fingerprint",
                    "value": hashlib.sha256(
                        f"{payload.source_name}:{payload.event_id}".encode()
                    ).hexdigest(),
                }],
                "tenant_id": str(organization_id) if organization_id else None,
                "attributes": attributes,
                "source_record": source_record.model_dump(mode="json"),
            },
            principal,
            create_if_unresolved=True,
        )
        canonical_entity_id = reconciliation.get("canonical_entity_id")
        if canonical_entity_id is None or reconciliation.get("status") not in {
            "EXACT_MATCH", "NEW_ENTITY"
        }:
            return {
                "reconciliation": reconciliation,
                "canonical_entity_id": None,
                "visibility": visibility.value,
                "entity_reconciliation": [],
            }

        entity_id = UUID(str(canonical_entity_id))
        await self.ensure_identifier(
            entity_id, "ip_licensing", "event_fingerprint",
            hashlib.sha256(f"{payload.source_name}:{payload.event_id}".encode()).hexdigest(),
            source_record, visibility, principal,
        )
        await self._merge_ip_attributes(
            entity_id, attributes, visibility, organization_id, principal,
            f"licensing-event:{entity_id}",
        )
        source_facts = {
            "title": payload.title,
            **attributes,
            "source_name": payload.source_name,
            "event_id": payload.event_id,
            "linked_entity_identifiers": [
                reference.model_dump(mode="json")
                for reference in payload.entity_references
            ],
        }
        observations = {}
        for property_name, value in source_facts.items():
            if value in (None, [], {}):
                continue
            observations[property_name] = await self.ensure_observation(
                ObservationCreate(
                    entity_id=entity_id,
                    visibility=visibility,
                    property_name=property_name,
                    observation_kind=ObservationKind.SOURCE_FACT,
                    value=value,
                    source_record=source_record,
                ),
                principal,
            )
        claims, evidence = await self._ensure_ip_claims(
            entity_id, source_record, visibility, principal, observations,
            payload.source_name, f"licensing event {payload.event_id}",
        )

        reconciled_references = []
        relationship_predicates = {
            "licensor": ("company", "LICENSING_EVENT_LICENSOR"),
            "licensee": ("company", "LICENSING_EVENT_LICENSEE"),
            "assignor": ("company", "LICENSING_EVENT_ASSIGNOR"),
            "assignee": ("company", "LICENSING_EVENT_ASSIGNEE"),
            "asset": ("therapeutic_asset", "LICENSING_EVENT_COVERS_ASSET"),
            "patent": ("patent", "LICENSING_EVENT_COVERS_PATENT"),
        }
        for reference in payload.entity_references:
            role = reference.role.value
            required_type, predicate = relationship_predicates[role]
            if reference.entity_type.value != required_type:
                raise ValueError(f"{role} references must identify {required_type} entities")
            async with self.store.connection(principal.organization_id) as connection:
                candidates = await connection.fetch(
                    """SELECT DISTINCT e.id FROM canonical.identifiers i
                    JOIN canonical.entities e ON e.id = i.entity_id
                    WHERE i.namespace = $1 AND i.identifier_type = $2
                      AND i.normalized_value = $3 AND e.entity_type = $4
                      AND (i.organization_id IS NULL OR i.organization_id = $5::uuid)
                      AND (e.organization_id IS NULL OR e.organization_id = $5::uuid)""",
                    reference.namespace.strip().casefold(),
                    reference.identifier_type.strip().casefold(),
                    normalize_identifier(reference.value),
                    required_type,
                    principal.organization_id,
                )
            candidate_ids = sorted({row["id"] for row in candidates})
            if len(candidate_ids) != 1:
                reconciled_references.append({
                    "role": role,
                    "identifier": reference.value,
                    "status": "UNRESOLVED" if not candidate_ids else "AMBIGUOUS",
                    "candidate_ids": [str(value) for value in candidate_ids],
                })
                continue
            linked_id = candidate_ids[0]
            relationship = await self.ensure_relationship(
                CanonicalRelationshipCreate(
                    subject_entity_id=entity_id,
                    predicate=predicate,
                    object_entity_id=linked_id,
                    visibility=visibility,
                    attributes={
                        "event_id": payload.event_id,
                        "role": role,
                        "identity_resolution": "exact_namespaced_identifier",
                    },
                    source_record=source_record,
                    property_name=f"{role}_relationship",
                    observation_value={
                        "namespace": reference.namespace,
                        "identifier_type": reference.identifier_type,
                        "value": reference.value,
                    },
                    observation_kind=ObservationKind.SOURCE_FACT,
                ),
                principal,
            )
            reconciled_references.append({
                "role": role,
                "status": "EXACT_MATCH",
                "canonical_entity_id": str(linked_id),
                "relationship_id": str(relationship["id"]),
            })

        source_record_id = await self._source_record_id(source_record, organization_id)
        async with self.store.connection(principal.organization_id) as connection:
            await self._enqueue_entity_projection(connection, entity_id, organization_id)
        return {
            "reconciliation": reconciliation,
            "canonical_entity_id": str(entity_id),
            "source_record_id": str(source_record_id),
            "observation_ids": {key: str(value["id"]) for key, value in observations.items()},
            "claim_ids": claims,
            "evidence_ids": evidence,
            "entity_reconciliation": reconciled_references,
            "visibility": visibility.value,
        }

    async def list_ip_entities(
        self,
        principal: CanonicalPrincipal,
        *,
        entity_type: EntityType,
        source_identifier: str | None = None,
        as_of: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        if entity_type not in {
            EntityType.PATENT, EntityType.PATENT_FAMILY, EntityType.LICENSING_EVENT
        }:
            raise ValueError("IP history supports patents, patent families, and licensing events")
        self._require_aware_as_of(as_of)
        async with self.store.connection(principal.organization_id) as connection:
            entities = await connection.fetch(
                """SELECT e.id, e.entity_type, e.preferred_name, e.visibility,
                    e.organization_id, e.attributes, e.created_at, e.updated_at
                FROM canonical.entities e
                WHERE e.entity_type = $1
                  AND (e.organization_id IS NULL OR e.organization_id = $2::uuid)
                  AND ($3::timestamptz IS NULL OR e.created_at <= $3)
                  AND EXISTS (
                      SELECT 1 FROM canonical.source_records s
                      WHERE s.id = e.created_source_record_id
                        AND ($3::timestamptz IS NULL OR s.ingested_at <= $3)
                  )
                ORDER BY e.created_at DESC, e.id""",
                entity_type.value, principal.organization_id, as_of,
            )
            items = []
            for entity in entities:
                entity_id = entity["id"]
                fact_rows = await connection.fetch(
                    """SELECT o.property_name, o.value, o.source_record_id,
                        o.created_at, s.namespace AS source_namespace,
                        s.external_id AS source_external_id, s.source_url,
                        s.provenance
                    FROM canonical.observations o
                    JOIN canonical.source_records s ON s.id = o.source_record_id
                    WHERE o.entity_id = $1 AND o.observation_kind = 'source_fact'
                      AND (o.organization_id IS NULL OR o.organization_id = $2::uuid)
                      AND ($3::timestamptz IS NULL OR (
                          o.created_at <= $3 AND o.ingested_at <= $3 AND s.ingested_at <= $3
                      ))
                    ORDER BY o.created_at, o.id""",
                    entity_id, principal.organization_id, as_of,
                )
                facts: dict[str, Any] = {}
                available_times = []
                for row in fact_rows:
                    available_times.append(row["created_at"])
                    facts.setdefault(row["property_name"], []).append({
                        "value": self._json_value(row["value"]),
                        "source_record_id": str(row["source_record_id"]),
                        "available_at": row["created_at"].isoformat(),
                        "source": {
                            "namespace": row["source_namespace"],
                            "external_id": row["source_external_id"],
                            "source_url": str(row["source_url"]) if row["source_url"] else None,
                            "provenance": self._json_value(row["provenance"]),
                        },
                    })
                selected_values = {
                    key: versions[-1]["value"] for key, versions in facts.items()
                }
                attributes = (
                    self._json_value(entity["attributes"])
                    if as_of is None else selected_values
                )
                if source_identifier and source_identifier.casefold() not in json.dumps(
                    [entity["preferred_name"], attributes], ensure_ascii=True
                ).casefold():
                    continue
                items.append({
                    "id": str(entity_id),
                    "entity_type": entity["entity_type"],
                    "preferred_name": entity["preferred_name"],
                    "visibility": entity["visibility"],
                    "organization_id": (
                        str(entity["organization_id"]) if entity["organization_id"] else None
                    ),
                    "attributes": attributes,
                    "facts": facts,
                    "created_at": entity["created_at"].isoformat(),
                    "updated_at": (
                        entity["updated_at"].isoformat()
                        if as_of is None else max(
                            available_times, default=entity["created_at"]
                        ).isoformat()
                    ),
                })
            total = len(items)
            offset = (page - 1) * page_size
            return items[offset:offset + page_size], total

    async def ensure_relationship(
        self,
        payload: CanonicalRelationshipCreate,
        principal: CanonicalPrincipal,
    ) -> dict[str, Any]:
        organization_id = self._scope(payload.visibility, principal)
        async with self.store.connection(principal.organization_id) as connection:
            existing = await connection.fetchrow(
                """SELECT id, subject_entity_id, predicate, object_entity_id
                FROM canonical.relationships
                WHERE subject_entity_id = $1 AND predicate = $2 AND object_entity_id = $3
                  AND (organization_id IS NULL OR organization_id = $4::uuid)""",
                payload.subject_entity_id, payload.predicate, payload.object_entity_id,
                principal.organization_id,
            )
            if existing:
                return dict(existing)
        return await self.create_relationship(payload, principal)

    async def list_relationships(
        self,
        entity_id: UUID,
        principal: CanonicalPrincipal,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        offset = (page - 1) * page_size
        async with self.store.connection(principal.organization_id) as connection:
            rows = await connection.fetch(
                """SELECT id, subject_entity_id, predicate, object_entity_id,
                    visibility, organization_id, attributes, created_at
                FROM canonical.relationships
                WHERE (subject_entity_id = $1 OR object_entity_id = $1)
                  AND (organization_id IS NULL OR organization_id = $2)
                ORDER BY created_at DESC, id OFFSET $3 LIMIT $4""",
                entity_id, principal.organization_id, offset, page_size,
            )
            total = await connection.fetchval(
                """SELECT count(*) FROM canonical.relationships
                WHERE (subject_entity_id = $1 OR object_entity_id = $1)
                  AND (organization_id IS NULL OR organization_id = $2)""",
                entity_id, principal.organization_id,
            )
            results = [dict(row) for row in rows]
            for result in results:
                result["attributes"] = self._json_value(result["attributes"])
            return results, total

    async def list_observations(
        self,
        entity_id: UUID,
        principal: CanonicalPrincipal,
        page: int = 1,
        page_size: int = 50,
        as_of: datetime | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        self._require_aware_as_of(as_of)
        offset = (page - 1) * page_size
        async with self.store.connection(principal.organization_id) as connection:
            rows = await connection.fetch(
                """WITH cutoff AS (SELECT COALESCE($5::timestamptz, transaction_timestamp()) AS at)
                SELECT o.id, o.entity_id, o.relationship_id, o.property_name,
                    o.observation_kind, o.value, o.verification_state, o.confidence,
                    o.valid_from, o.valid_to, o.published_at, o.observed_at,
                    o.source_updated_at, o.ingested_at, o.normalizer_version,
                    o.supersedes_observation_id, o.manually_verified_by,
                    o.manually_verified_at, s.namespace AS source_namespace,
                    s.external_id AS source_external_id, s.source_url, to_jsonb(s) AS source_record
                FROM canonical.observations o
                CROSS JOIN cutoff t
                JOIN canonical.source_records s ON s.id = o.source_record_id
                WHERE o.entity_id = $1
                  AND (o.organization_id IS NULL OR o.organization_id = $2)
                  AND o.created_at <= t.at AND o.ingested_at <= t.at AND s.ingested_at <= t.at
                  AND (o.valid_from IS NULL OR o.valid_from <= t.at)
                  AND (o.valid_to IS NULL OR o.valid_to >= t.at)
                ORDER BY o.observed_at DESC NULLS LAST, o.created_at DESC
                OFFSET $3 LIMIT $4""",
                entity_id, principal.organization_id, offset, page_size, as_of,
            )
            total = await connection.fetchval(
                """WITH cutoff AS (SELECT COALESCE($3::timestamptz, transaction_timestamp()) AS at)
                SELECT count(*) FROM canonical.observations o CROSS JOIN cutoff t
                JOIN canonical.source_records s ON s.id = o.source_record_id
                WHERE o.entity_id = $1 AND (o.organization_id IS NULL OR o.organization_id = $2)
                  AND o.created_at <= t.at AND o.ingested_at <= t.at AND s.ingested_at <= t.at
                  AND (o.valid_from IS NULL OR o.valid_from <= t.at)
                  AND (o.valid_to IS NULL OR o.valid_to >= t.at)""",
                entity_id, principal.organization_id, as_of,
            )
            results = [dict(row) for row in rows]
            for result in results:
                result["value"] = self._json_value(result["value"])
                result["source_record"] = self._json_value(result["source_record"])
            return results, total

    async def resolve_identifier(
        self,
        namespace: str,
        identifier_type: str,
        value: str,
        principal: CanonicalPrincipal,
    ) -> dict[str, Any]:
        normalized_id = normalize_identifier(value)
        normalized_name = normalize_name(value)
        async with self.store.connection(principal.organization_id) as connection:
            exact_ids = await connection.fetch(
                """SELECT DISTINCT entity_id FROM canonical.identifiers
                WHERE namespace = $1 AND identifier_type = $2 AND normalized_value = $3
                  AND (organization_id IS NULL OR organization_id = $4)""",
                namespace.strip().casefold(), identifier_type.strip().casefold(), normalized_id,
                principal.organization_id,
            )
            alias_rows = await connection.fetch(
                """SELECT DISTINCT entity_id, bool_or(verification_state = 'verified') AS verified
                FROM canonical.aliases WHERE normalized_value = $1
                  AND (organization_id IS NULL OR organization_id = $2)
                GROUP BY entity_id""",
                normalized_name, principal.organization_id,
            )
            matches = {row["entity_id"]: True for row in exact_ids}
            for row in alias_rows:
                matches[row["entity_id"]] = matches.get(row["entity_id"], False) or row["verified"]
            candidates = [
                await self._get_entity(connection, entity_id, principal.organization_id)
                for entity_id in matches
            ]
            if len(candidates) == 1 and (matches[next(iter(matches))] or exact_ids):
                return {"status": "resolved", "entity": candidates[0], "candidates": candidates}
            if len(candidates) > 1:
                return {"status": "ambiguous", "entity": None, "candidates": candidates}
            return {"status": "unresolved", "entity": None, "candidates": candidates}

    async def resolve_name(
        self,
        entity_type: str,
        value: str,
        principal: CanonicalPrincipal,
    ) -> dict[str, Any]:
        normalized_name = normalize_name(value)
        async with self.store.connection(principal.organization_id) as connection:
            rows = await connection.fetch(
                """SELECT id FROM canonical.entities
                WHERE entity_type = $1 AND normalized_name = $2
                  AND (organization_id IS NULL OR organization_id = $3)
                ORDER BY id""",
                entity_type,
                normalized_name,
                principal.organization_id,
            )
            candidates = [
                await self._get_entity(connection, row["id"], principal.organization_id)
                for row in rows
            ]
            if len(candidates) == 1:
                return {"status": "resolved", "entity": candidates[0], "candidates": candidates}
            if candidates:
                return {"status": "ambiguous", "entity": None, "candidates": candidates}
            return {"status": "unresolved", "entity": None, "candidates": []}

    async def get_reconciliation_result(
        self,
        source_type: str,
        source_record_id: str,
        tenant_id: str | UUID | None,
        entity_type: str,
    ) -> dict[str, Any]:
        tenant_uuid = self._coerce_uuid(tenant_id, "tenant_id") if tenant_id is not None else None
        async with self.store.connection(tenant_uuid) as connection:
            row = await connection.fetchrow(
                """SELECT * FROM canonical.reconciliation_results
                WHERE source_type = $1
                  AND source_record_id = $2
                  AND entity_type = $3
                  AND tenant_id IS NOT DISTINCT FROM $4""",
                source_type,
                source_record_id,
                entity_type,
                tenant_uuid,
            )
            if row is None:
                raise CanonicalNotFoundError("reconciliation result not found")
            result = dict(row)
            result["candidate_ids"] = list(result["candidate_ids"] or [])
            return result

    async def get_reconciliation_for_source(
        self,
        source_type: str,
        source_record_id: str,
        tenant_id: str | UUID | None,
    ) -> dict[str, Any] | None:
        tenant_uuid = self._coerce_uuid(tenant_id, "tenant_id") if tenant_id is not None else None
        async with self.store.connection(tenant_uuid) as connection:
            row = await connection.fetchrow(
                """SELECT * FROM canonical.reconciliation_results
                WHERE source_type = $1::text AND source_record_id = $2::text
                  AND tenant_id IS NOT DISTINCT FROM $3::uuid
                ORDER BY updated_at DESC LIMIT 1""",
                source_type, source_record_id, tenant_uuid,
            )
            if row is None:
                return None
            result = dict(row)
            result["candidate_ids"] = list(result["candidate_ids"] or [])
            return result

    async def reconcile_legacy_record(
        self,
        legacy_record: dict[str, Any],
        principal: CanonicalPrincipal,
        *,
        create_if_unresolved: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        tenant_scope = legacy_record.get("tenant_id")
        tenant_uuid = self._coerce_uuid(tenant_scope, "tenant_id") if tenant_scope not in (None, "") else None
        if tenant_uuid is not None and principal.organization_id is None:
            raise CanonicalAuthorizationError("tenant-scoped reconciliation requires a verified tenant context")
        if tenant_uuid is not None and principal.organization_id != tenant_uuid:
            raise CanonicalAuthorizationError("tenant-scoped reconciliation cannot cross tenant boundaries")
        if tenant_uuid is None and principal.organization_id is not None:
            tenant_uuid = principal.organization_id

        source_type = str(legacy_record.get("source_type") or "legacy")
        source_record_id = str(legacy_record.get("source_record_id") or legacy_record.get("source_id") or "unknown")
        entity_type = str(legacy_record.get("entity_type") or "unknown")
        source_record = self._coerce_source_record(legacy_record.get("source_record") or {})
        metadata = legacy_record.get("metadata") or {}

        existing_reconciliation = await self.get_reconciliation_for_source(
            source_type, source_record_id, tenant_uuid
        )
        if existing_reconciliation and existing_reconciliation.get("entity_type") == entity_type:
            existing_reconciliation["canonical_entity_id"] = (
                str(existing_reconciliation["canonical_entity_id"])
                if existing_reconciliation.get("canonical_entity_id")
                else None
            )
            existing_reconciliation["tenant_id"] = (
                str(existing_reconciliation["tenant_id"])
                if existing_reconciliation.get("tenant_id")
                else None
            )
            existing_reconciliation["candidate_ids"] = [
                str(item) for item in existing_reconciliation.get("candidate_ids", [])
            ]
            return existing_reconciliation

        candidate_ids: list[UUID] = []
        match_method = "NONE"
        match_reason = "No deterministic canonical match was found"
        status = "UNRESOLVED"

        async with self.store.connection(tenant_uuid) as connection:
            exact_identifier_candidates: set[UUID] = set()
            for identifier in legacy_record.get("identifiers") or []:
                namespace = str(identifier.get("namespace", "")).strip().casefold()
                identifier_type = str(identifier.get("identifier_type", "")).strip().casefold()
                value = str(identifier.get("value", "")).strip()
                if not namespace or not identifier_type or not value:
                    continue
                rows = await connection.fetch(
                    """SELECT DISTINCT entity_id FROM canonical.identifiers
                    WHERE namespace = $1 AND identifier_type = $2 AND normalized_value = $3
                      AND (organization_id IS NULL OR organization_id = $4)""",
                    namespace,
                    identifier_type,
                    normalize_identifier(value),
                    tenant_uuid,
                )
                exact_identifier_candidates.update(row["entity_id"] for row in rows)
            if exact_identifier_candidates:
                candidate_ids = sorted(exact_identifier_candidates)
                status = "EXACT_MATCH"
                match_method = "NAMESPACED_IDENTIFIER"
                match_reason = "Legacy record matched a canonical namespaced identifier"
                if len(candidate_ids) > 1:
                    status = "AMBIGUOUS"
                    match_reason = "Multiple canonical entities matched the same identifier namespace/value"

            if not candidate_ids and metadata.get("canonical_entity_id"):
                target_id = self._coerce_uuid(metadata["canonical_entity_id"], "canonical_entity_id")
                if target_id is not None:
                    candidate_ids = [target_id]
                    status = "EXACT_MATCH"
                    match_method = "TRUSTED_SOURCE_MAPPING"
                    match_reason = "Legacy metadata explicitly mapped to a canonical entity"

            if not candidate_ids:
                alias_candidates: set[UUID] = set()
                for alias in legacy_record.get("aliases") or []:
                    normalized_alias = normalize_name(str(alias))
                    rows = await connection.fetch(
                        """SELECT DISTINCT entity_id FROM canonical.aliases
                        WHERE normalized_value = $1
                          AND (organization_id IS NULL OR organization_id = $2)""",
                        normalized_alias,
                        tenant_uuid,
                    )
                    alias_candidates.update(row["entity_id"] for row in rows)
                if alias_candidates:
                    candidate_ids = sorted(alias_candidates)
                    status = "POSSIBLE_MATCH" if len(candidate_ids) == 1 else "AMBIGUOUS"
                    match_method = "EXACT_ALIAS" if len(candidate_ids) == 1 else "AMBIGUOUS_ALIAS"
                    match_reason = "Legacy alias matched one canonical alias" if len(candidate_ids) == 1 else "Legacy alias matched multiple canonical aliases"

            if not candidate_ids:
                name_candidates: set[UUID] = set()
                for name in legacy_record.get("names") or []:
                    normalized_name = normalize_name(str(name))
                    rows = await connection.fetch(
                        """SELECT id FROM canonical.entities
                        WHERE normalized_name = $1
                          AND entity_type = $2
                          AND (organization_id IS NULL OR organization_id = $3)""",
                        normalized_name,
                        entity_type,
                        tenant_uuid,
                    )
                    name_candidates.update(row["id"] for row in rows)
                if name_candidates:
                    candidate_ids = sorted(name_candidates)
                    status = "POSSIBLE_MATCH" if len(candidate_ids) == 1 else "AMBIGUOUS"
                    match_method = "NORMALIZED_NAME" if len(candidate_ids) == 1 else "AMBIGUOUS_NAME"
                    match_reason = "Legacy normalized name matched one canonical entity" if len(candidate_ids) == 1 else "Legacy normalized name matched multiple canonical entities"

        if not candidate_ids and create_if_unresolved and not dry_run:
            entity_payload = CanonicalEntityCreate(
                entity_type=EntityType(entity_type) if entity_type in {item.value for item in EntityType} else EntityType.TARGET,
                preferred_name=(legacy_record.get("names") or ["Legacy canonical entity"])[0],
                visibility=Visibility.TENANT if tenant_uuid is not None else Visibility.GLOBAL,
                source_record=source_record,
                identifiers=[
                    IdentifierInput(
                        namespace=str(identifier["namespace"]),
                        identifier_type=str(identifier["identifier_type"]),
                        value=str(identifier["value"]),
                        source_record=source_record,
                    )
                    for identifier in legacy_record.get("identifiers") or []
                    if identifier.get("namespace") and identifier.get("identifier_type") and identifier.get("value")
                ],
                attributes=legacy_record.get("attributes") or {},
            )
            created = await self.create_entity(entity_payload, principal)
            candidate_ids = [UUID(str(created["id"]))]
            status = "NEW_ENTITY"
            match_method = "CREATE_IF_UNRESOLVED"
            match_reason = "No match exists; explicit creation policy created a canonical entity"

        if not candidate_ids:
            status = "UNRESOLVED" if not (create_if_unresolved and dry_run) else "UNRESOLVED"
            match_method = "NONE"
            match_reason = "No canonical candidate matched the source record"

        if dry_run:
            return {
                "source_type": source_type,
                "source_record_id": source_record_id,
                "entity_type": entity_type,
                "tenant_id": str(tenant_uuid) if tenant_uuid else None,
                "canonical_entity_id": str(candidate_ids[0]) if len(candidate_ids) == 1 and status not in {"AMBIGUOUS", "UNRESOLVED"} else None,
                "status": status,
                "match_method": match_method,
                "match_reason": match_reason,
                "candidate_ids": [str(item) for item in candidate_ids],
                "source_provenance": {
                    "source_type": source_type,
                    "source_record_id": source_record_id,
                    "namespace": getattr(source_record, "namespace", None),
                    "external_id": getattr(source_record, "external_id", None),
                    "observed_at": getattr(source_record, "observed_at", None),
                },
            }

        result = {
            "source_type": source_type,
            "source_record_id": source_record_id,
            "entity_type": entity_type,
            "tenant_id": tenant_uuid,
            "canonical_entity_id": candidate_ids[0] if len(candidate_ids) == 1 and status not in {"AMBIGUOUS", "UNRESOLVED"} else None,
            "status": status,
            "match_method": match_method,
            "match_reason": match_reason,
            "candidate_ids": candidate_ids,
            "source_namespace": getattr(source_record, "namespace", None),
            "source_identifier": getattr(source_record, "external_id", None),
            "source_metadata": metadata,
            "created_at": None,
            "updated_at": None,
        }
        async with self.store.connection(tenant_uuid) as connection:
            existing = await connection.fetchrow(
                """SELECT id FROM canonical.reconciliation_results
                                WHERE source_type = $1::text AND source_record_id = $2::text
                                    AND entity_type = $3::text AND tenant_id IS NOT DISTINCT FROM $4::uuid""",
                source_type,
                source_record_id,
                entity_type,
                tenant_uuid,
            )
            if existing is None:
                row = await connection.fetchrow(
                    """INSERT INTO canonical.reconciliation_results (
                        source_type, source_record_id, entity_type, tenant_id,
                        canonical_entity_id, status, match_method, match_reason,
                        candidate_ids, source_namespace, source_identifier, source_metadata
                    ) VALUES ($1::text, $2::text, $3::text, $4::uuid, $5::uuid, $6::text,
                        $7::text, $8::text, $9::uuid[], $10::text, $11::text, $12::jsonb)
                    RETURNING *""",
                    source_type,
                    source_record_id,
                    entity_type,
                    tenant_uuid,
                    result["canonical_entity_id"],
                    status,
                    match_method,
                    match_reason,
                    result["candidate_ids"],
                    getattr(source_record, "namespace", None),
                    getattr(source_record, "external_id", None),
                    json.dumps(metadata),
                )
            else:
                row = await connection.fetchrow(
                    """UPDATE canonical.reconciliation_results
                    SET canonical_entity_id = $2::uuid,
                        status = $3::text,
                        match_method = $4::text,
                        match_reason = $5::text,
                        candidate_ids = $6::uuid[],
                        source_namespace = $7::text,
                        source_identifier = $8::text,
                        source_metadata = $9::jsonb,
                        updated_at = NOW()
                    WHERE id = $1
                    RETURNING *""",
                    existing["id"],
                    result["canonical_entity_id"],
                    status,
                    match_method,
                    match_reason,
                    result["candidate_ids"],
                    getattr(source_record, "namespace", None),
                    getattr(source_record, "external_id", None),
                    json.dumps(metadata),
                )
            result["created_at"] = row["created_at"]
            result["updated_at"] = row["updated_at"]
        result["canonical_entity_id"] = str(result["canonical_entity_id"]) if result["canonical_entity_id"] else None
        result["candidate_ids"] = [str(item) for item in result["candidate_ids"]]
        result["tenant_id"] = str(tenant_uuid) if tenant_uuid else None
        return result


canonical_repository = CanonicalRepository
