from __future__ import annotations

import unicodedata
from urllib.parse import urlparse


def normalize_name(value: str) -> str:
    """Normalize for exact lookup only; this function never merges entities."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def normalize_identifier(value: str) -> str:
    """Normalize identifier whitespace/case while preserving namespace punctuation."""
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    if normalized.startswith("https://doi.org/") or normalized.startswith("http://doi.org/"):
        normalized = urlparse(normalized).path.lstrip("/")
    if normalized.startswith("doi:"):
        normalized = normalized[4:].strip()
    return normalized
