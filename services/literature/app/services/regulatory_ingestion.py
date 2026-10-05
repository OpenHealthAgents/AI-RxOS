from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import jwt

from app.connectors.sources import FDARegulatoryConnector
from app.core.config import Settings, get_settings
from app.database.postgres import PostgresManager, postgres_manager
from app.integrations.kg_client import KGClient
from app.orchestrator.manager import IngestionJob


class RegulatoryIngestionProcessor:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        database: PostgresManager = postgres_manager,
        kg_client: KGClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.database = database
        self.kg_client = kg_client or KGClient({
            "kg_service_url": self.settings.kg_service_url,
            "kg_timeout": self.settings.kg_timeout,
            "kg_max_retries": self.settings.kg_max_retries,
            "kg_backoff_seconds": self.settings.kg_backoff_seconds,
        })

    def _connector(self) -> FDARegulatoryConnector:
        return FDARegulatoryConnector({
            "base_url": self.settings.fda_regulatory_base_url,
            "timeout": self.settings.fda_regulatory_timeout,
            "max_retries": self.settings.fda_regulatory_max_retries,
            "backoff_seconds": self.settings.fda_regulatory_backoff_seconds,
            "requests_per_second": self.settings.fda_regulatory_requests_per_second,
        })

    def _job_token(self, auth_context: dict[str, Any]) -> str:
        claims = {
            key: auth_context[key]
            for key in (
                "sub", "user_id", "userId", "organization_id", "organizationId",
                "roles", "permissions", "iss", "aud",
            )
            if key in auth_context
        }
        now = datetime.now(timezone.utc)
        claims["iat"] = now
        claims["exp"] = now + timedelta(minutes=5)
        return jwt.encode(claims, self.settings.jwt_secret, algorithm="HS256")

    @staticmethod
    def _checkpoint_key(record: dict[str, Any]) -> str:
        source_id = str(record.get("source_id") or "").strip().upper()
        if record.get("error_message"):
            serialized = json.dumps(
                {
                    "source_id": source_id,
                    "record_index": record.get("record_index"),
                    "submission_index": record.get("submission_index"),
                    "raw_payload": record.get("raw_payload"),
                },
                sort_keys=True,
                default=str,
            )
            return f"MALFORMED:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"
        if source_id:
            return source_id
        serialized = json.dumps(record.get("raw_payload", record), sort_keys=True, default=str)
        return f"MALFORMED:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"

    async def run(
        self,
        job: IngestionJob,
        persist_job: Callable[[IngestionJob], Awaitable[None]],
    ) -> None:
        if job.checkpoint.get("complete") is True:
            return
        connector = self._connector()
        page_size = int(job.checkpoint.get("page_size", self.settings.fda_regulatory_page_size))
        if not 1 <= page_size <= 1000:
            raise ValueError("persisted FDA page_size is outside 1..1000")
        offset = int(job.checkpoint.get("offset", 0))
        if offset < 0 or offset > 25_000:
            raise ValueError("persisted FDA offset is outside 0..25000")
        query = job.query.strip()
        if not query:
            raise ValueError("FDA regulatory ingestion requires an explicit openFDA search query")
        completed_keys = set(job.checkpoint.get("completed_record_keys", []))
        seen_offsets = set(job.checkpoint.get("seen_offsets", []))
        auth_token = self._job_token(job.auth_context)

        while True:
            page, next_offset = await asyncio.to_thread(
                connector.fetch_page,
                job.query,
                offset=offset,
                page_size=page_size,
            )
            for malformed in connector.last_malformed_records:
                checkpoint_key = self._checkpoint_key(malformed)
                if checkpoint_key in completed_keys:
                    continue
                job.progress.failed_documents += 1
                job.progress.dead_lettered_documents += 1
                job.dead_letter_count += 1
                job.dead_letter_items.append({
                    "source": "regulatory",
                    "source_id": malformed.get("source_id"),
                    "checkpoint_key": checkpoint_key,
                    "error_message": malformed.get("error_message", "malformed FDA record"),
                    "status": "permanent",
                    "raw_payload": malformed.get("raw_payload"),
                    "offset": offset,
                })
                completed_keys.add(checkpoint_key)
                job.checkpoint.update({
                    "offset": offset,
                    "page_size": page_size,
                    "completed_record_keys": sorted(completed_keys),
                    "seen_offsets": sorted(seen_offsets),
                })
                await persist_job(job)

            for record in page:
                source_id = self._checkpoint_key(record)
                if source_id in completed_keys:
                    continue
                retrieved_at = datetime.now(timezone.utc)
                metadata = dict(record.get("metadata") or {})
                metadata["retrieved_at"] = retrieved_at.isoformat()
                source_metadata = dict(metadata.get("source_metadata") or {})
                source_metadata["retrieved_at"] = retrieved_at.isoformat()
                metadata["source_metadata"] = source_metadata
                record["metadata"] = metadata

                await self.database.upsert_regulatory_record(
                    record,
                    organization_id=job.organization_id,
                    retrieved_at=retrieved_at,
                )
                canonical_result = await self.kg_client.ingest_regulatory_event(
                    {
                        "event_id": record["source_id"],
                        "regulator": metadata["regulator"],
                        "jurisdiction": metadata["jurisdiction"],
                        "event_type": metadata["event_type"],
                        "event_status": metadata.get("event_status"),
                        "application_number": metadata["application_number"],
                        "application_type": metadata.get("application_type"),
                        "submission_number": metadata["submission_number"],
                        "submission_type": metadata.get("submission_type"),
                        "submission_class_code": metadata.get("submission_class_code"),
                        "event_date_source": metadata.get("submission_status_date_source"),
                        "product_names": [
                            item["brand_name"] for item in metadata["products"]
                            if item.get("brand_name")
                        ],
                        "product_identifiers": [
                            {
                                "product_number": item["product_number"],
                                "brand_name": item.get("brand_name"),
                            }
                            for item in metadata["products"]
                            if item.get("product_number")
                        ],
                        "active_ingredients": [
                            ingredient
                            for item in metadata["products"]
                            for ingredient in item.get("active_ingredients", [])
                        ],
                        "sponsor_name": metadata.get("sponsor_name"),
                        "title": record["title"],
                        "retrieved_at": retrieved_at.isoformat(),
                        "content_hash": record["content_hash"],
                        "source_url": record["url"],
                        "source_metadata": source_metadata,
                        "raw_payload_ref": (
                            f"literature_source_snapshots:regulatory:"
                            f"{record['source_id']}:{record['content_hash']}"
                        ),
                        "query": query,
                    },
                    bearer_token=auth_token,
                )
                reconciliation = canonical_result.get("reconciliation") or {}
                canonical_entity_id = canonical_result.get("canonical_entity_id")
                await self.database.set_regulatory_reconciliation(
                    record["source_id"],
                    organization_id=job.organization_id,
                    canonical_entity_id=canonical_entity_id,
                    status=str(reconciliation.get("status") or "UNRESOLVED"),
                )
                completed_keys.add(source_id)
                job.progress.processed_documents += 1
                job.checkpoint.update({
                    "offset": offset,
                    "page_size": page_size,
                    "completed_record_keys": sorted(completed_keys),
                    "seen_offsets": sorted(seen_offsets),
                    "last_source_id": source_id,
                })
                await persist_job(job)

            if next_offset is None:
                if getattr(connector, "last_offset_limit_reached", False):
                    job.checkpoint.update({
                        "offset": offset,
                        "page_size": page_size,
                        "completed_record_keys": sorted(completed_keys),
                        "seen_offsets": sorted(seen_offsets),
                    })
                    await persist_job(job)
                    raise ValueError(
                        "FDA openFDA result exceeds the 25000-record offset window; narrow the query"
                    )
                job.progress.total_documents = (
                    job.progress.processed_documents + job.progress.failed_documents
                )
                job.checkpoint = {
                    "offset": 0,
                    "page_size": page_size,
                    "completed_record_keys": [],
                    "seen_offsets": sorted(seen_offsets),
                    "complete": True,
                }
                await persist_job(job)
                return
            if next_offset == offset or str(next_offset) in seen_offsets:
                raise RuntimeError("FDA openFDA repeated a pagination offset")

            seen_offsets.add(str(offset))
            offset = next_offset
            completed_keys.clear()
            job.checkpoint = {
                "offset": offset,
                "page_size": page_size,
                "completed_record_keys": [],
                "seen_offsets": sorted(seen_offsets),
            }
            await persist_job(job)
