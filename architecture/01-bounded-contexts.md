# Bounded Contexts - AI-RxOS

## Overview
AI-RxOS is organized into 12 bounded contexts based on Domain-Driven Design principles. Each context has clear boundaries, owns its data, and exposes well-defined APIs.

The **Identity & Access (Auth) Context** is implemented in Node.js/TypeScript to support the Better Auth framework, while the rest of the application services (like Knowledge Graph, AI Orchestration, and Molecule Discovery) are built using Go and Python to optimize performance and ML integration.

---

## 1. Identity & Access Context
**Purpose:** Authentication, authorization, and user management using the Better Auth framework (utilizing official `organization`, `admin` [RBAC], and `api-key` plugins)

**Core Concepts:**
- User
- Account (linked authentication providers)
- Session (better-auth session management)
- Organization (better-auth team/organization)
- Member (organization membership with roles)
- Role (better-auth role-based access control)
- Permission (granular permissions)
- Workspace (project-level isolation)
- Project (research project)
- API Key (service account authentication)
- Audit Log

**Responsibilities:**
- User authentication via better-auth (OAuth2, OIDC, Email/Password, Passkeys)
- Multi-provider account linking (Google, GitHub, SAML, etc.)
- Session management via better-auth (JWT + database sessions)
- Role-based access control via better-auth roles
- Organization/team management via better-auth organizations
- Multi-tenant isolation (Organization → Workspace → Project)
- API key management for service accounts
- Audit logging for all auth/authz events
- Compliance monitoring (SOC 2, HIPAA)

**Ubiquitous Language:**
- Tenant: Organization with isolated data
- Principal: Authenticated user or service account
- Account: External authentication provider linked to user
- Session: Active user session managed by better-auth
- Role: better-auth role (admin, member, etc.)
- Permission: Granular action on a resource
- Policy: Rule governing access decisions (RBAC + ABAC)

---

## 2. Knowledge Graph Context
**Purpose:** Biomedical knowledge representation and reasoning

**Core Concepts:**
- Entity (Gene, Protein, Disease, Drug, Target, Company, etc.)
- Relationship (Targets, Treats, Interacts, etc.)
- Ontology
- Evidence
- Graph Version
- Graph Query
- Graph Traversal

**Responsibilities:**
- Entity resolution and deduplication
- Relationship extraction
- Ontology mapping (GO, MeSH, ChEBI, etc.)
- Graph versioning
- Evidence scoring
- Graph querying (Cypher, Gremlin)
- Graph visualization
- Temporal graph operations

**Ubiquitous Language:**
- Node: Graph entity with properties
- Edge: Typed relationship between nodes
- Evidence: Source citation supporting a relationship
- Confidence: Score indicating relationship strength
- Provenance: Origin of graph data

---

## 3. Literature Intelligence Context
**Purpose:** Automated ingestion and analysis of scientific literature

**Core Concepts:**
- Publication
- Source (PubMed, bioRxiv, Conference, Patent)
- Ingestion Pipeline
- Extracted Entity
- Summary
- Citation Network
- Novelty Score
- Duplicate Detection

**Responsibilities:**
- Ingest from PubMed, PMC, bioRxiv, medRxiv, conferences, patents
- Automatic summarization
- Entity extraction (NER)
- Knowledge graph generation
- Duplicate detection
- Scientific novelty scoring
- Evidence ranking
- Citation linking
- Full-text indexing

**Ubiquitous Language:**
- Source: External data provider
- Ingestion: Process of acquiring and processing documents
- Extraction: Identification of structured entities from text
- Novelty: Measure of new scientific contribution
- Canonical ID: Persistent identifier for deduplication

---

## 4. AI Orchestration Context
**Purpose:** AI agent coordination and model management

**Core Concepts:**
- Agent
- Tool
- Model
- Prompt
- Context
- Conversation
- Workflow
- Tool Call
- Model Inference

**Responsibilities:**
- Agent lifecycle management
- Tool registry and execution
- Model registry and versioning
- Prompt template management
- Context window management
- Conversation memory
- Workflow orchestration (LangGraph, Temporal)
- Model Context Protocol (MCP) implementation
- Multi-agent coordination

**Ubiquitous Language:**
- Agent: Autonomous AI entity with tools and goals
- Tool: Function or API an agent can call
- Model: AI foundation model (LLM, embedding, etc.)
- Context: Information available to an agent
- Turn: Single interaction in a conversation
- Workflow: Multi-step agent process

---

## 5. Scientific Search Context
**Purpose:** Semantic search and retrieval across compiled biomedical wiki content (conforming to the Open Knowledge Format)

**Core Concepts:**
- Query
- OKF Bundle (directory of concepts)
- OKF Concept Page
- OKF Index (index.md)
- OKF Change Log (log.md)
- Local Search Engine (qmd)
- Hybrid Search (BM25 + local vector)
- Semantic Synthesis
- Citation Graph
- Ranking

**Responsibilities:**
- Keyword search (OpenSearch/Elasticsearch)
- Local hybrid search over the OKF wiki bundle (using qmd CLI/MCP)
- Wiki directory linting and contradiction checking
- Graph search (Neo4j)
- Citation search
- Evidence search
- Re-ranking and LLM-based query synthesis
- Query expansion
- Faceted search

**Ubiquitous Language:**
- OKF Bundle: Directory of markdown pages containing structured context for agents
- Concept Page: Markdown file representing an entity or topic with YAML metadata
- Local Search (qmd): On-device markdown search engine using BM25 and local embeddings
- Hybrid: Integration of keyword and local semantic search over the wiki
- Relevance: Match quality between user queries and wiki concepts
- Synthesis: Combining information from multiple wiki pages into a single response

---

## 6. Molecule Discovery Context
**Purpose:** Computational chemistry and molecular design

**Core Concepts:**
- Molecule
- Target
- Protein Structure
- Binding Pocket
- Docking
- ADMET
- Pharmacokinetics
- Toxicity
- Synthetic Accessibility
- Patent Similarity

**Responsibilities:**
- Virtual screening
- Generative chemistry
- Molecular docking
- ADMET prediction
- BBB penetration prediction
- PK prediction
- Toxicity prediction
- Synthetic accessibility scoring
- Patent similarity analysis
- Molecular property calculation

**Ubiquitous Language:**
- SMILES: String representation of molecular structure
- Docking: Computational prediction of ligand binding
- ADMET: Absorption, Distribution, Metabolism, Excretion, Toxicity
- BBB: Blood-brain barrier
- SA: Synthetic accessibility

---

## 7. Clinical Intelligence Context
**Purpose:** Clinical trial analysis and prediction

**Core Concepts:**
- Clinical Trial
- Phase
- Indication
- Endpoint
- Biomarker
- Patient Population
- Success Probability
- Trial Outcome
- Comparator

**Responsibilities:**
- Clinical trial ingestion
- Phase success prediction
- Indication expansion analysis
- Biomarker identification
- Companion diagnostic recommendation
- Combination therapy analysis
- Competitive trial tracking
- Trial outcome prediction

**Ubiquitous Language:**
- IND: Investigational New Drug application
- NDA: New Drug Application
- Endpoint: Measured outcome in a trial
- Biomarker: Biological indicator of disease or response
- Comparator: Standard of care or placebo

---

## 8. Competitive Intelligence Context
**Purpose:** Market and competitor analysis

**Core Concepts:**
- Competitor
- Pipeline
- Asset
- Market Map
- Technology Landscape
- Funding Round
- Leadership Change
- Licensing Opportunity
- Threat Analysis

**Responsibilities:**
- Competitor tracking
- Pipeline monitoring
- Conference presentation tracking
- Patent monitoring
- Company announcement tracking
- Funding round tracking
- Market map generation
- Technology landscape analysis
- Threat analysis
- Licensing opportunity identification

**Ubiquitous Language:**
- Asset: Drug or therapeutic in development
- Pipeline: Collection of assets in development
- FIC: First-in-class
- BIC: Best-in-class
- MoA: Mechanism of Action

---

## 9. Portfolio Management Context
**Purpose:** Portfolio evaluation and optimization

**Core Concepts:**
- Portfolio
- Asset
- Score
- Risk
- ROI
- Probability of Success
- Commercial Opportunity
- Scientific Novelty
- Patent Strength
- Investment Recommendation

**Responsibilities:**
- Portfolio scoring
- Scientific novelty assessment
- Commercial opportunity evaluation
- Competitive positioning analysis
- Patent landscape analysis
- Development cost estimation
- Probability of success calculation
- Investment recommendation
- Priority ranking

**Ubiquitous Language:**
- PoS: Probability of Success
- NPV: Net Present Value
- Risk-adjusted return: Return adjusted for failure probability
- Commercial score: Market potential assessment
- Technical score: Scientific feasibility assessment

---

## 10. Collaboration Context
**Purpose:** Scientific collaboration and document management

**Core Concepts:**
- Notebook
- Document
- Comment
- Version
- Citation
- Reference
- Dashboard
- Report
- Template

**Responsibilities:**
- Scientific notebook management
- Document versioning
- Real-time collaboration
- Citation management
- Reference linking
- Dashboard creation
- Report generation
- Template management
- Export (PDF, DOCX, PPTX)

**Ubiquitous Language:**
- Notebook: Interactive scientific document
- Cell: Unit of content in a notebook
- Citation: Reference to a publication
- Version: Immutable snapshot of a document
- Fork: Copy of a document for independent editing

---

## 11. Data Integration Context
**Purpose:** External data source integration

**Core Concepts:**
- Data Source
- Connector
- Ingestion Job
- Transformation
- Validation
- Schema Mapping
- Data Quality
- Sync Schedule

**Responsibilities:**
- Connector management (PubMed, ChEMBL, DrugBank, etc.)
- Ingestion scheduling
- Data transformation
- Schema mapping
- Data validation
- Error handling
- Retry logic
- Data quality monitoring

**Ubiquitous Language:**
- Connector: Interface to external data source
- Ingestion: Process of acquiring external data
- Transformation: Conversion of data to internal format
- Validation: Verification of data quality
- Sync: Scheduled data refresh

---

## 12. Observability Context
**Purpose:** System monitoring and analytics

**Core Concepts:**
- Metric
- Log
- Trace
- Alert
- Dashboard
- Health Check
- SLO
- SLA
- AI Metric

**Responsibilities:**
- Centralized logging
- Metrics collection
- Distributed tracing
- Health checks
- Alerting
- AI inference metrics
- GPU utilization monitoring
- Model drift detection
- Prompt analytics
- User analytics

**Ubiquitous Language:**
- Metric: Quantitative measurement
- Trace: Request path through system
- Span: Single unit of work in a trace
- SLO: Service Level Objective
- SLA: Service Level Agreement
- Drift: Model performance degradation over time

---

## Context Mapping

### Upstream Dependencies
- **Data Integration** → All contexts (provides raw data)
- **Identity & Access** → All contexts (provides auth/authz)
- **Literature Intelligence** → Knowledge Graph (provides extracted entities)
- **Knowledge Graph** → Scientific Search, AI Orchestration (provides graph data)

### Downstream Dependencies
- **AI Orchestration** → All contexts (consumes data via agents)
- **Scientific Search** → All contexts (provides search capabilities)
- **Collaboration** → All contexts (provides document management)

### Anti-Corruption Layers
- **Data Integration**: ACL for each external source
- **Literature Intelligence**: ACL for unstructured text processing
- **Clinical Intelligence**: ACL for clinical trial data formats

### Shared Kernel
- **Common Domain**: IDs, timestamps, audit fields
- **Domain Events**: Standardized event format
- **API Contracts**: OpenAPI specifications

---

## Context Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                    Identity & Access                        │
│                  (Upstream to all contexts)                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                     Data Integration                        │
│                  (Upstream to all contexts)                 │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ↓               ↓               ↓
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ Literature       │ │ Knowledge Graph  │ │ Clinical         │
│ Intelligence     │ │                  │ │ Intelligence     │
└──────────────────┘ └──────────────────┘ └──────────────────┘
              │               │               │
              └───────────────┼───────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   AI Orchestration                          │
│              (Coordinates all contexts)                     │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ↓               ↓               ↓
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ Scientific       │ │ Molecule         │ │ Competitive      │
│ Search           │ │ Discovery        │ │ Intelligence     │
└──────────────────┘ └──────────────────┘ └──────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   Portfolio Management                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Collaboration                            │
│              (Downstream to all contexts)                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Observability                            │
│              (Cross-cutting concern)                        │
└─────────────────────────────────────────────────────────────┘
```
