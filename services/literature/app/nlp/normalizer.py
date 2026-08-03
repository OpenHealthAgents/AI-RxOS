from __future__ import annotations

# Static normalization maps for known biomedical entities.
GENE_MAP = {"TP53": "HGNC:11998", "EGFR": "HGNC:3236", "BRCA1": "HGNC:1100"}
DISEASE_MAP = {
    "cancer": "MONDO:0000001",
    "diabetes": "MONDO:0001",
    "alzheimer": "MONDO:0002",
    "covid": "MONDO:0100",
}
DRUG_MAP = {
    "aspirin": "CHEBI:15365",
    "ibuprofen": "CHEBI:5855",
    "paracetamol": "CHEBI:46195",
}


def normalize_entity(entity: dict) -> dict:
    text = entity.get("text", "")
    t_low = text.lower()
    etype = entity.get("type")
    normalized_id = None
    ontology = None
    score = entity.get("confidence", 0.5)

    if etype == "gene":
        normalized_id = GENE_MAP.get(text.upper())
        ontology = "HGNC" if normalized_id else None
        if normalized_id:
            score = max(score, 0.9)
    elif etype == "disease":
        normalized_id = DISEASE_MAP.get(t_low)
        ontology = "MONDO" if normalized_id else None
        if normalized_id:
            score = max(score, 0.9)
    elif etype == "drug":
        normalized_id = DRUG_MAP.get(t_low)
        ontology = "ChEBI" if normalized_id else None
        if normalized_id:
            score = max(score, 0.9)
    elif etype == "variant":
        # simple pass-through for variants
        normalized_id = text
        ontology = "HGVS"
        score = max(score, 0.85)

    return {
        "text": text,
        "type": etype,
        "start": entity.get("start"),
        "end": entity.get("end"),
        "confidence": score,
        "normalized_id": normalized_id,
        "ontology": ontology,
    }
