from __future__ import annotations

import re
import unicodedata

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
TOKEN_RE = re.compile(r"[A-Za-z0-9_\-/\.:]+|\S")


def sentence_segment(text: str) -> list[str]:
    if not text:
        return []
    parts = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s and s.strip()]
    return parts


def tokenize_biomedical(sentence: str) -> list[str]:
    tokens = TOKEN_RE.findall(sentence)
    return tokens


def normalize_text(text: str) -> str:
    if text is None:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("\u2013", "-")
    t = t.strip()
    return t
