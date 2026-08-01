from __future__ import annotations


class ConfidenceScorer:
    """Apply a simple confidence policy to entity predictions."""

    def score(self, entity: dict[str, object]) -> float:
        confidence_value = entity.get("confidence", 0.5)
        base = (
            float(confidence_value)
            if isinstance(confidence_value, (int, float, str))
            else 0.5
        )
        entity_type = str(entity.get("type") or "")
        if entity_type == "variant":
            return round(min(1.0, base + 0.05), 2)
        if entity_type in {"gene", "disease", "drug"}:
            return round(min(1.0, base + 0.02), 2)
        return round(min(1.0, base), 2)
