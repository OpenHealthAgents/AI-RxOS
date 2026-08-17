from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.knowledge.models import deterministic_entity_id
from app.observability.metrics import metrics

logger = logging.getLogger(__name__)


class LLMWikiClient:
    """Integration boundary for updating the Open Knowledge Format (OKF) LLM Wiki."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.wiki_dir = Path(self.config.get("wiki_dir", os.environ.get("OKF_WIKI_DIR", "wiki-root")))
        self.service_url = self.config.get(
            "wiki_service_url",
            os.environ.get("LLM_WIKI_URL") or os.environ.get("OKF_WIKI_URL"),
        )
        self.wiki_api_key = self.config.get("wiki_api_key")
        self.timeout = float(self.config.get("wiki_timeout", 5.0))
        self.max_retries = int(self.config.get("wiki_max_retries", 1))
        self.backoff_seconds = float(self.config.get("wiki_backoff_seconds", 0.25))

    def update_wiki(
        self,
        document: dict[str, Any],
        entities: list[dict[str, Any]],
        summary: dict[str, Any],
        *,
        relationships: list[dict[str, Any]] | None = None,
        evidence: list[dict[str, Any]] | None = None,
        tenant: dict[str, Any] | None = None,
        chunks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Compile literature intelligence into OKF markdown wiki concepts.

        relationships/evidence/tenant/chunks are optional and additive: all
        default to None so existing callers (and the existing OKF-volume
        test, which calls update_wiki with only document/entities/summary)
        keep their prior behavior — with no tenant, pages are written to the
        same untenanted paths as before.
        """
        relationships = relationships or []
        evidence = evidence or []
        tenant = tenant or {}

        if self.service_url:
            headers = {"Content-Type": "application/json"}
            if self.wiki_api_key:
                headers["Authorization"] = f"Bearer {self.wiki_api_key}"

            for attempt in range(self.max_retries + 1):
                try:
                    with httpx.Client(timeout=self.timeout) as client:
                        res = client.post(
                            f"{self.service_url.rstrip('/')}/api/v1/wiki/compile",
                            json={
                                "document": document,
                                "entities": entities,
                                "summary": summary,
                                "relationships": relationships,
                                "evidence": evidence,
                                "tenant": tenant,
                                "chunks": chunks or [],
                            },
                            headers=headers,
                        )
                    if res.status_code in (200, 201):
                        metrics.increment("literature.wiki_update.success")
                        return {"success": True, "method": "http", "status": "completed"}
                    if res.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                        delay = self.backoff_seconds * (2**attempt)
                        logger.warning("Wiki HTTP retryable status %s on attempt %d, sleeping %.2fs", res.status_code, attempt + 1, delay)
                        time.sleep(delay)
                        continue
                    logger.warning("Wiki HTTP update failed: %s", res.text)
                    metrics.increment("literature.wiki_update.failure")
                    return {"success": False, "error": res.text, "retry_eligible": res.status_code >= 500 or res.status_code == 429, "status": "failed"}
                except (httpx.HTTPError, RuntimeError, KeyError, TypeError, ValueError, OSError) as exc:
                    if attempt < self.max_retries:
                        delay = self.backoff_seconds * (2**attempt)
                        logger.warning("Wiki HTTP service unreachable on attempt %d, retrying in %.2fs: %s", attempt + 1, delay, exc)
                        time.sleep(delay)
                        continue
                    logger.warning("Wiki HTTP service unreachable: %s", exc)
                    metrics.increment("literature.wiki_update.failure")
                    return {"success": False, "error": str(exc), "retry_eligible": True, "status": "failed"}

        # Direct OKF volume update fallback
        try:
            wiki_path = self.wiki_dir / "wiki"
            wiki_path.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).isoformat()

            organization_id = tenant.get("organization_id")
            workspace_id = tenant.get("workspace_id")

            updated_files: list[str] = []
            for entity in entities:
                text = entity.get("text")
                category = entity.get("category", "concepts")
                if not text:
                    continue

                # No tenant -> identical path to the pre-Prompt-8 behavior.
                # With a tenant, pages are namespaced under org/workspace so
                # one organization's wiki content is never written into (or
                # read from) another's directory tree.
                if organization_id:
                    category_dir = (
                        wiki_path
                        / str(organization_id)
                        / str(workspace_id or "_shared")
                        / category
                    )
                else:
                    category_dir = wiki_path / category
                category_dir.mkdir(parents=True, exist_ok=True)
                slug = text.replace(" ", "_")
                file_path = category_dir / f"{slug}.md"

                version = self._next_version(file_path)
                if file_path.exists():
                    self._archive_previous_version(category_dir, slug, file_path)

                entity_id = deterministic_entity_id(
                    entity.get("type") or category, text
                )

                entity_relationships = [
                    r
                    for r in relationships
                    if r.get("source_entity") == text or r.get("target_entity") == text
                ]
                entity_evidence = [e for e in evidence if e.get("entity") == text]

                relationships_section = "\n".join(
                    f"- {r.get('source_entity')} --{r.get('predicate')}--> "
                    f"{r.get('target_entity')} (confidence: {r.get('confidence', 'n/a')})"
                    for r in entity_relationships
                ) or "No relationships recorded."
                evidence_section = "\n".join(
                    f"- {e.get('entity')} (category: {e.get('category', 'unknown')}, "
                    f"score: {e.get('score', 'n/a')})"
                    for e in entity_evidence
                ) or "No additional evidence recorded."
                tenant_line = (
                    f"- **Organization**: {organization_id}"
                    + (f" / **Workspace**: {workspace_id}" if workspace_id else "")
                    + "\n"
                    if organization_id
                    else ""
                )

                content = f"""# Concept: {text}
- **Category**: {category}
- **Entity ID**: {entity_id}
- **Version**: {version}
- **Last Updated**: {timestamp}
- **Source**: {document.get('source')} ({document.get('source_id')})
{tenant_line}
## Primary Summary
{summary.get('concise_summary', 'No summary provided.')}

## Literature Evidence
- **Title**: {document.get('title')}
- **DOI**: {document.get('doi')}
- **URL**: {document.get('url')}

## Relationships
{relationships_section}

## Supporting Evidence
{evidence_section}
"""
                file_path.write_text(content, encoding="utf-8")
                updated_files.append(str(file_path))

            # Update log.md
            log_file = wiki_path / "log.md"
            log_entry = f"- [{timestamp}] Updated {len(updated_files)} concept pages from {document.get('source')}:{document.get('source_id')}\n"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)

            metrics.increment("literature.wiki_update.success")
            return {
                "success": True,
                "method": "okf_volume",
                "updated_concepts": len(updated_files),
                "status": "completed",
            }
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            logger.warning("OKF Wiki volume write failed: %s", exc)
            metrics.increment("literature.wiki_update.failure")
            return {"success": False, "error": str(exc), "retry_eligible": True, "status": "failed"}

    @staticmethod
    def _next_version(file_path: Path) -> int:
        """Read the current page's "- **Version**: N" line and return N + 1.

        Missing file, missing line, or an unparseable value all fall back
        to version 1 rather than raising — versioning is best-effort
        metadata on top of the markdown page, not a hard invariant.
        """
        if not file_path.exists():
            return 1
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            return 1
        for line in content.splitlines():
            if line.startswith("- **Version**:"):
                try:
                    return int(line.split(":", 1)[1].strip()) + 1
                except ValueError:
                    return 1
        return 1

    @staticmethod
    def _archive_previous_version(category_dir: Path, slug: str, file_path: Path) -> None:
        """Copy the current page into a _versions/ subdirectory before overwrite.

        This is the "history where appropriate" versioning the concept
        pages otherwise lack entirely (prior behavior was a full in-place
        overwrite with no way to recover an earlier version of a concept).
        """
        try:
            versions_dir = category_dir / "_versions"
            versions_dir.mkdir(parents=True, exist_ok=True)
            previous_version = LLMWikiClient._next_version(file_path) - 1
            archive_path = versions_dir / f"{slug}_v{previous_version}.md"
            archive_path.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to archive previous wiki page version for %s: %s", slug, exc)
