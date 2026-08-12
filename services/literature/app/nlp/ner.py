from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Simple rule-based patterns
GENE_PROTEIN_RE = re.compile(r"\b([A-Z0-9]{2,7})\b")
VARIANT_RE = re.compile(r"\b(p\.[A-Za-z]\d+[A-Za-z]|c\.\d+[A-Za-z]?)\b")
CLINICAL_TRIAL_RE = re.compile(r"\b(NCT\d{8})\b", re.IGNORECASE)

# Keywords mapping
DISEASE_KEYWORDS = {"cancer", "breast cancer", "diabetes", "alzheimer", "covid-19", "covid"}
DRUG_KEYWORDS = {"aspirin", "ibuprofen", "paracetamol", "tamoxifen", "trastuzumab"}
ORGANIZATION_KEYWORDS = {"aacr", "asco", "sabcs", "esmo", "fda", "ema", "nih", "who"}


def extract_entities(text: str) -> list[dict[str, Any]]:
    if not text:
        return []

    entities: list[dict[str, Any]] = []
    lower = text.lower()

    # gene/protein candidates
    for m in GENE_PROTEIN_RE.finditer(text):
        token = m.group(1)
        if token.isupper():
            entities.append(
                {
                    "text": token,
                    "start": m.start(1),
                    "end": m.end(1),
                    "type": "gene",
                    "label": "gene",
                    "category": "genes",
                    "confidence": 0.7,
                }
            )

    # variants
    for m in VARIANT_RE.finditer(text):
        token = m.group(1)
        entities.append(
            {
                "text": token,
                "start": m.start(1),
                "end": m.end(1),
                "type": "variant",
                "label": "variant",
                "category": "variants",
                "confidence": 0.9,
            }
        )

    # clinical trials
    for m in CLINICAL_TRIAL_RE.finditer(text):
        token = m.group(1)
        entities.append(
            {
                "text": token,
                "start": m.start(1),
                "end": m.end(1),
                "type": "clinical_trial",
                "label": "clinical_trial",
                "category": "clinical_trials",
                "confidence": 0.95,
            }
        )

    # diseases
    for kw in DISEASE_KEYWORDS:
        start_idx = 0
        while True:
            idx = lower.find(kw, start_idx)
            if idx == -1:
                break
            entities.append(
                {
                    "text": text[idx : idx + len(kw)],
                    "start": idx,
                    "end": idx + len(kw),
                    "type": "disease",
                    "label": "disease",
                    "category": "diseases",
                    "confidence": 0.8,
                }
            )
            start_idx = idx + 1

    # drugs
    for kw in DRUG_KEYWORDS:
        start_idx = 0
        while True:
            idx = lower.find(kw, start_idx)
            if idx == -1:
                break
            entities.append(
                {
                    "text": text[idx : idx + len(kw)],
                    "start": idx,
                    "end": idx + len(kw),
                    "type": "drug",
                    "label": "drug",
                    "category": "drugs",
                    "confidence": 0.8,
                }
            )
            start_idx = idx + 1

    # organizations
    for kw in ORGANIZATION_KEYWORDS:
        start_idx = 0
        while True:
            idx = lower.find(kw, start_idx)
            if idx == -1:
                break
            entities.append(
                {
                    "text": text[idx : idx + len(kw)],
                    "start": idx,
                    "end": idx + len(kw),
                    "type": "organization",
                    "label": "organization",
                    "category": "organizations",
                    "confidence": 0.85,
                }
            )
            start_idx = idx + 1

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


class RuleBasedEntityExtractor:
    """Rule-based clinical and molecular entity extractor."""

    def extract_entities(self, text: str) -> list[dict[str, Any]]:
        return extract_entities(text)


class SpaCyEntityExtractor:
    """SpaCy-based entity extractor with rule-based fallback behavior."""

    def __init__(self, model_name: str = "en_core_web_sm"):
        self.available = False
        self.nlp = None
        try:
            import spacy
            self.nlp = spacy.load(model_name)
            self.available = True
        except Exception as exc:
            logger.info("SpaCy model '%s' not available, falling back: %s", model_name, exc)
            self.available = False

    def extract_entities(self, text: str) -> list[dict[str, Any]]:
        if not self.available or not self.nlp:
            return []

        doc = self.nlp(text)
        entities = []
        for ent in doc.ents:
            label_lower = ent.label_.lower()
            if ent.label_ in ("ORG", "LAW"):
                label = "organization"
                category = "organizations"
            elif ent.label_ in ("GPE", "LOC"):
                label = "location"
                category = "locations"
            elif ent.label_ in ("DATE", "TIME"):
                label = "date"
                category = "dates"
            else:
                label = label_lower
                category = label_lower + "s"

            entities.append(
                {
                    "text": ent.text,
                    "start": ent.start_char,
                    "end": ent.end_char,
                    "type": label,
                    "label": label,
                    "category": category,
                    "confidence": 0.8,
                }
            )
        return entities
