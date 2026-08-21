"""The real end-to-end proof requested for this service:

    services/literature's actual LLMWikiClient
        -> real HTTP call to a real running llm-wiki service
            -> real Postgres (llm_wiki schema)
                -> retrieved back through llm-wiki's own read API

`wiki_client.py` is never modified or mocked -- it's imported and run
unmodified, in a **separate Python subprocess**, because both services'
top-level package is named `app`; importing both `services/literature/app`
and `services/llm-wiki/app` in one interpreter would collide in
sys.modules. A subprocess sidesteps that without touching either service's
code.

Skipped automatically when Postgres isn't reachable or services/literature
isn't checked out alongside this service.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import asyncpg
import httpx
import pytest
import uvicorn

from app.core.config import get_settings

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://ai_rxos:changeme@localhost:15432/ai_rxos"
)
LITERATURE_ROOT = Path(__file__).resolve().parents[2] / "literature"


def _postgres_available() -> bool:
    async def _check() -> bool:
        try:
            conn = await asyncpg.connect(TEST_DATABASE_URL, timeout=2)
            await conn.close()
            return True
        except Exception:
            return False

    return asyncio.run(_check())


pytestmark = [
    pytest.mark.skipif(
        not _postgres_available(),
        reason=f"Postgres not reachable at {TEST_DATABASE_URL} -- run `docker compose up -d postgres`",
    ),
    pytest.mark.skipif(
        not (LITERATURE_ROOT / "app" / "integrations" / "wiki_client.py").exists(),
        reason="services/literature not found next to services/llm-wiki",
    ),
]


@pytest.fixture()
def running_llm_wiki_server(monkeypatch):
    port = 18092
    api_key = f"e2e-key-{uuid.uuid4()}"
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("LLM_WIKI_API_KEY", api_key)
    get_settings.cache_clear()

    import importlib

    import app.main as main_module

    importlib.reload(main_module)  # re-reads settings with the env vars set above

    config = uvicorn.Config(main_module.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "llm-wiki test server did not start in time"

    yield f"http://127.0.0.1:{port}", api_key

    server.should_exit = True
    thread.join(timeout=5)
    get_settings.cache_clear()


def _run_literature_wiki_update(
    base_url: str,
    api_key: str,
    *,
    tenant: dict,
    document: dict,
    entities: list,
    summary: dict,
    relationships: list,
    evidence: list,
) -> dict:
    """Runs the real, unmodified LLMWikiClient.update_wiki() in a fresh
    subprocess against `base_url`, and returns its parsed JSON result."""
    script = f"""
import json, sys
sys.path.insert(0, {str(LITERATURE_ROOT)!r})
from app.integrations.wiki_client import LLMWikiClient

client = LLMWikiClient({{
    "wiki_service_url": {base_url!r},
    "wiki_api_key": {api_key!r},
}})
result = client.update_wiki(
    {document!r},
    {entities!r},
    {summary!r},
    relationships={relationships!r},
    evidence={evidence!r},
    tenant={tenant!r},
)
print(json.dumps(result))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, f"literature-side subprocess failed:\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_literature_client_writes_through_llm_wiki_to_postgres_and_back(running_llm_wiki_server):
    base_url, api_key = running_llm_wiki_server
    marker = f"e2e-{uuid.uuid4()}"
    document = {
        "source": "pubmed",
        "source_id": "PMID-E2E",
        "title": "E2E Title",
        "doi": "10.9/e2e",
        "url": "http://e2e.example",
    }
    entities = [{"text": "e2e-drug", "category": "drugs", "type": "drug"}]
    summary = {"concise_summary": "e2e summary"}
    relationships = [
        {
            "source_entity": "e2e-drug",
            "target_entity": "e2e-target",
            "predicate": "targets",
            "confidence": 0.5,
        }
    ]
    evidence = [{"entity": "e2e-drug", "category": "efficacy", "score": 0.6}]

    try:
        result = _run_literature_wiki_update(
            base_url,
            api_key,
            tenant={"organization_id": marker},
            document=document,
            entities=entities,
            summary=summary,
            relationships=relationships,
            evidence=evidence,
        )
        # method == "http" proves LLMWikiClient took the real remote path,
        # not the local markdown wiki-root fallback.
        assert result == {"success": True, "method": "http", "status": "completed"}

        res = httpx.get(
            f"{base_url}/api/v1/wiki/pages",
            params={"category": "drugs", "slug": "e2e-drug", "organization_id": marker},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5,
        )
        assert res.status_code == 200
        page = res.json()
        assert page["organization_id"] == marker
        assert page["latest_version"]["summary"]["concise_summary"] == "e2e summary"
        assert page["latest_version"]["provenance"]["doi"] == "10.9/e2e"
        assert page["latest_version"]["evidence"][0]["score"] == 0.6
        assert page["latest_version"]["relationships"][0]["predicate"] == "targets"
    finally:

        async def _cleanup() -> None:
            conn = await asyncpg.connect(TEST_DATABASE_URL)
            await conn.execute("DELETE FROM llm_wiki.wiki_pages WHERE organization_id = $1", marker)
            await conn.close()

        asyncio.run(_cleanup())
