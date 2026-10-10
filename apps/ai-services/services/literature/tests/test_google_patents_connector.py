from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import httpx

from app.connectors.google_patents import GooglePatentsConnector


def _result(source_id: str, title: str) -> dict:
    return {
        "id": f"patent/{source_id}/en",
        "rank": 0,
        "patent": {
            "title": title,
            "snippet": "Search result excerpt.",
            "filing_date": "2018-06",
            "publication_date": "2019",
            "grant_date": None,
            "publication_number": source_id,
            "inventor": "Inventor A",
            "assignee": "Assignee A",
            "language": "en",
            "family_metadata": {"family_id": "FAM-123"},
        },
    }


def _page(page: int, results: list[dict], total_pages: int = 2) -> str:
    return json.dumps({
        "results": {
            "total_num_results": 2,
            "total_num_pages": total_pages,
            "num_page": page,
            "cluster": [{"result": results}],
        },
    })


def _page_from_request(url: str) -> int:
    inner_url = parse_qs(urlsplit(url).query)["url"][0]
    return int(inner_url.split("page=", 1)[1].split("&", 1)[0])


def test_google_patents_json_adapter_preserves_precision_and_paginates(monkeypatch):
    responses = {
        0: _page(0, [_result("US20240123456A1", "One patent")]),
        1: _page(1, [_result("US20240123457A1", "Two patent")]),
    }
    requested = []

    def fake_get(self, url):
        requested.append(url)
        return responses[_page_from_request(url)]

    monkeypatch.setattr(GooglePatentsConnector, "_get", fake_get)
    connector = GooglePatentsConnector({"requests_per_second": 10000})

    first, next_token = connector.fetch_page("HER2 antibody", page_size=1)
    second, final_token = connector.fetch_page(
        "HER2 antibody", page_token=next_token, page_size=1
    )

    assert first[0]["source_id"] == "US20240123456A1"
    assert first[0]["metadata"]["jurisdiction"] == "US"
    assert first[0]["metadata"]["filing_date_source"] == "2018-06"
    assert first[0]["metadata"]["publication_date_source"] == "2019"
    assert first[0]["metadata"]["family_identifier"] == "FAM-123"
    assert first[0]["abstract"] is None
    assert first[0]["metadata"]["search_snippet_is_excerpt"] is True
    assert first[0]["metadata"]["assignees"] == ["Assignee A"]
    assert first[0]["metadata"]["applicants"] == []
    assert second[0]["authors"] == ["Inventor A"]
    assert len(first[0]["content_hash"]) == 64
    assert next_token == "1"
    assert final_token is None
    assert len(requested) == 2


def test_google_patents_identifier_query_uses_the_same_search_contract(monkeypatch):
    requested = []

    def fake_get(self, url):
        requested.append(url)
        return _page(0, [_result("US20240123456A1", "Direct patent")], total_pages=1)

    monkeypatch.setattr(GooglePatentsConnector, "_get", fake_get)
    connector = GooglePatentsConnector({"requests_per_second": 10000})
    records, token = connector.fetch_page("US20240123456A1")

    assert [record["source_id"] for record in records] == ["US20240123456A1"]
    assert token is None
    assert _page_from_request(requested[0]) == 0


def test_google_patents_malformed_result_is_dead_letter_data(monkeypatch):
    monkeypatch.setattr(
        GooglePatentsConnector,
        "_get",
        lambda _self, _url: _page(0, [{"id": "patent/not-a-number/en", "patent": {}}], 1),
    )
    connector = GooglePatentsConnector({"requests_per_second": 10000})

    records, token = connector.fetch_page("oncology")

    assert records == []
    assert token is None
    assert connector.last_malformed_records[0]["error_message"] == (
        "Google Patents result has no valid publication number"
    )


def test_google_patents_invalid_page_checkpoint_is_rejected():
    connector = GooglePatentsConnector()
    try:
        connector.fetch_page("oncology", page_token="not-a-checkpoint")
    except ValueError as exc:
        assert "checkpoint" in str(exc)
    else:
        raise AssertionError("invalid persisted checkpoint was accepted")


def test_google_patents_retries_rate_limit_with_a_bounded_attempt_count(monkeypatch):
    responses = [
        httpx.Response(429, request=httpx.Request("GET", "https://patents.google.com/")),
        httpx.Response(200, text="ok", request=httpx.Request("GET", "https://patents.google.com/")),
    ]
    calls = []

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url, **_kwargs):
            calls.append(url)
            return responses.pop(0)

    monkeypatch.setattr("app.connectors.google_patents.httpx.Client", FakeClient)
    monkeypatch.setattr("app.connectors.google_patents.time.sleep", lambda _delay: None)
    connector = GooglePatentsConnector({
        "max_retries": 1,
        "backoff_seconds": 0,
        "requests_per_second": 10000,
    })
    monkeypatch.setattr(connector, "_pace", lambda: None)

    assert connector._get("https://patents.google.com/") == "ok"
    assert len(calls) == 2
