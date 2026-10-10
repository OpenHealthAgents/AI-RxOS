"""Confirms the label/type filter query params on the read paths are
rejected before they ever reach the f-string-built Cypher label/type
clauses in app/cypher/queries.py. Structural Cypher fragments (labels,
relationship types) can't be parameterized, so these query params must be
checked against an allowlist in the router layer."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_nodes_rejects_unknown_label():
    with patch("app.services.graph_service.GraphService.list_nodes") as mock_list:
        res = client.get("/api/v1/graph/nodes?label=Gene)%20DETACH%20DELETE%20n%20//")
        assert res.status_code == 400
        mock_list.assert_not_called()


def test_list_nodes_accepts_known_label():
    with patch("app.services.graph_service.GraphService.list_nodes") as mock_list:
        mock_list.return_value = ([], 0)
        res = client.get("/api/v1/graph/nodes?label=Gene")
        assert res.status_code == 200
        mock_list.assert_called_once()


def test_list_nodes_accepts_biomarker_label():
    with patch("app.services.graph_service.GraphService.list_nodes") as mock_list:
        mock_list.return_value = ([], 0)
        res = client.get("/api/v1/graph/nodes?label=Biomarker")
        assert res.status_code == 200
        mock_list.assert_called_once()


def test_list_relationships_rejects_unknown_type():
    with patch("app.services.graph_service.GraphService.list_relationships") as mock_list:
        res = client.get("/api/v1/graph/relationships?type=TARGETS%7D%5D-%5B*%5D-%28%29%20//")
        assert res.status_code == 400
        mock_list.assert_not_called()


def test_list_relationships_accepts_known_type():
    with patch("app.services.graph_service.GraphService.list_relationships") as mock_list:
        mock_list.return_value = ([], 0)
        res = client.get("/api/v1/graph/relationships?type=TARGETS")
        assert res.status_code == 200
        mock_list.assert_called_once()


def test_list_relationships_accepts_validated_by_and_generate_types():
    with patch("app.services.graph_service.GraphService.list_relationships") as mock_list:
        mock_list.return_value = ([], 0)
        
        # Test VALIDATED_BY
        res = client.get("/api/v1/graph/relationships?type=VALIDATED_BY")
        assert res.status_code == 200
        
        # Test GENERATE
        res = client.get("/api/v1/graph/relationships?type=GENERATE")
        assert res.status_code == 200
        
        assert mock_list.call_count == 2


def test_search_rejects_unknown_label():
    with patch("app.services.graph_service.GraphService.search_nodes") as mock_search:
        res = client.get("/api/v1/graph/search?q=BRCA&label=NotARealLabel")
        assert res.status_code == 400
        mock_search.assert_not_called()


def test_search_accepts_known_label():
    with patch("app.services.graph_service.GraphService.search_nodes") as mock_search:
        mock_search.return_value = []
        res = client.get("/api/v1/graph/search?q=BRCA&label=Gene")
        assert res.status_code == 200
        mock_search.assert_called_once()


def test_search_allows_omitted_label():
    with patch("app.services.graph_service.GraphService.search_nodes") as mock_search:
        mock_search.return_value = []
        res = client.get("/api/v1/graph/search?q=BRCA")
        assert res.status_code == 200
        mock_search.assert_called_once()
