# Microservices Architecture - AI-RxOS

## Overview
AI-RxOS consists of 34 microservices organized into 12 bounded contexts. Services communicate via REST APIs, gRPC for high-performance inter-service calls, and event-driven messaging via Kafka. Authentication and authorization are consolidated using the Better Auth framework. Downstream microservices validate signed JWT tokens locally using JSON Web Key Sets (JWKS) to optimize performance, avoiding synchronous gRPC validation bottlenecks.

---

## Service Organization by Context

---

## 1. Identity & Access Context

### 1.1 Auth Service
**Purpose:** Authentication and authorization using the Better Auth framework

**Responsibilities:**
- User authentication via Better Auth (OAuth2, OIDC, Email/Password, Passkeys)
- Multi-provider account linking (Google, GitHub, SAML, etc.)
- Session management via Better Auth (JWT + database sessions using UUID keys)
- Role-based access control via official Better Auth admin plugin
- Organization/team management via official Better Auth organization plugin
- Permission evaluation (RBAC + ABAC)
- API key management for service accounts via official Better Auth api-key plugin
- Audit logging for all auth/authz events

**APIs:**
- REST: `/api/v1/auth/*` (Better Auth endpoints)
- REST: `/api/v1/auth/jwks` (JWKS public keys for local token validation)
- REST: `/api/v1/organizations/*` (organization management)
- REST: `/api/v1/api-keys/*` (API key management)

**Database:** PostgreSQL (Better Auth schema: user, account, session, verification, organization, member, role, user_role, api_key)

**Tech Stack:** Node.js/TypeScript (Better Auth), PostgreSQL, Redis

**Dependencies:** None (core service)

**better-auth Configuration:**
- Providers: Google, GitHub, Email/Password, Passkeys, SAML (enterprise)
- Session management: JWT + database-backed sessions (with UUID primary/foreign keys generated via `generateId: () => crypto.randomUUID()`)
- Organization support: official Better Auth organization plugin
- Role-based access: official Better Auth admin plugin (RBAC)
- Service accounts: official Better Auth api-key plugin
- Two-factor authentication: Better Auth 2FA plugin

---

## 2. Knowledge Graph Context

### 2.1 Graph Service
**Purpose:** Core graph operations and querying

**Responsibilities:**
- Graph CRUD operations
- Cypher query execution
- Graph traversal
- Graph versioning
- Graph statistics

**APIs:**
- REST: `/api/v1/graph/*`
- GraphQL: Graph queries
- gRPC: `graph.GraphService`

**Database:** Neo4j

**Tech Stack:** Go, Neo4j

**Dependencies:** Auth Service

---

### 2.2 Entity Resolution Service
**Purpose:** Entity deduplication and resolution

**Responsibilities:**
- Entity matching
- Duplicate detection
- Canonical ID assignment
- Entity merging
- Entity linking

**APIs:**
- gRPC: `entityresolution.EntityResolutionService`

**Database:** PostgreSQL (entity_mappings), Neo4j

**Tech Stack:** Python, PostgreSQL, Neo4j, ML models

**Dependencies:** Graph Service

---

### 2.3 Ontology Service
**Purpose:** Ontology management and mapping

**Responsibilities:**
- Ontology ingestion (GO, MeSH, ChEBI, etc.)
- Ontology querying
- Ontology mapping
- Term resolution
- Hierarchy traversal

**APIs:**
- REST: `/api/v1/ontologies/*`
- gRPC: `ontology.OntologyService`

**Database:** PostgreSQL (ontologies), Neo4j

**Tech Stack:** Python, PostgreSQL, Neo4j

**Dependencies:** Graph Service

---

## 3. Literature Intelligence Context

### 3.1 Ingestion Service
**Purpose:** Document ingestion from external sources

**Responsibilities:**
- PubMed ingestion
- bioRxiv/medRxiv ingestion
- Conference ingestion
- Patent ingestion
- Company website scraping
- Ingestion scheduling
- Error handling and retry

**APIs:**
- REST: `/api/v1/ingestion/*`
- gRPC: `ingestion.IngestionService`

**Database:** PostgreSQL (ingestion_jobs, documents)

**Tech Stack:** Python, PostgreSQL, Kafka

**Dependencies:** Data Integration Service

---

### 3.2 Extraction Service
**Purpose:** Entity extraction and NLP processing

**Responsibilities:**
- Named entity recognition
- Relationship extraction
- Summarization
- Duplicate detection
- Novelty scoring
- Evidence ranking

**APIs:**
- gRPC: `extraction.ExtractionService`

**Database:** PostgreSQL (extracted_entities), Kafka

**Tech Stack:** Python, PostgreSQL, Kafka, ML models (NER, LLM)

**Dependencies:** Ingestion Service

---

### 3.3 Citation Service
**Purpose:** Citation network management

**Responsibilities:**
- Citation extraction
- Citation graph building
- Citation counting
- Citation analysis
- Reference resolution

**APIs:**
- gRPC: `citation.CitationService`

**Database:** Neo4j (citation graph)

**Tech Stack:** Python, Neo4j

**Dependencies:** Ingestion Service, Graph Service

---

## 4. AI Orchestration Context

### 4.1 Agent Orchestrator Service
**Purpose:** AI agent lifecycle and coordination

**Responsibilities:**
- Agent registration
- Agent invocation
- Tool routing
- Context management
- Conversation memory
- Workflow orchestration
- MCP protocol implementation

**APIs:**
- gRPC: `agent.AgentOrchestratorService`
- WebSocket: Real-time agent communication

**Database:** PostgreSQL (agents, conversations, tool_calls)

**Tech Stack:** Python, PostgreSQL, Kafka, Temporal

**Dependencies:** Auth Service, Model Registry Service

---

### 4.2 Model Registry Service
**Purpose:** AI model versioning and management

**Responsibilities:**
- Model registration
- Model versioning
- Model deployment
- Model rollback
- A/B testing
- Model evaluation
- Model metadata

**APIs:**
- REST: `/api/v1/models/*`
- gRPC: `modelregistry.ModelRegistryService`

**Database:** PostgreSQL (models, model_versions, evaluations)

**Tech Stack:** Go, PostgreSQL, MLflow

**Dependencies:** None

---

### 4.3 Prompt Service
**Purpose:** Prompt template management

**Responsibilities:**
- Prompt template CRUD
- Prompt versioning
- Prompt variable interpolation
- Prompt testing
- Prompt analytics

**APIs:**
- REST: `/api/v1/prompts/*`
- gRPC: `prompt.PromptService`

**Database:** PostgreSQL (prompts, prompt_versions)

**Tech Stack:** Go, PostgreSQL

**Dependencies:** None

---

### 4.4 Tool Registry Service
**Purpose:** Tool registration and discovery

**Responsibilities:**
- Tool registration
- Tool metadata
- Tool discovery
- Tool invocation proxy
- Tool rate limiting

**APIs:**
- REST: `/api/v1/tools/*`
- gRPC: `toolregistry.ToolRegistryService`

**Database:** PostgreSQL (tools)

**Tech Stack:** Go, PostgreSQL

**Dependencies:** Auth Service

---

### 4.5 Inference Service
**Purpose:** AI model inference engine

**Responsibilities:**
- LLM inference
- Embedding generation
- Batch inference
- Streaming responses
- Token counting
- Cost tracking

**APIs:**
- gRPC: `inference.InferenceService`

**Database:** Redis (inference cache)

**Tech Stack:** Python, Redis, GPU cluster

**Dependencies:** Model Registry Service

---

## 5. Scientific Search Context

### 5.1 Search Service
**Purpose:** Unified search interface for keyword and LLM wiki content

**Responsibilities:**
- Keyword search
- Local hybrid search (BM25 + local vector) over the OKF wiki directory
- Query parsing and translation to qmd search requests
- Result ranking (integrating qmd scores and LLM re-ranking)
- Faceted search
- Search analytics

**APIs:**
- REST: `/api/v1/search/*`
- GraphQL: Search queries
- gRPC: `search.SearchService`

**Database:** OpenSearch, OKF Markdown Bundle (Shared Storage Volume)

**Tech Stack:** Go, OpenSearch, qmd CLI/MCP

**Dependencies:** Auth Service

---

### 5.2 OKF Compiler/Enricher Service
**Purpose:** Compiles literature and clinical data into the Open Knowledge Format (OKF) living wiki

**Responsibilities:**
- Ingested literature parsing and extraction
- Compiling OKF concept markdown pages with YAML frontmatter
- Managing and updating index.md and chronological log.md files
- Resolving cross-links between concept pages (using relative Markdown links)
- Auditing the wiki directory for schema consistency and contradictions (linting)
- Bulk conversion of historical data to OKF v0.1 format

**APIs:**
- gRPC: `okf.CompilerService`

**Database:** OKF Markdown Bundle (Shared Storage Volume)

**Tech Stack:** Python, markdown-it, qmd MCP server

**Dependencies:** Ingestion Service, Inference Service, Auth Service

---

### 5.3 Graph Search Service
**Purpose:** Graph-based search operations

**Responsibilities:**
- Graph traversal queries
- Path finding
- Subgraph matching
- Graph algorithms (PageRank, etc.)
- Graph-based ranking

**APIs:**
- gRPC: `graphsearch.GraphSearchService`

**Database:** Neo4j

**Tech Stack:** Python, Neo4j

**Dependencies:** Graph Service

---

## 6. Molecule Discovery Context

### 6.1 Molecule Service
**Purpose:** Molecular data management

**Responsibilities:**
- Molecule CRUD
- SMILES validation
- Molecular property calculation
- Structure search
- Substructure search
- Similarity search

**APIs:**
- REST: `/api/v1/molecules/*`
- gRPC: `molecule.MoleculeService`

**Database:** PostgreSQL (molecules), RDKit in-memory

**Tech Stack:** Python, PostgreSQL, RDKit

**Dependencies:** Auth Service

---

### 6.2 Docking Service
**Purpose:** Molecular docking calculations

**Responsibilities:**
- Protein-ligand docking
- Docking score calculation
- Binding pose prediction
- Batch docking
- Docking job queue

**APIs:**
- gRPC: `docking.DockingService`

**Database:** PostgreSQL (docking_results), Object Storage (structures)

**Tech Stack:** Python, PostgreSQL, AutoDock Vina, GPU cluster

**Dependencies:** Molecule Service, Inference Service

---

### 6.3 ADMET Service
**Purpose:** ADMET property prediction

**Responsibilities:**
- Absorption prediction
- Distribution prediction
- Metabolism prediction
- Excretion prediction
- Toxicity prediction
- BBB penetration prediction
- PK prediction

**APIs:**
- gRPC: `admet.ADMETService`

**Database:** PostgreSQL (admet_predictions)

**Tech Stack:** Python, PostgreSQL, ML models, GPU cluster

**Dependencies:** Molecule Service, Inference Service

---

### 6.4 Generative Chemistry Service
**Purpose:** AI-powered molecule generation

**Responsibilities:**
- De novo molecule generation
- Scaffold hopping
- Lead optimization
- Multi-objective optimization
- Constrained generation

**APIs:**
- gRPC: `generative.GenerativeChemistryService`

**Database:** PostgreSQL (generated_molecules)

**Tech Stack:** Python, PostgreSQL, ML models, GPU cluster

**Dependencies:** Molecule Service, Inference Service

---

## 7. Clinical Intelligence Context

### 7.1 Clinical Trial Service
**Purpose:** Clinical trial data management

**Responsibilities:**
- Clinical trial CRUD
- Trial status tracking
- Phase tracking
- Endpoint tracking
- Biomarker tracking
- Trial updates

**APIs:**
- REST: `/api/v1/trials/*`
- gRPC: `clinical.ClinicalTrialService`

**Database:** PostgreSQL (clinical_trials)

**Tech Stack:** Go, PostgreSQL

**Dependencies:** Auth Service

---

### 7.2 Clinical Prediction Service
**Purpose:** Clinical success prediction

**Responsibilities:**
- Phase I success prediction
- Phase II success prediction
- Phase III success prediction
- Overall approval probability
- Indication expansion prediction
- Combination therapy analysis

**APIs:**
- gRPC: `clinicalpred.ClinicalPredictionService`

**Database:** PostgreSQL (predictions)

**Tech Stack:** Python, PostgreSQL, ML models, GPU cluster

**Dependencies:** Clinical Trial Service, Inference Service

---

## 8. Competitive Intelligence Context

### 8.1 Competitor Service
**Purpose:** Competitor tracking and analysis

**Responsibilities:**
- Competitor CRUD
- Pipeline tracking
- Asset tracking
- Company monitoring
- Leadership tracking
- Funding tracking

**APIs:**
- REST: `/api/v1/competitors/*`
- gRPC: `competitor.CompetitorService`

**Database:** PostgreSQL (competitors, pipelines)

**Tech Stack:** Go, PostgreSQL

**Dependencies:** Auth Service

---

### 8.2 Market Intelligence Service
**Purpose:** Market analysis and mapping

**Responsibilities:**
- Market map generation
- Technology landscape analysis
- Threat analysis
- Licensing opportunity identification
- Market sizing

**APIs:**
- gRPC: `marketintel.MarketIntelligenceService`

**Database:** PostgreSQL (market_data)

**Tech Stack:** Python, PostgreSQL

**Dependencies:** Competitor Service, Knowledge Graph Service

---

## 9. Portfolio Management Context

### 9.1 Portfolio Service
**Purpose:** Portfolio management and scoring

**Responsibilities:**
- Portfolio CRUD
- Asset scoring
- Risk assessment
- ROI calculation
- Priority ranking
- Investment recommendations

**APIs:**
- REST: `/api/v1/portfolios/*`
- gRPC: `portfolio.PortfolioService`

**Database:** PostgreSQL (portfolios, assets, scores)

**Tech Stack:** Go, PostgreSQL

**Dependencies:** Auth Service

---

### 9.2 Scoring Engine Service
**Purpose:** Multi-dimensional asset scoring

**Responsibilities:**
- Scientific novelty scoring
- Commercial opportunity scoring
- Technical risk scoring
- Patent strength scoring
- Competitive positioning scoring
- Composite score calculation

**APIs:**
- gRPC: `scoring.ScoringEngineService`

**Database:** PostgreSQL (scores)

**Tech Stack:** Python, PostgreSQL, ML models

**Dependencies:** Portfolio Service, Knowledge Graph Service, Clinical Prediction Service

---

## 10. Collaboration Context

### 10.1 Notebook Service
**Purpose:** Scientific notebook management

**Responsibilities:**
- Notebook CRUD
- Cell management
- Version control
- Real-time collaboration
- Citation management
- Export (PDF, DOCX, PPTX)

**APIs:**
- REST: `/api/v1/notebooks/*`
- WebSocket: Real-time collaboration
- gRPC: `notebook.NotebookService`

**Database:** PostgreSQL (notebooks, cells, versions)

**Tech Stack:** Go, PostgreSQL, Redis (collaboration state)

**Dependencies:** Auth Service

---

### 10.2 Document Service
**Purpose:** Document management

**Responsibilities:**
- Document CRUD
- Document versioning
- Document sharing
- Document permissions
- Document search

**APIs:**
- REST: `/api/v1/documents/*`
- gRPC: `document.DocumentService`

**Database:** PostgreSQL (documents), Object Storage (files)

**Tech Stack:** Go, PostgreSQL, Object Storage

**Dependencies:** Auth Service

---

### 10.3 Report Service
**Purpose:** Report generation

**Responsibilities:**
- Report template management
- Report generation
- Scientific reports
- Competitive reports
- Due diligence reports
- Executive summaries

**APIs:**
- REST: `/api/v1/reports/*`
- gRPC: `report.ReportService`

**Database:** PostgreSQL (reports, templates)

**Tech Stack:** Python, PostgreSQL

**Dependencies:** Notebook Service, Document Service

---

## 11. Data Integration Context

### 11.1 Connector Service
**Purpose:** External data source connectors

**Responsibilities:**
- Connector registration
- Connector configuration
- Connector health monitoring
- Rate limiting
- Error handling

**APIs:**
- REST: `/api/v1/connectors/*`
- gRPC: `connector.ConnectorService`

**Database:** PostgreSQL (connectors, configurations)

**Tech Stack:** Go, PostgreSQL

**Dependencies:** Auth Service

---

### 11.2 Transformation Service
**Purpose:** Data transformation and validation

**Responsibilities:**
- Schema mapping
- Data transformation
- Data validation
- Data quality checks
- Error reporting

**APIs:**
- gRPC: `transformation.TransformationService`

**Database:** PostgreSQL (transformations, schemas)

**Tech Stack:** Python, PostgreSQL

**Dependencies:** Connector Service

---

## 12. Observability Context

### 12.1 Logging Service
**Purpose:** Centralized logging

**Responsibilities:**
- Log ingestion
- Log aggregation
- Log search
- Log retention
- Log parsing

**APIs:**
- gRPC: `logging.LoggingService`

**Database:** Elasticsearch (logs)

**Tech Stack:** Go, Elasticsearch

**Dependencies:** None

---

### 12.2 Metrics Service
**Purpose:** Metrics collection and aggregation

**Responsibilities:**
- Metric ingestion
- Metric aggregation
- Metric querying
- Alert evaluation
- Dashboard data

**APIs:**
- REST: `/api/v1/metrics/*`
- gRPC: `metrics.MetricsService`

**Database:** Prometheus (metrics)

**Tech Stack:** Go, Prometheus

**Dependencies:** None

---

### 12.3 Tracing Service
**Purpose:** Distributed tracing

**Responsibilities:**
- Trace ingestion
- Trace storage
- Trace querying
- Trace analysis
- Performance monitoring

**APIs:**
- gRPC: `tracing.TracingService`

**Database:** Jaeger/Tempo (traces)

**Tech Stack:** Go, Jaeger/Tempo

**Dependencies:** None

---

### 12.4 Health Check Service
**Purpose:** System health monitoring

**Responsibilities:**
- Health check execution
- Dependency health checks
- Health aggregation
- SLO/SLA tracking
- Incident detection

**APIs:**
- REST: `/api/v1/health/*`
- gRPC: `health.HealthCheckService`

**Database:** PostgreSQL (health_history)

**Tech Stack:** Go, PostgreSQL

**Dependencies:** All services (via health endpoints)

---

## Cross-Cutting Services

### API Gateway
**Purpose:** API routing, rate limiting, authentication

**Responsibilities:**
- Request routing
- Rate limiting
- Authentication validation
- Request/response transformation
- API versioning
- CORS handling

**Tech Stack:** Kong / Envoy / NGINX

---

### BFF (Backend for Frontend)
**Purpose:** Frontend-specific API aggregation

**Responsibilities:**
- API aggregation
- Data transformation for UI
- GraphQL federation
- Caching
- Mobile optimization

**Tech Stack:** Node.js / Go

---

## Service Communication Patterns

### Synchronous Communication
- **REST APIs:** Public-facing services, web clients
- **gRPC:** High-performance inter-service communication
- **GraphQL:** Complex queries, data federation

### Asynchronous Communication
- **Kafka:** Event-driven architecture, data pipelines
- **NATS:** Lightweight messaging, real-time updates
- **WebSocket:** Real-time collaboration, streaming

### Service Mesh
- **Istio / Linkerd:** Service-to-service communication, mTLS, observability

---

## Service Scaling

### Horizontal Scaling
All stateless services scale horizontally via Kubernetes HPA:
- Auth Service (better-auth)
- API Gateway
- BFF
- Search Service
- Indexing Service
- Inference Service
- Docking Service
- ADMET Service
- Generative Chemistry Service

### Vertical Scaling
Stateful services with resource requirements:
- Graph Service (Neo4j cluster)
- Clinical Trial Service (large datasets)
- Molecule Service (RDKit memory)

### GPU Scaling
GPU-intensive services:
- Inference Service (GPU autoscaling)
- Docking Service (GPU autoscaling)
- ADMET Service (GPU autoscaling)
- Generative Chemistry Service (GPU autoscaling)

---

## Service Dependencies Summary

```
API Gateway
    ↓
   BFF
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Identity & Access (better-auth)                              │
│   Auth Service (Authentication + Authorization)              │
│   - User authentication (OAuth2, OIDC, Email, Passkeys)       │
│   - Multi-provider account linking                           │
│   - Session management (JWT + database)                       │
│   - Role-based access control                                 │
│   - Organization/team management                              │
│   - Permission evaluation (RBAC + ABAC)                       │
│   - API key management                                       │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Data Integration                                            │
│   Connector Service → Transformation Service                │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Literature Intelligence                                     │
│   Ingestion Service → Extraction Service                    │
│   Citation Service                                          │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Knowledge Graph                                             │
│   Graph Service                                             │
│   Entity Resolution Service                                 │
│   Ontology Service                                          │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ AI Orchestration                                            │
│   Agent Orchestrator Service                                │
│   Model Registry Service                                    │
│   Prompt Service                                            │
│   Tool Registry Service                                     │
│   Inference Service                                         │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Scientific Search                                           │
│   Search Service                                            │
│   Indexing Service                                          │
│   Graph Search Service                                      │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Molecule Discovery                                          │
│   Molecule Service                                          │
│   Docking Service                                           │
│   ADMET Service                                             │
│   Generative Chemistry Service                              │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Clinical Intelligence                                       │
│   Clinical Trial Service                                    │
│   Clinical Prediction Service                               │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Competitive Intelligence                                    │
│   Competitor Service                                        │
│   Market Intelligence Service                               │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Portfolio Management                                        │
│   Portfolio Service                                         │
│   Scoring Engine Service                                    │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Collaboration                                               │
│   Notebook Service                                          │
│   Document Service                                          │
│   Report Service                                            │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Observability (Cross-cutting)                               │
│   Logging Service                                           │
│   Metrics Service                                           │
│   Tracing Service                                           │
│   Health Check Service                                      │
└─────────────────────────────────────────────────────────────┘
```
