from __future__ import annotations

import re
from typing import ClassVar


class EntityExtractor:
    """Rule-based biomedical entity extractor for genes, variants, diseases, and drugs."""

    _gene_pattern: ClassVar[re.Pattern[str]] = re.compile(r"\b([A-Z0-9]{2,7})\b")
    _variant_pattern: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(p\.[A-Za-z]\d+[A-Za-z]|c\.\d+[A-Za-z]?)\b"
    )
    _disease_keywords: ClassVar[set[str]] = {
        "cancer",
        "diabetes",
        "alzheimer",
        "covid",
        "covid-19",
    }
    _drug_keywords: ClassVar[set[str]] = {
        "aspirin",
        "ibuprofen",
        "paracetamol",
        "tamoxifen",
    }

    def _to_int(self, value: object) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        raise TypeError("entity index must be an integer")

    def _to_float(self, value: object) -> float:
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

    def extract(self, text: str) -> list[dict[str, object]]:
        if not text or not isinstance(text, str):
            return []

        entities: list[dict[str, object]] = []
        lower_text = text.lower()

        for match in self._gene_pattern.finditer(text):
            token = match.group(1)
            if token.isupper():
                entities.append(
                    {
                        "text": token,
                        "start": match.start(1),
                        "end": match.end(1),
                        "type": "gene",
                        "confidence": 0.72,
                    }
                )

        for match in self._variant_pattern.finditer(text):
            entities.append(
                {
                    "text": match.group(1),
                    "start": match.start(1),
                    "end": match.end(1),
                    "type": "variant",
                    "confidence": 0.93,
                }
            )

        for keyword in self._disease_keywords:
            index = lower_text.find(keyword)
            if index >= 0:
                entities.append(
                    {
                        "text": text[index : index + len(keyword)],
                        "start": index,
                        "end": index + len(keyword),
                        "type": "disease",
                        "confidence": 0.84,
                    }
                )

        for keyword in self._drug_keywords:
            index = lower_text.find(keyword)
            if index >= 0:
                entities.append(
                    {
                        "text": text[index : index + len(keyword)],
                        "start": index,
                        "end": index + len(keyword),
                        "type": "drug",
                        "confidence": 0.84,
                    }
                )

        entities = sorted(
            entities,
            key=lambda item: (
                self._to_int(item["start"]),
                -self._to_float(item["confidence"]),
            ),
        )
        filtered: list[dict[str, object]] = []
        occupied: set[int] = set()
        for entity in entities:
            start = self._to_int(entity["start"])
            end = self._to_int(entity["end"])
            if any(index in occupied for index in range(start, end)):
                continue
            for index in range(start, end):
                occupied.add(index)
            filtered.append(entity)
        return filtered
