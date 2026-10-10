"""Small, reusable scientific-document chunker.

No chunking implementation existed anywhere in the repo prior to this
module (only unrelated I/O-buffer reads in app/parsing/duplicates.py and
app/parsing/parser.py). This is intentionally simple: paragraph-aware,
character-budget-based splitting with overlap, not a general NLP
framework. Every chunk carries enough metadata to be traced back to its
source document, entities, and tenant without a second lookup.
"""

from __future__ import annotations

import re
from typing import Any

from app.knowledge.models import KnowledgeMetadata, TenantContext

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")


def _split_paragraphs(text: str) -> list[str]:
    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text or "") if p.strip()]
    return paragraphs or ([text.strip()] if text and text.strip() else [])


def chunk_text(
    text: str,
    *,
    max_chars: int = 1000,
    overlap_chars: int = 150,
) -> list[str]:
    """Split text into paragraph-respecting chunks of at most max_chars.

    Paragraphs are packed greedily; a paragraph longer than max_chars is
    hard-split with overlap so no chunk ever exceeds the budget.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")

    chunks: list[str] = []
    current = ""

    for paragraph in _split_paragraphs(text):
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(paragraph) <= max_chars:
            current = paragraph
            continue

        start = 0
        while start < len(paragraph):
            end = min(start + max_chars, len(paragraph))
            chunks.append(paragraph[start:end])
            if end >= len(paragraph):
                break
            start = end - overlap_chars if end - overlap_chars > start else end

    if current:
        chunks.append(current)

    return chunks


def build_chunks(
    *,
    document: dict[str, Any],
    text: str,
    source_type: str,
    entity_ids: list[str] | None = None,
    entity_types: list[str] | None = None,
    tenant: TenantContext | None = None,
    version: int = 1,
    max_chars: int = 1000,
    overlap_chars: int = 150,
) -> list[dict[str, Any]]:
    """Chunk a document's text and attach canonical provenance/metadata.

    Every chunk is traceable to: document id, source type, title, entity
    ids (where available), organization/workspace/project, and version —
    the minimum set required by the Prompt 8 chunking requirement.
    """
    tenant = tenant or TenantContext()
    document_id = str(
        document.get("id") or document.get("source_id") or document.get("doi") or ""
    )
    source_id = str(document.get("source_id") or document_id)
    title = str(document.get("title") or "")

    pieces = chunk_text(text, max_chars=max_chars, overlap_chars=overlap_chars)
    chunks: list[dict[str, Any]] = []
    for index, piece in enumerate(pieces):
        metadata = KnowledgeMetadata(
            document_id=document_id,
            source_type=source_type,
            source_id=source_id,
            title=title,
            entity_ids=list(entity_ids or []),
            entity_types=list(entity_types or []),
            organization_id=tenant.organization_id,
            workspace_id=tenant.workspace_id,
            project_id=tenant.project_id,
            version=version,
            provenance={
                "source": document.get("source"),
                "url": document.get("url"),
                "doi": document.get("doi"),
            },
            citation={
                "title": title,
                "doi": document.get("doi"),
                "url": document.get("url"),
            },
        )
        chunks.append(
            {
                "chunk_id": f"{document_id or source_id}:{index}",
                "chunk_index": index,
                "text": piece,
                "metadata": metadata.to_dict(),
            }
        )
    return chunks
