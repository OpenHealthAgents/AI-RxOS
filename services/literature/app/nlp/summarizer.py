from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from app.observability.metrics import (
    SUMMARIZER_DURATION_SECONDS,
    SUMMARIZER_ERRORS_TOTAL,
    SUMMARIZER_TOTAL,
)

logger = logging.getLogger(__name__)

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


class DocumentSummarizer:
    """LLM-based document summarization with extractive fallback."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.api_key = self.config.get("llm_api_key")
        self.api_url = self.config.get("llm_api_url", "http://localhost:8000/v1/chat/completions")
        self.max_retries = int(self.config.get("llm_max_retries", 2))
        self.backoff_seconds = float(self.config.get("llm_backoff_seconds", 0.5))
        self.timeout = float(self.config.get("llm_timeout", 5.0))
        self.model = self.config.get("llm_model", "gpt-3.5-turbo")

    def summarize(self, doc: dict[str, Any]) -> dict[str, Any]:
        abstract = doc.get("abstract") or doc.get("content") or ""
        title = doc.get("title") or ""

        if self.api_key:
            for attempt in range(self.max_retries + 1):
                try:
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    }
                    payload = {
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a helpful biomedical assistant. Summarize the following document concisely.",
                            },
                            {
                                "role": "user",
                                "content": f"Title: {title}\nAbstract: {abstract}",
                            },
                        ],
                    }
                    resp = httpx.post(self.api_url, json=payload, headers=headers, timeout=self.timeout)
                    resp.raise_for_status()
                    data = resp.json()
                    summary_text = data["choices"][0]["message"]["content"]
                    return {
                        "summary_type": "llm_generated",
                        "concise_summary": summary_text,
                        "llm_used": True,
                    }
                except Exception as exc:
                    if attempt >= self.max_retries:
                        logger.warning("LLM summarization failed after retries: %s", exc)
                        break
                    time.sleep(self.backoff_seconds * (2**attempt))

        # Extractive fallback
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", abstract) if s.strip()]
        concise = ""
        if title:
            concise += title + ". "
        if sentences:
            concise += " ".join(sentences[:2])
        else:
            concise += abstract[:300]

        return {
            "summary_type": "extractive_fallback",
            "concise_summary": concise.strip(),
            "llm_used": False,
        }
