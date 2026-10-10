from __future__ import annotations

from typing import Any, ClassVar


class RelationshipExtractor:
    """Dedicated relationship extraction stage for literature documents."""

    PREDICATE_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"(?P<subj>[\w\s-]+)\s+(?:targets|inhibits|blocks|binds to)\s+(?P<obj>[\w\s-]+)", "targets"),
        (r"(?P<subj>[\w\s-]+)\s+(?:treats|is indicated for|improves outcomes in)\s+(?P<obj>[\w\s-]+)", "treats"),
        (r"(?P<subj>[\w\s-]+)\s+(?:is associated with|correlates with|predicts response to)\s+(?P<obj>[\w\s-]+)", "associated_with"),
        (r"(?P<subj>[\w\s-]+)\s+(?:evaluates|investigates|assesses)\s+(?P<obj>[\w\s-]+)", "evaluates"),
        (r"(?P<subj>[\w\s-]+)\s+(?:reports|demonstrates|shows)\s+(?P<obj>[\w\s-]+)", "reports"),
    ]

    def extract(self, document: dict[str, Any], entities: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        abstract = document.get("abstract") or ""
        content = document.get("content") or abstract
        title = document.get("title") or ""
        combined_text = f"{title}. {abstract} {content}".lower()

        relationships: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        drugs = [e["text"] for e in (entities or []) if e.get("label") == "drug"]
        diseases = [e["text"] for e in (entities or []) if e.get("label") == "disease"]
        genes = [e["text"] for e in (entities or []) if e.get("label") == "gene" or e.get("label") == "protein"]
        biomarkers = [e["text"] for e in (entities or []) if e.get("label") == "biomarker"]
        trials = [e["text"] for e in (entities or []) if e.get("label") == "clinical_trial"]

        for drug in drugs:
            for gene in genes:
                if drug in combined_text and gene in combined_text:
                    key = (drug, "targets", gene)
                    if key not in seen:
                        seen.add(key)
                        relationships.append(
                            {
                                "subject": drug,
                                "predicate": "targets",
                                "object": gene,
                                "subject_label": "drug",
                                "object_label": "gene_protein",
                                "confidence": 0.85,
                                "evidence": f"Co-occurrence in literature text for {drug} and {gene}.",
                            }
                        )

            for disease in diseases:
                if drug in combined_text and disease in combined_text:
                    key = (drug, "treats", disease)
                    if key not in seen:
                        seen.add(key)
                        relationships.append(
                            {
                                "subject": drug,
                                "predicate": "treats",
                                "object": disease,
                                "subject_label": "drug",
                                "object_label": "disease",
                                "confidence": 0.85,
                                "evidence": f"Co-occurrence in document text for {drug} and {disease}.",
                            }
                        )

            for biomarker in biomarkers:
                if drug in combined_text and biomarker in combined_text:
                    key = (drug, "associated_with", biomarker)
                    if key not in seen:
                        seen.add(key)
                        relationships.append(
                            {
                                "subject": drug,
                                "predicate": "associated_with",
                                "object": biomarker,
                                "subject_label": "drug",
                                "object_label": "biomarker",
                                "confidence": 0.80,
                                "evidence": f"Association reported between {drug} and {biomarker}.",
                            }
                        )

        for trial in trials:
            for drug in drugs:
                if trial.lower() in combined_text and drug in combined_text:
                    key = (trial, "evaluates", drug)
                    if key not in seen:
                        seen.add(key)
                        relationships.append(
                            {
                                "subject": trial,
                                "predicate": "evaluates",
                                "object": drug,
                                "subject_label": "clinical_trial",
                                "object_label": "drug",
                                "confidence": 0.90,
                                "evidence": f"Clinical trial {trial} evaluates intervention {drug}.",
                                "source_document": {
                                    "source": document.get("source"),
                                    "source_id": document.get("source_id"),
                                    "url": document.get("url"),
                                },
                            }
                        )

        source_id = document.get("source_id") or document.get("doi") or "literature_doc"
        if title:
            key = (str(source_id), "reports", title)
            if key not in seen:
                seen.add(key)
                relationships.append(
                    {
                        "subject": str(source_id),
                        "predicate": "reports",
                        "object": title,
                        "subject_label": "publication",
                        "object_label": "finding",
                        "confidence": 0.95,
                        "evidence": "Document primary title finding.",
                        "source_document": {
                            "source": document.get("source"),
                            "source_id": document.get("source_id"),
                            "url": document.get("url"),
                        },
                    }
                )

        return relationships
