"""Tests for the Prompt 8 LLM Wiki knowledge-layer additions:
chunking, canonical metadata, knowledge linking (KG <-> wiki entity ids),
tenant/workspace isolation in the wiki write path, and wiki versioning.

Uses only local fakes/mocks for the external KG/search/LLM Wiki services —
no real credentials or running services required, matching the existing
test_prompt6_comprehensive.py / test_llmwiki_integration.py conventions.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.integrations.kg_client import KGClient
from app.integrations.wiki_client import LLMWikiClient
from app.knowledge.models import (
    TenantContext,
    deterministic_entity_id,
    normalize_entity_label,
    normalize_relationship_type,
)
from app.services.chunking import build_chunks, chunk_text


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def test_chunk_text_respects_max_chars_and_preserves_content():
    text = "\n\n".join([f"Paragraph {i} " + ("word " * 40) for i in range(5)])
    chunks = chunk_text(text, max_chars=250, overlap_chars=20)

    assert len(chunks) > 1
    assert all(len(c) <= 250 for c in chunks)
    # No content is silently dropped.
    assert "Paragraph 0" in chunks[0]
    assert "Paragraph 4" in chunks[-1]


def test_chunk_text_hard_splits_a_single_oversized_paragraph():
    text = "x" * 1000
    chunks = chunk_text(text, max_chars=300, overlap_chars=50)
    assert len(chunks) >= 3
    assert all(len(c) <= 300 for c in chunks)


def test_build_chunks_attaches_canonical_metadata_and_provenance():
    document = {
        "id": "doc-42",
        "source_id": "PMID42",
        "title": "HER2 Targeted Therapy",
        "source": "pubmed",
        "doi": "10.1000/xyz",
        "url": "https://example.com/42",
    }
    tenant = TenantContext(organization_id="org-1", workspace_id="ws-1")

    chunks = build_chunks(
        document=document,
        text="Trastuzumab is a HER2-targeted therapy. " * 10,
        source_type="paper",
        entity_ids=["entity-abc"],
        entity_types=["Drug"],
        tenant=tenant,
        version=3,
        max_chars=200,
    )

    assert len(chunks) >= 1
    for i, chunk in enumerate(chunks):
        assert chunk["chunk_id"] == f"doc-42:{i}"
        assert chunk["chunk_index"] == i
        meta = chunk["metadata"]
        assert meta["document_id"] == "doc-42"
        assert meta["source_type"] == "paper"
        assert meta["source_id"] == "PMID42"
        assert meta["title"] == "HER2 Targeted Therapy"
        assert meta["entity_ids"] == ["entity-abc"]
        assert meta["entity_types"] == ["Drug"]
        assert meta["organization_id"] == "org-1"
        assert meta["workspace_id"] == "ws-1"
        assert meta["version"] == 3
        assert meta["provenance"]["source"] == "pubmed"
        assert meta["citation"]["doi"] == "10.1000/xyz"


def test_build_chunks_without_tenant_leaves_org_workspace_none():
    chunks = build_chunks(
        document={"id": "doc-1", "title": "T"},
        text="short text",
        source_type="paper",
    )
    assert chunks[0]["metadata"]["organization_id"] is None
    assert chunks[0]["metadata"]["workspace_id"] is None


# ---------------------------------------------------------------------------
# Knowledge linking (deterministic entity ids, KG label/relationship mapping)
# ---------------------------------------------------------------------------


def test_deterministic_entity_id_is_stable_and_case_insensitive():
    id1 = deterministic_entity_id("gene", "HER2")
    id2 = deterministic_entity_id("gene", "her2")
    id3 = deterministic_entity_id("gene", " HER2 ")
    assert id1 == id2 == id3

    id_different_category = deterministic_entity_id("disease", "HER2")
    assert id_different_category != id1


def test_normalize_entity_label_handles_singular_and_plural():
    assert normalize_entity_label("gene") == "Gene"
    assert normalize_entity_label("genes") == "Gene"
    assert normalize_entity_label("drugs") == "Drug"
    assert normalize_entity_label("clinical_trials") == "ClinicalTrial"
    assert normalize_entity_label("not_a_real_category") is None


def test_normalize_relationship_type_maps_known_predicates():
    assert normalize_relationship_type("treats") == "TREATS"
    assert normalize_relationship_type("targets") == "TARGETS"
    assert normalize_relationship_type("associated_with") == "INTERACTS"
    assert normalize_relationship_type("nonsense") is None


def test_kg_client_sends_correct_url_and_flat_node_relationship_shape():
    entities = [
        {"text": "trastuzumab", "type": "drug"},
        {"text": "her2", "type": "gene"},
    ]
    relationships = [
        {"source_entity": "trastuzumab", "target_entity": "her2", "predicate": "targets", "confidence": 0.9}
    ]

    with patch("httpx.Client.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        client = KGClient({"kg_service_url": "http://kg:8083"})
        result = client.update_knowledge_graph(entities, relationships)

    assert result["success"] is True
    called_url = mock_post.call_args.args[0]
    assert called_url == "http://kg:8083/api/v1/graph/import/json"

    payload = mock_post.call_args.kwargs["json"]
    assert len(payload["nodes"]) == 2
    for node in payload["nodes"]:
        assert set(node.keys()) >= {"id", "label", "name", "source", "metadata"}
        assert node["label"] in {"Drug", "Gene"}

    assert len(payload["relationships"]) == 1
    rel = payload["relationships"][0]
    assert rel["type"] == "TARGETS"
    assert rel["from_node_id"] == deterministic_entity_id("drug", "trastuzumab")
    assert rel["to_node_id"] == deterministic_entity_id("gene", "her2")


def test_kg_client_skips_unrecognized_entities_and_relationships_without_erroring():
    entities = [{"text": "some author fragment", "type": "unknown_type"}]
    relationships = [{"source_entity": "a", "target_entity": "b", "predicate": "unmapped_predicate"}]

    client = KGClient({"kg_service_url": "http://kg:8083"})
    result = client.update_knowledge_graph(entities, relationships)

    assert result == {
        "success": True,
        "updated_nodes": 0,
        "updated_edges": 0,
        "status": "no_op",
        "entity_id_map": {},
    }


def test_wiki_entity_id_matches_kg_entity_id_for_the_same_entity(tmp_path):
    """The core knowledge-linking guarantee: a wiki concept page's Entity ID
    is the same id KGClient would assign the matching KG node, so retrieved
    wiki knowledge is traceable back to the graph without a lookup."""
    wiki_client = LLMWikiClient({"wiki_dir": str(tmp_path)})
    doc = {"source": "pubmed", "source_id": "PMID1", "title": "T"}
    entities = [{"text": "her2", "category": "genes", "type": "gene"}]
    summary = {"concise_summary": "summary"}

    wiki_client.update_wiki(doc, entities, summary)

    page = (tmp_path / "wiki" / "genes" / "her2.md").read_text(encoding="utf-8")
    expected_id = deterministic_entity_id("gene", "her2")
    assert f"**Entity ID**: {expected_id}" in page


# ---------------------------------------------------------------------------
# Tenant / workspace isolation in the wiki write path
# ---------------------------------------------------------------------------


def test_wiki_pages_are_namespaced_by_organization_and_workspace(tmp_path):
    wiki_client = LLMWikiClient({"wiki_dir": str(tmp_path)})
    doc = {"source": "pubmed", "source_id": "PMID2", "title": "T"}
    entities = [{"text": "aspirin", "category": "drugs"}]
    summary = {"concise_summary": "s"}

    wiki_client.update_wiki(
        doc, entities, summary, tenant={"organization_id": "org-a", "workspace_id": "ws-1"}
    )
    wiki_client.update_wiki(
        doc, entities, summary, tenant={"organization_id": "org-b", "workspace_id": "ws-1"}
    )

    org_a_page = tmp_path / "wiki" / "org-a" / "ws-1" / "drugs" / "aspirin.md"
    org_b_page = tmp_path / "wiki" / "org-b" / "ws-1" / "drugs" / "aspirin.md"
    assert org_a_page.exists()
    assert org_b_page.exists()
    # Writing org B's page must never touch org A's directory tree.
    assert "org-a" not in org_b_page.read_text(encoding="utf-8").replace("org-a/ws-1", "")


def test_wiki_pages_without_tenant_use_pre_prompt8_untenanted_path(tmp_path):
    """Backward compatibility: no tenant means the exact same path as before
    tenant scoping was added (see test_wiki_integration_okf_volume_write in
    test_prompt6_comprehensive.py, which asserts this same untenanted path)."""
    wiki_client = LLMWikiClient({"wiki_dir": str(tmp_path)})
    doc = {"source": "pubmed", "source_id": "PMID3", "title": "T"}
    entities = [{"text": "her2", "category": "genes"}]
    summary = {"concise_summary": "s"}

    wiki_client.update_wiki(doc, entities, summary)

    assert (tmp_path / "wiki" / "genes" / "her2.md").exists()
    assert not (tmp_path / "wiki" / "_none").exists()


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------


def test_wiki_page_version_increments_and_archives_previous_content(tmp_path):
    wiki_client = LLMWikiClient({"wiki_dir": str(tmp_path)})
    doc = {"source": "pubmed", "source_id": "PMID4", "title": "First Title"}
    entities = [{"text": "her2", "category": "genes"}]

    wiki_client.update_wiki(doc, entities, {"concise_summary": "v1 summary"})
    page = tmp_path / "wiki" / "genes" / "her2.md"
    assert "- **Version**: 1" in page.read_text(encoding="utf-8")

    doc2 = {"source": "pubmed", "source_id": "PMID5", "title": "Second Title"}
    wiki_client.update_wiki(doc2, entities, {"concise_summary": "v2 summary"})
    content_v2 = page.read_text(encoding="utf-8")
    assert "- **Version**: 2" in content_v2
    assert "v2 summary" in content_v2

    archived = tmp_path / "wiki" / "genes" / "_versions" / "her2_v1.md"
    assert archived.exists()
    assert "v1 summary" in archived.read_text(encoding="utf-8")
