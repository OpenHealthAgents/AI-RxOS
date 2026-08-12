from __future__ import annotations

import hashlib
import re
from typing import Any


class DuplicateDetector:
    """Multi-tiered duplicate detector for literature documents."""

    @staticmethod
    def _normalize_string(text: str | None) -> str:
        if not text:
            return ""
        clean = re.sub(r"[^\w\s]", "", str(text)).lower()
        return " ".join(clean.split())

    def detect_duplicate(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        """Detect if two documents are duplicates using 4 identifier tiers."""
        left_doi = (left.get("doi") or "").strip().lower()
        right_doi = (right.get("doi") or "").strip().lower()
        if left_doi and right_doi and left_doi == right_doi:
            return {
                "duplicate": True,
                "reason": "doi_match",
                "tier": 1,
                "matched_fields": {"doi": left_doi},
            }

        left_src = (left.get("source") or "").strip().lower()
        right_src = (right.get("source") or "").strip().lower()
        left_id = (left.get("source_id") or left.get("id") or "").strip().lower()
        right_id = (right.get("source_id") or right.get("id") or "").strip().lower()

        if left_src and right_src and left_id and right_id and left_src == right_src and left_id == right_id:
            return {
                "duplicate": True,
                "reason": "source_id_match",
                "tier": 2,
                "matched_fields": {"source": left_src, "source_id": left_id},
            }

        norm_left_title = self._normalize_string(left.get("title"))
        norm_right_title = self._normalize_string(right.get("title"))

        if norm_left_title and norm_right_title and norm_left_title == norm_right_title:
            return {
                "duplicate": True,
                "reason": "title_match",
                "tier": 3,
                "matched_fields": {"normalized_title": norm_left_title},
            }

        left_content = (left.get("content") or left.get("abstract") or norm_left_title).strip().lower()
        right_content = (right.get("content") or right.get("abstract") or norm_right_title).strip().lower()

        if left_content and right_content:
            left_hash = hashlib.sha256(left_content.encode("utf-8")).hexdigest()
            right_hash = hashlib.sha256(right_content.encode("utf-8")).hexdigest()

            if left_hash == right_hash:
                return {
                    "duplicate": True,
                    "reason": "content_hash_match",
                    "tier": 4,
                    "matched_fields": {"content_sha256": left_hash},
                }

        return {
            "duplicate": False,
            "reason": "distinct_documents",
            "tier": 0,
            "matched_fields": {},
        }
