from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.observability.metrics import metrics

logger = logging.getLogger(__name__)


class LLMWikiClient:
    """Integration boundary for updating the Open Knowledge Format (OKF) LLM Wiki."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.wiki_dir = Path(self.config.get("wiki_dir", os.environ.get("OKF_WIKI_DIR", "wiki-root")))
        self.service_url = self.config.get("wiki_service_url", os.environ.get("OKF_WIKI_URL"))
        self.wiki_api_key = self.config.get("wiki_api_key")
        self.timeout = float(self.config.get("wiki_timeout", 5.0))
        self.max_retries = int(self.config.get("wiki_max_retries", 1))
        self.backoff_seconds = float(self.config.get("wiki_backoff_seconds", 0.25))

    def update_wiki(self, document: dict[str, Any], entities: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
        """Compile literature intelligence into OKF markdown wiki concepts."""
        if self.service_url:
            headers = {"Content-Type": "application/json"}
            if self.wiki_api_key:
                headers["Authorization"] = f"Bearer {self.wiki_api_key}"

            for attempt in range(self.max_retries + 1):
                try:
                    with httpx.Client(timeout=self.timeout) as client:
                        res = client.post(f"{self.service_url.rstrip('/')}/api/v1/wiki/compile", json={"document": document, "entities": entities, "summary": summary}, headers=headers)
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

            updated_files: list[str] = []
            for entity in entities:
                text = entity.get("text")
                category = entity.get("category", "concepts")
                if not text:
                    continue
                category_dir = wiki_path / category
                category_dir.mkdir(parents=True, exist_ok=True)
                file_path = category_dir / f"{text.replace(' ', '_')}.md"

                content = f"""# Concept: {text}
- **Category**: {category}
- **Last Updated**: {timestamp}
- **Source**: {document.get('source')} ({document.get('source_id')})

## Primary Summary
{summary.get('concise_summary', 'No summary provided.')}

## Literature Evidence
- **Title**: {document.get('title')}
- **DOI**: {document.get('doi')}
- **URL**: {document.get('url')}
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
