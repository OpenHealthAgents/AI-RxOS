from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from uuid import UUID

import jwt

from app.connectors.sources import ClinicalTrialsConnector
from app.core.config import Settings, get_settings
from app.database.postgres import PostgresManager, postgres_manager
from app.integrations.kg_client import KGClient
from app.orchestrator.manager import IngestionJob
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ClinicalTrialsIngestionProcessor:
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

    def _connector(self) -> ClinicalTrialsConnector:
        return ClinicalTrialsConnector({
            "base_url": self.settings.clinicaltrials_base_url,
            "timeout": self.settings.clinicaltrials_timeout,
            "max_retries": self.settings.clinicaltrials_max_retries,
            "backoff_seconds": self.settings.clinicaltrials_backoff_seconds,
            "requests_per_second": self.settings.clinicaltrials_requests_per_second,
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
        identity = str(record.get("nct_id") or record.get("source_id") or "").strip().upper()
        if identity:
            return identity
        raw = record.get("raw_payload", record)
        serialized = json.dumps(raw, sort_keys=True, default=str)
        return f"MALFORMED:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"

    async def run(
        self,
        job: IngestionJob,
        persist_job: Callable[[IngestionJob], Awaitable[None]],
    ) -> None:
        connector = self._connector()
        page_size = int(job.checkpoint.get("page_size", self.settings.clinicaltrials_page_size))
        if not 1 <= page_size <= 1000:
            raise ValueError("persisted ClinicalTrials page_size is outside 1..1000")
        page_token = job.checkpoint.get("page_token")
        completed_keys = set(job.checkpoint.get("completed_record_keys", []))
        seen_page_tokens = set(job.checkpoint.get("seen_page_tokens", []))
        auth_token = self._job_token(job.auth_context)

        while True:
            page, next_page_token = await asyncio.to_thread(
                connector.fetch_page,
                job.query,
                page_token=page_token,
                page_size=page_size,
            )
            total_count = getattr(connector, "last_total_count", None)
            if isinstance(total_count, int):
                job.progress.total_documents = max(job.progress.total_documents, total_count)
            malformed_records = getattr(connector, "last_malformed_records", [])
            for malformed in malformed_records:
                checkpoint_key = self._checkpoint_key(malformed)
                if checkpoint_key in completed_keys:
                    continue
                job.progress.failed_documents += 1
                job.progress.dead_lettered_documents += 1
                job.dead_letter_count += 1
                job.dead_letter_items.append({
                    "source": "clinicaltrials",
                    "source_id": malformed.get("source_id"),
                    "checkpoint_key": checkpoint_key,
                    "error_message": malformed.get("error_message", "malformed ClinicalTrials study"),
                    "status": "permanent",
                    "raw_payload": malformed.get("raw_payload"),
                    "page_token": page_token,
                })
                completed_keys.add(checkpoint_key)
                job.checkpoint.update({
                    "page_token": page_token,
                    "page_size": page_size,
                    "completed_record_keys": sorted(completed_keys),
                    "seen_page_tokens": sorted(seen_page_tokens),
                })
                await persist_job(job)

            for record in page:
                nct_id = str(record.get("nct_id") or "").strip().upper()
                checkpoint_key = self._checkpoint_key(record)
                if not re.fullmatch(r"NCT\d{8}", nct_id):
                    if checkpoint_key in completed_keys:
                        continue
                    job.progress.failed_documents += 1
                    job.progress.dead_lettered_documents += 1
                    job.dead_letter_count += 1
                    job.dead_letter_items.append({
                        "source": "clinicaltrials",
                        "source_id": record.get("source_id"),
                        "checkpoint_key": checkpoint_key,
                        "error_message": "record is missing a valid NCT identifier",
                        "status": "permanent",
                        "raw_payload": record.get("raw_payload"),
                    })
                    completed_keys.add(checkpoint_key)
                    job.checkpoint.update({
                        "page_token": page_token,
                        "page_size": page_size,
                        "completed_record_keys": sorted(completed_keys),
                        "seen_page_tokens": sorted(seen_page_tokens),
                    })
                    await persist_job(job)
                    continue
                if nct_id in completed_keys:
                    continue

                retrieved_at = datetime.now(timezone.utc)
                normalized_metadata = dict(record.get("metadata") or {})
                normalized_metadata["retrieved_at"] = retrieved_at.isoformat()
                record["metadata"] = normalized_metadata
                paper_id = await self.database.upsert_clinicaltrial_record(
                    record,
                    organization_id=job.organization_id,
                    retrieved_at=retrieved_at,
                )
                canonical_metadata = normalized_metadata.get("source_metadata") or {}
                canonical_result = await self.kg_client.ingest_clinical_trial(
                    {
                        "nct_id": nct_id,
                        "title": record.get("title") or nct_id,
                        "abstract": record.get("abstract"),
                        "study_data": {
                            key: value
                            for key, value in normalized_metadata.items()
                            if key != "source_metadata"
                        },
                        "retrieved_at": retrieved_at.isoformat(),
                        "content_hash": record["content_hash"],
                        "source_metadata": {
                            "parser": canonical_metadata.get("parser"),
                            "query": job.query,
                            "source_url": record.get("url"),
                            "api_endpoint": self.settings.clinicaltrials_base_url,
                        },
                        "query": job.query,
                    },
                    bearer_token=auth_token,
                )
                reconciliation = canonical_result.get("reconciliation") or {}
                canonical_entity_id = canonical_result.get("canonical_entity_id")
                if canonical_entity_id:
                    canonical_entity_id = UUID(str(canonical_entity_id))
                await self.database.set_clinicaltrial_reconciliation(
                    nct_id,
                    organization_id=job.organization_id,
                    canonical_entity_id=canonical_entity_id,
                    status=str(reconciliation.get("status") or "UNRESOLVED"),
                )
                completed_keys.add(nct_id)
                job.progress.processed_documents += 1
                job.checkpoint.update({
                    "page_token": page_token,
                    "page_size": page_size,
                    "completed_record_keys": sorted(completed_keys),
                    "seen_page_tokens": sorted(seen_page_tokens),
                    "last_source_id": nct_id,
                    "last_paper_id": str(paper_id),
                })
                await persist_job(job)

            if not next_page_token:
                job.checkpoint = {
                    "page_token": None,
                    "page_size": page_size,
                    "completed_record_keys": [],
                    "seen_page_tokens": sorted(seen_page_tokens),
                }
                await persist_job(job)
                return
            if next_page_token == page_token or next_page_token in seen_page_tokens:
                raise RuntimeError("ClinicalTrials.gov repeated a pagination token")

            seen_page_tokens.add(page_token or "__first_page__")
            page_token = next_page_token
            completed_keys.clear()
            job.checkpoint = {
                "page_token": page_token,
                "page_size": page_size,
                "completed_record_keys": [],
                "seen_page_tokens": sorted(seen_page_tokens),
            }
            await persist_job(job)
