def _compile(client, org, title):
    return client.post(
        "/api/v1/wiki/compile",
        json={
            "document": {"source": "s", "source_id": org, "title": title},
            "entities": [{"text": "shared-drug-name", "category": "drugs"}],
            "summary": {"concise_summary": title},
            "tenant": {"organization_id": org},
        },
    )


def test_tenant_a_cannot_retrieve_tenant_b_page_by_id(client):
    res_a = _compile(client, "org-a", "org-a page")
    page_id_a = res_a.json()["pages"][0]["id"]

    # org-b explicitly asking for org-a's page id must not see it.
    res_as_b = client.get(f"/api/v1/wiki/pages/{page_id_a}", params={"organization_id": "org-b"})
    assert res_as_b.status_code == 404

    # org-a can read its own page.
    res_as_a = client.get(f"/api/v1/wiki/pages/{page_id_a}", params={"organization_id": "org-a"})
    assert res_as_a.status_code == 200

    # a caller with no organization scope at all also cannot see it.
    res_no_org = client.get(f"/api/v1/wiki/pages/{page_id_a}")
    assert res_no_org.status_code == 404


def test_same_category_slug_creates_separate_pages_per_tenant(client):
    res_a = _compile(client, "org-a", "org-a page")
    res_b = _compile(client, "org-b", "org-b page")
    id_a = res_a.json()["pages"][0]["id"]
    id_b = res_b.json()["pages"][0]["id"]
    assert id_a != id_b


def test_tenant_isolation_in_query_results(client):
    id_a = _compile(client, "org-a", "org-a page").json()["pages"][0]["id"]
    id_b = _compile(client, "org-b", "org-b page").json()["pages"][0]["id"]

    res = client.post(
        "/llmwiki/query", json={"embedding": [], "limit": 10, "organization_id": "org-a"}
    )
    returned_ids = {item["id"] for item in res.json()["items"]}
    assert id_a in returned_ids
    assert id_b not in returned_ids


def test_untenanted_page_is_visible_to_every_org(client):
    global_res = client.post(
        "/api/v1/wiki/compile",
        json={
            "document": {"source": "s", "source_id": "g1", "title": "global page"},
            "entities": [{"text": "global-concept", "category": "concepts"}],
            "summary": {"concise_summary": "global"},
        },
    )
    page_id = global_res.json()["pages"][0]["id"]

    for org in (None, "org-a", "org-b"):
        params = {"organization_id": org} if org else {}
        res = client.get(f"/api/v1/wiki/pages/{page_id}", params=params)
        assert res.status_code == 200
