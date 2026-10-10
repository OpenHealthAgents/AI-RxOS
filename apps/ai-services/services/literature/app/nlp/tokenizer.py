from __future__ import annotations

import re


class BiomedicalTokenizer:
    """Tokenize biomedical text while preserving punctuation-heavy tokens such as variants."""

    _token_pattern = re.compile(r"[A-Za-z0-9_.\-/]+|\S")

    def tokenize(self, text: str) -> list[str]:
        if not text or not isinstance(text, str):
            return []
        tokens: list[str] = []
        for token in self._token_pattern.findall(text):
            if not token:
                continue
            if token in {".", ",", "!", "?", ":", ";", "(", ")"}:
                continue
            tokens.append(token.rstrip(".,;:!?()"))
        return [token for token in tokens if token]
