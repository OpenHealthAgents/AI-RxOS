"""Deterministic evidence scoring for graph relationships.

confidence = 0.5 * source_trust + 0.35 * corroboration + 0.15 * recency

- source_trust: how reliable the cited `source` is (curated biomedical DBs
  score highest; unknown/free-text sources fall back to a neutral default).
- corroboration: how many other relationships of the same type already
  connect the same node pair, saturating at CORROBORATION_SATURATION.
- recency: how recent the evidence is, based on a 4-digit year found in the
  `evidence` text, decaying linearly over RECENCY_WINDOW_YEARS. Unknown/no
  year found is treated as neutral (0.5) rather than penalized, since most
  evidence strings won't carry a parseable date.

Score is clamped to [0.0, 1.0] and rounded to 4 decimal places.
"""
import re
from datetime import datetime, timezone
from typing import Optional

SOURCE_TRUST_WEIGHTS: dict[str, float] = {
    "drugbank": 0.95,
    "clinicaltrials.gov": 0.95,
    "fda": 0.95,
    "ncbi": 0.9,
    "uniprot": 0.9,
    "pubmed": 0.85,
    "chembl": 0.85,
    "opentargets": 0.85,
}
DEFAULT_SOURCE_TRUST = 0.5

SOURCE_WEIGHT = 0.5
CORROBORATION_WEIGHT = 0.35
RECENCY_WEIGHT = 0.15

CORROBORATION_SATURATION = 5
RECENCY_WINDOW_YEARS = 10

_YEAR_RE = re.compile(r"(19|20)\d{2}")


def _source_trust(source: Optional[str]) -> float:
    if not source:
        return DEFAULT_SOURCE_TRUST
    key = source.strip().lower()
    for known, weight in SOURCE_TRUST_WEIGHTS.items():
        if known in key:
            return weight
    return DEFAULT_SOURCE_TRUST


def _corroboration_score(corroboration_count: int) -> float:
    if corroboration_count <= 0:
        return 0.0
    return min(corroboration_count / CORROBORATION_SATURATION, 1.0)


def _recency_score(evidence: Optional[str]) -> float:
    if not evidence:
        return 0.5
    match = _YEAR_RE.search(evidence)
    if not match:
        return 0.5
    year = int(match.group(0))
    current_year = datetime.now(timezone.utc).year
    age_years = max(current_year - year, 0)
    return max(1.0 - (age_years / RECENCY_WINDOW_YEARS), 0.0)


def compute_confidence(
    source: Optional[str],
    evidence: Optional[str],
    corroboration_count: int = 0,
) -> float:
    score = (
        SOURCE_WEIGHT * _source_trust(source)
        + CORROBORATION_WEIGHT * _corroboration_score(corroboration_count)
        + RECENCY_WEIGHT * _recency_score(evidence)
    )
    return round(min(max(score, 0.0), 1.0), 4)
