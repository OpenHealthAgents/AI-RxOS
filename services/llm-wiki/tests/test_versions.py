def _payload(summary_text):
    return {
        "document": {"source": "pubmed", "source_id": "PMID1", "title": "T1"},
        "entities": [{"text": "her2", "category": "genes"}],
        "summary": {"concise_summary": summary_text},
    }


def test_version_history_and_archived_versions_are_retrievable(client):
    res1 = client.post("/api/v1/wiki/compile", json=_payload("v1 summary"))
    page_id = res1.json()["pages"][0]["id"]
    assert res1.json()["pages"][0]["version"] == 1

    res2 = client.post("/api/v1/wiki/compile", json=_payload("v2 summary"))
    assert res2.json()["pages"][0]["version"] == 2

    res3 = client.post("/api/v1/wiki/compile", json=_payload("v3 summary"))
    assert res3.json()["pages"][0]["version"] == 3

    versions = client.get(f"/api/v1/wiki/pages/{page_id}/versions").json()
    assert [v["version"] for v in versions] == [3, 2, 1]

    v1 = client.get(f"/api/v1/wiki/pages/{page_id}/versions/1").json()
    assert v1["summary"]["concise_summary"] == "v1 summary"

    v2 = client.get(f"/api/v1/wiki/pages/{page_id}/versions/2").json()
    assert v2["summary"]["concise_summary"] == "v2 summary"

    # current page state reflects only the latest version
    page = client.get(f"/api/v1/wiki/pages/{page_id}").json()
    assert page["latest_version"]["summary"]["concise_summary"] == "v3 summary"
    assert page["current_version"] == 3


def test_unknown_version_returns_404(client):
    res = client.post("/api/v1/wiki/compile", json=_payload("v1"))
    page_id = res.json()["pages"][0]["id"]
    missing = client.get(f"/api/v1/wiki/pages/{page_id}/versions/99")
    assert missing.status_code == 404
