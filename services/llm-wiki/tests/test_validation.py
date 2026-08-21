import uuid


def test_invalid_field_types_rejected(client):
    res = client.post(
        "/api/v1/wiki/compile", json={"document": {}, "entities": "not-a-list", "summary": {}}
    )
    assert res.status_code == 422


def test_missing_body_rejected(client):
    res = client.post("/api/v1/wiki/compile")
    assert res.status_code == 422


def test_entities_without_text_are_skipped_not_erroring(client):
    res = client.post(
        "/api/v1/wiki/compile",
        json={"document": {"title": "T"}, "entities": [{"category": "drugs"}], "summary": {}},
    )
    assert res.status_code == 201
    assert res.json()["pages"] == []


def test_organization_id_too_long_rejected(client):
    res = client.post(
        "/api/v1/wiki/compile",
        json={
            "document": {"title": "T"},
            "entities": [{"text": "x"}],
            "summary": {},
            "tenant": {"organization_id": "a" * 600},
        },
    )
    assert res.status_code == 422


def test_get_nonexistent_page_returns_404(client):
    res = client.get(f"/api/v1/wiki/pages/{uuid.uuid4()}")
    assert res.status_code == 404


def test_get_page_with_malformed_id_returns_404_not_500(client):
    res = client.get("/api/v1/wiki/pages/not-a-uuid")
    assert res.status_code == 404


def test_query_limit_is_clamped_not_rejected(client):
    res = client.post("/llmwiki/query", json={"embedding": [], "limit": 10000})
    assert res.status_code == 200
    assert res.json() == {"items": []}
