# Literature Service Integration Map

## Upstream Sources
- `pubmed`
  NCBI E-utilities search and summary APIs
- `pmc`
  NCBI E-utilities search and summary APIs
- `clinicaltrials`
  ClinicalTrials.gov API v2
- `aacr`
  AACR public search pages, with full-text access limitations
- `asco`
  ASCO publisher search pages, with access limitations
- `sabcs`
  SABCS public conference site, with access limitations
- `esmo`
  ESMO public search pages, with member-content limitations
- `biorxiv`
  bioRxiv public API
- `medrxiv`
  medRxiv public API
- `patents`
  Public search-page fetch with documented structured API limitations
- `company_websites`
  Explicitly configured public URLs only

## Downstream Integrations
- Knowledge Graph
  - Client: `app/integrations/kg_client.py`
  - Target: AI-RxOS KG service `POST /api/v1/graph/import`
  - Behavior: structured node/relationship payloads, graceful failure, retry-eligible error reporting

- LLM Wiki
  - Client: `app/integrations/wiki_client.py`
  - Primary path: HTTP `POST /api/v1/wiki/compile`
  - Fallback path: direct OKF volume writes under `wiki-root/wiki`
  - Behavior: graceful failure with metrics and retry eligibility

## Cross-Cutting Dependencies
- `httpx`
  outbound HTTP
- `FastAPI`
  API hosting
- `pydantic`
  contracts and state models

