from __future__ import annotations

import re

# Simple rule-based patterns for demonstration purposes
GENE_PROTEIN_RE = re.compile(r"\b([A-Z0-9]{2,7})\b")
VARIANT_RE = re.compile(r"\b(p\.[A-Za-z]\d+[A-Za-z]|c\.\d+[A-Za-z]?)\b")
# small disease/drug keyword lists
DISEASE_KEYWORDS = {"cancer", "diabetes", "alzheimer", "covid-19", "covid"}
DRUG_KEYWORDS = {"aspirin", "ibuprofen", "paracetamol", "tamoxifen"}


def extract_entities(text: str) -> list[dict]:
    entities = []
    # gene/protein candidates
    for m in GENE_PROTEIN_RE.finditer(text):
        token = m.group(1)
        # heuristic: all-caps tokens likely gene/protein if length 2-7
        if token.isupper():
            entities.append(
                {
                    "text": token,
                    "start": m.start(1),
                    "end": m.end(1),
                    "type": "gene",
                    "confidence": 0.7,
                }
            )

    # variants
    for m in VARIANT_RE.finditer(text):
        entities.append(
            {
                "text": m.group(1),
                "start": m.start(1),
                "end": m.end(1),
                "type": "variant",
                "confidence": 0.9,
            }
        )

    # diseases and drugs via simple keyword matching
    lower = text.lower()
    for kw in DISEASE_KEYWORDS:
        idx = lower.find(kw)
        if idx >= 0:
            entities.append(
                {
                    "text": text[idx : idx + len(kw)],
                    "start": idx,
                    "end": idx + len(kw),
                    "type": "disease",
                    "confidence": 0.8,
                }
            )
    for kw in DRUG_KEYWORDS:
        idx = lower.find(kw)
        if idx >= 0:
            entities.append(
                {
                    "text": text[idx : idx + len(kw)],
                    "start": idx,
                    "end": idx + len(kw),
                    "type": "drug",
                    "confidence": 0.8,
                }
            )

    # deduplicate overlapping entities by choosing highest confidence
    def _int_value(value: object) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
        raise TypeError("entity index must be an integer")

    def _float_value(value: object) -> float:
        if isinstance(value, float):
            return value
        if isinstance(value, int):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
        raise TypeError("entity confidence must be numeric")

    entities_sorted = sorted(
        entities,
        key=lambda e: (_int_value(e["start"]), -_float_value(e["confidence"])),
    )
    filtered = []
    occupied = set()
    for e in entities_sorted:
        start = _int_value(e["start"])
        end = _int_value(e["end"])
        rng = range(start, end)
        if any(i in occupied for i in rng):
            continue
        for i in rng:
            occupied.add(i)
        filtered.append(e)

    return filtered
