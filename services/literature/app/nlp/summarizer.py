from __future__ import annotations

import re
import time
from typing import Any

from app.observability.metrics import (
    SUMMARIZER_DURATION_SECONDS,
    SUMMARIZER_ERRORS_TOTAL,
    SUMMARIZER_TOTAL,
)

SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")
SUMMARY_KEYWORDS = [
    "treat",
    "efficacy",
    "risk",
    "associated",
    "linked",
    "improved",
    "reduced",
    "benefit",
    "adverse",
    "clinical",
    "patient",
    "therapy",
    "prognosis",
    "outcome",
    "mortality",
]
LIMITATION_KEYWORDS = [
    "limit",
    "limitation",
    "future",
    "small sample",
    "further research",
    "bias",
]


class SummarizerService:
    """Generate a lightweight structured summary for a literature document."""

    def summarize(self, document: dict[str, Any]) -> dict[str, Any]:
        start_time = time.perf_counter()
        try:
            if not isinstance(document, dict):
                raise TypeError("document must be a dictionary")

            document_id = document.get("document_id") or document.get("id") or "unknown"
            title = self._first_nonempty_string(document.get("title"))
            abstract = self._first_nonempty_string(document.get("abstract"))
            sections = self._normalize_sections(document.get("sections"))

            source_text = self._assemble_source_text(abstract, sections)
            sentences = self._split_sentences(source_text)

            abstract_summary = self._build_abstract_summary(abstract, sentences)
            key_findings = self._build_key_findings(sentences)
            clinical_relevance = self._build_clinical_relevance(sentences)
            limitations = self._build_limitations(abstract, sections, sentences)

            structured_summary = {
                "abstract_summary": abstract_summary,
                "key_findings": key_findings,
                "clinical_relevance": clinical_relevance,
                "limitations": limitations,
            }

            SUMMARIZER_TOTAL.inc()
            SUMMARIZER_DURATION_SECONDS.observe(time.perf_counter() - start_time)
            return {
                "document_id": document_id,
                "title": title,
                "abstract_summary": abstract_summary,
                "key_findings": key_findings,
                "clinical_relevance": clinical_relevance,
                "limitations": limitations,
                "structured_summary": structured_summary,
            }
        except Exception:
            SUMMARIZER_ERRORS_TOTAL.inc()
            raise

    def _first_nonempty_string(self, value: Any) -> str:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return ""

    def _normalize_sections(self, sections: Any) -> list[dict[str, str]]:
        if not isinstance(sections, list):
            return []
        normalized: list[dict[str, str]] = []
        for section in sections:
            if isinstance(section, dict):
                text = self._first_nonempty_string(section.get("text"))
                title = self._first_nonempty_string(section.get("title"))
                normalized.append({"title": title, "text": text})
        return normalized

    def _assemble_source_text(
        self, abstract: str, sections: list[dict[str, str]]
    ) -> str:
        parts: list[str] = []
        if abstract:
            parts.append(abstract)
        for section in sections:
            if section.get("title"):
                parts.append(section["title"])
            if section.get("text"):
                parts.append(section["text"])
        return "\n\n".join(parts).strip()

    def _split_sentences(self, text: str) -> list[str]:
        if not text:
            return []
        sentences = [
            sentence.strip()
            for sentence in SENTENCE_END_RE.split(text)
            if sentence.strip()
        ]
        return sentences

    def _build_abstract_summary(self, abstract: str, sentences: list[str]) -> str:
        if abstract:
            abstract_sentences = self._split_sentences(abstract)
            if abstract_sentences:
                return " ".join(abstract_sentences[:2])
        if sentences:
            return " ".join(sentences[:2])
        return "No abstract summary available."

    def _build_key_findings(self, sentences: list[str]) -> list[str]:
        findings: list[str] = []
        for sentence in sentences:
            text = sentence.lower()
            if any(
                keyword in text
                for keyword in [
                    "treat",
                    "efficacy",
                    "risk",
                    "associated",
                    "linked",
                    "improved",
                    "reduced",
                    "adverse",
                ]
            ):
                findings.append(sentence)
            if len(findings) >= 3:
                break
        if not findings and sentences:
            findings.append(sentences[0])
        return findings

    def _build_clinical_relevance(self, sentences: list[str]) -> str:
        for sentence in sentences:
            text = sentence.lower()
            if any(
                keyword in text
                for keyword in [
                    "clinical",
                    "patient",
                    "therapy",
                    "prognos",
                    "outcome",
                    "mortality",
                    "adverse",
                ]
            ):
                return sentence
        return "Clinical relevance is not explicit in the source text."

    def _build_limitations(
        self, abstract: str, sections: list[dict[str, str]], sentences: list[str]
    ) -> str:
        candidates: list[str] = []
        if abstract:
            candidates.extend(
                [
                    s
                    for s in self._split_sentences(abstract)
                    if any(keyword in s.lower() for keyword in LIMITATION_KEYWORDS)
                ]
            )
        for section in sections:
            candidates.extend(
                [
                    s
                    for s in self._split_sentences(section.get("text", ""))
                    if any(keyword in s.lower() for keyword in LIMITATION_KEYWORDS)
                ]
            )
        if candidates:
            return candidates[0]
        for sentence in sentences:
            if any(keyword in sentence.lower() for keyword in LIMITATION_KEYWORDS):
                return sentence
        return "No explicit limitations were identified."
