from __future__ import annotations

import html
import re
from typing import Any


class TextParser:
    """Prompt 6 document parser with deterministic normalization, HTML stripping, and safe optional field handling."""

    def strip_tags(self, text: str) -> str:
        """Strip HTML/XML markup safely."""
        if not text:
            return ""
        clean = re.sub(r"<[^>]+>", "", text)
        clean = html.unescape(clean)
        clean = re.sub(r"\s+", " ", clean)
        return re.sub(r"\s+([.,!?;:])", r"\1", clean).strip()

    def parse(self, text: str | None) -> dict[str, Any]:
        raw = text or ""
        cleaned = self.strip_tags(raw)
        sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", cleaned) if segment.strip()]
        paragraphs = [paragraph.strip() for paragraph in re.split(r"\n+", cleaned) if paragraph.strip()]
        tokens = re.findall(r"\b[\w-]+\b", cleaned)
        return {
            "text": cleaned,
            "sentences": sentences,
            "paragraphs": paragraphs,
            "token_count": len(tokens),
        }

    def normalize_document(self, document: dict[str, Any]) -> dict[str, Any]:
        raw_title = str(document.get("title") or document.get("headline") or "").strip()
        raw_abstract = str(document.get("abstract") or document.get("summary") or "").strip()
        raw_content = str(document.get("content") or document.get("full_text") or raw_abstract or raw_title)

        title = self.strip_tags(raw_title)
        abstract = self.strip_tags(raw_abstract)
        content = self.strip_tags(raw_content)

        source = str(document.get("source") or "unknown").strip().lower()
        source_id_val = document.get("source_id") or document.get("id")
        source_id = str(source_id_val).strip() if source_id_val is not None else None

        doi_val = document.get("doi")
        doi = str(doi_val).strip() if doi_val is not None else None

        url_val = document.get("url") or document.get("link")
        url = str(url_val).strip() if url_val is not None else None

        pub_date_val = document.get("published_date") or document.get("date") or document.get("publishedAt")
        published_date = str(pub_date_val).strip() if pub_date_val is not None else None

        authors_raw = document.get("authors") or []
        if isinstance(authors_raw, str):
            authors = [a.strip() for a in authors_raw.split(",") if a.strip()]
        elif isinstance(authors_raw, list):
            authors = [str(a).strip() for a in authors_raw if a]
        else:
            authors = []

        journal_val = document.get("journal") or document.get("conference")
        journal = str(journal_val).strip() if journal_val is not None else None

        metadata = document.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        document_type = document.get("document_type") or document.get("type") or source
        return {
            "title": title,
            "abstract": abstract,
            "content": content,
            "authors": authors,
            "published_date": published_date,
            "source": source,
            "source_id": source_id,
            "doi": doi,
            "url": url,
            "journal": journal,
            "document_type": str(document_type).strip() if document_type is not None else None,
            "metadata": metadata,
        }
