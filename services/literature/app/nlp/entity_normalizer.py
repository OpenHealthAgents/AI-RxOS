from __future__ import annotations

from typing import ClassVar


class EntityNormalizer:
    """Normalize entity text to stable biomedical identifiers when possible."""

    _gene_map: ClassVar[dict[str, str]] = {
        "TP53": "HGNC:11998",
        "EGFR": "HGNC:3236",
        "BRCA1": "HGNC:1100",
    }
    _disease_map: ClassVar[dict[str, str]] = {
        "cancer": "MONDO:0000001",
        "diabetes": "MONDO:0001",
        "alzheimer": "MONDO:0002",
        "covid": "MONDO:0100",
    }
    _drug_map: ClassVar[dict[str, str]] = {
        "aspirin": "CHEBI:15365",
        "ibuprofen": "CHEBI:5855",
        "paracetamol": "CHEBI:46195",
    }

    def normalize(self, entity: dict[str, object]) -> dict[str, object]:
        text = str(entity.get("text") or "")
        entity_type = str(entity.get("type") or "")
        confidence_value = entity.get("confidence", 0.5)
        confidence = (
            float(confidence_value)
            if isinstance(confidence_value, (int, float, str))
            else 0.5
        )
        normalized_identifier: str | None = None
        ontology_source: str | None = None

        if entity_type == "gene":
            normalized_identifier = self._gene_map.get(text.upper())
            ontology_source = "HGNC" if normalized_identifier else None
            confidence = max(confidence, 0.9)
        elif entity_type == "disease":
            normalized_identifier = self._disease_map.get(text.lower())
            ontology_source = "MONDO" if normalized_identifier else None
            confidence = max(confidence, 0.9)
        elif entity_type == "drug":
            normalized_identifier = self._drug_map.get(text.lower())
            ontology_source = "ChEBI" if normalized_identifier else None
            confidence = max(confidence, 0.9)
        elif entity_type == "variant":
            normalized_identifier = text
            ontology_source = "HGVS"
            confidence = max(confidence, 0.85)

        return {
            "text": text,
            "type": entity_type,
            "start": entity.get("start"),
            "end": entity.get("end"),
            "confidence": round(min(max(confidence, 0.0), 1.0), 2),
            "normalized_identifier": normalized_identifier,
            "ontology_source": ontology_source,
        }
