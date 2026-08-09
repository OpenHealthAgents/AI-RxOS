from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, ClassVar


class EvidenceRanker:
    """Deterministic, structured evidence-ranking component based on metadata."""

    SOURCE_WEIGHTS: ClassVar[dict[str, float]] = {
        "pubmed": 0.90,
        "pmc": 0.90,
        "clinicaltrials": 0.95,
        "aacr": 0.85,
        "asco": 0.85,
        "sabcs": 0.85,
        "esmo": 0.85,
        "biorxiv": 0.70,
        "medrxiv": 0.70,
        "patents": 0.65,
        "company_websites": 0.50,
    }

    def rank_document(self, document: dict[str, Any]) -> dict[str, Any]:
        source = (document.get("source") or "unknown").lower()
        source_weight = self.SOURCE_WEIGHTS.get(source, 0.60)

        pub_type_score = 0.70
        journal = str(document.get("journal") or "").lower()
        title = str(document.get("title") or "").lower()
        abstract = str(document.get("abstract") or "").lower()
        metadata = document.get("metadata") or {}

        if "clinical trial" in journal or "clinical trial" in title or source == "clinicaltrials":
            pub_type_score = 0.95
            status = metadata.get("overallStatus") or ""
            if status.lower() in ("completed", "approved"):
                pub_type_score = 1.0
        elif "guideline" in title or "consensus" in title:
            pub_type_score = 0.95
        elif "review" in title or "meta-analysis" in abstract:
            pub_type_score = 0.85
        elif source in ("biorxiv", "medrxiv"):
            pub_type_score = 0.65

        recency_score = 0.80
        published_date = document.get("published_date")
        if published_date:
            try:
                year = int(str(published_date)[:4])
                current_year = datetime.now(timezone.utc).year
                diff = current_year - year
                if diff <= 1:
                    recency_score = 1.0
                elif diff <= 3:
                    recency_score = 0.90
                elif diff <= 5:
                    recency_score = 0.80
                else:
                    recency_score = max(0.40, 0.80 - ((diff - 5) * 0.05))
            except (ValueError, TypeError, KeyError):
                recency_score = 0.75

        peer_reviewed = source not in ("biorxiv", "medrxiv", "company_websites")
        peer_review_score = 1.0 if peer_reviewed else 0.70

        citation_count = int(document.get("citation_count") or metadata.get("citationCount") or 0)
        citation_score = min(1.0, 0.50 + (citation_count * 0.05))

        total_score = round(
            (source_weight * 0.35)
            + (pub_type_score * 0.25)
            + (recency_score * 0.20)
            + (peer_review_score * 0.10)
            + (citation_score * 0.10),
            4,
        )

        tier = "High" if total_score >= 0.85 else ("Medium" if total_score >= 0.70 else "Low")

        return {
            "score": total_score,
            "tier": tier,
            "breakdown": {
                "source_weight": source_weight,
                "publication_type_score": pub_type_score,
                "recency_score": recency_score,
                "peer_review_score": peer_review_score,
                "citation_score": citation_score,
            },
            "peer_reviewed": peer_reviewed,
            "citation_count": citation_count,
        }
