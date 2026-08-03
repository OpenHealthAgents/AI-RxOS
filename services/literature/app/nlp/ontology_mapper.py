from __future__ import annotations

from typing import ClassVar


class OntologyMapper:
    """Maps normalized entities to ontology identifiers using lightweight lookup tables."""

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

    def map_entity(self, entity: dict[str, object]) -> dict[str, object]:
        entity_type = str(entity.get("type", ""))
        text = str(entity.get("text", ""))
        identifier: str | None = None
        source: str | None = None
        if entity_type == "gene":
            identifier = self._gene_map.get(text.upper())
            source = "HGNC" if identifier else None
        elif entity_type == "disease":
            identifier = self._disease_map.get(text.lower())
            source = "MONDO" if identifier else None
        elif entity_type == "drug":
            identifier = self._drug_map.get(text.lower())
            source = "ChEBI" if identifier else None
        elif entity_type == "variant":
            identifier = text
            source = "HGVS"
        return {"normalized_identifier": identifier, "ontology_source": source}
