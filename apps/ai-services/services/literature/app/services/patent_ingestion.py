from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import jwt

from app.connectors.google_patents import GooglePatentsConnector
from app.core.config import Settings, get_settings
from app.database.postgres import PostgresManager, postgres_manager
from app.integrations.kg_client import KGClient
from app.orchestrator.manager import IngestionJob


class PatentIngestionProcessor:
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

    def _connector(self) -> GooglePatentsConnector:
        return GooglePatentsConnector({
            "base_url": self.settings.google_patents_base_url,
            "timeout": self.settings.google_patents_timeout,
            "max_retries": self.settings.google_patents_max_retries,
            "backoff_seconds": self.settings.google_patents_backoff_seconds,
            "requests_per_second": self.settings.google_patents_requests_per_second,
            "user_agent": self.settings.crawler_user_agent,
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
        if source_id:
            return source_id
        raw = json.dumps(record, sort_keys=True, default=str)
        return f"MALFORMED:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"

    async def run(
        self,
        job: IngestionJob,
        persist_job: Callable[[IngestionJob], Awaitable[None]],
    ) -> None:
        if job.checkpoint.get("complete") is True:
            return
        if not job.query.strip():
            raise ValueError("patent ingestion requires a patent identifier or explicit query")
        connector = self._connector()
        page_size = int(job.checkpoint.get(
            "page_size", self.settings.google_patents_page_size
        ))
        if not 1 <= page_size <= 100:
            raise ValueError("persisted Google Patents page_size is outside 1..100")
        page_token = job.checkpoint.get("page_token")
        completed_keys = set(job.checkpoint.get("completed_record_keys", []))
        seen_tokens = set(job.checkpoint.get("seen_page_tokens", []))
        bearer_token = self._job_token(job.auth_context)

        while True:
            page, next_page_token = await asyncio.to_thread(
                connector.fetch_page,
                job.query,
                page_token=page_token,
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
                    "source": "patent",
                    "source_id": malformed.get("source_id"),
                    "checkpoint_key": checkpoint_key,
                    "error_message": malformed.get("error_message", "malformed patent record"),
                    "source_url": malformed.get("source_url"),
                    "status": "permanent",
                    "page_token": page_token,
                })
                completed_keys.add(checkpoint_key)
                job.checkpoint.update({
                    "page_token": page_token,
                    "page_size": page_size,
                    "completed_record_keys": sorted(completed_keys),
                    "seen_page_tokens": sorted(seen_tokens),
                })
                await persist_job(job)

            for record in page:
                source_id = self._checkpoint_key(record)
                if source_id in completed_keys:
                    continue
                try:
                    retrieved_at = record.get("retrieved_at") or datetime.now(timezone.utc)
                    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
                        raise ValueError("patent retrieval timestamp must be timezone-aware")
                    metadata = dict(record.get("metadata") or {})
                    metadata["retrieved_at"] = retrieved_at.isoformat()
                    record["metadata"] = metadata
                    await self.database.upsert_patent_record(
                        record,
                        organization_id=job.organization_id,
                        retrieved_at=retrieved_at,
                    )
                    canonical_result = await self.kg_client.ingest_patent_record(
                        {
                            "source_name": metadata.get("source_name", "Google Patents"),
                            "source_id": source_id,
                            "jurisdiction": metadata.get("jurisdiction", source_id[:2]),
                            "title": record.get("title") or source_id,
                            "abstract": record.get("abstract"),
                            "application_number": metadata.get("application_number"),
                            "publication_number": metadata.get("publication_number") or source_id,
                            "grant_number": metadata.get("grant_number"),
                            "family_identifier": metadata.get("family_identifier"),
                            "filing_date_source": metadata.get("filing_date_source"),
                            "publication_date_source": metadata.get("publication_date_source")
                                or record.get("published_date"),
                            "grant_date_source": metadata.get("grant_date_source"),
                            "status": metadata.get("status"),
                            "patent_type": metadata.get("patent_type"),
                            "applicants": metadata.get("applicants", []),
                            "assignees": metadata.get("assignees", []),
                            "inventors": metadata.get("inventors") or record.get("authors", []),
                            "classifications": metadata.get("classifications", []),
                            "priority_numbers": metadata.get("priority_numbers", []),
                            "citations": metadata.get("citations", []),
                            "source_url": record["url"],
                            "retrieved_at": retrieved_at.isoformat(),
                            "content_hash": record["content_hash"],
                            "raw_payload_ref": (
                                f"literature_source_snapshots:patent:"
                                f"{source_id}:{record['content_hash']}"
                            ),
                            "source_metadata": metadata,
                            "query": job.query,
                        },
                        bearer_token=bearer_token,
                    )
                    reconciliation = canonical_result.get("reconciliation") or {}
                    await self.database.set_patent_reconciliation(
                        source_id,
                        organization_id=job.organization_id,
                        canonical_entity_id=canonical_result.get("canonical_entity_id"),
                        status=str(reconciliation.get("status") or "UNRESOLVED"),
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    job.progress.failed_documents += 1
                    job.progress.dead_lettered_documents += 1
                    job.dead_letter_count += 1
                    job.dead_letter_items.append({
                        "source": "patent",
                        "source_id": record.get("source_id"),
                        "checkpoint_key": source_id,
                        "error_message": str(exc),
                        "status": "permanent",
                        "page_token": page_token,
                    })
                else:
                    job.progress.processed_documents += 1
                completed_keys.add(source_id)
                job.checkpoint.update({
                    "page_token": page_token,
                    "page_size": page_size,
                    "completed_record_keys": sorted(completed_keys),
                    "seen_page_tokens": sorted(seen_tokens),
                })
                await persist_job(job)

            job.progress.total_documents = max(
                job.progress.total_documents,
                job.progress.processed_documents + job.progress.failed_documents,
            )
            if next_page_token is None:
                job.checkpoint = {
                    "page_size": page_size,
                    "completed_record_keys": sorted(completed_keys),
                    "seen_page_tokens": sorted(seen_tokens),
                    "complete": True,
                }
                job.progress.total_documents = (
                    job.progress.processed_documents + job.progress.failed_documents
                )
                await persist_job(job)
                return
            if next_page_token == page_token or next_page_token in seen_tokens:
                raise RuntimeError("Google Patents repeated a pagination checkpoint")
            if not page and not connector.last_malformed_records:
                raise RuntimeError("Google Patents returned an empty page with a next checkpoint")
            seen_tokens.add(str(page_token))
            page_token = next_page_token
            completed_keys.clear()
            job.checkpoint = {
                "page_token": page_token,
                "page_size": page_size,
                "completed_record_keys": [],
                "seen_page_tokens": sorted(seen_tokens),
            }
            await persist_job(job)
