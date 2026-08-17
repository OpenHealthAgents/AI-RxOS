"""Create/get/metadata/evidence/provenance round trip -- the core wiki
contract mirrored from services/literature/app/integrations/wiki_client.py's
own request shape (see WikiCompileRequest in app/models.py)."""


def _payload(**overrides):
    base = {
        "document": {
            "source": "pubmed",
            "source_id": "PMID1",
            "title": "HER2 Targeted Therapy",
            "doi": "10.1000/xyz",
            "url": "https://example.com/42",
        },
        "entities": [{"text": "trastuzumab", "category": "drugs", "type": "drug"}],
        "summary": {"concise_summary": "s1"},
        "relationships": [
            {
                "source_entity": "trastuzumab",
                "target_entity": "her2",
                "predicate": "targets",
                "confidence": 0.9,
            }
        ],
        "evidence": [{"entity": "trastuzumab", "category": "efficacy", "score": 0.8}],
        "tenant": {},
        "chunks": [{"chunk_id": "doc-1:0", "chunk_index": 0, "text": "chunk text"}],
    }
    base.update(overrides)
    return base


def test_create_page_returns_id_category_slug_version(client):
    res = client.post("/api/v1/wiki/compile", json=_payload())
    assert res.status_code == 201
    body = res.json()
    assert body["success"] is True
    assert len(body["pages"]) == 1
    page_ref = body["pages"][0]
    assert page_ref["category"] == "drugs"
    assert page_ref["slug"] == "trastuzumab"
    assert page_ref["version"] == 1


def test_get_page_returns_metadata_evidence_provenance_relationships(client):
    create_res = client.post("/api/v1/wiki/compile", json=_payload())
    page_id = create_res.json()["pages"][0]["id"]

    res = client.get(f"/api/v1/wiki/pages/{page_id}")
    assert res.status_code == 200
    page = res.json()

    assert page["category"] == "drugs"
    assert page["slug"] == "trastuzumab"
    assert page["current_version"] == 1

    lv = page["latest_version"]
    assert lv["summary"]["concise_summary"] == "s1"
    assert lv["provenance"] == {
        "source": "pubmed",
        "url": "https://example.com/42",
        "doi": "10.1000/xyz",
    }
    assert lv["evidence"] == [{"entity": "trastuzumab", "category": "efficacy", "score": 0.8}]
    assert lv["relationships"][0]["predicate"] == "targets"
    assert lv["relationships"][0]["confidence"] == 0.9
    assert lv["chunks"][0]["chunk_id"] == "doc-1:0"
    assert lv["document"]["doi"] == "10.1000/xyz"


def test_update_page_overwrites_metadata_and_bumps_version(client):
    create_res = client.post("/api/v1/wiki/compile", json=_payload())
    page_id = create_res.json()["pages"][0]["id"]

    update_res = client.post(
        "/api/v1/wiki/compile", json=_payload(summary={"concise_summary": "s2 updated"})
    )
    assert update_res.json()["pages"][0]["id"] == page_id
    assert update_res.json()["pages"][0]["version"] == 2

    page = client.get(f"/api/v1/wiki/pages/{page_id}").json()
    assert page["current_version"] == 2
    assert page["latest_version"]["summary"]["concise_summary"] == "s2 updated"


def test_relationships_and_evidence_are_filtered_per_entity(client):
    payload = _payload(
        entities=[
            {"text": "trastuzumab", "category": "drugs"},
            {"text": "her2", "category": "genes"},
        ],
        relationships=[
            {
                "source_entity": "trastuzumab",
                "target_entity": "her2",
                "predicate": "targets",
                "confidence": 0.9,
            }
        ],
        evidence=[{"entity": "trastuzumab", "category": "efficacy", "score": 0.8}],
    )
    res = client.post("/api/v1/wiki/compile", json=payload)
    pages_by_slug = {p["slug"]: p["id"] for p in res.json()["pages"]}

    trastuzumab_page = client.get(f"/api/v1/wiki/pages/{pages_by_slug['trastuzumab']}").json()
    her2_page = client.get(f"/api/v1/wiki/pages/{pages_by_slug['her2']}").json()

    # Both entities are relationship endpoints, so both pages see it...
    assert len(trastuzumab_page["latest_version"]["relationships"]) == 1
    assert len(her2_page["latest_version"]["relationships"]) == 1
    # ...but evidence was only recorded against trastuzumab.
    assert len(trastuzumab_page["latest_version"]["evidence"]) == 1
    assert len(her2_page["latest_version"]["evidence"]) == 0
