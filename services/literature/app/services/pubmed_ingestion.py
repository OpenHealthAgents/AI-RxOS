from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import jwt

from app.connectors.sources import PubMedConnector
from app.core.config import Settings, get_settings
from app.database.postgres import PostgresManager, postgres_manager
from app.integrations.kg_client import KGClient
from app.nlp.pipeline import LiteratureNLP
from app.orchestrator.manager import IngestionJob
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PubMedIngestionProcessor:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        database: PostgresManager = postgres_manager,
        kg_client: KGClient | None = None,
        nlp: LiteratureNLP | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.database = database
        self.kg_client = kg_client or KGClient({
            "kg_service_url": self.settings.kg_service_url,
            "kg_timeout": self.settings.kg_timeout,
            "kg_max_retries": self.settings.kg_max_retries,
            "kg_backoff_seconds": self.settings.kg_backoff_seconds,
        })
        self.nlp = nlp or LiteratureNLP({"ner_provider": self.settings.ner_provider})

    def _connector(self) -> PubMedConnector:
        return PubMedConnector({
            "base_url": self.settings.pubmed_base_url,
            "api_key": self.settings.pubmed_api_key,
            "email": self.settings.pubmed_email,
            "requests_per_second": self.settings.pubmed_requests_per_second,
            "max_retries": self.settings.pubmed_max_retries,
            "backoff_seconds": self.settings.pubmed_backoff_seconds,
            "timeout": self.settings.crawler_timeout,
        })

    def _job_token(self, auth_context: dict[str, Any]) -> str:
        claims = {
            key: auth_context[key]
            for key in ("sub", "user_id", "userId", "organization_id", "organizationId", "roles", "permissions", "iss", "aud")
            if key in auth_context
        }
        now = datetime.now(timezone.utc)
        claims["iat"] = now
        claims["exp"] = now + timedelta(minutes=5)
        return jwt.encode(claims, self.settings.jwt_secret, algorithm="HS256")

    @staticmethod
    def _checkpoint_key(record: dict[str, Any]) -> str:
        identity = str(record.get("pmid") or record.get("source_id") or "").strip()
        if identity:
            return identity
        payload = json.dumps(record, sort_keys=True, default=str)
        return f"MALFORMED:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"

    async def run(
        self,
        job: IngestionJob,
        persist_job: Callable[[IngestionJob], Awaitable[None]],
    ) -> None:
        connector = self._connector()
        page_token = job.checkpoint.get("page_token")
        completed_pmids = set(job.checkpoint.get("completed_pmids", []))
        job.checkpoint.setdefault("page_token", page_token)

        while True:
            page, next_page_token = await asyncio.to_thread(
                connector.fetch_page,
                job.query,
                page_token=page_token,
                page_size=50,
            )
            job.progress.total_documents = max(
                job.progress.total_documents,
                int(getattr(connector, "last_total_count", 0) or len(page)),
            )
            for malformed in getattr(connector, "last_malformed_records", []):
                checkpoint_key = self._checkpoint_key(malformed)
                if checkpoint_key in completed_pmids:
                    continue
                job.progress.failed_documents += 1
                job.dead_letter_count += 1
                job.progress.dead_lettered_documents += 1
                job.dead_letter_items.append({
                    "source": "pubmed",
                    "source_id": malformed.get("pmid"),
                    "checkpoint_key": checkpoint_key,
                    "error_message": "NCBI EFetch article is missing required PMID/article metadata",
                    "status": "permanent",
                    "raw_xml": malformed.get("raw_xml"),
                })
                completed_pmids.add(checkpoint_key)
                job.checkpoint.update({
                    "page_token": page_token,
                    "completed_pmids": sorted(completed_pmids),
                })
                await persist_job(job)
            auth_token = self._job_token(job.auth_context)

            for record in page:
                pmid = str(record.get("pmid") or "").strip()
                if not pmid:
                    checkpoint_key = self._checkpoint_key(record)
                    if checkpoint_key in completed_pmids:
                        continue
                    job.progress.failed_documents += 1
                    job.dead_letter_count += 1
                    job.progress.dead_lettered_documents += 1
                    job.dead_letter_items.append({
                        "source": "pubmed",
                        "source_id": record.get("source_id"),
                        "checkpoint_key": checkpoint_key,
                        "error_message": "record is missing a PMID",
                        "status": "permanent",
                    })
                    completed_pmids.add(checkpoint_key)
                    job.checkpoint.update({
                        "page_token": page_token,
                        "completed_pmids": sorted(completed_pmids),
                    })
                    await persist_job(job)
                    continue
                if pmid in completed_pmids:
                    continue

                text = "\n".join(part for part in (record.get("title"), record.get("abstract")) if part)
                entities = self.nlp.ner.extract_entities(text)
                relationships = self.nlp.extract_relationships({
                    **record,
                    "entities": entities,
                })
                retrieved_at = datetime.now(timezone.utc)
                paper_id = await self.database.upsert_pubmed_paper(
                    record,
                    organization_id=job.organization_id,
                    retrieved_at=retrieved_at,
                    extracted_entities=entities,
                    extracted_relationships=relationships,
                )
                canonical_result = await self.kg_client.ingest_pubmed_article(
                    {
                        "pmid": pmid,
                        "pmcid": record.get("pmcid"),
                        "doi": record.get("doi"),
                        "title": record.get("title") or f"PubMed PMID:{pmid}",
                        "abstract": record.get("abstract"),
                        "authors": record.get("metadata", {}).get("authors", []),
                        "journal": record.get("journal"),
                        "publication_date_source": record.get("publication_date"),
                        "retrieved_at": retrieved_at.isoformat(),
                        "source_metadata": record.get("metadata", {}),
                        "extracted_entities": entities,
                        "extracted_relationships": relationships,
                        "query": job.query,
                    },
                    bearer_token=auth_token,
                )
                canonical_entity_id = canonical_result.get("canonical_entity_id")
                reconciliation = canonical_result.get("reconciliation", {})
                await self.database.set_pubmed_reconciliation(
                    pmid,
                    organization_id=job.organization_id,
                    canonical_entity_id=canonical_entity_id,
                    status=str(reconciliation.get("status") or "UNRESOLVED"),
                )
                job.progress.processed_documents += 1
                completed_pmids.add(pmid)
                job.checkpoint = {
                    "page_token": page_token,
                    "completed_pmids": sorted(completed_pmids),
                }
                job.checkpoint["last_source_id"] = record.get("source_id")
                job.checkpoint["last_paper_id"] = str(paper_id)
                await persist_job(job)

            if not next_page_token:
                job.checkpoint = {"page_token": None, "completed_pmids": []}
                await persist_job(job)
                break

            page_token = next_page_token
            completed_pmids.clear()
            job.checkpoint = {"page_token": page_token, "completed_pmids": []}
            await persist_job(job)

        if job.progress.failed_documents:
            logger.warning(
                "PubMed ingestion completed with isolated malformed records",
                extra={"job_id": job.job_id, "failed_documents": job.progress.failed_documents},
            )
