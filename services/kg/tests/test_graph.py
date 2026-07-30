import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture
def mock_session():
    with patch("app.database.neo4j.neo4j_manager.get_session") as mock_get:
        mock_sess = AsyncMock()
        mock_get.return_value.__aenter__.return_value = mock_sess
        
        # Create an async mock context manager for session
        mock_get.return_value.__aexit__ = AsyncMock(return_value=None)
        
        yield mock_sess

def test_health_endpoints():
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "kg"}

    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "kg"}

    res = client.get("/api/v1/graph/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "kg"}

@patch("app.services.graph_service.GraphService.create_node")
def test_create_node(mock_create):
    mock_create.return_value = {
        "id": "e0e28f32-75d1-44bb-857e-07a82fe814e5",
        "label": "Gene",
        "name": "BRCA1",
        "description": "Breast cancer susceptibility gene",
        "source": "NCBI",
        "metadata": {"chromosome": "17"},
        "created_at": "2026-07-29T00:00:00",
        "updated_at": "2026-07-29T00:00:00"
    }

    payload = {
        "label": "Gene",
        "id": "e0e28f32-75d1-44bb-857e-07a82fe814e5",
        "name": "BRCA1",
        "description": "Breast cancer susceptibility gene",
        "source": "NCBI",
        "metadata": {"chromosome": "17"}
    }
    res = client.post("/api/v1/graph/nodes", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "BRCA1"
    assert data["label"] == "Gene"
    mock_create.assert_called_once()

@patch("app.services.graph_service.GraphService.get_node")
def test_get_node(mock_get):
    mock_get.return_value = {
        "id": "e0e28f32-75d1-44bb-857e-07a82fe814e5",
        "label": "Gene",
        "name": "BRCA1",
        "description": "Breast cancer susceptibility gene",
        "source": "NCBI",
        "metadata": {"chromosome": "17"},
        "created_at": "2026-07-29T00:00:00",
        "updated_at": "2026-07-29T00:00:00"
    }

    res = client.get("/api/v1/graph/nodes/e0e28f32-75d1-44bb-857e-07a82fe814e5")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "e0e28f32-75d1-44bb-857e-07a82fe814e5"
    assert data["name"] == "BRCA1"

    mock_get.return_value = None
    res = client.get("/api/v1/graph/nodes/f0000000-0000-0000-0000-000000000000")
    assert res.status_code == 404

@patch("app.services.graph_service.GraphService.update_node")
def test_update_node(mock_update):
    mock_update.return_value = {
        "id": "e0e28f32-75d1-44bb-857e-07a82fe814e5",
        "label": "Gene",
        "name": "BRCA1-Modified",
        "description": "Breast cancer susceptibility gene",
        "source": "NCBI",
        "metadata": {"chromosome": "17"},
        "created_at": "2026-07-29T00:00:00",
        "updated_at": "2026-07-29T01:00:00"
    }

    payload = {"name": "BRCA1-Modified"}
    res = client.put("/api/v1/graph/nodes/e0e28f32-75d1-44bb-857e-07a82fe814e5", json=payload)
    assert res.status_code == 200
    assert res.json()["name"] == "BRCA1-Modified"

@patch("app.services.graph_service.GraphService.delete_node")
def test_delete_node(mock_delete):
    mock_delete.return_value = True
    res = client.delete("/api/v1/graph/nodes/e0e28f32-75d1-44bb-857e-07a82fe814e5")
    assert res.status_code == 204

    mock_delete.return_value = False
    res = client.delete("/api/v1/graph/nodes/f0000000-0000-0000-0000-000000000000")
    assert res.status_code == 404

@patch("app.services.graph_service.GraphService.list_nodes")
def test_list_nodes(mock_list):
    mock_list.return_value = ([
        {
            "id": "e0e28f32-75d1-44bb-857e-07a82fe814e5",
            "label": "Gene",
            "name": "BRCA1",
            "description": "Susceptibility gene",
            "source": "NCBI",
            "metadata": {},
            "created_at": "2026-07-29T00:00:00",
            "updated_at": "2026-07-29T00:00:00"
        }
    ], 1)

    res = client.get("/api/v1/graph/nodes?label=Gene&page=1&size=20")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["name"] == "BRCA1"

@patch("app.services.graph_service.GraphService.create_relationship")
def test_create_relationship(mock_create):
    mock_create.return_value = {
        "id": "f0e28f32-75d1-44bb-857e-07a82fe814e5",
        "from_node_id": "a0e28f32-75d1-44bb-857e-07a82fe814e5",
        "to_node_id": "b0e28f32-75d1-44bb-857e-07a82fe814e5",
        "type": "TARGETS",
        "evidence": "PubMed:12345",
        "confidence": 0.85,
        "source": "DrugBank",
        "created_at": "2026-07-29T00:00:00"
    }

    payload = {
        "from_node_id": "a0e28f32-75d1-44bb-857e-07a82fe814e5",
        "to_node_id": "b0e28f32-75d1-44bb-857e-07a82fe814e5",
        "type": "TARGETS",
        "evidence": "PubMed:12345",
        "confidence": 0.85,
        "source": "DrugBank"
    }
    res = client.post("/api/v1/graph/relationships", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["type"] == "TARGETS"
    assert data["confidence"] == 0.85

@patch("app.services.graph_service.GraphService.delete_relationship")
def test_delete_relationship(mock_delete):
    mock_delete.return_value = True
    res = client.delete("/api/v1/graph/relationships/f0e28f32-75d1-44bb-857e-07a82fe814e5")
    assert res.status_code == 204

    mock_delete.return_value = False
    res = client.delete("/api/v1/graph/relationships/f0000000-0000-0000-0000-000000000000")
    assert res.status_code == 404

@patch("app.services.graph_service.GraphService.get_neighbors")
def test_get_neighbors(mock_neighbors):
    mock_neighbors.return_value = {
        "node": {
            "id": "e0e28f32-75d1-44bb-857e-07a82fe814e5",
            "label": "Gene",
            "name": "BRCA1",
            "created_at": "2026-07-29T00:00:00",
            "updated_at": "2026-07-29T00:00:00",
            "metadata": {}
        },
        "neighbors": [
            {
                "relationship": {
                    "id": "f0e28f32-75d1-44bb-857e-07a82fe814e5",
                    "from_node_id": "e0e28f32-75d1-44bb-857e-07a82fe814e5",
                    "to_node_id": "b0e28f32-75d1-44bb-857e-07a82fe814e5",
                    "type": "TARGETS",
                    "created_at": "2026-07-29T00:00:00"
                },
                "node": {
                    "id": "b0e28f32-75d1-44bb-857e-07a82fe814e5",
                    "label": "Protein",
                    "name": "BRCA1 Protein",
                    "created_at": "2026-07-29T00:00:00",
                    "updated_at": "2026-07-29T00:00:00",
                    "metadata": {}
                }
            }
        ]
    }

    res = client.get("/api/v1/graph/neighbors/e0e28f32-75d1-44bb-857e-07a82fe814e5")
    assert res.status_code == 200
    data = res.json()
    assert data["node"]["name"] == "BRCA1"
    assert len(data["neighbors"]) == 1

@patch("app.services.graph_service.GraphService.get_path")
def test_get_path(mock_path):
    mock_path.return_value = {
        "nodes": [
            {"id": "a0e28f32-75d1-44bb-857e-07a82fe814e5", "label": "Gene", "name": "A", "created_at": "2026-07-29T00:00:00", "updated_at": "2026-07-29T00:00:00"},
            {"id": "b0e28f32-75d1-44bb-857e-07a82fe814e5", "label": "Protein", "name": "B", "created_at": "2026-07-29T00:00:00", "updated_at": "2026-07-29T00:00:00"}
        ],
        "relationships": [
            {"id": "f0e28f32-75d1-44bb-857e-07a82fe814e5", "from_node_id": "a0e28f32-75d1-44bb-857e-07a82fe814e5", "to_node_id": "b0e28f32-75d1-44bb-857e-07a82fe814e5", "type": "TARGETS", "created_at": "2026-07-29T00:00:00"}
        ]
    }

    res = client.get("/api/v1/graph/path?start_node_id=a0e28f32-75d1-44bb-857e-07a82fe814e5&end_node_id=b0e28f32-75d1-44bb-857e-07a82fe814e5&max_depth=3")
    assert res.status_code == 200
    data = res.json()
    assert len(data["nodes"]) == 2

@patch("app.services.graph_service.GraphService.get_subgraph")
def test_get_subgraph(mock_subgraph):
    mock_subgraph.return_value = {
        "nodes": [{"id": "a0e28f32-75d1-44bb-857e-07a82fe814e5", "label": "Gene", "name": "A", "created_at": "2026-07-29T00:00:00", "updated_at": "2026-07-29T00:00:00"}],
        "relationships": []
    }

    res = client.get("/api/v1/graph/subgraph?node_ids=a0e28f32-75d1-44bb-857e-07a82fe814e5")
    assert res.status_code == 200
    assert len(res.json()["nodes"]) == 1

@patch("app.services.graph_service.GraphService.search_nodes")
def test_search_nodes(mock_search):
    mock_search.return_value = [
        {"id": "a0e28f32-75d1-44bb-857e-07a82fe814e5", "label": "Gene", "name": "BRCA1", "created_at": "2026-07-29T00:00:00", "updated_at": "2026-07-29T00:00:00", "metadata": {}}
    ]

    res = client.get("/api/v1/graph/search?q=BRCA&label=Gene")
    assert res.status_code == 200
    assert len(res.json()) == 1

@patch("app.services.import_service.ImportService.import_json")
def test_import_json(mock_import):
    mock_import.return_value = {
        "version_number": 2,
        "nodes_imported": 2,
        "relationships_imported": 1,
        "elapsed_seconds": 0.05,
        "status": "completed"
    }

    payload = {
        "nodes": [
            {"label": "Gene", "name": "G1", "id": "a0e28f32-75d1-44bb-857e-07a82fe814e5"},
            {"label": "Protein", "name": "P1", "id": "b0e28f32-75d1-44bb-857e-07a82fe814e5"}
        ],
        "relationships": [
            {"from_node_id": "a0e28f32-75d1-44bb-857e-07a82fe814e5", "to_node_id": "b0e28f32-75d1-44bb-857e-07a82fe814e5", "type": "TARGETS"}
        ],
        "description": "Batch test import"
    }
    res = client.post("/api/v1/graph/import/json", json=payload)
    assert res.status_code == 201
    assert res.json()["version_number"] == 2

@patch("app.services.import_service.ImportService.import_csv")
def test_import_csv(mock_import):
    mock_import.return_value = {
        "version_number": 3,
        "nodes_imported": 2,
        "relationships_imported": 1,
        "elapsed_seconds": 0.08,
        "status": "completed"
    }

    nodes_csv = "id,label,name,description,source\na0e28f32-75d1-44bb-857e-07a82fe814e5,Gene,G1,desc,NCBI"
    files = {
        "nodes_file": ("nodes.csv", nodes_csv, "text/csv")
    }
    res = client.post("/api/v1/graph/import/csv", files=files, data={"description": "CSV import"})
    assert res.status_code == 201
    assert res.json()["version_number"] == 3

@patch("app.services.version_service.VersionService.list_versions")
def test_list_versions(mock_list):
    mock_list.return_value = [
        {"id": "a0e28f32-75d1-44bb-857e-07a82fe814e5", "version_number": 1, "description": "First import", "status": "active", "created_at": "2026-07-29T00:00:00"}
    ]

    res = client.get("/api/v1/graph/versions")
    assert res.status_code == 200
    assert len(res.json()["versions"]) == 1

@patch("app.services.version_service.VersionService.rollback_to_version")
def test_rollback(mock_rollback):
    mock_rollback.return_value = 2
    res = client.post("/api/v1/graph/versions/rollback/1")
    assert res.status_code == 200
    assert res.json()["rolled_back_versions_count"] == 2
