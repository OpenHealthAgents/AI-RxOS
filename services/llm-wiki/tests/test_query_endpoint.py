"""POST /llmwiki/query response shape must match services/search's Hit
struct exactly (services/search/internal/search/opensearch.go:161-169) --
`id`, `score`, `title`, `snippet` at minimum, since that's what
services/search's LLMWikiProvider.SimilaritySearchForTenant decodes."""


def test_query_response_matches_hit_struct_field_names(client):
    client.post(
        "/api/v1/wiki/compile",
        json={
            "document": {"source": "pubmed", "source_id": "P1", "title": "T"},
            "entities": [{"text": "aspirin", "category": "drugs"}],
            "summary": {"concise_summary": "aspirin summary"},
        },
    )
    res = client.post("/llmwiki/query", json={"embedding": [0.1, 0.2], "limit": 5})
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    hit = items[0]
    assert set(hit.keys()) >= {"id", "score", "title", "snippet"}
    assert hit["snippet"] == "aspirin summary"


def test_query_with_no_matching_tenant_returns_empty_items(client):
    client.post(
        "/api/v1/wiki/compile",
        json={
            "document": {"source": "s", "source_id": "P2", "title": "T"},
            "entities": [{"text": "ibuprofen", "category": "drugs"}],
            "summary": {"concise_summary": "s"},
            "tenant": {"organization_id": "org-a"},
        },
    )
    res = client.post(
        "/llmwiki/query", json={"embedding": [], "limit": 10, "organization_id": "org-does-not-exist"}
    )
    assert res.json() == {"items": []}
