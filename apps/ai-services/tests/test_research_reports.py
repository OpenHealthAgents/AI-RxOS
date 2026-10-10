from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.opportunity_engine.request_context import _trusted_tenant_id
from app.opportunity_engine.research_reports import (
    REPORT_SECTIONS,
    get_research_llm,
)
import app.opportunity_engine.research_reports as research_reports

client = TestClient(app)

TOPIC_QUESTIONS = [
    "Summarize this therapeutic asset.",
    "What biology and mechanism evidence is available?",
    "What is known about clinical development?",
    "What patients and biomarkers are supported?",
    "What CNS evidence is available?",
    "What resistance evidence is available?",
    "What combination evidence is available?",
    "What competition evidence is available?",
    "What is known about asset ownership?",
    "What licensing evidence is available?",
    "What commercial opportunity evidence is available?",
    "What recommendation did the existing decision engine return?",
]


class StubResearchLLM:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response
        self.context: dict[str, Any] | None = None

    async def complete(
        self, question: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        self.context = context
        if self.response is not None:
            return self.response
        if not context["evidence"]:
            return {
                "summary": "The available context does not establish an answer.",
                "summary_classification": "UNKNOWN",
                "summary_evidence_ids": [],
                "claims": [
                    {
                        "classification": "UNKNOWN",
                        "statement": "No supporting internal evidence was retrieved.",
                        "evidence_ids": [],
                    }
                ],
                "unknowns": ["No supporting internal evidence was retrieved."],
                "contradictory_evidence_ids": [],
            }
        evidence_id = context["evidence"][0]["evidence_id"]
        return {
            "summary": "Source evidence is available for this question.",
            "summary_classification": "FACT",
            "summary_evidence_ids": [evidence_id],
            "claims": [
                {
                    "classification": "FACT",
                    "statement": f"Evidence was retrieved for: {question}",
                    "evidence_ids": [evidence_id],
                },
                {
                    "classification": "UNKNOWN",
                    "statement": "The retrieved context does not establish all requested details.",
                    "evidence_ids": [],
                },
            ],
            "unknowns": ["Some details are not established by retrieved evidence."],
            "contradictory_evidence_ids": [],
        }


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    previous = app.dependency_overrides.copy()
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


@pytest.mark.parametrize("question", TOPIC_QUESTIONS)
def test_research_questions_use_retrieved_evidence_and_typed_claims(
    question: str,
) -> None:
    model = StubResearchLLM()
    app.dependency_overrides[get_research_llm] = lambda: model

    response = client.post(
        "/api/research/copilot",
        json={"asset_id": "zongertinib", "question": question},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["question"] == question
    assert payload["summary_classification"] == "FACT"
    assert payload["claims"][0]["classification"] == "FACT"
    assert payload["claims"][1]["classification"] == "UNKNOWN"
    assert payload["citations"]
    assert payload["claims"][0]["evidence_ids"][0] == payload["citations"][0]["evidence_id"]
    assert model.context is not None
    assert model.context["asset"]["id"] == "zongertinib"


def test_copilot_rejects_unknown_citation_ids_and_uncited_claims() -> None:
    unknown_reference = StubResearchLLM(
        {
            "summary": "Unverified claim.",
            "summary_classification": "FACT",
            "summary_evidence_ids": ["fabricated-source"],
            "claims": [
                {
                    "classification": "FACT",
                    "statement": "Unverified claim.",
                    "evidence_ids": ["fabricated-source"],
                }
            ],
            "unknowns": [],
            "contradictory_evidence_ids": [],
        }
    )
    app.dependency_overrides[get_research_llm] = lambda: unknown_reference
    response = client.post(
        "/api/research/copilot",
        json={"asset_id": "zongertinib", "question": "What is known?"},
    )
    assert response.status_code == 502
    assert "not retrieved" in response.json()["detail"]

    uncited = StubResearchLLM(
        {
            "summary": "Some source-backed answer.",
            "summary_classification": "UNKNOWN",
            "summary_evidence_ids": [],
            "claims": [
                {
                    "classification": "INFERENCE",
                    "statement": "An uncited inference.",
                    "evidence_ids": [],
                }
            ],
            "unknowns": [],
            "contradictory_evidence_ids": [],
        }
    )
    app.dependency_overrides[get_research_llm] = lambda: uncited
    response = client.post(
        "/api/research/copilot",
        json={"asset_id": "zongertinib", "question": "What is known?"},
    )
    assert response.status_code == 502
    assert "uncited substantive claim" in response.json()["detail"]


def test_copilot_rejects_malformed_and_unsupported_provider_output() -> None:
    malformed = StubResearchLLM({"summary": "Missing required typed fields."})
    app.dependency_overrides[get_research_llm] = lambda: malformed
    response = client.post(
        "/api/research/copilot",
        json={"asset_id": "zongertinib", "question": "What is known?"},
    )
    assert response.status_code == 502
    assert "answer schema" in response.json()["detail"]

    unsupported = StubResearchLLM(
        {
            "summary": "Unknown.",
            "summary_classification": "SPECULATION",
            "summary_evidence_ids": [],
            "claims": [
                {
                    "classification": "UNKNOWN",
                    "statement": "Unknown.",
                    "evidence_ids": [],
                }
            ],
        }
    )
    app.dependency_overrides[get_research_llm] = lambda: unsupported
    response = client.post(
        "/api/research/copilot",
        json={"asset_id": "zongertinib", "question": "What is known?"},
    )
    assert response.status_code == 502


def test_copilot_returns_explicit_unknown_when_no_evidence_is_retrieved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = StubResearchLLM()
    app.dependency_overrides[get_research_llm] = lambda: model
    monkeypatch.setattr(research_reports, "_citations_for_asset", lambda *_: [])

    response = client.post(
        "/api/research/copilot",
        json={"asset_id": "zongertinib", "question": "What is not established?"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["summary_classification"] == "UNKNOWN"
    assert response.json()["citations"] == []
    assert response.json()["claims"][0]["classification"] == "UNKNOWN"


def test_copilot_contradictions_must_resolve_to_contradictory_internal_objects() -> None:
    report = client.get("/api/assets/zongertinib/report")
    assert report.status_code == 200, report.text
    contradictory_ids = report.json()["sections"][17]["contradictory_evidence_ids"]
    assert contradictory_ids
    model = StubResearchLLM(
        {
            "summary": "The source context contains a contradiction.",
            "summary_classification": "FACT",
            "summary_evidence_ids": [contradictory_ids[0]],
            "claims": [
                {
                    "classification": "FACT",
                    "statement": "The source context contains a contradiction.",
                    "evidence_ids": [contradictory_ids[0]],
                }
            ],
            "unknowns": [],
            "contradictory_evidence_ids": [contradictory_ids[0]],
        }
    )
    app.dependency_overrides[get_research_llm] = lambda: model

    response = client.post(
        "/api/research/copilot",
        json={"asset_id": "zongertinib", "question": "Are there contradictions?"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["contradictions"][0]["evidence_id"] == contradictory_ids[0]


def test_provider_unavailable_fails_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        research_reports,
        "get_settings",
        lambda: Settings(
            research_llm_base_url=None,
            research_llm_model=None,
            research_llm_api_key=None,
        ),
    )
    response = client.post(
        "/api/research/copilot",
        json={"asset_id": "zongertinib", "question": "What is known?"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Research Copilot provider is not configured."


def test_model_catalog_does_not_report_an_unconfigured_llm_as_active() -> None:
    response = client.get("/api/v1/models")
    assert response.status_code == 200
    assert response.json()["models"] == [
        {
            "id": "default-llm",
            "provider": "openai-compatible",
            "status": "unavailable",
        }
    ]


def test_report_has_all_sections_preserves_citations_and_marks_missing_data() -> None:
    response = client.get("/api/assets/zongertinib/report?cutoff=2024-01-01")

    assert response.status_code == 200, response.text
    report = response.json()
    assert [(section["section_id"], section["title"]) for section in report["sections"]] == list(
        REPORT_SECTIONS
    )
    known_ids = {citation["evidence_id"] for citation in report["citations"]}
    assert known_ids
    for section in report["sections"]:
        assert set(section["evidence_ids"]) <= known_ids
        assert set(section["contradictory_evidence_ids"]) <= known_ids

    by_id = {section["section_id"]: section for section in report["sections"]}
    assert by_id["preclinical"]["status"] == "UNKNOWN"
    assert by_id["preclinical"]["source_data"] is None
    assert by_id["regulatory"]["status"] == "UNKNOWN"
    assert by_id["regulatory"]["source_data"] is None
    assert by_id["why"]["source_data"]["decision"] == by_id["recommendation"]["source_data"]["decision"]["decision"]
    assert by_id["unknowns"]["source_data"]
    assert by_id["next_actions"]["status"] in {"AVAILABLE", "UNKNOWN"}


def test_copilot_and_report_resolve_to_same_internal_evidence_objects() -> None:
    model = StubResearchLLM()
    app.dependency_overrides[get_research_llm] = lambda: model
    answer = client.post(
        "/api/research/copilot",
        json={"asset_id": "zongertinib", "question": "What is known?"},
    )
    report = client.get("/api/assets/zongertinib/report")

    assert answer.status_code == 200, answer.text
    assert report.status_code == 200, report.text
    report_ids = {item["evidence_id"] for item in report.json()["citations"]}
    copilot_ids = {item["evidence_id"] for item in answer.json()["citations"]}
    assert copilot_ids
    assert copilot_ids <= report_ids


def test_copilot_and_report_use_trusted_tenant_context() -> None:
    model = StubResearchLLM()
    app.dependency_overrides[get_research_llm] = lambda: model
    app.dependency_overrides[_trusted_tenant_id] = lambda: "trusted-tenant"

    response = client.post(
        "/api/research/copilot?tenant_id=attacker-tenant",
        json={"asset_id": "zongertinib", "question": "What is known?"},
    )
    report = client.get(
        "/api/assets/zongertinib/report?tenant_id=attacker-tenant"
    )

    assert response.status_code == 200, response.text
    assert report.status_code == 200, report.text
    assert "trusted-tenant" not in json_context(model.context)
    assert "attacker-tenant" not in json_context(model.context)
    assert report.json()["tenant_id"] == "trusted-tenant"
    assert "attacker-tenant" not in json_context(report.json())


def json_context(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True)
