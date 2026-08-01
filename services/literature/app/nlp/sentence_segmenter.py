from __future__ import annotations

import re


class SentenceSegmenter:
    """Simple, deterministic sentence segmentation for biomedical text."""

    _split_pattern = re.compile(r"(?<=[.!?])\s+|\n+")

    def segment(self, text: str) -> list[str]:
        if not text or not isinstance(text, str):
            return []
        return [
            segment.strip()
            for segment in self._split_pattern.split(text)
            if segment and segment.strip()
        ]
